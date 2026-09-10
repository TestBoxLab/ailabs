# Configuration repository operations and verification

The approved private repository is
https://github.com/TestBoxLab/ailabls-benchmark-config, branch `main`.
AI Labs owns the loaders, validation rules and execution code. The associated
repository contains concrete `config/` artifacts using the existing directory
layout. No Git submodule or configuration redeploy is required.

## Setup

Configure `WB_CONFIG_REPOSITORY=TestBoxLab/ailabls-benchmark-config` and
`WB_CONFIG_GITHUB_TOKEN` on the Studio service. The credential needs Contents
read/write access to this repository only. Keep it in Railway variables or the
existing gitignored WorkflowBench `.env`; never place it in configuration files.
The default hosted cache is `$STUDIO_DATA_DIR/config-revisions`.
`WB_CONFIG_CACHE` overrides the CLI cache. Local CLI use can also use an existing
GitHub CLI login. The hosted service never falls back to that login.

In Studio, open Settings, then Benchmark configuration. Select or create a file,
edit its YAML, validate, inspect the diff, enter your name and a commit message,
then save to main. Multiple edits form one commit. A conflicting main revision
keeps the draft for explicit comparison; no forced update overwrites another save.
Saving never launches a run. Select the saved product and plan, preview attempts,
cost ceiling and readiness, then use the separate launch control when authorized.

From `monarch-benchmark/workflowbench`, use `uv run wb preview --product
simulated-apps --plan check-infrastructure --revision <full-commit>` for a free
preview. Configured execution uses the same resolver and orchestrator in CLI and
Studio. Existing ad hoc Studio comparisons remain separate. Use `--local-config`
for an explicitly local CLI plan; a configured remote source never silently falls
back to bundled files.

Each configured run retains the full source revision and resolved configuration.
Resume uses that original source even after cache deletion. A changed budget
ceiling needs a new committed plan and a new run. Configured Studio runs support
graceful cancel, not pause; repeat them from the saved-plan selector in Settings.
Approval, verified billing, budget and task-freeze checks still gate launch.

## Migration evidence

All 41 original configuration artifacts were verified byte for byte against
remote commit `c32d16d1d76f9b7ea6409f25acb59ddfa36614a7`. The repository's
`migration.json` records their SHA-256 hashes; `.gitattributes` preserves those
bytes. Original bundled configurations remain available for historical/local use.
No AutomationBench tasks, assertions, seeds or vendor code changed.

Four existing missing-harness references in two achievable-50 plans remain
visible warnings when those files are untouched. Editing an invalid file requires
fixing it; selecting an invalid plan still blocks launch. Migration does not
silently repair benchmark artifacts.

## Verification evidence

- Existing configuration baseline: 115 passed.
- Repository, Studio integration, execution, Studio regressions and CSP group:
  104 passed in 37.46 seconds, including the final persisted billing-shape regression.
- Runtime agent groups: 124 configuration/resolution checks; 117 run/approval/
  dispatch/guard checks; 26 competitor/budget checks passed. Groups overlap.
- Browser fixture exercises editing, multi-file commits, conflicts, outages,
  preview gates, immutable launch payloads, operator changes and run controls.
  Desktop and 390-pixel views were inspected. Auxiliary knowledge files remain
  editable but are excluded from product choices.
- Independent review reproduced a billing aggregation issue using numeric cost
  plus unknown-billing flags. The repaired aggregation retains unknown totals for `None`, `billing=unknown`
  and `cost_missing`; regression tests preserve real numeric subtotals.

No paid competitor calls belong to this feature verification. The complete test
set has not been run for this feature. Real local-browser save created commit
`cecb7e4f8291e02a43082fe8d67e9420b07347f4`, changing only config/README.md
(+7 lines), with exactly one save request and no run request.

Hosted code deployment is verified; repository access remains blocked. The Railway token is present and was
copied into the original checkout's existing gitignored WorkflowBench `.env`.
It authenticates against GitHub (HTTP 200 for the user endpoint), but access to
the private configuration repository currently returns HTTP 404. Carlos was asked
to check repository selection and organization approval; no broader credential
was substituted into the hosted service.

Graphify AST refresh completed: 17,197 nodes, 43,036 edges, 412 communities.
Deployment source: clean commit `9bd2f2c`. Railway deployment
`723fa1c7-a747-44c8-be34-4d4a39842aa9` reached SUCCESS; image digest
`sha256:189a54f061cfa8edd1e877ae5162889622f4bd17b15c6964675e235346fbad49`.
The authenticated hosted browser renders Settings > Benchmark configuration and
reports the repository HTTP 404 accurately. Existing job listing was checked
before deployment: 11 jobs and no active job. No benchmark run was launched.

The local browser verified a saved-plan preview using Carlos as operator; missing
provider credentials correctly blocked launch. Desktop and mobile screenshots
were inspected. The local test server was stopped after verification.

The AI Labs implementation is committed locally on `ailabs/config-repository`;
it has not been pushed to AI Labs GitHub. Configuration repository commits are
published to main as explicitly authorized. Hosted browse/save/preview completion
still requires the restricted token to access the private repository.
