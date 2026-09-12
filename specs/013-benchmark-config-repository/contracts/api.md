# Configuration repository API

All endpoints use existing Studio authentication, trusted-host/origin and CSRF
checks. Writes use existing person permissions. Error responses contain `error`
and appropriate 400/403/409/503 status; never credential values.

- `GET /api/benchmark-config`: `{repository, branch, commit, files, history_url,
  configured, writable}`. Files are `{path, text, sha256}`; paths start `config/`.
- `POST /api/benchmark-config/validate`: `{base_commit, changes}` returns
  `{valid, errors, diff}`. Changes are `[{path, text}]`; null text deletes a file.
- `POST /api/benchmark-config/save`: `{base_commit, changes, message, operator}`
  returns the updated catalog. Saves are atomic across all changes. A stale base
  is 409. No-op returns the existing catalog without committing.
- `POST /api/benchmark-config/preview`: `{commit, product, plan}` returns
  `{preview_id, commit, product, plan, config_hash, tasks, competitors, attempts_min,
  attempts_max, cost_ceiling_usd, launchable, reasons}`. It never reserves or spends.
- `POST /api/benchmark-config/run`: `{preview_id, commit, product, plan, request_id, operator}`
  returns the normal Studio job. Existing launch gates apply; unsupported runtime
  settings return a refusal, not a substituted comparison.

Preview and run names refer to filenames without the `.yaml` suffix. The server
resolves the entire revision and dependencies; the browser cannot provide resolved
prices, substitute config bytes at launch, or override approval rules. The preview
commit is echoed at launch, never replaced with current main. UI can link the
configured repository history; GitHub handles normal revert history.
The server-issued preview ID binds the resolved hash and external task hashes;
launch refuses task changes since preview before it can spend.
