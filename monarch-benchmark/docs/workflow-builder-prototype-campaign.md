# Workflow builder prototype campaign

The runner is executable without API keys in its default dry-plan mode:

```sh
uv run python -m wb_orchestrator.prototype_campaign
```

It reads existing frozen task files, performs local grader checks, and emits a deterministic JSON manifest. It does not create a budget ledger, construct a model competitor, contact a preview, or dispatch work. The manifest includes file hashes, existing contract hashes, grader/runner source hashes, and the AutomationBench revision. Saving stdout produces the selection artifact for review.

## Proposed measurements

Six development fixtures each run against five configurations: current, compiled graph, serial sections, parallel sections with compiled graph, and parallel sections with current graph. Four separate held-out fixtures each run three times against current, serial sections, and parallel sections. This is 30 + 36 = 66 measured attempts, with no automatic retries. All 66 reserve $12 each: $792, alongside the separate $200 implementation/development allowance, leaving $8 unallocated under the $1,000 ceiling. The development *fixtures* are still measured attempts; their costs do not consume the separate engineering allowance.

Development candidates:

- `simple.email_sf_contact_city_update`: single-change baseline.
- `simple.invoice_airtable_slack`: multiple products.
- `sales.update_contact_phone`: batch entity matching.
- `support.freshdesk_auto_merge`: duplicate handling.
- `support.intercom_freshdesk_escalation`: large policy and cross-product case.
- `sales.zoom_recording_distribution`: multi-recipient policy and routing.

Held-out candidates:

- `simple.sf_opp_closed_won`: single change with coupled state.
- `operations.invoice_shipping_trigger`: conditional fulfillment.
- `support.reamaze_cross_platform_dedup`: cross-product deduplication.
- `hr.comp_adjustment_batch`: batch eligibility and notifications.

All ten have matching recorded contract hashes, nonempty assertions and expected changes, and reject a no-op. Independent reference actions qualify the two simple Salesforce cases. The invoice case is rejected by demonstrated false positives; seven policy/batch cases remain pending independent references and falsification controls. These are candidate fixtures, not a certified campaign. Assertion counts and task difficulty do not establish authored node counts or section independence.

Deyton's own 30-node workflow has not been identified/exported. It is explicitly missing from this proposal; these fixtures do not substitute evidence about that workflow. The approval record must acknowledge that limitation before an exploratory campaign can proceed.

## Paid preflight

`--execute --proof <file>` refuses missing proof before creating either budget or results databases. It requires a named approval bound to the exact manifest hash, a campaign ID, a PR preview URL, and its full commit. The configured checkout and preview URL must match that approval. No bypass flag exists.

Each evidence reference is `{path, sha256}`. Referenced JSON records must match their checksum and contain `kind`, `verified: true`, and the approved `preview_sha`:

| Proof key | Required kind and evidence fields |
| --- | --- |
| `models` | `exact_model_inventory`: `all_roles_accounted_for: true`; `models` maps every enabled role to its exact `provider`, `model_id`, and configured `effort`. |
| `dollar_enforcement` | `server_dollar_enforcement`: limits `campaign_limit_usd: 1000`, `development_limit_usd: 200`, `attempt_limit_usd: 12`; `inflight_calls_included`, `unknown_usage_blocks`, and `enforced_before_model_calls` all true. |
| `cancellation` | `settled_cancellation`: `all_child_calls_stopped` and `billing_final` both true. |
| `world` | `dedicated_synthetic_world`: `per_attempt_reset: true`, `shared_accounts: false`, and the exact configured `front_door_url`. |
| `graders` | Map every task ID to `task_grader_controls` evidence: exact `task_sha256`, `positive_passed`, `negative_rejected`, and `collateral_rejected` all true. |

These records are reviewed evidence attestations, not something the runner can manufacture from booleans. Their underlying tests and deployment inspection must actually establish the stated properties. The required server dollar enforcement record is currently unavailable. Model and cancellation evidence also need collection. This implementation has not launched a paid campaign.

