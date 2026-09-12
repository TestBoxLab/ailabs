# Data model

- **Configuration revision**: repository, branch, commit, file paths and bytes,
  per-file SHA-256. Immutable, complete cache directory with a manifest.
- **Edit**: expected base commit, changed/deleted files, operator and message.
  Validated as one proposed tree. One edit produces zero or one branch commit.
- **Resolved plan**: existing RunConfig plus additive source metadata and explicit
  runtime root. Existing semantic hashes remain compatible for unchanged inputs.
- **Run evidence**: existing job/results with source revision, config bytes and
  resolved model/harness/plan values. Later cache or main updates cannot alter it.

Secret values never belong to these entities. Their named environment references
are resolved only by the server at the existing credential boundary.
