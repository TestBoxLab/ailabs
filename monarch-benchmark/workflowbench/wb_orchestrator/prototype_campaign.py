"""Keyless campaign planning; paid dispatch requires separately supplied proof."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import random
import shutil
import subprocess
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path

from grader.grade import grade
from wb_orchestrator.prototype_controls import qualify
from wb_arms.api_loop import InfraError
from wb_orchestrator.campaign_budget import CampaignBudget, BudgetBlocked
from wb_world.episode import Episode, contract_hash, load_task_file

ROOT = Path(__file__).resolve().parents[1]
CONFIGURATIONS = ['current', 'compiled', 'sections-serial', 'sections-parallel', 'sections-parallel-current']
SELECTION = {
    'development': [
        ('tasks/simple.email_sf_contact_city_update.json', 'single change baseline'),
        ('tasks/tier-medium/simple.invoice_airtable_slack.json', 'multiple products'),
        ('tasks/tier-simple/sales.update_contact_phone.json', 'batch entity matching'),
        ('tasks/tier-medium/support.freshdesk_auto_merge.json', 'duplicate handling'),
        ('tasks/tier-complex/support.intercom_freshdesk_escalation.json', 'large policy and cross-product case'),
        ('tasks/tier-complex/sales.zoom_recording_distribution.json', 'multi-recipient policy and routing'),
    ],
    'holdout': [
        ('tasks/simple.sf_opp_closed_won.json', 'single change with coupled state'),
        ('tasks/tier-medium/operations.invoice_shipping_trigger.json', 'conditional fulfillment'),
        ('tasks/random-10/support.reamaze_cross_platform_dedup.json', 'cross-product deduplication'),
        ('tasks/tier-medium/hr.comp_adjustment_batch.json', 'batch eligibility and notifications'),
    ],
}


class PreflightError(RuntimeError):
    pass


def durable_section_usage_complete(turn_log: list[dict]) -> bool:
    pages = [record['authoring_events'] for record in turn_log
             if isinstance(record, dict) and isinstance(record.get('authoring_events'), dict)]
    if not pages or pages[-1].get('complete') is not True:
        return False
    pending, call_ids = Counter(), set()
    for page in pages:
        events = page.get('events')
        if not isinstance(events, list):
            return False
        for event in events:
            if not isinstance(event, dict):
                return False
            data = event.get('data')
            if data is None:
                continue
            if not isinstance(data, dict) or data.get('truncated') is True:
                return False
            kind = data.get('kind')
            if kind not in ('section_authoring', 'section_model_usage'):
                continue
            if kind == 'section_authoring' and data.get('phase') in ('merge', 'validate', 'build'):
                continue
            key = (data.get('buildAttempt'), data.get('phase'),
                   data.get('sectionId'), data.get('attempt'))
            valid_key = (type(key[0]) is int and key[0] > 0
                         and key[1] in ('plan', 'author')
                         and (key[1] == 'plan' and key[2] is None
                              or key[1] == 'author' and isinstance(key[2], str) and bool(key[2]))
                         and type(key[3]) is int and key[3] >= 0)
            if not valid_key:
                return False
            if kind == 'section_authoring':
                if data.get('status') != 'started':
                    continue
                # A clarification resume can reuse the same per-turn build key.
                pending[key] += 1
                continue
            call_id = data.get('callId')
            if (not isinstance(call_id, str) or not call_id or call_id in call_ids
                    or pending[key] == 0 or data.get('usageComplete') is not True
                    or data.get('costKnown') is not True):
                return False
            call_ids.add(call_id)
            pending[key] -= 1
    return not any(pending.values())


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _control(task, action=None) -> dict:
    episode = Episode(task, episode_id='keyless-readiness')
    if action:
        action.run(episode)
    final = episode.finish()
    return {**grade(task, episode.snapshot0, final), 'snapshot_sha256': digest(final)}


def paired_schedule(tasks, phases, seed=20260907):
    rng = random.Random(seed)
    order = []
    for phase in phases:
        blocks = [(task['id'], repetition) for task in tasks if task['split'] == phase['name']
                  for repetition in range(1, phase['repetitions'] + 1)]
        rng.shuffle(blocks)
        arms = list(phase['configurations'])
        rng.shuffle(arms)
        for block, (task_id, repetition) in enumerate(blocks):
            rotated = arms[block % len(arms):] + arms[:block % len(arms)]
            for position, setting in enumerate(rotated):
                order.append({'phase': phase['name'], 'task_id': task_id, 'repetition': repetition,
                              'configuration': setting, 'position': position})
    return order


def build_manifest(root: Path = ROOT) -> dict:
    tasks = []
    for split, selection in SELECTION.items():
        for relative, purpose in selection:
            path = root / relative
            task = load_task_file(path)
            info = task.get('info', {})
            readiness = {
                'assertions': len(info.get('assertions', [])),
                'expected_changes': len(info.get('expected_changes', [])),
                'source_contract_matches': task.get('contract_sha256') in (None, contract_hash(task)),
                'negative_control': 'not_checked',
                'positive_control': 'not_checked',
                'collateral_control': 'not_checked',
            }
            try:
                readiness['negative_control'] = 'accepted' if _control(task)['passed'] else 'rejected'
                readiness.update({key: value for key, value in qualify(task).items() if key != 'evidence'})
            except Exception as error:
                readiness['error'] = f'{type(error).__name__}: {error}'
            tasks.append({
                'id': task['task'], 'path': relative, 'split': split, 'purpose': purpose,
                'file_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'contract_hash': contract_hash(task), 'readiness': readiness,
            })
    phases = [
        {'name': 'development', 'configurations': CONFIGURATIONS, 'tasks': 6, 'repetitions': 1, 'attempts': 30},
        {'name': 'holdout', 'configurations': ['current', 'sections-serial', 'sections-parallel'], 'tasks': 4, 'repetitions': 3, 'attempts': 36},
    ]
    sources = ['grader/grade.py', 'grader/invariant.py', 'wb_world/episode.py',
               'runner/arms.py', 'wb_orchestrator/prototype_controls.py', 'wb_orchestrator/prototype_campaign.py',
               'wb_orchestrator/campaign_budget.py', 'wb_orchestrator/orchestrator.py',
               'wb_orchestrator/config.py', 'wb_arms/monarch.py', 'wb_arms/monarch_client.py']
    source_hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources}
    try:
        vendor_revision = subprocess.check_output(['git', '-C', str(ROOT / 'vendor/automation-bench'), 'rev-parse', 'HEAD'], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        vendor_revision = None
    manifest = {
        'source_sha256': source_hashes, 'automationbench_revision': vendor_revision,
        'version': 1, 'tasks': tasks, 'phases': phases, 'attempts': 66,
        'schedule_seed': 20260907, 'schedule': paired_schedule(tasks, phases),
        'reservation_estimate_usd': 792, 'development_allowance_usd': 200,
        'maximum_combined_allocation_usd': 992, 'campaign_limit_usd': 1000,
        'attempt_limit_usd': 12, 'automatic_retries': 0, 'missing': ['personal_30_node_workflow'],
        'qualification': 'Candidate fixtures, not evidence of 30-node authoring or representative pilot coverage. Readiness records distinguish qualified, rejected, and pending independent controls; all must qualify before paid dispatch.',
        'paid_prerequisites': ['approved_manifest', 'exact_model_inventory', 'server_dollar_enforcement',
                               'settled_cancellation', 'dedicated_world', 'per_task_grader_evidence'],
    }
    manifest['manifest_sha256'] = digest(manifest)
    return manifest


def _evidence(proof_path: Path, reference: dict, kind: str, preview_sha: str) -> dict:
    if not isinstance(reference, dict) or not reference.get('path') or not reference.get('sha256'):
        raise PreflightError(f'Missing {kind} evidence reference')
    path = proof_path.parent / reference['path']
    try:
        raw = path.read_bytes()
        record = json.loads(raw)
    except (OSError, ValueError) as error:
        raise PreflightError(f'Cannot read {kind} evidence') from error
    if not isinstance(record, dict):
        raise PreflightError(f'{kind} evidence must be an object')
    if hashlib.sha256(raw).hexdigest() != reference['sha256']:
        raise PreflightError(f'{kind} evidence hash differs')
    if record.get('kind') != kind or record.get('verified') is not True or record.get('preview_sha') != preview_sha:
        raise PreflightError(f'{kind} evidence is not verified against this preview')
    return record


def validate_preflight(path: str | Path | None, manifest: dict) -> dict:
    if path is None:
        raise PreflightError('Paid preflight proof is required; dollar enforcement is currently unverified')
    path = Path(path)
    try:
        proof = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise PreflightError('Cannot read paid preflight proof') from error
    if not isinstance(proof, dict):
        raise PreflightError('Paid preflight proof must be an object')
    if proof.get('manifest_sha256') != manifest['manifest_sha256']:
        raise PreflightError('Approved manifest differs from the current task/configuration manifest')
    if not manifest.get('automationbench_revision'):
        raise PreflightError('The AutomationBench source revision must be established')
    if not proof.get('approved_by') or not re.fullmatch(r'[A-Za-z0-9._-]+', proof.get('campaign_id', '')):
        raise PreflightError('Named campaign approval is required')
    if not re.fullmatch(r'https://pr-[0-9]+\.monarch-dev\.testbox\.com', proof.get('preview_url', '')):
        raise PreflightError('A dedicated Monarch PR preview URL is required')
    sha = proof.get('preview_sha', '')
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise PreflightError('An exact preview commit is required')
    if proof.get('personal_30_node_workflow_not_included') is not True:
        raise PreflightError('Approval must acknowledge the missing personal 30-node workflow')
    model = _evidence(path, proof.get('models'), 'exact_model_inventory', sha)
    models = model.get('models')
    if model.get('all_roles_accounted_for') is not True or not isinstance(models, dict) or not models:
        raise PreflightError('A complete configured model inventory is required')
    for role, configured in models.items():
        if (not role or not isinstance(configured, dict) or not configured.get('model_id')
                or not configured.get('provider') or 'effort' not in configured):
            raise PreflightError('Every model role must name exact provider, model, and effort')
    dollars = _evidence(path, proof.get('dollar_enforcement'), 'server_dollar_enforcement', sha)
    if not (dollars.get('campaign_limit_usd') == 1000 and dollars.get('development_limit_usd') == 200
            and dollars.get('attempt_limit_usd') == 12 and dollars.get('inflight_calls_included') is True
            and dollars.get('unknown_usage_blocks') is True and dollars.get('enforced_before_model_calls') is True):
        raise PreflightError('Server dollar enforcement is not established')
    cancel = _evidence(path, proof.get('cancellation'), 'settled_cancellation', sha)
    if cancel.get('all_child_calls_stopped') is not True or cancel.get('billing_final') is not True:
        raise PreflightError('Cancellation must settle all child calls and final billing')
    world = _evidence(path, proof.get('world'), 'dedicated_synthetic_world', sha)
    if world.get('per_attempt_reset') is not True or world.get('shared_accounts') is not False:
        raise PreflightError('A dedicated resettable world is required')
    for task in manifest['tasks']:
        if task['readiness'].get('status') != 'qualified':
            raise PreflightError(f"Local independent grader controls are not qualified: {task['id']}")
        if not task['readiness']['source_contract_matches'] or not task['readiness']['assertions'] or not task['readiness']['expected_changes']:
            raise PreflightError(f"Task source/approval contract is not ready: {task['id']}")
        review = _evidence(path, (proof.get('graders') or {}).get(task['id']), 'task_grader_controls', sha)
        if (review.get('task_sha256') != task['file_sha256'] or review.get('positive_passed') is not True
                or review.get('negative_rejected') is not True or review.get('collateral_rejected') is not True):
            raise PreflightError(f"Grader controls are not verified: {task['id']}")
    return proof


class BudgetedCompetitor:
    def __init__(self, inner, budget: CampaignBudget, *, authorize, stop):
        self.inner, self.budget, self.authorize, self.stop = inner, budget, authorize, stop
        self.name, self.provider_key = inner.name, inner.provider_key
        self.model_label = getattr(inner, 'model_label', None)

    def prepare(self):
        self.authorize()
        if hasattr(self.inner, 'prepare'):
            self.inner.prepare()

    def run(self, episode, deadline=None):
        try:
            self.authorize()
            reservation = self.budget.reserve(episode.episode_id, 'measured')
            if not reservation.created:
                raise BudgetBlocked('Attempt already reserved; inspect its prior state before recovery')
        except (BudgetBlocked, PreflightError) as error:
            self.stop()
            if isinstance(error, PreflightError):
                raise
            raise InfraError('infra:harness_crash', str(error), retryable=False) from error
        try:
            result = self.inner.run(episode, deadline=deadline)
        except BaseException as error:
            self.budget.reconcile(episode.episode_id, None)
            self.stop()
            if isinstance(error, InfraError):
                error.retryable = False
            raise
        unknown = ('cost_missing' in result.flags or result.termination == 'timeout'
                   or not durable_section_usage_complete(result.turn_log)
                   or any('execution_cancel_error' in record
                          or 'authoring_cancel_error' in record
                          for record in result.turn_log))
        try:
            self.budget.reconcile(episode.episode_id, None if unknown else result.cost_usd)
        except BaseException:
            self.budget.reconcile(episode.episode_id, None)
            self.stop()
            raise
        if unknown or self.budget.snapshot()['overruns']:
            self.stop()
        return result


def execute(manifest: dict, proof_path: Path, *, product: Path, plan: Path, budget_path: Path, output: Path):
    proof = validate_preflight(proof_path, manifest)
    from wb_orchestrator import config
    from wb_orchestrator.monarch_setup import expand, public_front_door_url
    from wb_orchestrator.orchestrator import Orchestrator
    from wb_results.store import Store
    base = config.resolve(product, plan)
    monarch = [c for c in base.competitors if c.harness.kind == 'monarch']
    if len(monarch) != 1 or base.plan.mode != 'create-run':
        raise PreflightError('Base plan must contain exactly one create-and-run Monarch competitor')
    competitor = monarch[0]
    if expand(competitor.harness.base_url, os.environ, 'base_url') != proof['preview_url']:
        raise PreflightError('Configured Monarch URL differs from approved preview')
    models = _evidence(proof_path, proof['models'], 'exact_model_inventory', proof['preview_sha'])
    if models.get('resolved_competitor_sha256') != digest(asdict(competitor)):
        raise PreflightError('Model evidence differs from resolved competitor model/effort/harness settings')
    world = _evidence(proof_path, proof['world'], 'dedicated_synthetic_world', proof['preview_sha'])
    if public_front_door_url(competitor.harness, os.environ) != world.get('front_door_url'):
        raise PreflightError('Configured fixture front door differs from isolation evidence')
    repo = config.from_workflowbench(competitor.harness.monarch_repo, base.config_dir)
    try:
        checkout_sha = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise PreflightError('Cannot establish the configured Monarch checkout revision') from error
    if checkout_sha != proof['preview_sha']:
        raise PreflightError('Configured Monarch checkout differs from approved preview commit')
    # Validation and read-only configuration resolution happen before either DB exists.
    budget = CampaignBudget(budget_path)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'campaign-manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True))
    (output / 'preflight-proof.json').write_text(json.dumps(proof, indent=2, sort_keys=True))
    store = Store(output / 'results.sqlite')
    def authorize():
        refreshed = build_manifest()
        if refreshed['manifest_sha256'] != manifest['manifest_sha256']:
            raise PreflightError('Task files changed after campaign approval')
        if validate_preflight(proof_path, refreshed) != proof:
            raise PreflightError('Paid proof changed during the campaign')
        if subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip() != proof['preview_sha']:
            raise PreflightError('Configured Monarch checkout changed during the campaign')
    try:
        frozen_tasks = {}
        frozen_dir = (output / 'tasks').resolve()
        frozen_dir.mkdir(parents=True, exist_ok=True)
        for task in manifest['tasks']:
            destination = frozen_dir / Path(task['path']).name
            shutil.copyfile(ROOT / task['path'], destination)
            frozen_tasks[task['id']] = load_task_file(destination)
        for index, entry in enumerate(manifest['schedule']):
            setting = entry['configuration']
            configured = replace(competitor, harness=replace(competitor.harness, builder_experiment=setting))
            run_plan = replace(base.plan, name=f"prototype-{index:03d}-{setting}", tasks=str(frozen_dir), repetitions=1,
                               retry_on_fail=0, concurrency=1, timeout_s=1200,
                               approved_by=proof['approved_by'], cost_ceiling_usd=1000)
            run_config = replace(base, plan=run_plan, competitors=[configured], tasks=[frozen_tasks[entry['task_id']]], tasks_dir=str(frozen_dir),
                                 harnesses={configured.harness.name: configured.harness}, excluded_tasks={})
            orchestrator = Orchestrator.from_config(store, run_config, output)
            orchestrator.arm_wrapper = lambda inner: BudgetedCompetitor(inner, budget, authorize=authorize, stop=orchestrator._abort.set)
            orchestrator.run(f"{proof['campaign_id']}-{index:03d}-{entry['phase']}-{setting}")
            if orchestrator._abort.is_set():
                raise PreflightError('Campaign stopped after an unsettled or over-budget attempt')
    finally:
        store.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-plan', action='store_true', help='Emit a keyless plan without budget mutations (default)')
    mode.add_argument('--execute', action='store_true', help='Requires verified paid preflight proof')
    parser.add_argument('--proof', type=Path)
    parser.add_argument('--budget', type=Path, default=Path('prototype-campaign-budget.sqlite'))
    parser.add_argument('--output', type=Path, default=Path('prototype-campaign-results'))
    parser.add_argument('--product', type=Path, default=ROOT / 'config/products/simulated-apps.yaml')
    parser.add_argument('--plan', type=Path, default=ROOT / 'config/plans/pilot-monarch-single.yaml')
    args = parser.parse_args(argv)
    manifest = build_manifest()
    if not args.execute:
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0
    execute(manifest, args.proof, product=args.product, plan=args.plan, budget_path=args.budget, output=args.output)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except PreflightError as error:
        raise SystemExit(f'Paid campaign blocked: {error}') from error