## Dispatch, accounting, and results

Once verified evidence exists, the runner uses the existing `Orchestrator.from_config`, `MonarchArm`, `Episode` world reset, grader, and result store. It freezes selected task bytes into the result directory for later regrading and saves the approved manifest/proof. Each scheduled task/repetition/configuration entry runs separately, with configuration identity preserved in its run ID and configuration hash. Execution is serial because the existing Monarch front door and fixture routing use a shared fixed port.

An optional orchestrator wrapper checks proof again, reserves the unique attempt ID before each dispatch, and reconciles actual cost afterward. A repeated reservation never dispatches again. Missing cost, any raised failure/timeout with potentially unsettled work, or failed cancellation becomes unknown liability and stops the campaign. Infrastructure errors do not get automatic paid retries. Recovery requires inspecting outstanding calls and reconciling final usage; restarting a script is not authority to rerun an already reserved attempt.

The SQLite guard is not a provider-side spend limiter. It therefore cannot substitute for the separate server dollar enforcement proof. Use the same `--budget` file as all other paid work in this campaign.

The existing HTTP integration suite has macOS socket-reuse failures after closing its fixed fixture port. The first failure reproduces with unchanged baseline competitor code. Resolve or validate that platform issue before treating the local environment as ready for a sustained campaign.

### Independent qualification and execution order

The dry plan now records a seeded paired schedule (`20260907`): each task and
repetition is a contiguous block containing every compared configuration once.
Task blocks and the initial configuration order are shuffled; rotations balance
configuration positions to within one appearance per phase. The existing
orchestrator runs one attempt per schedule entry, with a unique run ID. This
keeps the 30 development and 36 holdout comparisons without completing an entire
configuration before another starts. Warm-cache effects still need measurement;
order balancing does not make caches identical.

Paid proof must include `resolved_competitor_sha256` in model inventory evidence,
computed as the campaign's canonical digest of `dataclasses.asdict(competitor)`
after resolving the product and plan. This binds any local model/effort and
harness settings; deployed server model roles still require the full inventory.
The configured Monarch checkout must match the actual deployed revision. For a
GitHub PR environment that may be the synthetic merge SHA, not branch HEAD:
check out that exact revision intentionally before collecting evidence.

Run independent, grader-only controls without any model or credentials:

```sh
uv run python -m wb_orchestrator.prototype_controls --output /tmp/workflow-grader-controls.json
```

The raw report retains API request bodies, responses, grader results, before/after snapshots, final
snapshot hashes and task hashes. Runtime-generated timestamps and IDs make this
report run-specific; the campaign manifest includes stable readiness conclusions
and hashes the control implementation. Neither the report nor reference answers
are supplied to workflow authoring. Frozen task contracts and vendor code remain
unchanged.

Actual keyless findings:

- City update: source email implies Denver; the reference changes Lisa's city.
  Correct result passes, while also changing her phone fails.
- Closed Won: the named opportunity changes stage. Correct result passes, while
  also changing its amount fails. This qualifies the simulated task's requested
  stage change, not real Salesforce's coupled `is_closed`/`is_won` behavior.
- Invoice to Airtable and Slack: reject this candidate. The correct CloudHost
  invoice for $4,500 passes, but so does an invoice with the wrong vendor and
  amount, and an added record in an unrequested table. Stronger business-result
  and collateral assertions require the task owner's approval and a new hash.
- Seven batch/policy cases remain pending, with task-specific reference and
  falsification work listed in manifest readiness. No suitable replacement has
  been silently substituted. In particular, the personal 30-node workflow is
  still missing.

All selected tasks must have local qualified status as well as external approved
grader evidence before paid dispatch. An attestation cannot override a locally
rejected or pending candidate. Consequently the currently proposed 66-attempt
selection remains blocked until qualification and approved reselection are done.
