# Feature Specification: Declarative Benchmark Configuration

**Feature Branch**: `001-declarative-benchmark-config`

**Created**: 2026-09-02

**Status**: Draft

**Input**: User description: "Declarative benchmark configuration. Replace the `wb run` CLI flags and the in-code model price table and side-effect list with YAML files a person edits, in four folders (products, models, harnesses, plans). A run = product × plan, chosen by flag or interactively. Validation and cost guards before any spend. Methodology in PLAN.md §1 unchanged."

## Why

Today a benchmark round is described by command-line flags plus three things that
live in code: the model price table, the list of side effects per service, and the
audience allowlist. Carlos, who owns the program, cannot read or change a round
without reading Python. Every input to the fixed methodology should be a file a
person can open, understand, and edit, and the command should be thin.

## Vocabulary

Plain names are used throughout, in files and in this spec:

| Plain name | Meaning | Old internal name |
|---|---|---|
| product | the platform under test and its data | target |
| model | a language model with its provider and prices | provider key |
| harness | how a model is driven: direct tool loop, a coding agent, Monarch, or a scripted check | arm kind |
| competitor | one model + harness pair, or a harness alone | arm |
| plan | which competitors run, on which tasks, how many times, under what limits | flags |
| task set | a folder of prompts with their approval rules | suite |
| repetitions | how many times each competitor attempts each task | k |
| attempt | one task, one competitor, one repetition | episode |
| mode | how much of Monarch is under test: full-flow, create-run, run-only | test mode |

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Launch a round from files (Priority: P1)

Carlos opens a terminal, types `wb run`, and is asked to pick a product and a plan
from numbered lists of the files that exist. He picks `simulated-apps` and
`smoke-frontier`. The command shows the number of attempts and the cost ceiling,
then runs. Passing `--product` and `--plan` skips the questions.

**Why this priority**: This is the feature. Without it nothing else matters.

**Independent Test**: Run `wb run --product simulated-apps --plan smoke-frontier`
against the existing pilot tasks and confirm the same attempts run as in
`smoke-frontier-001`.

**Acceptance Scenarios**:

1. **Given** the four folders contain valid files, **When** the user runs `wb run`
   in a terminal with no flags, **Then** the command lists the products and plans by
   name, accepts a number for each, and starts the run.
2. **Given** the user passes `--product simulated-apps --plan smoke-frontier`,
   **When** the command starts, **Then** no question is asked.
3. **Given** the command runs without a terminal (CI) and a flag is missing,
   **When** it starts, **Then** it stops with an error that lists the available names.
4. **Given** a plan reproducing `smoke-frontier-001` (10 pilot tasks, two
   repetitions, oracle + Claude Opus 4.8 + GPT-5.6 Sol through the direct tool
   loop, 600-second timeout), **When** it runs, **Then** the set of attempts is
   identical to the earlier run.
5. **Given** a run started from files, **When** the user runs `wb resume`,
   `wb status`, `wb grade`, or `wb report` on it, **Then** those commands behave
   exactly as before.

---

### User Story 2 - Describe models and harnesses without code (Priority: P2)

Lucas wants to add DeepSeek driven through Claude Code as a competitor. He adds
`models/deepseek-v4.yaml` with provider, model id, default effort, prices per
million tokens, and the environment variable holding the key. Claude Code is
already described in `harnesses/claude-code.yaml`, including how a foreign
provider is injected. He adds `{model: deepseek-v4, harness: claude-code}` to a
plan. No Python changes.

**Why this priority**: Adding competitors is the most frequent change; today it
requires editing the registry in code.

**Independent Test**: Add a model file and a plan entry; `wb doctor` lists the new
competitor and reaches its provider.

**Acceptance Scenarios**:

1. **Given** a new model file with all required fields, **When** it is referenced
   from a plan, **Then** the run uses its provider, id, effort, and prices, and the
   result rows carry the competitor name `deepseek-v4/claude-code`.
2. **Given** a harness file that lists accepted providers, **When** a plan pairs it
   with a model from a provider it does not accept, **Then** validation fails
   naming the plan file, the competitor entry, and the harness.
3. **Given** the existing registered models (Claude Opus 4.8, GPT-5.6 Sol,
   Kimi K3, GLM 5.3, Gemini 3.7 Flash), **When** the feature ships, **Then** each
   has a model file and the code no longer holds prices.
4. **Given** the existing scripted checks (oracle, sloppy, null), Claude Code
   headless, and Monarch, **When** the feature ships, **Then** each has a harness
   file. Monarch's harness file carries address, credential variable, release, and
   supported modes; it may remain unrunnable until the Monarch competitor exists.

---

### User Story 3 - Describe the product and its data (Priority: P2)

