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

All ten currently have matching recorded contract hashes, nonempty assertions and expected changes, and reject a no-op. The existing scripted answer key passes only the two simple Salesforce cases. The other eight need supported positive controls and collateral checks. The existing sloppy competitor makes no additional change on the closed-won fixture, so that fixture needs an applicable collateral control. Only the city-update fixture currently passes all three local controls. These are candidate fixtures, not a certified campaign. Assertion counts and task difficulty do not establish authored node counts or section independence.

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

Once verified evidence exists, the runner uses the existing `Orchestrator.from_config`, `MonarchArm`, `Episode` world reset, grader, and result store. It freezes selected task bytes into the result directory for later regrading and saves the approved manifest/proof. Each configuration runs separately, with configuration identity preserved in its run ID and configuration hash. Execution is serial because the existing Monarch front door and fixture routing use a shared fixed port.

An optional orchestrator wrapper checks proof again, reserves the unique attempt ID before each dispatch, and reconciles actual cost afterward. A repeated reservation never dispatches again. Missing cost, any raised failure/timeout with potentially unsettled work, or failed cancellation becomes unknown liability and stops the campaign. Infrastructure errors do not get automatic paid retries. Recovery requires inspecting outstanding calls and reconciling final usage; restarting a script is not authority to rerun an already reserved attempt.

The SQLite guard is not a provider-side spend limiter. It therefore cannot substitute for the separate server dollar enforcement proof. Use the same `--budget` file as all other paid work in this campaign.

The existing HTTP integration suite has macOS socket-reuse failures after closing its fixed fixture port. The first failure reproduces with unchanged baseline competitor code. Resolve or validate that platform issue before treating the local environment as ready for a sustained campaign.
