# Repaired candidate: isolated full validation

**Latest derived-candidate result:** locked installation, all **1,940 tests** (127.14s), and locked Ruff pass after the four packaging-only metadata repairs detailed below. The active benchmark remains unchanged. The original reference results are retained as historical evidence.

Date: 2026-09-08 America/Sao_Paulo. Candidate only; not adopted into the active benchmark.

The full repaired test suite completed with **1,938 passed and 2 failed in 131.86 seconds**. Both failures are the previously investigated raw evidence-hash links. The pinned Ruff checker passed. Strict locked installation and execution are **not passing**: the package manifest says `1.0.6+evalrepair.10`, while the lockfile's editable self-entry still says `1.0.6+evalrepair.9`.

## Candidate identity and environment

| Item | Recorded value |
|---|---|
| Repository | [TestBoxLab/ApplicationBench](https://github.com/TestBoxLab/ApplicationBench/tree/4cf5ef5ad8f417387e2898fd40d9e7aeba870699) |
| Reference HEAD | `4cf5ef5ad8f417387e2898fd40d9e7aeba870699` |
| Vendor import commit | `0bb57926f1e4a3ab5a4094add80cc2ee8b702f38` |
| Vendor subtree | `vendor/automation-bench`, Git tree `7ac9559eb65540feac74d5d12c37406b4d69fd56` |
| Candidate environment | `.references/ApplicationBench/vendor/automation-bench/.venv` |
| Host | Windows, Python 3.13.9, MSC v.1944 AMD64 |
| uv | `0.9.10 (44f5a14f4 2025-11-17)` |
| Installed package | `automation-bench==1.0.6+evalrepair.10` |
| Key pinned dependencies | `verifiers==0.2.1`, `pydantic==2.12.5`, `pytest==9.0.2`, `ruff==0.14.10` |
| Preserved lock SHA-256 | `a03ea7adb3ad0b7379d70c10c155d2413b456b3b9c9565b792f94eb0231d313b` |

## Executed commands and results

All commands ran from `.references/ApplicationBench/vendor/automation-bench`.

| Command | Result |
|---|---|
| `uv sync --locked` | Exit 1: lock needs updating; isolated `.venv` created, installation refused |
| `uv sync --frozen` | Exit 0: installed 117 packages from the preserved lock; built the current local `.10` package |
| `uv run --frozen python -m pytest tests -q` | Exit 1: 1,938 passed, 2 failed; 131.86 seconds |
| `uv run --locked ruff check .` | Exit 1: same lock gate; Ruff did not execute |
| `uv run --frozen ruff check . --output-format concise` | Exit 0: `All checks passed!` |

`--frozen` was an explicit diagnostic continuation after the `--locked` rejection. It does not validate manifest-lock consistency, and these results must not be described as a passing locked build. The reference lock records the `.9` editable self-entry at `uv.lock:184–186`; the manifest records `.10` at `pyproject.toml:7`. Neither file was edited. uv also warned that pinned `numpy==2.4.0` is yanked for a backward-compatibility bug; installation nevertheless completed.

The two full-suite failures were:

1. `tests/test_microscopic_brittleness_audit.py::test_microscopic_audit_hash_linkage_and_release_metadata`, line 89: historical change-report SHA `05844c15...` versus packaged LF bytes `af8da62f...`.
2. `tests/test_second_pass_audit.py::test_second_pass_ledger_schema_coverage_hashes_and_counts`, line 70: historical Operations/Support source SHA `1445478a...` versus packaged LF bytes `a28da975...`.

No hash assertion was weakened, skipped or changed. This run used the original packaged LF artifact bytes. Prior reconstruction checks remain separately reported in the dependency audit: exact CRLF restoration resolves three links, after which the microscopic test reaches a final unverified parent-ledger byte hash. That final link is not silently credited as passing.

The suite also printed its evaluator-error summary: two Jira `ValueError` events and one unknown-assertion `ValueError`, retained without credit. These are diagnostic output separate from the two pytest failure IDs; the full pytest summary above is the authoritative test result.

## Provenance reconciliation

The new [repair-provenance-reconciliation.json](repair-provenance-reconciliation.json) records:

- Exact repository, subtree, lock and Git-blob identities.
- Packaged raw, LF-normalized and CRLF-reconstructed hashes for five linked artifacts.
- Exact newline transformation and inserted-byte counts; parsed JSON content remains equal.
- Three historical raw hashes verified by CRLF reconstruction, with untouched finance and marketing source hashes verified directly.
- The remaining v2 parent SHA `19427a136248a6b446b659eda379ca69446a357f3d0d45e3362959aec1e2e832`, explicitly **unverified**.
- Verified full-object equality between the shipped v1 parent and a reverse derivation from v2 using `scripts/build_second_pass_600_v2.py`'s documented transformation. Both canonical objects hash to `2aa170ce4ef93ba01b7884835349294f868f334b9720a842e6cfbd98f20430b6`.
- Full candidate validation commands, results and captured-log digests.

Semantic parent equality does not authenticate the unrecovered historical byte serialization. Preserve that distinction in the next candidate manifest. Do not overwrite the original historical hashes or claim that this record makes the original tests green.

## Evidence files

The ignored local reference checkout retains full output:

| Log | SHA-256 |
|---|---|
| `.references/ApplicationBench/vendor/automation-bench/candidate-pytest.log` | `759a8a5c81fe30e8179f3536eb713258fb1807eebfd6db161b09dc9bc354abc1` |
| `.references/ApplicationBench/vendor/automation-bench/candidate-ruff.log` | `a4443afdcfb6d7363adb285762515ccf7cf50473b1a05c20c1a50f6bed4d26b0` |

The versioned JSON record retains the exact failure identities, counts and hashes even when that ignored checkout is unavailable. Reproduction uses the pinned source and commands above.

## Preservation and remaining gates

The active dependency remains upstream `4a8e1061254004d9dac807054eed33fad7d1ff14`. Active and reference vendor Git status were clean after validation. No production source, scored task, expected-hash test, lockfile or historical result was edited. No paid calls were launched.

A future staged migration should produce a separate candidate lock whose editable self-entry agrees with its manifest, preserve the original lock and provenance artifacts, and carry a new explicit evidence-link reconciliation record. Then rerun the locked gate and candidate checks before integration. The full test result supports the availability of the repaired runtime; it does not establish safe evaluator isolation, correct strict-denominator handling, complete WorkflowBench integration, or model performance. Those remain separate foundation gates.

## Derived packaging candidate: passing locked validation

A separate `.references/automation-bench-candidate` was created from the 611 tracked files of the pinned repaired subtree. It carries identity `automation-bench-evalrepair.10-packaging-reconciliation.1` in `DERIVED-PACKAGING-PROVENANCE.json`. Its four changed existing files are metadata only; the other **607 source files are byte-identical**, including every task, runtime/grader module and test. No test was edited, skipped or weakened.

The repairs are exactly eight replacements: one editable self-version in `uv.lock` and seven `sha256` reference fields in three adjudication JSON files. A parsed-lock comparison proves all dependency pins and other lock metadata unchanged. A structural JSON comparison proves every changed JSON value is one of the explicitly declared hash pointers in the reconciliation manifest.

| Metadata path | Original SHA-256 | Derived SHA-256 |
|---|---|---|
| `adjudication/microscopic-brittleness-358-v1.json` | `33a9b229a5da400ed73d16a67d8ea3f8a11b0f7b559dfd20ae8ac70ac1aab816` | `216808813729be4fd2d241ba838ca1356d711da247729c092bedbe3fc72dd05e` |
| `adjudication/second-pass-600-v1.json` | `cac54ae8f3c06c4e1edb39d0c3749af6b03fe40f0f56c23aef4e1a866369ecdb` | `1fbf28a7ab1067ffda353948612228e544399b7c8f5df6afd91bd2768eef26db` |
| `adjudication/second-pass-600-v2.json` | `67494538358c6387b41275ddd03696e6ac97a8e1be209cc00f90bb216c3bafdf` | `ad493b96b8b5a6d178eaab0546edf8c553315f2576108c4d4173ef691a82d384` |
| `uv.lock` | `a03ea7adb3ad0b7379d70c10c155d2413b456b3b9c9565b792f94eb0231d313b` | `1a6408393bf14b6154e35631158688b608dbdcebd865ba26bcf26e00919af67e` |

The JSON propagation updates the microscopic audit's change-report link, v1/v2 Operations/Support and microscopic-audit links, and v2's parent-ledger and fairness-artifact links to the exact bytes present in this derived package. The additional fairness link also reproduces its historical hash exactly by CRLF reconstruction: expected `8825a395c4809c5e63e0de50a571f50ac8e440b4d0874f685cf3ab079b0ab124`, packaged LF `b8532fdada8fd301f324490ad56bc4b264ab12bf893831aaa0d588bc3aefc8f4`. The fairness artifact itself was not changed.

The unresolved historical parent SHA remains marked unverified in the preserved reconciliation record. The derived link authenticates the explicit derived v1 bytes; passing this derived package does not retroactively authenticate the missing historical serialization. Original raw hashes, CRLF transformations, semantic-parent proof and initial failures remain preserved.

Executed from `.references/automation-bench-candidate`, with its own isolated `.venv`:

```powershell
uv sync --locked
uv run --locked python -m pytest tests -q
uv run --locked ruff check . --output-format concise
```

Results: strict sync **exit 0**, full tests **1,940 passed in 127.14s**, and Ruff **All checks passed!** The derived lock hash remained unchanged during these commands. No active-vendor adoption or paid run occurred.

| Derived validation log | SHA-256 |
|---|---|
| `.references/automation-bench-candidate/candidate-locked-pytest.log` | `0b7f02f38deb8eafa738bd0b2c92a2d4859f69a4bbad799eefc468e0c395eb60` |
| `.references/automation-bench-candidate/candidate-locked-ruff.log` | `a4443afdcfb6d7363adb285762515ccf7cf50473b1a05c20c1a50f6bed4d26b0` |

Derived manifest SHA-256: `e9b009c7390d787d1a39582e4a06a9a5904536502a2181e220c93285c12314e1`. The versioned reconciliation JSON embeds all changed paths, old/new values, byte hashes, scope assertions and validation results, so the repair remains reviewable without relying on the ignored checkout.

The earlier remaining-gates paragraph applies to the untouched imported candidate; this derived package has now completed its proposed lock/provenance packaging gate. Runtime isolation, WorkflowBench world/invariant integration and any scored migration remain separate work.
