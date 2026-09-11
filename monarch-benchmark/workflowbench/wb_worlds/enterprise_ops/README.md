# EnterpriseOps-Gym runtime

This adapter serves the source's real ITSM HTTP API, seeds a private database for
each attempt, stores the final SQLite database, and runs the unmodified source SQL
checks after teardown. WorkflowBench separately checks the snapshot diff against
reviewed, task-specific permitted changes. There is no source reference-solution
competitor or published-score ceiling for this product.

## Immutable inputs

- Source: `ServiceNow/EnterpriseOps-Gym` commit `271f2c357f763376997dfd16807fcde2474ae41b`.
- Dataset: `ServiceNow-AI/EnterpriseOps-Gym` revision `c8e538eae8a6205294f0a86675fefdc1fac408f6`, `itsm/oracle`.
- ITSM image: `shivakrishnareddyma225/enterpriseops-gym-mcp-itsm@sha256:a234ae3fb7cee196ba25e6b9957969dea829919b6e8271dddae128f065aaf39f`.
- Rules: `reviewed-rules.yaml`. Lucas selected reviewed rules for the initial set on 11 September 2026. The named reviewer is Codex; this does not claim a human reviewed the individual records.
- Tasks: `tasks/eog-itsm-smoke-2/`. The adjacent `.manifest.yaml` records all exclusions.

The originally considered task ending `f931fd42` is excluded because its seed already
contains `INC_024`, while its checker requires a newly created incident at that ID.
The task and seed remain unchanged. The replacement task ending `8fd400d1` asks for
two alerts, and `be0bd794` asks for one service correction and one alert. These are
reviewed development smoke tasks, not a representative sample.

## Setup

Run commands from `monarch-benchmark/workflowbench/`. Acquire the pinned source and
extract its `gym_dbs.zip` outside tracked files. Keep the original extracted relative
paths. Set `WB_EOG_DBS` to that root (the local default is
`.external/enterprise-ops-dbs`). Import rejects a missing seed; provisioning rejects
a seed whose SHA-256 differs from the frozen task.

```powershell
docker run -d --name workflowbench-eog-itsm -p 127.0.0.1:18005:8005 shivakrishnareddyma225/enterpriseops-gym-mcp-itsm@sha256:a234ae3fb7cee196ba25e6b9957969dea829919b6e8271dddae128f065aaf39f
$env:WB_EOG_URL='http://127.0.0.1:18005'
uv run python -m wb_worlds.enterprise_ops.smoke_check
```

Reuse an existing container only after inspecting its immutable image ID/digest.
The adapter health check proves connectivity, not container provenance. Remote
runtime operators must verify the deployed image separately before a paid round.
`WB_EOG_URL_GYM_ITSM_MCP` overrides `WB_EOG_URL`; the dataset's original server URL
is used only when neither override is configured.

`import_eog(["itsm"], output, reviewed_rules=path)` downloads the immutable dataset
through the optional `datasets` package. For offline acquisition tests, pass recorded
`rows`, `seed_root`, `revision`, and `source_revision`. Existing frozen files are never
silently overwritten; different content requires a new output directory.

The source's selected tool list is enforced in search, public OpenAPI, and actual
requests. The lab supplies private database and synthetic user-identity headers.
Database administration, seed/reset, raw SQL, snapshots and grader data are blocked
from competitors. Source task system and user messages remain unchanged. Only
API transport and the native harness differ from the source evaluation.

## Monarch source catalogue

Use the `monarch-eog` harness and its source-only organisation. The source catalogue
is separate from the existing AutomationBench products. After configuring the
harness environment and mounting this catalogue in the discovery service:

```powershell
uv run wb monarch setup --product enterprise-ops-gym --harness monarch-eog --tasks tasks/eog-itsm-smoke-2 --out .external/monarch-seeds-eog
uv run wb monarch verify --product enterprise-ops-gym --harness monarch-eog
```

Setup requires the frozen task contracts and generates the published ITSM API
under `bench-enterprise-ops-gym-gym-itsm-mcp`. Every import uses the discovery
service's current knowledge-base hash, or an explicit absence guard. Its validation
checks source API documents; source-native live execution is a separate smoke
check. AutomationBench knowledge maps and synthetic conformance do not apply.

## Verification evidence

`uv run python -m pytest tests/test_worlds_enterprise_ops.py tests/test_eog_import.py -q`
runs offline. The free integration command above runs positive, null, and stray-write
cases for each of the two tasks against the real source container. Every case keeps
before/after snapshots, observable API calls, termination, final SQLite database,
grading details and artifact hashes under a unique output directory.

The 11 September check at
`out/external-checks/enterprise-ops/2cd5a09693024326b187e7773e4d0dc1/summary.json`
completed six cases with zero provider calls. Both positive cases passed. Both null
cases failed the source checks. Both stray-write cases still passed source checks,
but WorkflowBench rejected the extra notification with collateral damage of one.
This validates wiring and both grading halves; it is not the requested paid Monarch
versus native-agent smoke result.

The free orchestration check also exercises the shared loader, Store, retained
source artifacts, regrading and HTML/Markdown reports:

```powershell
uv run python -m wb_worlds.enterprise_ops.orchestrated_check
```

The completed check at `out/eog-9efb6d5a/summary.json` ran two correct and two null
controls. Both correct controls passed and both null controls failed; all four
stored attempts regraded identically after teardown. It used zero provider calls.
The corresponding results database and report are in that directory. These
controls validate setup and analysis; they are not Monarch or native-agent scores.
