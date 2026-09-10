# Dependency adoption: AutomationBench `1.0.6+evalrepair.10` becomes the bench's world

Date: 2026-09-08 America/Sao_Paulo. Milestone M1 of `docs/AI-LABS-UNBLOCK-PLAN-2026-09-08.md`
(decision D6; tasks T1.1 to T1.4). Work done on a worktree branch off
`007-benchmark-foundations` at `cf745f1`; nothing pushed; no paid call. Earlier records this
note builds on: [dependency-audit.md](dependency-audit.md), [candidate-validation.md](candidate-validation.md),
[baseline.md](baseline.md).

## What was swapped

| Item | Before (upstream world) | After (repaired world) |
|---|---|---|
| Package under `vendor/automation-bench` | AutomationBench 1.0.6, Git commit `4a8e1061254004d9dac807054eed33fad7d1ff14` | `automation-bench==1.0.6+evalrepair.10` |
| Source of the copy | plain clone of upstream | `.references/ApplicationBench/vendor/automation-bench` (ApplicationBench HEAD `4cf5ef5ad8f417387e2898fd40d9e7aeba870699`, vendor Git tree `7ac9559eb65540feac74d5d12c37406b4d69fd56`, as recorded in the audit; not recomputed here) |
| `pyproject.toml` of the copy, SHA-256 | — | `751f2566b894e1b21f4eeea54240748bb1575436e5c392e38b76a6db5a219558` (equals the audit's pinned value) |
| Files copied | — | 612 (the 611 tracked files plus the generated `automationbench/tools/api/schemas/index.txt`); `.venv`, `__pycache__`, `.pytest_cache`, `.ruff_cache`, `.git` and the two `candidate-*.log` files left behind |
| Content hash of the copy (`tree_sha256`, see `VENDORED-FROM.txt`) | — | `0dc6481a686e2207ed855e7b282cab372a6fc42f7ba2cc7d6a0f7cdd966ffb43` |
| `monarch-benchmark/workflowbench/uv.lock`, SHA-256 | `178018bc8191d913829362045e7fe1e50d8af2e2b9c15a58d923043ac95880bb` | `d301f61ad6cd15a52242db7583c3af3b77db5cf67a54bf17010102eafe94556f` |
| `pyproject.toml` dependency | `automation-bench` (unpinned) | `automation-bench==1.0.6+evalrepair.10` |

The lock moved on one package only (`automation-bench 1.0.6 -> 1.0.6+evalrepair.10`); uv 0.9.10
also rewrote two dependency markers (`httpcore2`, `uvicorn`: `sys_platform != 'emscripten'`)
without changing any version. The lock records the editable path without the version
specifier, so the pin acts when `uv lock` or `uv sync` reads the vendored `pyproject.toml`:
a vendor folder of another version refuses to lock.

The old world stays reachable: local tag `world-1.0.6-upstream` marks `cf745f1`, the last
commit whose `pyproject.toml`, lock and setup notes describe upstream 1.0.6. To regrade rows
recorded under `workflowbench-synthetic@0.1`, check that tag out, clone upstream at `4a8e106`
into `vendor/automation-bench` (or run the script below with `--expect-version 1.0.6`) and
`uv sync --frozen`.

### How the copy is made from now on

`monarch-benchmark/workflowbench/scripts/vendor_automation_bench.py` copies a source tree
into `vendor/automation-bench`, refuses any `pyproject.toml` version other than
`--expect-version` (nothing is copied), refuses to overwrite an existing copy without
`--replace`, leaves caches, logs and the Git folder behind, and writes
`vendor/automation-bench/VENDORED-FROM.txt` (source path, version, `pyproject.toml` hash,
file count, content hash, the Git tree id as given, date). Tests:
`tests/test_vendor_script.py` (six tests on a fake source tree).

```
cd monarch-benchmark/workflowbench
uv run python scripts/vendor_automation_bench.py \
    --source ../../.references/ApplicationBench/vendor/automation-bench \
    --expect-version 1.0.6+evalrepair.10 \
    --tree-id 7ac9559eb65540feac74d5d12c37406b4d69fd56 --replace
uv lock
uv sync
uv run --frozen python -c "from importlib.metadata import version; print(version('automation-bench'))"
```

Output of the last line: `1.0.6+evalrepair.10`.

### The vendored copy's own tests

From the bench environment, with `vendor/automation-bench` as the working directory (its
tests open `docs/...` relative to it): the three files that carry the known failures give
**2 failed, 46 passed**, the two failures being exactly the hash-link checks documented in
candidate-validation.md (`test_microscopic_audit_hash_linkage_and_release_metadata`,
`test_second_pass_ledger_schema_coverage_hashes_and_counts`). The whole vendored suite run
from the bench folder gives 1937 passed, 3 failed, the third being only the working-directory
path (`test_all_79_changed_operations_support_contracts_have_reviewed_regex_surface`
opens `docs/AUTOMATIONBENCH_106_REPAIR_CHANGE_REPORT.json`), which passes from the vendor
folder. No vendored file was edited.

## The bench's test suite

All runs: `uv run --frozen python -m pytest tests -q -p no:cacheprovider` from
`monarch-benchmark/workflowbench`, Python 3.13.9, Windows.

| Tree | World | Result |
|---|---|---|
| `cf745f1`, unchanged (1097 collected) | upstream 1.0.6 | **1093 passed, 4 skipped in 728.78s (12:08)** |
| `cf745f1`, unchanged, run from a temporary copy | 1.0.6+evalrepair.10 | **1092 passed, 1 failed, 4 skipped in 1015.16s (16:55)** |
| this branch (M1 changes, 1125 collected) | 1.0.6+evalrepair.10 | **1121 passed, 4 skipped in 703.97s (11:43)** |

The one failure of the unchanged tree on the new world is not the world's doing:
`tests/test_run_config.py::test_build_arm_for_monarch_competitor` uses the repository
itself as a stand-in Monarch checkout and runs `git rev-parse` in it; the temporary copy
was not a Git repository. The same test passes in the worktree on the new world. **No
bench test fails because of the repaired package**: the assertion registry, the world model
and the runner behave as the bench expects, and every existing test that reads the old
corpus (`tests/test_declare_scored.py`, `tests/test_tiers.py`) still passes with the new
registry.

The run before that one (same code, while the vendored copy's own suite ran on the same
machine) had three failures, none of them the world's: two runs of
`tests/test_evidence.py::test_uncommitted_attempt_is_quarantined_before_resume` recorded
their crashed run under the placeholder suite label `"test"`, which the new suite-drift check
in `Orchestrator.resume` now refuses before the evidence is looked at; the fixture now
records the set's own suite id, and the test keeps its point (quarantine before resume).
`tests/test_monarch_recipes.py::test_a_third_attempt_that_passes_deletes_the_two_before_it`
failed once on `git rev-parse` in its temporary repository with an empty error, passed alone
and passed in the final run: a transient of the two concurrent pytest processes.

## What the repaired world changes, and what was done about it

### Every scored task now spells out all 48 apps

The repaired world's determinism pass writes every service's default state into each scored
task's `initial_state`: a finance task that used to seed `airtable` and `gmail` now carries
48 services, 46 of them the world's empty default (for example
`linkedin_leadgen_forms: {"actions": {}}`). Measured on the imported corpus:

