# Contract — product configuration for an external world

**Feature**: [026-external-benchmark-products](../spec.md) · **Date**: 2026-09-11

Additions to the product file schema in `wb_orchestrator/config.py`. Existing fields keep
their meaning and their validation; `config/products/simulated-apps.yaml` stays valid
byte for byte.

## New fields

| Field | Required | Meaning |
|---|---|---|
| `world` | yes for an external product; defaults to the AutomationBench adapter otherwise | which adapter serves this product's attempts |
| `source` | yes when `world` is external | the source pin |
| `participants` | no | paid parties inside an attempt besides the competitor |

### `source`

```yaml
source:
  benchmark: enterprise-ops-gym     # enterprise-ops-gym | appworld | tau2
  version: "<the installed source's own version string>"
  split: itsm/oracle                # the source's own split, domain or mode
  checker: "SQL verifiers over the final environment state"
  positive_half_is_end_state_only: true
```

`checker` is prose, and it is the phrase the report's comparability sentence uses. It is
written by a person and read by a person.

`positive_half_is_end_state_only` is `false` for τ², whose reward also scores the actions
taken. It drives the extra disclosure sentence, so a τ² pass rate is never read as the
end-state-only pass rate the other products report.

### `participants`

```yaml
participants:
  - role: simulated-user
    model: <a model in config/models/>
    price_table: <the versioned price table>
```

Every field enters the configuration hash by the path every other configuration value
already takes. No new hashing rule.

## Validation rules

The loader refuses, naming the file and the field:

1. `world` that does not resolve in the adapter registry.
2. `source` absent when `world` is external, or present when it is not.
3. `participants[].model` that is not a model file, or `price_table` that is not a price
   table.
4. `services` that do not match the world's own `service_names()`. Checked against
   the adapter, not trusted, because an approval rule addresses a service by name and
   a typo would silently match nothing.
5. A `modes` entry the adapter does not support.

Refusals happen at configuration load, before anything is reserved and before any
container starts.

## The three product files

```yaml
# config/products/enterprise-ops-gym.yaml
name: enterprise-ops-gym
description: >
  Eight enterprise domains from ServiceNow's EnterpriseOps-Gym, served as containers.
  Frontier models reach 37.4 per cent on it, so it discriminates. Apache-2.0.
kind: real-api
world: enterprise-ops-gym
source:
  benchmark: enterprise-ops-gym
  version: "<pinned at import>"
  split: "<domain>/oracle"
  checker: "SQL verifiers over the final environment state, about 5.3 per task"
  positive_half_is_end_state_only: true
data: {dataset: enterpriseops-gym, mutable: true}
services: [calendar, csm, drive, email, hr, itsm, teams]
side_effects: config/side-effects.enterprise-ops-gym.yaml
modes: [create-run]
```

```yaml
# config/products/appworld.yaml
name: appworld
description: >
  Nine everyday apps and 457 interfaces from AppWorld, with about 100 fictitious
  people. Its own checks already look for collateral damage, so its finding and ours
  are recorded side by side. Imported from train and dev, where a reference solution
  exists for the answer key. Content is never committed to this repository.
kind: real-api
world: appworld
source:
  benchmark: appworld
  version: "<pinned at import>"
  split: dev
  checker: "state-based unit tests over before-and-after database state"
  positive_half_is_end_state_only: true
data: {dataset: appworld, mutable: true}
services: [amazon, file_system, gmail, phone, simple_note, splitwise, spotify, todoist, venmo]
side_effects: config/side-effects.appworld.yaml
modes: [create-run]
```

```yaml
# config/products/tau2.yaml
name: tau2
description: >
  Customer-service work from Sierra's tau2-bench, where a model plays the customer.
  Its reward is composite and partly scores the actions taken, not only the state
  reached; every round on it says so. MIT.
kind: real-api
world: tau2
source:
  benchmark: tau2
  version: "<pinned at import; below 1.0.1 is not comparable with later>"
  split: retail
  checker: "the benchmark's own reward, composite and partly path-based"
  positive_half_is_end_state_only: false
data: {dataset: tau2, mutable: true}
services: [users, orders, products]
side_effects: config/side-effects.tau2.yaml
modes: [create-run]
participants:
  - role: simulated-user
    model: <the cheapest keyed route>
    price_table: <current>
```

The `services` lists and the `split` values above are the shape, not the answer: each is
fixed to what the adapter actually dumps when its spike runs
([research.md](../research.md) S1–S3). Validation rule 4 exists precisely so a wrong
guess here fails loudly at load rather than quietly at grading.
