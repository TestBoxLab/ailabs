# Research and decisions

- Existing config kinds and loaders live in wb_orchestrator/config.py. Extra
  files include price tables, knowledge-base references, knowledge maps and side
  effects. Preserve their current format rather than adding kind/apiVersion keys.
- `from_workflowbench` currently anchors relative paths to config's parent;
  external artifacts require an explicit runtime root for non-config references.
- CLI configured execution already exists in Orchestrator.from_config. Studio's
  older create-and-run API-control workflow is different; do not silently map one
  to the other. Present configured-plan execution as its actual semantics.
- Provider registry is populated at import time. Bind loaded model objects to a
  run instead of mutating this process-global registry on repository refresh.
- GitHub Git trees/commits support atomic multi-file changes. Update main with
  force=false; compare expected parent and surface 409 on intervening commits.
  Docs: https://docs.github.com/en/rest/git/refs#update-a-reference and
  https://docs.github.com/en/rest/git/trees#create-a-tree .
- No submodule: direct revision reads avoid updating the parent repo for each
  config edit. No webhook: refresh on demand/preview meets the approved workflow.
- Auth currently includes shared Basic Auth plus an optional person-key layer.
  A declared operator alone must never be described as an authenticated person.
