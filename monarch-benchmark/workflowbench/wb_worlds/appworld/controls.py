"""Free, explicit answer-key/null controls through the real orchestration pipeline.

These arms are never native-agent or Monarch measurements. Restricted task answers
and all detailed artifacts stay in APPWORLD_ROOT, outside this public repository.
"""
from __future__ import annotations

import json
from pathlib import Path
import yaml

from wb_arms.api_loop import ArmResult
from wb_orchestrator.config import resolve
from wb_orchestrator.orchestrator import Orchestrator, regrade
from wb_report.report import build_report, write_report
from wb_results.store import Store
from .adapter import AppWorldWorld
from .importer import appworld_root, outside_repository


class _Control:
    provider_key = None

    def __init__(self, reference):
        self.reference = reference
        self.name = 'reference-control' if reference else 'null-control'

    def run(self, episode, deadline=None):
        if self.reference:
            # Deliberately privileged answer-key control. No evaluated agent sees it.
            source = appworld_root() / 'data/tasks' / episode.task_id / 'ground_truth/answer.json'
            answer = json.loads(source.read_text(encoding='utf-8'))
            result = json.loads(episode.api_fetch('POST', '/supervisor/message',
                body=json.dumps({'answer':answer, 'status':'success'})))
            if result.get('error'):
                raise RuntimeError('Published source completion operation failed')
        return ArmResult(tool_calls=len(episode.tool_calls), cost_usd=0)


def run_controls(task_directory, output_directory):
    tasks = outside_repository(task_directory)
    output = outside_repository(output_directory)
    config = output / 'config'
    for folder in ['products', 'plans', 'harnesses']:
        (config / folder).mkdir(parents=True, exist_ok=True)
    for name in ['reference-control', 'null-control']:
        (config / 'harnesses' / f'{name}.yaml').write_text(yaml.safe_dump({
            'name':name, 'kind':'scripted', 'accepts':'none', 'script':'null'}), encoding='utf-8')
    product = {'name':'appworld-control', 'kind':'real-api', 'world':'appworld',
        'source':{'benchmark':'appworld', 'version':'0.1.3.post1', 'split':'dev',
                  'checker':'AppWorld evaluate_task', 'positive_half_is_end_state_only':True},
        'data':{'dataset':'appworld-dev', 'mutable':True}, 'services':AppWorldWorld.service_names(),
        'side_effects':'config/side-effects.yaml', 'modes':['create-run']}
    plan = {'name':'appworld-control', 'tasks':str(tasks), 'mode':'create-run', 'repetitions':1,
        'timeout_s':600, 'concurrency':1, 'competitors':[{'harness':'reference-control'}, {'harness':'null-control'}],
        'baseline':'null-control', 'cost_ceiling_usd':1}
    product_path = config / 'products/appworld-control.yaml'
    plan_path = config / 'plans/appworld-control.yaml'
    product_path.write_text(yaml.safe_dump(product), encoding='utf-8')
    plan_path.write_text(yaml.safe_dump(plan), encoding='utf-8')
    resolved = resolve(product_path, plan_path)
    store = Store(output / 'results.sqlite')
    engine = Orchestrator.from_config(store, resolved, output / 'out')
    engine._arms = lambda:[_Control(True), _Control(False)]
    run_id = engine.run('appworld-free-source-controls-v2')
    rows = store.episodes(run=run_id)['rows']
    assert len(rows) == 4, 'both source tasks must have one reference and one null attempt'
    assert all(row['passed'] == (row['arm'] == 'reference-control') for row in rows)
    assert all(row['termination'] == 'completed' for row in rows)
    assert all(row['cost_usd'] == 0 for row in rows)
    assert all('grading=ungraded' not in row['flags'] for row in rows)
    report = build_report(store, run_id, baseline_arm='null-control')
    assert report['product']['world'] == 'appworld'
    assert any('AppWorld' in note or 'appworld' in note for note in report['caveats'])
    paths = write_report(store, run_id, output / 'reports', tasks_dir=tasks, baseline_arm='null-control')
    repeated = regrade(store, run_id, tasks)
    assert repeated['regraded'] == 4 and repeated['changed'] == 0
    summary = {'run_id':run_id, 'kind':'free source integration controls', 'cost_usd':0,
        'reference_passes':sum(row['passed'] for row in rows if row['arm'] == 'reference-control'),
        'null_passes':sum(row['passed'] for row in rows if row['arm'] == 'null-control'),
        'attempts':len(rows), 'regrade':repeated, 'reports':paths,
        'configuration_sha256':resolved.hash, 'runtime':AppWorldWorld.runtime_identity(),
        'arm_factory_override':'Direct Python software control: _Control injects source answer-key/null arms; not a wb run competitor round.'}
    (output / 'summary.json').write_text(json.dumps(summary,indent=2)+'\n', encoding='utf-8')
    return summary
