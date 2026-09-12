# Local WorkflowBench output cleanup

Date: 2026-09-10. Requested by Carlos. Status: completed and verified; files sent to the Windows Recycle Bin.

## Scope and decision

`C:/Users/cgmat/Desktop/TestBox/ailabs/monarch-benchmark/workflowbench/out` only.
No hosted Studio data, Downloads, sibling checkout, runtime configuration,
AutomationBench inputs or spending ledger are removed. Git-tracked evidence and
reports referenced by the program documents remain in place.

Declarative configuration does not replace execution history. Feature 013
excludes results, ledgers and experimental architecture artifacts from migration.
Files are classified by actual dependencies and content, never by extension.

## Retained sources

| Source | Evidence / reason to retain |
|---|---|
| `out/wb.sqlite3` | CLI default; 213 runs and 8,987 attempt records, including imported history. SHA-256 `f718a6064c463c02c7b68c8a44c2da2a96149855040564b0b268c52443b5ecf3`. |
| Other distinct result databases | Smoke and hosted diagnostics have separate historical rows. |
| `out/tier-simple-ui-20260910/results-final.sqlite3` | 106 final attempts; existing CSV/JSON exports retained. |
| Recovery directories and their evidence archives | Old archives contain 5 and 10 changed file members versus the final archive, including prior job/database/events and one earlier attempt state. They are not redundant copies. |
| Langfuse/billing and deployment records | Delivery, unknown charges, run interruptions and provenance cannot be reconstructed from YAML. |
| `out/studio/` | Local Studio state; startup also uses it as initial volume seed. No migration has made it disposable. |
| `out/product_graph.json`, `openapi/`, `monarch-seeds/` | Existing generated application knowledge / historical inputs, outside feature-013 config migration. |
| `out/single-task/` | Referenced by `config/plans/pilot-monarch-single.yaml`. |
| Tracked reports and raw run directories | Versioned evidence and source links; no replacement migration verified. |
| `report-run-20260910-155059-internal.*` | Current renderer refuses this run because its episode evidence is invalid/unavailable to its verification path. Existing report retained; no guard bypass or regrading. |
| Operational launch/watch scripts and logs | Existing local routing tools and historical incident records; ngrok/processes still present during audit. Hosted routing changes do not establish local obsolescence. |

Set/architecture creator JSON is not automatically replaced by declarative config:
`wb_studio/blueprints.py` and `product_graphs.py` still persist versioned artifacts
under the Studio directory. No standalone obsolete set-creator export was found
in this checkout. Do not delete these stores without a verified migration.

## Verification

- Six historical runs regenerated both technical and executive HTML offline from
  a temporary SQLite backup; original database SHA-256 stayed identical.
- Run `run-20260910-155059` was refused by the evidence gate and excluded from deletion.
- Duplicate database, configuration, screenshot and helper copies matched SHA-256.
- Final Excel helper now reads `results-final.sqlite3` instead of the redundant
  live copy. Running it on a temporary copy reproduced all three export files
  byte-for-byte: 106 attempts, 83 attempt columns and 745 check rows.
- No paid calls, regrading, application deployment or hosted database mutation.

To regenerate a removed report, from `monarch-benchmark/workflowbench/` use
`uv run wb report <run-id> --audience internal` (or `--format executive`).
This renders retained results; it does not run competitors.

## Deletion manifest

35 files; 3,625,821 bytes removed from `out/` (recoverable in the Recycle Bin). Paths below are relative to `out/`.
Hashes record the bytes before deletion. The empty `drafts/` directory remains; no recursive directory deletion was needed.

