"""External product identity and evidence survive the real run/report pipeline."""
import copy
import json
from pathlib import Path

import pytest
import yaml

from grader.grade import grade
from wb_orchestrator import config, orchestrator
from wb_results.store import Store
from wb_world.adapter import PositiveResult
from wb_world.episode import Episode, contract_hash, load_task_file, suite_id


def external_task():
    task = load_task_file(Path('tasks/simple.sf_opp_amount_update.json'))
    task = copy.deepcopy(task)
    task['info']['world'] = {'package': 'enterprise-ops-gym', 'version': 'source-123',
                             'revision': 'abc123', 'split': 'itsm/oracle'}
    task['source_ref'] = {'task_id': 'upstream-1', 'verifiers': [{'query': 'SELECT 1'}]}
    task['contract_sha256'] = contract_hash(task)
    return task


def test_external_checker_reference_is_frozen():
    task = external_task()
    before = contract_hash(task)
    task['source_ref']['verifiers'][0]['query'] = 'SELECT 0'
    assert contract_hash(task) != before


def test_external_suites_name_source_and_split_and_refuse_mixing():
    task = external_task()
    assert suite_id([task]) == 'enterprise-ops-gym@source-123/itsm/oracle'
    other = copy.deepcopy(task)
    other['info']['world']['package'] = 'appworld'
    with pytest.raises(ValueError, match='mix.*world|mix.*source'):
        suite_id([task, other])


def product_plan(tmp_path, task):
    folder = tmp_path / 'config'
    (folder / 'products').mkdir(parents=True)
    (folder / 'plans').mkdir()
    (folder / 'harnesses').mkdir()
    (tmp_path / 'tasks').mkdir()
    (tmp_path / 'tasks' / 'sample.json').write_text(json.dumps(task))
    (folder / 'harnesses' / 'null.yaml').write_text(yaml.safe_dump({'name': 'null', 'kind': 'scripted', 'accepts': 'none', 'script': 'null'}))
    product = {'name': 'external', 'kind': 'real-api', 'world': 'enterprise-ops-gym',
               'source': {'benchmark': 'enterprise-ops-gym', 'version': 'source-123',
                          'split': 'itsm/oracle', 'checker': 'SQL verifiers'},
               'data': {'dataset': 'external', 'mutable': True}, 'services': ['gym-itsm-mcp'],
               'side_effects': 'config/side-effects.yaml', 'modes': ['create-run']}
    # External seeds are references, not AutomationBench's embedded world.
    task['info']['initial_state'] = {}
    task['contract_sha256'] = contract_hash(task)
    (tmp_path / 'tasks' / 'sample.json').write_text(json.dumps(task))
    pp = folder / 'products' / 'external.yaml'
    pp.write_text(yaml.safe_dump(product))
    plan = {'name': 'smoke', 'tasks': 'tasks', 'mode': 'create-run', 'repetitions': 1,
            'timeout_s': 30, 'concurrency': 1, 'competitors': [{'harness': 'null'}],
            'baseline': 'null', 'cost_ceiling_usd': 1}
    pl = folder / 'plans' / 'smoke.yaml'
    pl.write_text(yaml.safe_dump(plan))
    return pp, pl


def test_external_resolution_uses_product_pin_not_automationbench(tmp_path):
    pp, pl = product_plan(tmp_path, external_task())
    rc = config.resolve(pp, pl, env={})
    assert rc.product.world == 'enterprise-ops-gym'
    assert len(rc.tasks) == 1


def test_external_resolution_refuses_source_or_content_drift(tmp_path):
    task = external_task()
    pp, pl = product_plan(tmp_path, task)
    path = tmp_path / 'tasks' / 'sample.json'
    task = json.loads(path.read_text())
    task['source_ref']['task_id'] = 'other'
    path.write_text(json.dumps(task))
    with pytest.raises(config.ConfigError, match='hash|drift'):
        config.resolve(pp, pl, env={})
    task['contract_sha256'] = contract_hash(task)
    task['info']['world']['version'] = 'different'
    task['contract_sha256'] = contract_hash(task)
    path.write_text(json.dumps(task))
    with pytest.raises(config.ConfigError, match='source|version'):
        config.resolve(pp, pl, env={})


class ArtifactWorld(Episode):
    closed = []

    def finish(self):
        if self.artifacts_dir:
            (Path(self.artifacts_dir) / 'source-proof.json').write_text('{"checked": true}')
        return super().finish()

    def close(self):
        self.closed.append(self.episode_id)

    @classmethod
    def positive_check(cls, task, snapshot0, snapshot1, artifacts=None):
        proof = json.loads((Path(artifacts) / 'source-proof.json').read_text())
        return PositiveResult(proof['checked'], {'checks': [proof]}, 'stored source check')


