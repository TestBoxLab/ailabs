# Benchmark artifacts: acceptance walkthrough

Open **Benchmarks** in Studio. Harnesses, Models, Plans and Products have their
own routes (`#benchmarks/harnesses`, `#benchmarks/models`, `#benchmarks/plans`,
`#benchmarks/products`). Settings retains host and account configuration.

## Editing and history

Select a supported YAML artifact, or choose its type and name to start from an
AI Labs example. Review required fields and references, validate the whole draft,
inspect its diff and save with a commit message. Validation also runs on the
server when saving. README is excluded; generated knowledge/recipe YAMLs are
read-only. Update generated evidence through its existing generator.

The authenticated Studio account authors the commit. With the shared Basic
login, its configured username is recorded; Studio cannot identify who shares its
password. The technical committer is `AI Labs Studio`. Recent history shows both.
The run operator field belongs to paid run approval, not commit authorship.

## Definitions supported ahead of execution

Keep the other required product and plan fields. Add `feature-discovery` to the
product's `modes` and set a corresponding plan's `mode: feature-discovery`.
These definitions validate; preview and execution explicitly refuse them until
discovery execution and evaluation are implemented. They cannot run workflow
tasks under a discovery label.

A Monarch harness may declare role-to-family requirements, for example:

```yaml
model_families:
  brain: claude
  writer: claude
```

Use family names present in that harness's referenced price table; `claude`
above is illustrative, not a guaranteed configured family. Supported role names
are `brain`, `writer`, `selector`, `critic`, `triage`, `reviewer`, `storyteller`,
`advisory`, `investigator`, `engine_small` and `engine_large`. A nonempty mapping
blocks execution until Monarch can select and verify those families. An omitted
mapping preserves current execution behavior and configuration hashes.

## Recorded Monarch version

Open a run and expand **Monarch version**. Full retained source commits,
knowledge-base hashes and execution segments appear when available. A local
checkout or operator declaration is labeled accordingly; neither proves which
source Railway ran. Older runs without that evidence say **Not recorded**.
This release does not fabricate historical commits or implement deployment
selection. Source attestation across independently deployed Monarch services
still needs integration before every run can prove its exact deployed commit.

## Browser acceptance

- Visit each artifact group and open its direct URL after reloading.
- Confirm README is absent and generated product evidence cannot be edited.
- Create a draft from a supported type; invalid YAML/unknown fields prevent save.
- Move between groups and confirm draft edits remain available for one diff.
- Confirm the displayed authenticated author and separate technical committer.
- Inspect a run's recorded Monarch version and any explicit missing evidence.
- At a narrow viewport, reach the editor, validation, history and preview controls.
- Preview only if desired; **launching a run spends money** and requires the
  usual verified billing, operator and approval conditions.