Carlos wants the simulated 47-app set and a future real Salesforce to be two
files in `products/`. Each names the product's kind, its dataset, whether the
benchmark may change the data, which services it exposes, and where the
per-service side-effect list lives. The side-effect list moves out of code into
that file, and `wb corpus declare` reads it from there.

**Why this priority**: The product is the axis that changes least often but
carries the most legal and cost weight; it must be explicit.

**Independent Test**: `wb corpus declare` on the imported corpus using the
side-effect list from the product file produces the same approval rules as today.

**Acceptance Scenarios**:

1. **Given** `products/simulated-apps.yaml` points at the side-effect list,
   **When** `wb corpus declare` runs, **Then** the derived approval rules are
   byte-identical to the ones derived today.
2. **Given** a plan whose task set touches a service the chosen product does not
   list, **When** validation runs, **Then** it fails naming the task, the service,
   and the product file.
3. **Given** a product whose supported modes do not include the plan's mode,
   **When** validation runs, **Then** it fails naming both files.

---

### User Story 4 - Never spend by accident (Priority: P1)

Before any attempt starts, the command validates every file and applies two
guards: a plan above smoke scale (more than 10 tasks × 2 repetitions) must carry
`approved_by`, and a run stops when accumulated spend exceeds the plan's cost
ceiling.

**Why this priority**: Full rounds cost real money and the approval rule is today
only a verbal agreement. Encoding it is the reason Carlos wants files.

**Independent Test**: Run a plan with 11 tasks and no `approved_by`; it refuses
before contacting any provider. Run a plan with a US$ 0.01 ceiling; it stops after
the first paid attempt.

**Acceptance Scenarios**:

1. **Given** any file has an unknown field, an unknown model or harness name, or
   a missing environment variable, **When** the command starts, **Then** it stops
   before contacting any provider with a message naming the file and the field.
2. **Given** the plan exceeds smoke scale and `approved_by` is empty, **When** the
   command starts, **Then** it refuses and says who must approve.
3. **Given** accumulated spend passes `cost_ceiling_usd` during a run, **When** the
   next attempt would start, **Then** the run stops, pending attempts are marked
   as not run, and the report shows the stop reason.
4. **Given** a run stopped on the ceiling, **When** the user raises the ceiling in
   the plan and runs `wb resume`, **Then** the run continues; **When** the ceiling
   is unchanged, **Then** `wb resume` refuses and says why.
5. **Given** any referenced file changed since the run started (product, plan,
   model, harness), **When** the user runs `wb resume`, **Then** it refuses as it
   does today for changed flags.

---

### Edge Cases

- The plan references a harness alone (oracle, Monarch): the competitor name is
  the harness name and no model fields are required.
- Two plan entries resolve to the same competitor name: validation fails.
- The same model appears with two harnesses: two competitors, both allowed.
- A plan's `baseline` names a competitor absent from its list: validation fails.
- A folder is empty: the interactive list says so and the command stops.
- Two files share a `name` inside one folder: validation fails.
- A model file names a key variable that is unset: fails at validation, not at
  the first paid call.
- The environment variable holding Monarch's credential is unset while the plan
  uses Monarch: fails at validation.
- A secret value never appears in any hash, log, or report.
- `mode` is set on a plan with no Monarch competitor: allowed; every result row
  records the mode.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The benchmark MUST read its inputs from four folders of YAML files
  under the benchmark's `config/` directory: `products/`, `models/`,
  `harnesses/`, `plans/`. Each file's `name` MUST equal its file name without
  extension.
- **FR-002**: A product file MUST declare: `name`, `kind` (one of `simulated`,
  `real-api-ui`, `real-api`), `data.dataset`, `data.mutable` (true or false),
  `services` (list), `side_effects` (path to the per-service side-effect list),
  and `modes` (list of supported modes).
