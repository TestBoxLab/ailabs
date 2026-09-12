# EnterpriseOps-Gym — licence and provenance

**Source**: <https://github.com/ServiceNow/EnterpriseOps-Gym>
**Dataset**: <https://huggingface.co/datasets/ServiceNow-AI/EnterpriseOps-Gym>
**Paper**: arXiv 2603.13594
**Authors**: ServiceNow AI Research, Mila — Quebec AI Institute, Université de Montréal
**Licence**: Apache License 2.0
**Checked**: 11 September 2026

## What we use

The dataset rows — `task_id`, `domain`, `system_prompt`, `user_prompt`,
`selected_tools`, `verifiers`, `gym_servers_config` — and the seed databases the
rows name. The containerized servers serve the world during an attempt.

## What we never modify

Their world, their seeds, their requests and their verifiers. The verifiers are SQL
strings with expected values; we execute them and compare, exactly as shipped. We
do not edit them, re-derive them or filter them. This is the same rule the
repository already lives by for AutomationBench, and for the same reason: a
benchmark whose answer key we have adjusted is no longer that benchmark.

WorkflowBench adds a second half to the verdict — its own approval rule, computed
from its own before-and-after snapshots — and says so in every report. That is an
addition beside their check, never a change to it.

## What is stored here

The two reviewed development task rows are frozen under `tasks/eog-itsm-smoke-2/`
with original prompts and SQL checks, under the source Apache-2.0 licence. Their
copyright and licence attribution remains here; the licence text is preserved in
`LICENSE.enterpriseops`. The importer acquires the larger dataset at its pinned
revision. Source code, bulk seed data and container images remain external runtime
dependencies and are not vendored into this repository.

## Comparability

Our numbers will not match their published numbers. We add a collateral half to the
verdict, our harness differs, and the tool-set mode (`oracle`, `plus_5_tools`,
`plus_10_tools`, `plus_15_tools`) changes the difficulty. Every report on this
product carries a generated sentence saying so.