def test_run_and_regrade_pass_stored_source_artifacts_and_close_world(tmp_path):
    task = external_task()
    task['info']['expected_changes'] = []
    task['info']['allowed_changes'] = []
    task['contract_sha256'] = contract_hash(task)
    tasks = tmp_path / 'tasks'
    tasks.mkdir()
    (tasks / 'task.json').write_text(json.dumps(task))
    store = Store(tmp_path / 'results.sqlite')
    engine = orchestrator.Orchestrator(store, tasks, ['null'], 1, tmp_path / 'out')
    engine.world = ArtifactWorld
    ArtifactWorld.closed = []
    run = engine.run('external-pipeline')
    row = store.episodes(run=run)['rows'][0]
    evidence = json.loads((Path(row['artifacts_uri']) / 'grading.json').read_text())
    assert evidence['ungraded'] is False
    assert evidence['positive'] == {'checks': [{'checked': True}]}
    assert ArtifactWorld.closed == [row['episode_id']]
    result = orchestrator.regrade(store, run, tasks, world=ArtifactWorld)
    assert result['regraded'] == 1
    assert result['changed'] == 0


def test_external_undeclared_collateral_rule_cannot_accept_changes():
    task = external_task()
    task['info']['expected_changes'] = []
    task['info']['allowed_changes'] = []
    class Checker:
        @classmethod
        def positive_check(cls, *args, **kwargs):
            return PositiveResult(True, {}, 'source')
    result = grade(task, {}, {'app': {'unrequested': 'write'}}, world=Checker)
    assert result['passed'] is False
    assert result['invariant']['unexpected_changes']


def test_ungraded_attempt_is_excluded_and_counted_without_losing_cost():
    from wb_report.metrics import competitor_metrics
    from wb_studio.measures import pass_rate
    rows = [dict(task_id='t', task='t', arm='a', model='a', trial=0, passed=False,
                 termination='completed', flags=['grading=ungraded'], cost_usd=0.2)]
    result = competitor_metrics(rows, 1)
    assert result['strict_pass_denominator'] == 0
    assert result['strict_pass']['mean'] is None
    assert result['ungraded'] == 1
    assert result['infra'] == 0
    assert result['cost_total'] == 0.2
    assert pass_rate(rows)['attempts'] == 0
    assert pass_rate(rows)['ungraded'] == 1


def test_cross_product_pairing_and_studio_grouping_are_separate():
    from wb_stats.stats import paired_wl
    from wb_studio.leaderboard import evaluation_contract
    a = dict(task_id='same', trial=0, passed=True, suite='eog@1')
    b = dict(a, suite='appworld@1')
    with pytest.raises(ValueError, match='products|suites'):
        paired_wl([a], [b])
    job = {'settings': {'tasks': ['same'], 'product': {'name': 'eog'}},
           'task_hashes': {'same': 'same-hash'}}
    other = copy.deepcopy(job)
    other['settings']['product']['name'] = 'appworld'
    assert evaluation_contract(job) != evaluation_contract(other)


def test_external_report_discloses_checker_and_participant_from_frozen_config():
    from wb_world.source import comparison_notes
    product = {'name': 'tau2', 'world': 'tau2', 'source': {'benchmark': 'tau2',
               'version': '1.0.1', 'split': 'retail/base', 'checker': 'original composite reward',
               'positive_half_is_end_state_only': False},
               'participants': [{'role': 'simulated-user', 'model': 'pinned-model'}]}
    text = ' '.join(comparison_notes(product))
    assert all(value in text for value in ('tau2', '1.0.1', 'retail/base', 'original composite reward',
                                           'WorkflowBench', 'pinned-model', 'path'))
    assert 'AutomationBench' not in text


def test_customer_and_competitor_share_one_capped_reservation(tmp_path):
    from wb_orchestrator.budget import BudgetLedger, BudgetExceeded
    from wb_orchestrator.external_runtime import AttemptBudget
    ledger = BudgetLedger(tmp_path / "ledger.sqlite3", weekly_limit_usd="10")
    budget = AttemptBudget(ledger, "attempt-1", "3", participants=[{"role":"simulated-user","model":"customer"}])
    budget.open()
    ledger.reserve("competitor", "2", scope_id=budget.identity, scope_limit_usd="3")
    with pytest.raises(BudgetExceeded):
        ledger.reserve("customer", "1.01", scope_id=budget.identity, scope_limit_usd="3")
    ledger.reserve("customer", "1", scope_id=budget.identity, scope_limit_usd="3")
    assert len(ledger.run_reservations()) == 1
    assert ledger.status().held_usd == 3
    budget.close()
    assert ledger.status().held_usd == 3  # outstanding calls retain their liability


