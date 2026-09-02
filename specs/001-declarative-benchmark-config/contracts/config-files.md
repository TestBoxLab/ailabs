# Contract: configuration files

These are the files a person edits. Shipped examples are the contract's
executable form; the loader rejects anything not shown here.

## products/simulated-apps.yaml

```yaml
name: simulated-apps
description: The 47 simulated business apps from AutomationBench. No UI. Cents per attempt.
kind: simulated
data:
  dataset: automationbench-47-apps
  mutable: true                 # every attempt starts from a fresh copy
services: [airtable, asana, bamboohr, basecamp3, buffer, calendly, canva, chatgpt, confluence,
           docusign, facebook_conversions, facebook_lead_ads, facebook_pages, freshdesk, gmail,
           google_ads, google_calendar, google_drive, google_sheets, gorgias, helpcrunch, helpscout,
           hiver, hubspot, instagram, intercom, jira, linkedin, linkedin_ads, linkedin_conversions,
           mailchimp, monday, notion, pipefy, quickbooks, reamaze, recruitee, salesforce, slack,
           trello, twilio, twitter, wave, xero, zendesk, zoho_desk, zoom]
side_effects: config/side-effects.yaml
modes: [full-flow, create-run, run-only]
```

## models/claude-opus-4-8.yaml

```yaml
name: claude-opus-4-8
provider: anthropic
model: claude-opus-4-8
effort: xhigh
usd_per_million: {input: 5.00, cached: 0.50, cache_write: 6.25, output: 25.00}
key_env: ANTHROPIC_API_KEY
cache_min_prompt_tokens: 1024
prices_verified: 2026-09-02
description: Monarch's own authoring brain; the baseline competitor.
```

## models/kimi-k3.yaml (OpenAI-compatible endpoint)

```yaml
name: kimi-k3
provider: moonshot
model: kimi-k3
effort: xhigh
usd_per_million: {input: 3.00, cached: 0.30, output: 15.00}
key_env: MOONSHOT_API_KEY
adapter: openai
base_url: https://api.moonshot.ai/v1
cache_min_prompt_tokens: 256
```

## harnesses/api.yaml

```yaml
name: api
kind: api
accepts: [anthropic, openai, google, zai, moonshot, fireworks]
description: The generic three-tool loop. No harness; the model calls tools directly.
```

## harnesses/claude-code.yaml

```yaml
name: claude-code
kind: cli
launcher: claude-code
accepts: [anthropic]              # foreign providers need a gateway; add when tested
command: claude -p
env:
  ANTHROPIC_MODEL: "{model}"
output: json-stream
description: Claude Code headless. API-key billing only.
```

## harnesses/codex.yaml (descriptive)

```yaml
name: codex
kind: cli
launcher: codex
accepts: [openai]
runnable: false
command: codex exec
env: {OPENAI_MODEL: "{model}"}
description: Not runnable yet; describes how the harness would be driven.
```

## harnesses/oracle.yaml

```yaml
name: oracle
kind: scripted
script: oracle
accepts: none
description: The answer key. Applies the expected changes directly; validates the checker.
```

## harnesses/monarch.yaml (descriptive until the Monarch competitor exists)

```yaml
name: monarch
kind: monarch
accepts: none
runnable: false
base_url: ${MONARCH_URL}
credential_env: MONARCH_TOKEN
release: "1.4"
modes: [full-flow, create-run, run-only]
description: The product under comparison. Model team fixed by the release.
```

## plans/smoke-frontier.yaml

```yaml
name: smoke-frontier
description: Small run to test the machine. Reproduces smoke-frontier-001.
tasks: tasks
mode: create-run
repetitions: 2
timeout_s: 600
concurrency: 4
competitors:
  - {harness: oracle}
  - {model: claude-opus-4-8, harness: api}
  - {model: gpt-5.6-sol, harness: api}
baseline: claude-opus-4-8/api
audience: internal
cost_ceiling_usd: 5
approved_by: null
```

## side-effects.yaml

```yaml
- service: gmail
  allowed:
    - {service: gmail, op: "*", path: "gmail.messages[*].is_read"}
    - {service: gmail, op: "*", path: "gmail.messages[*].label_ids"}
    - {service: gmail, op: "*", path: "gmail.threads*"}
- service: salesforce
  when: ".stage_name"
  allowed:
    - {service: salesforce, op: "*", path: "salesforce.opportunities[*].is_closed"}
    - {service: salesforce, op: "*", path: "salesforce.opportunities[*].is_won"}
    - {service: salesforce, op: "*", path: "salesforce.opportunities[*].probability"}
# ... every entry of the old SIDE_EFFECTS constant, in the same order
```

## Error message shape

```
config error in config/plans/smoke-frontier.yaml: competitors[2].model: unknown model 'gpt-6'; known: claude-opus-4-8, gpt-5.6-sol, ...
config error in config/plans/full-round.yaml: approved_by: 400 attempts per competitor exceed smoke scale (20); set approved_by
```
