# Artifact workspace verification

## Local implementation

The current revision follows Carlos's rejected hosted acceptance and his explicit
choice to define feature discovery now, with execution/evaluation later.
No paid run, provider request, upstream benchmark edit, GitHub configuration
commit, push, PR or merge was used for verification.

- Repository/API/execution group: **71 passed** after the final boundary fixes.
- Construction/provenance/configured-run/recipes group: **79 passed** after the
  shared construction guard and competitor identity fixes.
- Root confirmation of artifact schemas, future modes, provenance, static CSP
  and run presentation: **57 passed** on the final implementation.
- Earlier configuration/controls/Enterprise regression group: **201 passed**.
  These groups overlap; their counts must not be added as distinct tests.
- Browser checks passed at desktop and 390px: four artifact groups, typed
  creation, required fields, generated evidence read-only, authenticated author
  and technical committer, multi-file drafts, validation, conflicts, network
  failures, pinned preview/launch and configured-run controls. All write/launch
  requests in these browser checks use in-page mocks, not GitHub or providers.
- A separate browser check covers full retained commits/KB hashes, missing
  historical provenance, multiple Monarch setups, continuation segments and
  escaped labels. It never modifies a stored run.
- New regressions were observed failing before their fixes: README edit policy,
  duplicate keys, spoofed authors, missing navigation/provenance, wrong artifact
  references, malformed change payloads and direct-construction refusal bypasses.
- `git diff --check` and JavaScript syntax checks passed. The UI detector found
  no issues in the grouped editor; the wider workspace scan reported one
  pre-existing padding animation outside this change.
- Graphify refreshed 11 changed Python/JavaScript files: 507 structural nodes,
  1,306 edges, 23 communities, no paid extraction. HTML, CSS, tests and other
  repository areas are outside this graph's stated scope.

## Limits and remaining acceptance

The current capture records declarations/checkouts and existing retained service
evidence. It cannot independently prove the deployed Monarch commit without
source attestation from its services/deployment pipeline. Missing historical
commits remain unknown. Discovery execution, model-family routing, deployment
orchestration and individual SSO/budget profiles remain explicit follow-up work.

Hosted integration preserved unpublished source already present on Railway.
The previous release baseline is `c822b12d-d7a0-44d8-b0ea-995776424331`; uploading
the feature worktree wholesale would remove that source. Hosted verification
passed; Carlos's renewed acceptance remains required before PR/merge.

The integrated source retained the canonical report's 106 attempts, seven
competitors, Monarch 3/10 initial and 4/10 after retries, USD 41.357219 Monarch
cost, performance details and guide hashes. Both browser checks passed against
that source. The final integrated Python group passed **73/73**; configured
execution/pause/resume/provenance also passed **27/27** in both worktrees. The
first integrated Python check reported seven failures: six came from test
fixtures sharing a fake commit in an unrelated immutable cache, and one from
an incomplete test RunConfig. Only fixture isolation/shape changed; the cache
guard, runtime code and frozen manifests remained intact.

The final deployment is `faa848df-d257-41a9-a58f-316853bbfc5c`, SUCCESS.
Eight HTTP checks and final hosted browser checks passed. The existing canonical
run API fields have the identical SHA-256 before and after deployment, excluding
only the new response-only provenance projection. Hosted catalog: 40 recognized
artifacts, nine types, authenticated account displayed, read-only repository
access. Saving/history remain unavailable with the current snapshot connection.
A repeated version-explanation sentence found in the visual pass was corrected;
its browser regression failed first, then passed locally and on the final host.
See the [release record](../../../monarch-benchmark/docs/rounds/2026-09-11-benchmark-artifact-workspace.md).

## Subsequent editing activation

Carlos accepted the artifact segregation and authorized push/PR after restoring
editing. The earlier read-only status above records the first deployment.
Removing only the obsolete snapshot selector restored Git-backed editing and
history on the same validated image; README and historical inputs are intact.
Hosted browser checks passed. Merge remains pending.
See the September 11 Studio configuration editing restoration record.