def test_customer_history_conversion_keeps_tool_results():
    from wb_orchestrator.external_runtime import customer_input
    system, items = customer_input([
        {"role":"system","content":"private scenario"},
        {"role":"user","content":"hello"},
        {"role":"assistant","content":None,"tool_calls":[{"id":"c1","type":"function","function":{"name":"check","arguments":"{}"}}]},
        {"role":"tool","tool_call_id":"c1","content":"approved"},
    ])
    assert system == "private scenario"
    assert items == [{"role":"user","content":"hello"},
                     {"type":"function_call","call_id":"c1","name":"check","arguments":"{}"},
                     {"type":"function_call_output","call_id":"c1","output":"approved"}]


def test_external_report_retains_selected_source_verdict_and_independent_halves(tmp_path):
    from wb_report.report import build_report, render_html, render_md
    task = external_task()
    task['info']['expected_changes'] = []
    task['info']['allowed_changes'] = []
    task['contract_sha256'] = contract_hash(task)
    pp, pl = product_plan(tmp_path, task)
    rc = config.resolve(pp, pl, env={})
    store = Store(tmp_path / 'results.sqlite')
    engine = orchestrator.Orchestrator.from_config(store, rc, tmp_path / 'out')
    engine.world = ArtifactWorld
    run = engine.run('source-report')
    orchestrator.regrade(store, run, tmp_path / 'tasks', world=ArtifactWorld)
    report = build_report(store, run)
    selected = next(iter(report['grading_evidence'].values()))
    assert selected['kind'] == 'regrade'
    assert selected['details']['positive'] == {'checks': [{'checked': True}]}
    assert selected['details']['invariant']['passed'] is True
    assert selected['termination'] == 'completed'
    assert selected['passed'] is True
    assert 'Grading evidence' in render_html(report)
    assert 'stored source check' in render_html(report)
    assert '"checked": true' in render_md(report)
    assert 'does not estimate general performance' in ' '.join(report['caveats'])


def test_source_monarch_verification_cannot_reuse_another_org(tmp_path, monkeypatch):
    from dataclasses import replace
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from wb_orchestrator import approvals, monarch_probe
    monkeypatch.setenv('STUDIO_DATA_DIR', str(tmp_path))
    harness = config.load_harness('config/harnesses/monarch-eog.yaml')
    record = {'checked_at': datetime.now(timezone.utc).isoformat(), 'ok': True,
              'backend_host': 'localhost:4174', 'checks': [],
              'harness_sha256': monarch_probe.harness_hash(harness)}
    (tmp_path / 'studio').mkdir()
    Path(monarch_probe.probe_path(tmp_path / 'studio')).write_text(json.dumps(record))
    env = {'MONARCH_URL':'http://localhost:4174'}
    assert approvals.monarch_reason(harness, env) is not None
    site = SimpleNamespace(directory=tmp_path / 'studio', enterprise_harness=harness.name)
    monarch_probe.probe_path(site).write_text(json.dumps(record))
    assert approvals.monarch_reason(harness, env) is None
    other = replace(harness, login_email='different@workflowbench.testbox.com')
    assert 'exact source harness' in approvals.monarch_reason(other, env)


def test_external_maximum_counts_every_infrastructure_retry(tmp_path):
    pp, pl = product_plan(tmp_path, external_task())
    rc = config.resolve(pp, pl, env={})
    assert rc.attempts_per_competitor_min == 1
    assert rc.attempts_per_competitor == 3
    assert rc.config_json['infrastructure_retries'] == 2


def test_appworld_results_cannot_be_written_into_public_repository(tmp_path):
    from dataclasses import replace
    pp, pl = product_plan(tmp_path, external_task())
    rc = config.resolve(pp, pl, env={})
    rc.product = replace(rc.product, world='appworld')
    store = Store(tmp_path / 'private.sqlite')
    with pytest.raises(ValueError, match='outside the public repository'):
        orchestrator.Orchestrator.from_config(store, rc, Path.cwd() / 'out' / 'appworld-refused')
    store.path = Path.cwd() / 'out' / 'appworld-refused.sqlite'
    with pytest.raises(ValueError, match='outside the public repository'):
        orchestrator.Orchestrator.from_config(store, rc, tmp_path / 'private-out')


