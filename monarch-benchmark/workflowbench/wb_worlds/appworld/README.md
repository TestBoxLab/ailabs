# AppWorld adapter

The adapter uses AppWorld distribution `0.1.3.post1` and data bundle `0.1.0`.
The environment runs in a Linux container because source execution uses SIGALRM.
The source evaluator runs in a separate Python environment, retaining the source
package's dependency constraints. No source evaluator runs inside a competitor.

## Local runtime

Set `APPWORLD_ROOT` to the installed AppWorld data directory outside this public
repository and `WB_APPWORLD_PYTHON` to the isolated source Python interpreter.
Set `WB_APPWORLD_URL` for the private environment server (default
`http://127.0.0.1:18080`). Build `Dockerfile` in this directory. Mount the external
root's `data` at `/run/data` read-only and its `experiments/outputs` at
`/run/experiments/outputs` writable. Publish container port 8000 on loopback only.
The `/workflowbench-runtime` administrative probe checks the server's distribution
and data version against the local source evaluator before paid launch.
`runtime_identity()` also inspects `WB_APPWORLD_CONTAINER` (default
`wb-appworld-pinned-v2`) and verifies the running container owns the configured
loopback port. Source manifests can freeze `source_ref.runtime_image`; hydration
then refuses an image change. Offline regrading verifies stored source evidence
without requiring the original container to remain running.

The image used for the September 11 controls is recorded in
`smoke-control-manifest.json`. Rebuilding can change dependencies and the image
hash; freeze the resulting image identity for each experiment. The base image is
pinned in the Dockerfile; the upstream application data and assertions are untouched.

## Tasks and evidence

`import_tasks(split, out, task_ids=[...], reviewed_rules=...)` supports only train
and dev, whose reference solutions are published. Manifests contain task IDs,
source pins and hashes; hydrate the task immediately before constructing the arm.
Each task's source fingerprint covers its complete source task tree, base databases,
API documents and data version. The suite revision is shared across tasks.

All AppWorld run output, journals, snapshots, source checker output and detailed
reports must be written outside this repository. `attach_journal` refuses a path
inside it. Use external `wb run --out` and `--db` locations. A source evidence
manifest preserves the unique experiment identifier and hashes of the final source
databases; grading refuses missing, changed or mismatched evidence. Repository
records may retain task IDs, scalar results and hash pointers as demonstrated by
`smoke-control-manifest.json`.

The source server holds a single global active world. A cross-process lock prevents
two adapter attempts from sharing it, and every attempt uses a unique experiment.
Teardown releases the lock even when the source close fails. Native application
operations are translated to fixed Requester calls against its local client;
competitors cannot submit arbitrary Python or reach administrative operations.

## Independent checks

`positive_check` preserves the full source `evaluate_task().to_dict()` result.
Only entries labelled `no_op_pass` represent the source's collateral finding.
Entries labelled `no_op_fail` are checks that a null action should fail, and remain
part of source success without being mislabeled as collateral. WorkflowBench's
reviewed snapshot rules are reported separately and strict success requires both.

The September 11 free controls verified two reference completions, a null action
and a correct completion with one unrelated application change. These are source
integration controls, not Monarch or native-agent performance measurements. Both
reviewed reference completions passed. The null action failed source success with
identical snapshots; the unrelated change failed both source and lab collateral.
The frozen smoke tasks and detailed evidence remain at the external paths recorded
in `smoke-control-manifest.json`.

Focused offline checks:

```powershell
uv run python -m pytest tests/test_worlds_appworld.py tests/test_appworld_import.py -q
```

The common three-tool interface has no header argument. Published façade schemas
therefore declare `access_token` as a query input for GET or a JSON body field for
writes; the source Requester converts it to its original bearer header. Source
form login fields are also published as JSON inputs and retain their native form
transport inside Requester. `api_search` and front-door OpenAPI agree on these
transformations; installed source documents remain unchanged.

`controls.run_controls(task_directory, output_directory)` is the explicit free
reference/null pipeline control. It resolves external product/plan files, runs the
actual Orchestrator and Store, generates reports, then checks independent regrade.
It does not call providers and must never be labeled a Monarch/native comparison.
