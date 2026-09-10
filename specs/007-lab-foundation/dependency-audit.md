# AutomationBench dependency and grader reconciliation

Audit date: 2026-09-07 America/Sao_Paulo. Read-only comparison for foundation step 1. No paid calls, scored-task replacements, production-vendor edits, commits, or external writes occurred. An ignored reference checkout was created at `.references/ApplicationBench`; `/.references/` was added to local `.git/info/exclude`.

## Decision

The repaired dependency is available and executable. It is a new 600-task contract, not a nine-task patch to the existing benchmark. Preserve the current upstream baseline and frozen draws, and prepare a separately versioned replacement from the pinned ApplicationBench vendor subtree. Do not infer the current migration surface from its historical 358-task report.

Focused behavioral checks passed. The packaged audit provenance contains newline-induced hash mismatches plus one unresolved raw parent-ledger hash. These are described below rather than silently rewritten. They do not show an actor/grader failure. A migration must carry a new explicit provenance manifest retaining the original artifacts and the reconciliation evidence.

## Exact sources and provenance

| Item | Verified identity |
|---|---|
| Scored dependency currently installed | AutomationBench 1.0.6, Git `4a8e1061254004d9dac807054eed33fad7d1ff14` |
| Reference repository | [TestBoxLab/ApplicationBench](https://github.com/TestBoxLab/ApplicationBench/tree/4cf5ef5ad8f417387e2898fd40d9e7aeba870699) |
| Reference HEAD inspected | `4cf5ef5ad8f417387e2898fd40d9e7aeba870699` |
| Vendor import commit | `0bb57926f1e4a3ab5a4094add80cc2ee8b702f38` |
| Exact repaired source | `vendor/automation-bench/` at that HEAD; Git tree `7ac9559eb65540feac74d5d12c37406b4d69fd56` |
| Actual package metadata | `pyproject.toml`: `1.0.6+evalrepair.10` |
| Historical source claim | `docs/HISTORY.md:277,286` names `5a0dea3`; that object is not available in the imported repository |

The upstream child `4a8e106` changes only README; the release report's task/grader base `6d21054` is consistent with the observed commit diff. ApplicationBench carries only one vendor import commit; it is not the complete repair-branch Git history. Use the verified repository/subtree pin for extraction, not an unresolvable historical short SHA. The vendor README, CHANGELOG and EVAL_REPAIR_RELEASE still describe `.9`; package metadata, overlay code and snapshot tests establish `.10`.

File comparison, with CRLF normalized to LF for source comparison: **572 upstream tracked files versus 611 repaired files; 36 modified, 39 added, none deleted.** Additions include 15 test files. The modified runtime includes all six domain task files; registry/rubric/export/eval; 12 assertion modules; QuickBooks schema/tools; BambooHR actions, Calendly users and the tool registry. Four new runtime files are:

- `automationbench/domains/_evalrepair10.py`
- `automationbench/domains/_determinism.py`
- `automationbench/domains/_fairgrade.py`
- `automationbench/tools/zapier/quickbooks/deposits.py`

These changes form a coupled task/schema/tool/grader repair. Copying only the six task files would omit required capabilities and assertion behavior. The exact patch source is the pinned whole subtree above; retain its tests, scripts, adjudication and dependency lock alongside runtime code.

## Actual effective task comparison

Executed each revision's six dataset loaders in a separate Python subprocess using the reference `scripts/build_repair_change_report_data.py` `_snapshot` implementation. It serializes effective rows after each revision's noise and wrappers, keyed by `info.task_name`; it compares prompt, tools, initial state, assertions and evaluation payload.

| Surface | Current `.10` versus upstream tasks changed |
|---|---:|
| Any measured surface | 600 |
| Initial state | 600 |
| Assertions | 369 |
| Prompt | 48 |
| Served tool list | 20 |
| Answer/evaluation payload | 0 |

Both sides have the same 600 unique task names, exactly 100 in each of Finance, HR, Marketing, Operations, Sales and Support. Surface counts overlap. This is measured object change, not a claim that every semantic requirement changed.

Canonical snapshot SHA-256, using the reference script's sorted compact JSON hash:

- Upstream: `8bec572b81992732da466b977c2f9a61d7b09e954d1b3de799a080ad6f8e4243`
- Repaired: `998234d1b66f02145639e5792bdab5ddd66083d529c0707c7eb5e80e38eef7f0`

The packaged [historical report](https://github.com/TestBoxLab/ApplicationBench/blob/4cf5ef5ad8f417387e2898fd40d9e7aeba870699/vendor/automation-bench/docs/AUTOMATIONBENCH_106_REPAIR_CHANGE_REPORT.md) compares upstream with earlier `1f48a71`: 358 definitions, assertions 353, prompts 59, tools 25, states 20. It explicitly remains frozen at that earlier revision. Its numbers are not the current `.10` migration inventory.

## What the repairs actually do

Verified source inspection supports these mechanisms; historical adjudication counts below describe source records, not independently re-adjudicated model outcomes.

- Reachability: Slack channel names resolve to IDs, the missing Finance Gmail writer and two HR DocuSign creation paths are served, Slack user lookup is registered, and six Marketing tasks gain existing Drive discovery. QuickBooks deposits and persisted vendor terms have matching schema, tools and checks.
- Grading: same-artifact and same-entity matching prevents fragments spread across unrelated emails, Slack messages or rows from earning credit. Numeric checks use exact Decimal-style comparisons and labeled numbers. Calendar/cardinality checks scope relevant events; actor-path gold tests exercise served writes.
- Fairness restoration `.10`: `_evalrepair10.py` removes leaked world policies and computed answers from prompts, restores conflicting user instructions and withdrawn violation-capable tools, and verifies every declared edit applied. The fairness artifact records **30 tasks**, with overlapping L1/L2/L3/L4 counts **25/7/8/2**; prompt 29, tools 8, assertions 5, world 2 relative to its parent.
- World determinism: `_determinism.py` materializes omitted schema defaults once during dataset creation, seeds entropy by task name and freezes previously unpinned time at `2026-08-14T00:00:00Z`. This explains the 600 effective state-object changes. It does not freeze IDs/timestamps produced by actor writes during an episode. Historical comments differ between 150 and 151 affected paths; this audit does not adopt either count as a newly measured fact.
- Error semantics: repaired `AssertionRegistry.evaluate()` returns structured evaluator failures without credit. `check()` remains strict by default and raises. Unknown-parameter validation is opt-in. WorkflowBench currently calls `check()`, so merely replacing the dependency will not automatically preserve the repaired evaluator-error structure in local episode records.

## Strict expected-change integration

Both the local and reference `workflowbench/grader/grade.py` use a wildcard expected matcher when declarations are absent. The wildcard accepts arbitrary changed paths, sets `invariant_declared=False`, and still requires at least one observed change: it is not a collateral-change safety guarantee. The flag alone does not prevent a result from entering a report.

Local `grader/invariant.py` otherwise requires every expected matcher to match a change and every observed change to match an expected or allowed matcher. Local `wb_orchestrator/tiers.py` excludes tasks with empty declarations. Existing `declare.py` derives rules from world collections and assertion markers.

Read-only compatibility probe: invoking current `derive(task, default_side_effects())` over all repaired tasks found **354 assertion types, zero unmapped types, and zero tasks with empty expected matchers**. This proves mapping coverage only. It does not prove correct cardinality, exact field coverage, seed semantics, allowed side effects or full task executability. Repaired gold and near-miss trajectories must also pass through WorkflowBench's snapshot diff and invariant after a separate import.

Migration should fail closed or explicitly exclude undeclared tasks from the strict denominator, preserve structured evaluator errors as infrastructure/evaluator outcomes, and distinguish historical assertion-only grading. Do not silently change old results or regenerate frozen task hashes in place.

## Executed offline validation

Runtime: existing WorkflowBench `.venv/Scripts/python.exe`, Python 3.13.9, with reference working directory so imports resolve to repaired code. This deliberately left both lockfiles and the installed baseline dependency untouched. It is not a reproduction under the reference's own locked environment.

Run from `.references/ApplicationBench/vendor/automation-bench`:

```powershell
$py = '../../../../monarch-benchmark/workflowbench/.venv/Scripts/python.exe'
& $py -m pytest tests/test_evalrepair10_fairness.py tests/test_evalrepair10_determinism.py tests/test_evalrepair10_contract_snapshot.py tests/test_eval_repair_release.py tests/test_second_pass_audit.py tests/test_microscopic_brittleness_audit.py -q
```

**78 passed, 2 failed in 56.53s.** Fairness, deterministic construction, 600-task effective contract snapshots and repair-release checks passed. Both failures were byte-hash linkage assertions, explored below.

```powershell
& $py -m pytest tests/test_task_contract_repairs.py tests/test_second_pass_shared_contracts.py tests/test_second_pass_finance_hr_repairs.py tests/test_second_pass_hr_remaining_repairs.py tests/test_second_pass_marketing_sales_repairs.py tests/test_second_pass_ops_support_repairs.py tests/test_ops_support_brittleness_corrections.py -q
```

**451 passed in 36.89s.** These are existing gold/adversarial contract tests; this audit did not author replacement tests. No full repaired test suite or locked Ruff run was performed. Passing these checks is not proof of model completion or zero benchmark defects.

## Evidence byte-hash reconciliation

The imported repository sets `* text=auto eol=lf`. Three historical references hash original CRLF bytes. For each listed artifact, converting every LF byte to CRLF reproduces the cited SHA exactly. JSON content is unchanged. These reference-only transforms were applied temporarily to investigate the original failing tests, then all files were restored to packaged LF bytes; both vendor Git status checks were clean.

All paths below are relative to repaired `vendor/automation-bench/` at import commit `0bb57926f1e4a3ab5a4094add80cc2ee8b702f38`:

| Artifact | Packaged LF SHA-256 | Reconstructed CRLF SHA-256, matching historical reference |
|---|---|---|
| `adjudication/second-pass-operations-support.json` | `a28da9751c87e3253fd2dfd3b3d87bf419d10c0d823b8e36e94f5c2998d741ca` | `1445478a34ae7a59bcfc013ae1157acb200cb312ac02da0e215c5f290c810228` |
| `docs/AUTOMATIONBENCH_106_REPAIR_CHANGE_REPORT.json` | `af8da62f225f81066a525085517f82b60d98b51ce00546c89a909bde277a90cf` | `05844c15eb32abd6fc3f1d8c2d22ec0eda978a76c3e0f986d0b32e07b14e6577` |
| `adjudication/microscopic-brittleness-358-v1.json` | `33a9b229a5da400ed73d16a67d8ea3f8a11b0f7b559dfd20ae8ac70ac1aab816` | `2477849feb196ccdc072c81b00588daca6a7cd47c317a155a7433296f43206c5` |

After these reconstructions the ledger schema/hash test passes, and the microscopic hash test advances to its final parent-ledger assertion. Rerunning the two originally failing checks gave **1 passed, 1 failed in 0.50s**. The remaining check is:

- `second-pass-600-v2.json.parent_ledger.sha256` expects `19427a136248a6b446b659eda379ca69446a357f3d0d45e3362959aec1e2e832`.
- Shipped `second-pass-600-v1.json` LF is `cac54ae8f3c06c4e1edb39d0c3749af6b03fe40f0f56c23aef4e1a866369ecdb`; all-CRLF is `b53119df465d7297d25bf1766a91f6973bd78090d106c8cc4e73fc622f553281`.
- Reversing the documented v2 carry-forward transformation produces a JSON object **exactly equal** to shipped v1. The per-task and metadata parent content is therefore semantically recoverable from the child; the original byte serialization is not verified.
- Standard JSON indentation/key-order/Unicode/newline variants and every single-boundary LF/CRLF combination did not reproduce the expected hash. Available Git history has one import for these files; it contains no original repair-branch commits or alternate artifact copy found by repository search.

Do not relabel that final byte hash as verified. Preserve it as a historical mismatch and produce a versioned reconciliation manifest with both artifact hashes, transformation descriptions and semantic-parent equality. This is a recoverable migration bookkeeping task, not a request for user permission or evidence that task behavior fails. A proposed candidate release must either recover the exact original bytes or explicitly repair this link in a new derived provenance record and validate it without changing the frozen originals.

## Additional pinned bytes

| File under repaired vendor | SHA-256 |
|---|---|
| `pyproject.toml` | `751f2566b894e1b21f4eeea54240748bb1575436e5c392e38b76a6db5a219558` |
| `uv.lock` | `a03ea7adb3ad0b7379d70c10c155d2413b456b3b9c9565b792f94eb0231d313b` |
| `automationbench/domains/_evalrepair10.py` | `d15e87367bee2484d3f08bb8c4ed58e278e240a32791eeaac268a33fcb2e7d75` |
| `automationbench/domains/_determinism.py` | `7698e8c6e070a03b3aca962f6121e537771aec3542aef863c3ee2c3cbae2cb66` |
| `adjudication/evalrepair10-contract-snapshot-v1.json` | `e9bdc73ed102ae3f66a60e207f0f9b309cd59a970d8d14ea2843fcb185cff197` |
| `adjudication/evalrepair10-fairness-restoration-v1.json` | `b8532fdada8fd301f324490ad56bc4b264ab12bf893831aaa0d588bc3aefc8f4` |

## Safe validation and migration route

1. Extract the pinned repaired subtree into a separate candidate directory; retain the current scored dependency, task sets, configurations and results. Record subtree Git identity plus raw file hashes and the provenance reconciliation above.
2. In that separate candidate, create its own environment with `uv sync --locked`. Run `uv run --locked python -m pytest tests -q` and `uv run --locked ruff check .`; record any independent dependency/platform failures. The release's lock includes `verifiers==0.2.1`.
3. Regenerate an effective 600-task comparison using `scripts/build_repair_change_report_data.py --baseline-root <exact upstream checkout> --output <new candidate report>`. The historical report remains untouched. Retain current per-task snapshot fingerprints and a fresh materialized-world digest across independent processes.
4. Import into a new WorkflowBench corpus namespace, derive expected/allowed changes and run oracle/no-action/near-miss checks through real served tool paths and local snapshot grading. Assert no undeclared strict contracts, no suppressed evaluator errors and no unexpected world-reset drift. Mapping coverage alone is insufficient.
5. Freeze new draw/config/difficulty hashes only after those gates, and report upstream and repaired attempts separately. No paid run follows merely from this audit; isolation, shared budget reservations and billing verification remain independent foundation gates.

## Bounded Monarch API inspection

The local configuration points to a sibling `monarch` repository, which was not present at the configured resolved location during this audit. Current local `wb_arms/monarch_client.py` implements workflow authoring/execution routes: `POST /api/workflows/recipe/runs`, its `stream/reply/cancel` subroutes, `POST /api/workflows/{id}/run`, version `llm-ack`, workflow and run reads, and workflow deletion. These are not a verified one-off adapter.

ApplicationBench's historical engine snapshot documents `OperateRequest`, `OperateOutcome`, `OperateContinuation` and `assembleOperatorContract` in `docs/reference/engine-source/shared/src/operate-engine.ts`; it also mentions `POST /atlas/operate/step-up`. `OperateRequest` exposes `instruction`, context, account/thread/idempotency fields, `mode:'auto'|'plan'`, surface and autonomous flags. This is a useful interface lead, not a verified current HTTP submission endpoint. The snapshot manifest names ATLAS source HEAD `250697e73d7faf80151e8b0f1e2dbf80b2816ddf` on `bridge/automationbench-corpus-run`, and marks some benchmark engine files as working-tree content differing from HEAD. Its source identity must not be substituted for a current stock Monarch release.

The historical platform plan lists proposed `/api/benchmarks/experiments/...` control-plane endpoints. They are design requirements, not observed deployed APIs. Current Monarch stock release, one-off route, credentials and live behavior remain unverified.