| Domain | Tasks | Changed on any surface | Prompt | Tools | Starting data | Assertions |
|---|---:|---:|---:|---:|---:|---:|
| finance | 100 | 100 | 16 | 7 | 100 | 75 |
| hr | 100 | 100 | 26 | 7 | 100 | 74 |
| marketing | 100 | 100 | 2 | 6 | 100 | 81 |
| operations | 100 | 100 | 1 | 0 | 100 | 15 |
| sales | 100 | 100 | 0 | 0 | 100 | 56 |
| support | 100 | 100 | 3 | 0 | 100 | 68 |
| simple | 200 | 0 | 0 | 0 | 0 | 0 |

The totals (600 starting states, 369 assertion sets, 48 prompts, 20 tool lists) are the
audit's numbers. The `simple` domain is byte-identical in content; only its hashes moved,
because every task under the new revision carries its world (below).

Three places in the bench read `initial_state`'s keys as "the services this task seeds",
which under the new world would say "all 48" for every scored task:

1. `wb corpus declare` (`declare.derive`): the seeded services decide which housekeeping
   side effects (`config/side-effects.yaml`) a task allows. Counting keys would allow the
   Gmail, Google Sheets and Slack side effects in every scored task, including tasks that
   never touch those apps.
2. The difficulty measure (`tiers.score_task`): every scored task would score 48 plus its
   rules and tools, and the measure would say nothing.
3. The service checks of `wb corpus import-ab` and `config.resolve`: the product file lists
   47 apps, and the world's 48th (`linkedin_leadgen_forms`, present in the world model
   before and after the repair, never seeded by any task) made the import exit 1 and would
   make `wb run` refuse every scored task.

The fix, in one place (`wb_world.episode.seeded_services`): a service is seeded when its
starting state differs from the world's own default (None-valued keys ignored, `meta` never
counted). Checked against the old corpus: for the 800 tasks, the new definition never counts
a service the old seeds omitted, and it only drops old seeds that already equalled the
empty default (244 occurrences over 193 tasks, `google_drive` 105 of them). The four callers
now use it. `MEASURE` in `tiers.py` says so in words; the old `tasks/tiers-manifest.yaml`
keeps its old wording, as a record. **For M2:** confirm the measure's wording with Carlos and
Lucas before any new draw records a score.

