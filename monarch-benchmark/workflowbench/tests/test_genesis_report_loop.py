"""Exercise report stages through Genesis's real loop and ledger, using fake models."""
import json
import re

import pytest
import threading
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

from wb_orchestrator.budget import BudgetLedger
from wb_studio import genesis_harness as harness, genesis_reports as reports
from wb_studio.genesis import Genesis
from tests.test_genesis_reports import lab  # the same frozen evidence fixture


class Immediate:
    def __init__(self, target, args=(), **kwargs): self.target, self.args = target, args
    def start(self): self.target(*self.args)


class ReportAdapter:
    made = []

    def __init__(self, provider, tools, timeout):
        self.tools, self.step, self.results = tools, 0, []
        self.made.append(self)

    def start(self, system, brief, images=None):
        self.system = system
        self.role = 'analysis' if 'Genesis report analysis procedure' in system else 'review' if 'Genesis report review procedure' in system else 'author'
        self.count = int(re.search(r'The report has (\d+) recorded attempts', brief).group(1))
        match = re.search(r'assigned attempt indexes are (\[[\d, ]+\])', brief)
        self.indexes = json.loads(match.group(1)) if match else []
        return [{'role': 'user', 'content': brief}]

    def append_tool_result(self, messages, call, result):
        self.results.append(json.loads(result))
        messages.append({'role': 'tool', 'content': result})

    def turn(self, messages, timeout=None):
        self.step += 1
        calls, answer = [], ''
        if self.step == 1:
            calls = [('report_evidence' if self.role == 'analysis' else 'read_report_digest', {'run': 'run1'}), ('read_report_draft', {'run': 'run1', 'summary_only': True})]
        elif self.step == 2:
            calls = [('read_report_batch', {'run': 'run1'})] if self.role == 'analysis' else [('read_report_draft', {'run': 'run1', 'indexes': [0], 'include_draft': False})]
        elif self.step == 3 and self.role == 'analysis':
            calls = [('record_report_batch', {'run': 'run1', 'batch_sha256': self.results[-1]['batch_sha256'], 'attempts': [{'index': i, 'expected': 'Create the contact.',
                'observed': 'The final check ' + ('passed.' if i else 'failed.'), 'explanation': 'The recorded outcome is explicit.',
                'mechanism': 'The write is present.' if i else 'The write is absent.', 'alternatives': 'Cause requires an intervention.',
                'confidence': 'limited', 'missing_evidence': 'No controlled intervention.', 'event_ids': [i + 1]} for i in self.indexes]})]
        elif self.step == 3 and self.role == 'author':
            calls = [('write_report_draft', {'run': 'run1', 'summary': 'Monarch left the requested contact unwritten.',
                'what_went_right': 'Bare passed the recorded check.', 'what_went_wrong': 'Monarch failed the recorded check.',
                'why': 'The write was missing; the selection decision has not been experimentally isolated.',
                'next_experiment': 'Change only the selection instruction and repeat the task.', 'limitations': 'Only one task was observed.',
                'findings': [{'title': 'Missing write', 'explanation': 'The final check failed.', 'kind': 'fact', 'event_ids': [1]}]})]
        elif self.role == 'review':
            viewed = self.results[0]
            answer = json.dumps({'verdict': 'accept', 'issues': [], 'reason': 'The interpretation preserves the limits of the record.',
                                 'draft_sha256': viewed['draft_sha256'], 'evidence_sha256': viewed['evidence_sha256']})
        else:
            answer = 'The assigned report work was saved.'
        return {'text': answer, 'tool_calls': [{'id': 'call' + str(i), 'name': name, 'args': args} for i, (name, args) in enumerate(calls)],
                'stop_reason': 'stop', 'prompt_tokens': 100, 'cached_tokens': 0, 'cache_write_tokens': 0, 'output_tokens': 20}


@pytest.mark.parametrize('attempt_count', [2, 106])
def test_real_genesis_loop_publishes_with_bounded_receipts_and_restricted_tools(lab, monkeypatch, attempt_count):
    studio = lab.studio
    studio.job.return_value['settings']['maximum_usd'] = '100'
    studio.job.return_value['results'] = [{'task': 't1', 'model': 'bare' if i % 2 else 'monarch', 'passed': bool(i % 2), 'termination': 'completed'} for i in range(attempt_count)]
    studio.events.return_value = [{'id': i + 1, 'task': 't1', 'model': 'bare' if i % 2 else 'monarch', 'type': 'attempt_finished'} for i in range(attempt_count)]
    studio.ledger = BudgetLedger(studio.directory / 'budget.sqlite3')
    studio.jobs = lambda: [studio.job('run1')]
    studio.runtime = SimpleNamespace(provider=lambda *args, **kwargs: nullcontext())
    g = Genesis(studio); studio.genesis = g
    g.allowance_allows = lambda amount: (True, None)
    route = {'id': 'claude-opus-4-8', 'available': True}
    g.config.route_for = lambda step: route
    g.config.effort_for = lambda step, route=None: None
    monkeypatch.setattr(harness, 'model_routes', lambda: [route])
    monkeypatch.setattr(harness, 'ADAPTERS', {'anthropic': ReportAdapter})
    monkeypatch.setattr(harness.providers, 'cost_usd', Mock(return_value=0.001))
    monkeypatch.setattr(threading, 'Thread', Immediate)
    ReportAdapter.made = []
    result = reports.start(g, {'run': 'run1', 'maximum_usd': '40'})
    assert result['stage'] == 'published', result
    assert reports.published(studio, 'run1')['attempts'][0]['model'] == 'monarch'
    batches = (attempt_count + 7) // 8
    assert len(ReportAdapter.made) == batches + 2
    assert [a.role for a in ReportAdapter.made] == ['analysis'] * batches + ['author', 'review']
    assert len(reports.published(studio, 'run1')['attempts']) == attempt_count
    for adapter in ReportAdapter.made:
        names = {t['name'] for t in adapter.tools}
        assert 'propose_experiment' not in names and 'author_report' not in names
    assert 'Editorial standard' in ReportAdapter.made[-2].system
    assert 'Figure and statistical explanation standard' in ReportAdapter.made[-1].system
    receipts = studio.ledger.reservations()
    assert len(receipts) == batches * 4 + 7 and all(r.actual_microusd == 1000 for r in receipts)
    assert studio.ledger.status().held_microusd == 0
