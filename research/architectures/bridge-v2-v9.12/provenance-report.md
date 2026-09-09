# BRIDGE v2 + v9.12 provenance inventory

Generated 2026-09-08T10:45:01.754349+00:00. Identity `bridge-v2-v9.12`. Readiness: source `source_required`, runtime `source_required`.

Report claims (361/600 vs 289/600) are transcribed, not recomputed. Regeneration without the original manifest hash is a reconstructed candidate, never a reproduction.

| Role | Status | Layout | Hash |
|---|---|---|---|
| graph_producer | present | `<project-root>/scripts/vendor-monarch-graph-inline-v6.ts` | 571d294c90f5, c0e4768e2376 |
| source_freshness_audit | present | `<project-root>/scripts/audit-monarch-source-freshness.py` | 2cb280ae493a, 30613fe33232 |
| actor_contract | missing | `<project-root>/.automationbench-local/suite-package-7a08b5047c89/actor/actor-contract.json` | — |
| reviewed_tasks_358 | present | `Monarch_Main/AutomationBench-repair/adjudication/microscopic-brittleness-358-v1.json` | 2477849feb19, 2477849feb19 |
| capability_manifest | present | `Monarch_Main/ATLAS/backend/data/bench/bridge-v8/zapier-wired273-4a8e106-manifest-v1/capability-manifest-v1.json` | 0574deafe9e3 |
| reviewed_catalog | present | `Monarch_Main/ATLAS/backend/config/bridge-v8-zapier-hard50-reviewed-capabilities-enriched-4a8e106-v2.json` | 7aea3d995c26 |
| source_provenance | missing | `<project-root>/config/monarch/source-provenance-evalrepair10.json` | — |
| generated_graph | missing | `<project-root>/config/monarch/graph-inline-v6-evalrepair10.json` | — |
| capability_runtime | present | `Monarch_Main/ATLAS/backend/scripts/dev/automationbench-capability-runtime.ts` | e60e836c41b2 |
| shim_doctrine | present | `Monarch_Main/ATLAS/backend/scripts/dev/automationbench-shim.ts` | 460b52f997f2 |
| extension_source_slack | present_unpinned | `Monarch_Main/AutomationBench-repair/automationbench/tools/zapier/slack/users.py` | f2128217a471 (matches repair revisions: none of the candidates) |
| extension_source_quickbooks | present_unpinned | `Monarch_Main/AutomationBench-repair/automationbench/tools/zapier/quickbooks/deposits.py` | 5ab471c87f37 (matches repair revisions: 00a4fad, 24588c2, 41b0a84, 5a0dea3, d18dce7, f7acf6a) |
| extension_source_recruitee | present_unpinned | `Monarch_Main/AutomationBench-repair/automationbench/tools/zapier/recruitee/actions.py` | 67bf28f410b8 (matches repair revisions: none of the candidates) |
| run_manifests_600 | missing | `unknown: per-run manifests naming graph, prompts, grader and provider settings by hash` | — |
| report | present | `Monarch_Main/Monarch_Report.html` | 7d48f013de65 |
| bridge_v2_diagram | present | `Monarch_Main/MONARCH_BRIDGE_V2_DIAGRAM.html` | de9de2f59b42 |
| attempts_catalog | present | `Monarch_Main/docs/bridge/AUTOMATIONBENCH_ATTEMPTS_CATALOG.md` | ed868a5978ce |
| smoke12_rehearsal | present | `Monarch_Main/bench-host-state/runs/evalrepair10-smoke12-v1/rehearsal/result.json (zero-provider rehearsal, not scored evidence)` | acdce2b8c5cb |
| suite_revision_evalrepair10 | present | `{monarch_main}/AB-5a0dea3-clean@5a0dea3:pyproject.toml` | 751f2566b894 |

Summary: {'present': 12, 'present_unpinned': 3, 'missing': 4}

Missing components required for regeneration or reproduction: actor_contract, source_provenance, generated_graph, run_manifests_600

## Recovered settings

- identity: bridge-v2-v9.12
- name: Product graph enrichment — BRIDGE v2 + v9.12
- model: claude-opus-5
- effort: medium
- provider: anthropic
- graph_artifact: config/monarch/graph-inline-v6-evalrepair10.json
- suite_revision: 1.0.6+evalrepair.10
- report_claim: 361/600 with Monarch v9.12 (Opus 5, medium) versus 289/600 bare (Opus 5, max); unverified
- schema: monarch-graph-inline-v6-evalrepair10.v1
- implementation_revision: atlas-monarch-v8-1-p0-runtime-record-opus5-graph-inline-v6-evalrepair10-port-v2
- historical_treatment: atlas-monarch-v8-1-p0-runtime-record-opus5-graph-inline-v6
- doctrine_constant: AUTOMATIONBENCH_OPUS5_GRAPH_INLINE_V6_DOCTRINE (ATLAS/backend/scripts/dev/automationbench-shim.ts)
- reviewed_extensions: ['slack_find_user_by_id', 'quickbooks_create_bank_deposit', 'recruitee_jobCreate']
- source_freshness_rule: unchanged actions reuse reviewed v6 cards; changed/added actions receive current source-pinned descriptions; product contexts of changed origins are replaced
- runtime_behaviours_not_in_graph: ['operator contract per model family', 'declared work list', 'write gates', 'reconciliation', 'pre-run retrieval delivery']

## Frozen suite revision

The producer names suite `1.0.6+evalrepair.10`; `AB-5a0dea3-clean` at 5a0dea3 carries that version string. The repair checkout advanced to evalrepair.17, so its working files cannot stand in for the frozen revision. Extension-source hashes are listed per candidate commit before the evalrepair.11 cut (2026-08-15 19:14) so the exact producer-time revision can be settled by matching the original artifact's recorded hashes.

- 5a0dea3: slack=9d3e3fb17805, quickbooks=5ab471c87f37, recruitee=fd9b0e7e5963
- f7acf6a: slack=9d3e3fb17805, quickbooks=5ab471c87f37, recruitee=fd9b0e7e5963
- 00a4fad: slack=9d3e3fb17805, quickbooks=5ab471c87f37, recruitee=fd9b0e7e5963
- 41b0a84: slack=9d3e3fb17805, quickbooks=5ab471c87f37, recruitee=fd9b0e7e5963
- 24588c2: slack=9d3e3fb17805, quickbooks=5ab471c87f37, recruitee=fd9b0e7e5963
- d18dce7: slack=9d3e3fb17805, quickbooks=5ab471c87f37, recruitee=fd9b0e7e5963

## Next recovery steps

1. Locate the producer's project root (a sibling of ATLAS with `.automationbench-local/suite-package-7a08b5047c89` and `config/monarch/`) in backups or deleted worktrees.
2. Recover `graph-inline-v6-evalrepair10.json` and its `artifactSha256`; recover the 600-task run manifests the report refers to.
3. Only then regenerate with the producer against the frozen revision and compare hashes.
