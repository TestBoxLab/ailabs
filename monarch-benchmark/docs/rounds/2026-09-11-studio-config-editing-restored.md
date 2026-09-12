# Studio configuration editing restored

Carlos accepted the artifact segregation and authorized push and a PR after
restoring editing. README must remain in the configuration repository and be
filtered only from Studio. Merge remains pending.

## Cause and correction

`WB_CONFIG_SNAPSHOT` still selected the read-only repository implementation,
even after the existing token acquired repository access. Removed only that
environment selector; all other service variables and the frozen snapshot file
were preserved. No application patch was needed for this operational correction.

With no active jobs or Genesis turns, redeployed the known successful image from
`faa848df-d257-41a9-a58f-316853bbfc5c`, explicitly reusing its image. This avoided
a separate failed source upload and preserved unpublished hosted work.
Deployment `87dc0b5e-5a74-484c-ab31-74708330b0dd` succeeded with identical digest
`sha256:a02848170d57e604e3ce4ddd5039228f365282d1af302db430f0dbd9880d4c82`.

## Verification

- Authenticated hosted browser: 40 recognized artifacts, README filtered,
  editable model YAML, invalid unknown field rejected, valid comment-only draft
  enabling Save and displaying its diff. Discarded the draft after the check.
- The actual save endpoint accepted an empty change list without creating a
  commit. History returned three entries. Changed saves and concurrency are
  covered by offline tests; no configuration commit was made by this check.
- A bounded Git blob write of the existing README bytes returned its existing
  blob SHA, proving Contents write access without changing a ref or file.
- Configuration main remains `cecb7e4f8291e02a43082fe8d67e9420b07347f4`.
  `config/README.md` remains 25,691 bytes, blob
  `fc0c67bc03566328eaf59d479b1bbd21cbca927f`, SHA-256
  `bba801341897a7aa38040c0d2046eb960b857de73de37dd24f9b3e3dbef616ad`.
- Canonical run `f2799405-f9b3-4fb2-8e41-a517e9c39260` remains completed with
  106 attempts and USD 51.06925921. Its API JSON, excluding only the response-only
  provenance projection, retains SHA-256
  `854a2dd6af1d16bf98efecdde95e12cc9bd0d9f49885eb94a409ca0874189511`.
- Fresh targeted Python verification: 93 passed. Independent final review:
  53 passed, no confirmed blocker. These groups overlap and are not additive.
  Full Ubuntu CI runs on the PR; the CI workflow tests and validates the corpus,
  without infrastructure deployment or paid model calls.

No benchmark attempt, paid analysis, historical rewrite or upstream data change.
Reload an already open Studio page after the service restart to refresh the
catalog connection and session token.