- **FR-003**: A model file MUST declare: `name`, `provider`, `model` (the
  provider's id), `effort` (default), `usd_per_million` with `input`, `cached`,
  and `output`, and `key_env` (the environment variable holding the key).
- **FR-004**: A harness file MUST declare: `name`, `kind` (one of `api`,
  `cli`, `scripted`, `monarch`), `accepts` (providers, or `none` for harnesses
  without a model), and the kind-specific launch description (command, how the
  model and provider are injected, how output is read). A Monarch harness MUST
  also declare `base_url`, `credential_env`, `release`, and `modes`.
- **FR-005**: A plan file MUST declare: `name`, `tasks` (path to a task set),
  `mode`, `repetitions`, `timeout_s`, `concurrency`, `competitors` (list of
  `{model, harness}` or `{harness}`), `baseline`, `audience`,
  `cost_ceiling_usd`, and `approved_by` (may be empty).
- **FR-006**: `wb run` MUST accept `--product` and `--plan`, each a name or a
  path, and MUST prompt interactively for any missing one when attached to a
  terminal, listing files by name. Without a terminal, a missing choice MUST be
  an error that lists the available names.
- **FR-007**: The flags `--suite`, `--arms`, `--k`, `--timeout`, and
  `--concurrency` MUST be removed from `wb run`.
- **FR-008**: Before contacting any provider, the command MUST validate all
  referenced files and MUST stop on: unknown field; missing required field;
  unknown model or harness name; duplicate `name` within a folder; harness not
  accepting the model's provider; product not supporting the plan's mode; task
  set touching a service the product lacks; `baseline` not in `competitors`;
  duplicate competitor names; missing environment variable. Every error MUST
  name the file and the field.
- **FR-009**: The command MUST refuse to start a plan whose attempts exceed
  smoke scale (10 tasks × 2 repetitions = 20 attempts per competitor) unless
  `approved_by` is non-empty. The refusal MUST state the attempt count.
- **FR-010**: The command MUST stop a run when accumulated spend exceeds
  `cost_ceiling_usd`, mark pending attempts as not run with that reason, and
  record the reason in the run. `wb resume` MUST continue only if the ceiling
  in the plan is now higher than the spend.
- **FR-011**: The run's configuration hash MUST cover the resolved content of
  the product, the plan, and every referenced model and harness file, with
  secret values excluded, so `wb resume` refuses when any of them changed.
- **FR-012**: Competitor names in results MUST be `model/harness`, or the
  harness name alone when there is no model.
- **FR-013**: Prices and provider identity MUST come only from model files;
  the code MUST NOT hold a price table.
- **FR-014**: The side-effect list used by `wb corpus declare` MUST come from
  the path in the product file; the code MUST NOT hold the list.
- **FR-015**: The audience allowlist MUST keep working unchanged; `audience` in
  the plan selects the report audience as `--audience` does today.
- **FR-016**: `wb resume`, `wb status`, `wb grade`, and `wb report` MUST keep
  their current interfaces.
- **FR-017**: The manual CI smoke workflow MUST call `wb run --product
  simulated-apps --plan smoke-frontier`.
- **FR-018**: Files shipped with the feature MUST include: one product
  (`simulated-apps`), one model per model registered today, one harness per
  competitor kind that exists today (`api`, `claude-code`, `oracle`,
  `sloppy`, `null`, `monarch`), and one plan (`smoke-frontier`). Harness files
  for Codex, Gemini CLI, and OpenCode MAY ship as descriptions without a
  runnable launcher, clearly marked.
- **FR-019**: The console output at start MUST state the product, plan, number
  of attempts, and cost ceiling before the first attempt runs.

### Key Entities

- **Product**: the platform under test, its dataset, whether data may change,
  its services, its side-effect list, its supported modes.
- **Model**: a language model at a provider with prices and a key location.
- **Harness**: a way to drive a model (or none): direct tool loop, a coding
  agent, a scripted check, or Monarch.
- **Competitor**: a model + harness pair or a harness alone; named
  `model/harness` or `harness`.
- **Plan**: task set, mode, repetitions, timeout, concurrency, competitors,
  baseline, audience, cost ceiling, approval.
- **Run**: product × plan, with a configuration hash over all resolved files.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A person who has never read the code can start the smoke round by
  answering two numbered prompts.
- **SC-002**: Adding a new model competitor requires editing zero code files.
- **SC-003**: The smoke plan reproduces the attempts of `smoke-frontier-001`
  exactly: same tasks, competitors, repetitions, and timeout.
- **SC-004**: Every invalid configuration in the edge-case list is rejected
  before any provider is contacted, with a message naming file and field.
- **SC-005**: A plan above smoke scale without approval never starts; a run
  never spends more than its ceiling plus one attempt.
- **SC-006**: The approval rules derived from the corpus are byte-identical
  before and after moving the side-effect list into the product file.
- **SC-007**: The existing test suite stays green and gains one test per guard
  and one per validation rule.

## Assumptions

- YAML is the file format, matching the existing `audiences.yaml`.
- The `config/` folder lives beside the benchmark code
  (`monarch-benchmark/workflowbench/config/`).
- Secrets are referenced by environment-variable name only; values live in
  `.env`, which stays gitignored.
- The old run `smoke-frontier-001` need not be resumable from files; "same
  attempts" is the compatibility bar, not the same hash value.
- The Monarch harness file is descriptive until the Monarch competitor is built
  (a separate feature); validation of its fields is in scope, running it is not.
- Codex, Gemini CLI, and OpenCode harness files describe how the harness is
  driven; making them runnable is a separate feature per harness.
- `mode` lives on the plan because every competitor in a mode must see the same
  catalog of actions (PLAN.md §1.1 rule 2); harnesses without stages ignore it.
- Smoke scale is fixed at 10 tasks × 2 repetitions per competitor, per the
  standing rule; changing it is a constitution amendment, not a plan field.
- The methodology in PLAN.md §1 is unchanged; only its inputs move to files.