| Path | Bytes | SHA-256 | Reason / retained source |
|---|---:|---|---|
| `report-run-20260904-125645-internal.html` | 15909 | `9dfb165a1933ff7fd3e943fa4af41f2ed8e38d5bb0663fb3184ead4a3e46a785` | Generated presentation; HTML and executive report regenerated offline from preserved results; `out/wb.sqlite3: run-20260904-125645` |
| `report-run-20260904-192933-internal-executive.html` | 24021 | `cb6537e0431502f77f029991487e4be49055b6abc6ef54e339298cb8a93a7a0d` | Generated presentation; HTML and executive report regenerated offline from preserved results; `out/wb.sqlite3: run-20260904-192933` |
| `report-run-20260904-192933-internal.html` | 43063 | `93e1f77ae4682546f7e1d3374ac9485c53119c217af83c7bf6d1c63f1a52a14f` | Generated presentation; HTML and executive report regenerated offline from preserved results; `out/wb.sqlite3: run-20260904-192933` |
| `report-run-20260904-192933-internal.md` | 4828 | `a8e86a40d571cb4c2f25ddfb4e8e8d4b8b089e6b0accfd250779fc4ba1e8b48f` | Generated presentation; HTML and executive report regenerated offline from preserved results; `out/wb.sqlite3: run-20260904-192933` |
| `report-run-20260904-192933-internal.pdf` | 133256 | `b645c0771cba9317c367473c6de3c5f898089f7d8f9e7a3231fe8dc73b935e17` | Generated presentation; HTML and executive report regenerated offline from preserved results; `out/wb.sqlite3: run-20260904-192933` |
| `report-run-20260905-022823-internal-executive.html` | 23836 | `9c30ab6a4e6ab18dfc7065f2a7f4485d2199883e23a2509184b5da0113498d52` | Generated presentation; HTML and executive report regenerated offline from preserved results; `out/wb.sqlite3: run-20260905-022823` |
| `report-run-20260905-022823-internal.html` | 73758 | `65b448318e7e9ca6a0aea681a44a5efc29ab04fbec82b2b14eb20c01ead9a0e2` | Generated presentation; HTML and executive report regenerated offline from preserved results; `out/wb.sqlite3: run-20260905-022823` |
| `report-run-20260905-022823-internal.md` | 5192 | `588236d4395e4a87eff9af6e0bb5c454e30a387148b53a3d2582d10e9d66611e` | Generated presentation; HTML and executive report regenerated offline from preserved results; `out/wb.sqlite3: run-20260905-022823` |
| `report-run-20260905-154934-internal-executive.html` | 23791 | `1b425900f8ddadc7f3cd6e4ea5690d9c3c0dc3bf7ac7c41a9ffd946fc428407a` | Generated presentation; HTML and executive report regenerated offline from preserved results; `out/wb.sqlite3: run-20260905-154934` |
| `report-run-20260905-154934-internal.html` | 72502 | `2c0fe3ada08b6b5d9bb99d0617c2d6155b29423786d99bc912f5bc1c602a25e2` | Generated presentation; HTML and executive report regenerated offline from preserved results; `out/wb.sqlite3: run-20260905-154934` |
| `report-run-20260905-154934-internal.md` | 5194 | `bd4296b6fbcb5ddcaacb7365ad76cbe52e78f0c523c8a155fccade232548421a` | Generated presentation; HTML and executive report regenerated offline from preserved results; `out/wb.sqlite3: run-20260905-154934` |
| `report-run-20260905-204158-internal-executive.html` | 23795 | `dad5ae6ccd41e05f4326c59fba48c7ab1dd6133950ff59fe690adcf0f2ef23f9` | Generated presentation; HTML and executive report regenerated offline from preserved results; `out/wb.sqlite3: run-20260905-204158` |
| `report-run-20260905-204158-internal.html` | 140347 | `edc9d7a819b7f41b8364a40649ad7a07cf7244f556e1dd01928e43e763c78f0a` | Generated presentation; HTML and executive report regenerated offline from preserved results; `out/wb.sqlite3: run-20260905-204158` |
| `report-run-20260905-204158-internal.md` | 5194 | `a9da9f8ee37373ac2029dd5a7b8d56085fd1cee14feb74b18d0e219a68c7c928` | Generated presentation; HTML and executive report regenerated offline from preserved results; `out/wb.sqlite3: run-20260905-204158` |
| `report-run-20260906-002313-internal-executive.html` | 22743 | `774c864a406523b287160c4da340cd982b43bd4cfb9cb462e6a1abb0f93b5453` | Generated presentation; HTML and executive report regenerated offline from preserved results; `out/wb.sqlite3: run-20260906-002313` |
| `report-run-20260906-002313-internal.html` | 139998 | `77f7a0bf87066f90e3926cc2e7d78d1f3dfb78def3b27bbe23f45eab9b85d806` | Generated presentation; HTML and executive report regenerated offline from preserved results; `out/wb.sqlite3: run-20260906-002313` |
| `report-run-20260906-002313-internal.md` | 5167 | `476158cfe33f315b1b677549e4f24f373296c8c71e3788166711f4f5b7afcfbe` | Generated presentation; HTML and executive report regenerated offline from preserved results; `out/wb.sqlite3: run-20260906-002313` |
| `drafts/executive.html` | 25654 | `a9f0b34afc3eeabe50f3ba37760e1fbfe0abd2364be92737604c38cc19faec7f` | Obsolete presentation draft for the September 4 pilot; source results and renderer retained; `out/wb.sqlite3: run-20260904-192933` |
| `drafts/monarch-benchmark-pilot-technical-TEST.html` | 47098 | `ec5c0616be8bc1663d31692fc5026e6554e27332cedcc8c3dc230791ff10fd1f` | Obsolete presentation draft for the September 4 pilot; source results and renderer retained; `out/wb.sqlite3: run-20260904-192933` |
| `drafts/technical.html` | 47098 | `ec5c0616be8bc1663d31692fc5026e6554e27332cedcc8c3dc230791ff10fd1f` | Obsolete presentation draft for the September 4 pilot; source results and renderer retained; `out/wb.sqlite3: run-20260904-192933` |
| `drafts/technical.pdf` | 209394 | `af908da23492402fa4a98717197c82e2a962cc5ee8a40d1f02394b07858f3d47` | Obsolete presentation draft for the September 4 pilot; source results and renderer retained; `out/wb.sqlite3: run-20260904-192933` |
| `airtable-before-filter.py` | 10941 | `d5360647db1a7b82d5e604c71687fb6a88b616c8b0011fd48a7fad0cda82bc33` | Byte-identical temporary upstream source backup; `vendor/automation-bench/automationbench/tools/api/impl/airtable.py` |
| `collected-langfuse-20260910.txt` | 378218 | `0773691b1543c353b56544e5fd3d2e13cc943072e84b28cf77e5e358dfe5be21` | Temporary pytest collection listing, not a usage or billing export; `tests/; regenerate with pytest --collect-only` |
| `pr3-body-langfuse.md` | 3422 | `a81db3e0b3e0521af19aca9ed788220cd62355f9ca47e816db29d5910ac09232` | Obsolete PR composition draft after completed merge; implementation and diagnosis records retained; `monarch-benchmark/docs/rounds/2026-09-10-pr3-ci-and-langfuse.md` |
| `tier-simple-ui-20260910/results-live.sqlite3` | 970752 | `910dfba5a4057a84b299648297e1e62ede7feec18b316951da84d5372e4f5f3d` | Byte-identical redundant copy; `out/tier-simple-ui-20260910/results-final.sqlite3` |
| `tier-simple-ui-20260910/results-live.sqlite3-shm` | 32768 | `fd4c9fda9cd3f9ae7c962b0ddf37232294d55580e1aa165aa06129b8549389eb` | Transient sidecar of removed duplicate database; WAL empty; `out/tier-simple-ui-20260910/results-final.sqlite3` |
| `tier-simple-ui-20260910/results-live.sqlite3-wal` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | Transient sidecar of removed duplicate database; WAL empty; `out/tier-simple-ui-20260910/results-final.sqlite3` |
| `tier-simple-ui-20260910/before-retries/results-live.sqlite3` | 917504 | `21db2b9100b96b5ca5635e9844b58f45e71daa63ed7c04f02a81853c93cfe0a8` | Byte-identical redundant copy; `out/tier-simple-ui-20260910/before-retries/results-final.sqlite3` |
| `tier-simple-ui-20260910/before-retries/results-live.sqlite3-shm` | 32768 | `fd4c9fda9cd3f9ae7c962b0ddf37232294d55580e1aa165aa06129b8549389eb` | Transient sidecar of removed duplicate database; WAL empty; `out/tier-simple-ui-20260910/before-retries/results-final.sqlite3` |
| `tier-simple-ui-20260910/before-retries/results-live.sqlite3-wal` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | Transient sidecar of removed duplicate database; WAL empty; `out/tier-simple-ui-20260910/before-retries/results-final.sqlite3` |
| `tier-simple-ui-20260910/before-retries/config-source.json` | 92289 | `0d027fe8286ee9dc41ed7ac578bb88a1a7c26e28048468eb72e115ec3dbf5df1` | Byte-identical redundant copy; `out/tier-simple-ui-20260910/config-source.json` |
| `tier-simple-ui-20260910/before-retries/preview.png` | 34715 | `1450b468c68d26ad9cc2b5979e60b7672f2e7a99ab1352d3888582bc07d532a3` | Byte-identical redundant copy; `out/tier-simple-ui-20260910/preview.png` |
| `tier-simple-ui-20260910/before-retries/resumed.png` | 29135 | `26f32d0cc74a468cb09fa9f575fa9e96ca19b9a8ab98f160536acfdcc91f4f8b` | Byte-identical redundant copy; `out/tier-simple-ui-20260910/resumed.png` |
| `tier-simple-ui-20260910/before-retries/running.png` | 29240 | `287783fa9d3e2f343d369a1ec89c6d36f55416dc7e4b5163ab5e309423c5c446` | Byte-identical redundant copy; `out/tier-simple-ui-20260910/running.png` |
| `tier-simple-ui-20260910/before-retries/export_metrics.py` | 2231 | `49c6ae980f1a44bf1c9fe2c0946e7de2ce5fba690109bc655fd83e5b1e8b4d06` | Byte-identical redundant copy; `out/tier-simple-ui-20260910/export_metrics.py` |

## Post-cleanup verification

All 35 selected files are absent. 1219 retained files match their pre-cleanup
SHA-256. The export helper has its documented two-line change; the active ngrok
process appended to its own log, with the original log prefix byte-identical.
The original results database and final 106-attempt database are unchanged.
The automatic approval review rejected permanent bulk deletion with only
`blocked by policy`; the accepted, safer operation used the Windows Recycle Bin.
No permanent deletion or hosted data cleanup was performed.