The product file was left at 47 apps. Adding `linkedin_leadgen_forms` was tried and reverted:
`config/products/simulated-apps.monarch-kb.yaml` must carry one knowledge-base entry per
product service, which needs `wb monarch setup` against a live Monarch (milestone M5), and
the two shipped plans' pinned config hashes move with the product file. Open item for M5:
add the app to the product and the knowledge base together, and re-pin the hashes.

### `wb corpus validate` on the scored domains

`validate` reports no-op failures on every scored domain (finance 58, hr 100, marketing 98,
operations 100, sales 98, support 100; simple 0). This is not new: the old corpus gives the
same picture under either package (hr 100, finance 55). The no-op checker flags any
assertion that already holds on the untouched world, and the scored domains use negative
assertions (`*_not_sent_to`, `*_action_not_exists`) that hold on the untouched world by
design. Split by kind, new corpus: tasks whose only holding assertions are negative:
finance 54, hr 99, marketing 89, operations 99, sales 66, support 73; tasks with a positive
assertion already holding (guard-style checks, `salesforce_field_equals` on a value the seed
already has, `freshdesk_ticket_exists` on a seeded ticket): finance 4, hr 1, marketing 9,
operations 1, sales 32, support 27; tasks whose every assertion holds: **0** in every domain,
old and new. The validator was not changed. Open item: make it count negative assertions
separately, so the number it prints means "a task that can be passed by doing nothing".

## The corpus under the new revision

```
uv run --frozen wb corpus import-ab --domains all --revision evalrepair10 --out corpus-evalrepair10 --product simulated-apps
for d in simple finance hr marketing operations sales support:
    uv run --frozen wb corpus declare corpus-evalrepair10/imported-$d --overwrite --product simulated-apps
    uv run --frozen wb corpus validate corpus-evalrepair10/imported-$d
uv run --frozen wb corpus manifest corpus-evalrepair10
```

The import wrote 800 tasks in 7 folders (simple 200; finance, hr, marketing, operations,
sales, support 100 each) and, after the `seeded_services` fix, reports no service missing
from the product. `declare` derived a rule for every task: 0 unmapped assertion types in all
seven folders. `validate`: contract drift 0 everywhere; the no-op numbers above; oracle
unsupported for the scored domains (the scripted answer key only drives Salesforce field
updates) and 184 of 200 in `simple`, as before.

`corpus-evalrepair10/MANIFEST.yaml`: revision `evalrepair10`; world `automation-bench
1.0.6+evalrepair.10` with the vendored copy's source, tree id, content hash and
`pyproject.toml` hash; `imported_at 2026-09-08T21:19:58Z`; per domain 100 (200 for simple)
tasks, declared, **usable 100 (200)**; `tasks_total 800`, `usable_total 800`,
`without_rule: []`. Usable means what `wb corpus tiers` means: a non-empty approval rule and
a hash that matches the content.

Every imported task carries `info.world = {package: automation-bench, version:
1.0.6+evalrepair.10, revision: evalrepair10}`, hashed into `contract_sha256`.

## Suite ids and the guard against running a set on the wrong world

- `wb_world.episode.suite_id(tasks)`: `workflowbench-synthetic@0.1` for a set that records
  no world (every set before today), `workflowbench-synthetic@1.0.6+evalrepair.10` for a set
  drawn from `corpus-evalrepair10`. The orchestrator writes it on the run and on every row;
  the Studio's runs use the same function. A set that mixes worlds is refused by name.
- `config.resolve` refuses a task set whose recorded world (1.0.6 when none is recorded) is
  not the installed package version, naming both and the way out; `wb run` and `wb resume`
  go through it. `Orchestrator.resume` also refuses a run recorded under another suite id.
- `wb report` already refused rows of two suites in one run; `wb summary` now refuses rounds
  of different suite ids, naming each round's suite, and writes nothing.
- Tests: `tests/test_world_revision.py` (22 tests). The test suite pins the "installed world"
  to upstream 1.0.6 for fixture sets that record none (`tests/conftest.py`, autouse), and the
  guard's own tests set both sides.

`wb doctor --arms monarch` on this machine fails on the missing `MONARCH_URL`,
`MONARCH_FD_URL` and `LANGFUSE_URL` variables, before anything about the world; it needs the
Railway instances of M5.

## Not done here, on purpose

- No new task set was drawn or frozen (M2). The frozen sets under `tasks/`, the ten pilot
  files, `tasks/tiers-manifest.yaml` and `corpus/imported-*` were not touched; they record the
  old world and `wb run` now refuses them on this one.
- The Monarch seed generator and conformance check (`wb_world/seeds.py`,
  `wb_world/conformance.py`, `default_corpus_dirs`) still read `corpus/`; pointing them at the
  corpus of the installed world belongs with `wb monarch setup` in M5.
- The 48th app in the product file and the knowledge base (M5, above).
- The no-op validator's accounting of negative assertions (above).
- Regrading rows of the old world on the new package is not blocked: the regrade revision
  records the installed dependency version. To regrade on the old world, use the tag.