def test_customer_resolves_the_same_default_transport_as_native_provider(tmp_path):
    pp, pl = product_plan(tmp_path, external_task())
    product = yaml.safe_load(pp.read_text())
    product['participants'] = [{'role':'simulated-user','model':'customer','price_table':'customer'}]
    pp.write_text(yaml.safe_dump(product))
    models = tmp_path / 'config' / 'models'
    models.mkdir()
    (models / 'customer.yaml').write_text(yaml.safe_dump({
        'name':'customer','provider':'openai','model':'customer','effort':'low',
        'usd_per_million':{'input':1,'cached':0.1,'output':2},
        'key_env':'CUSTOMER_KEY','prices_verified':'2026-09-11'}))
    rc = config.resolve(pp, pl, env={'CUSTOMER_KEY':'test'})
    from wb_orchestrator.external_runtime import frozen_provider
    assert frozen_provider(rc.models['customer']).adapter == 'openai_responses'


def test_budget_capability_status_uses_fresh_exact_harness_verification(tmp_path, monkeypatch):
    from datetime import datetime, timezone, timedelta
    from types import SimpleNamespace
    from wb_orchestrator import approvals, monarch_probe
    monkeypatch.setenv('STUDIO_DATA_DIR', str(tmp_path))
    harness = config.load_harness('config/harnesses/monarch-eog.yaml')
    env = {'MONARCH_URL':'http://localhost:4174'}
    assert approvals.capabilities([harness], env)['monarch'] == approvals.MONARCH_REASON
    site = SimpleNamespace(directory=tmp_path / 'studio', enterprise_harness=harness.name)
    site.directory.mkdir()
    record = {'checked_at':datetime.now(timezone.utc).isoformat(), 'ok':True,
              'backend_host':'localhost:4174','checks':[],
              'harness_sha256':monarch_probe.harness_hash(harness)}
    monarch_probe.probe_path(site).write_text(json.dumps(record))
    assert approvals.capabilities([harness], env)['monarch'] is None
    record['checked_at'] = (datetime.now(timezone.utc)-timedelta(hours=3)).isoformat()
    monarch_probe.probe_path(site).write_text(json.dumps(record))
    assert approvals.capabilities([harness], env)['monarch'] == approvals.MONARCH_REASON


def test_a_failure_after_admission_releases_the_round_envelope(tmp_path, monkeypatch):
    """The envelope was closed by `_execute`'s finally alone, so anything raising
    between `_admit` and `_execute` left the round's whole liability held against the
    week with nothing spent.

    A duplicate `--run-id` is enough: `_admit` reserves the envelope, `create_run`
    raises on the unique constraint, and `_execute` is never entered. Nothing can
    release a run envelope afterwards -- `wb budget release` only looks in
    `budget_reservations` -- and the scope never appears in `status.unknown_ids`, so
    the operator cannot even name what is holding the money.
    """
    from types import SimpleNamespace
    from wb_orchestrator.budget import ROUND_ENVELOPE_MARKER, BudgetLedger
    pp, pl = product_plan(tmp_path, external_task())
    rc = config.resolve(pp, pl, env={})
    ledger = BudgetLedger(tmp_path / 'ledger.sqlite3', weekly_limit_usd='100')
    store = Store(tmp_path / 'wb.sqlite3')
    engine = orchestrator.Orchestrator.from_config(store, rc, tmp_path / 'out', ledger=ledger)
    # A paid competitor, so admission opens an envelope at all, and a world that needs
    # no container: this test is about the round's lifecycle, not about either of those.
    paid = SimpleNamespace(name='paid', provider_key='mock', run=lambda ep, deadline=None: None)
    monkeypatch.setattr(engine, '_arms', lambda: [paid])
    monkeypatch.setattr(engine, 'world', SimpleNamespace(prerequisites=lambda: []))

    store.create_run('run-x', engine._hash(), engine.suite, engine._config())
    with pytest.raises(Exception):
        engine.run('run-x')                       # UNIQUE constraint on runs.run_id

    envelopes = [r for r in ledger.run_reservations() if ROUND_ENVELOPE_MARKER in r.scope_id]
    assert envelopes, 'admission should have opened one, or this proves nothing'
    assert all(r.closed_at is not None for r in envelopes), 'the round envelope leaked'
    assert ledger.status().held_usd == 0
