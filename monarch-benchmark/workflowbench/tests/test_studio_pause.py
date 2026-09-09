"""Offline acceptance for task-boundary run controls; no provider dispatch."""
import threading
from copy import deepcopy
import pytest
from wb_studio.app import ROOT, Studio, Orchestrator
from wb_world.episode import load_suite

@pytest.fixture
def studio(tmp_path, monkeypatch):
    monkeypatch.setenv('STUDIO_EXECUTION_MODE', 'local')
    def forbidden(*args, **kwargs):
        pytest.fail('Paid dispatch forbidden')
    return Studio(tmp_path, tasks=load_suite(ROOT/'tasks')[:1], gateway_factory=forbidden)

@pytest.mark.parametrize('action', ['resume', 'cancel'])
def test_pause_drains_current_task_then_resume_or_cancel_without_replay(studio, monkeypatch, action):
    entered, release, drained, second = (threading.Event() for _ in range(4))
    original = Orchestrator._run_episode
    calls = []
    def episode(self, identity, arm, task, repetition):
        calls.append(arm.name)
        if len(calls) == 1:
            entered.set()
            assert release.wait(5)
        else:
            second.set()
        return original(self, identity, arm, task, repetition)
    monkeypatch.setattr(Orchestrator, '_run_episode', episode)
    end = studio.end_attempt
    def finished(identity):
        end(identity)
        drained.set()
    monkeypatch.setattr(studio, 'end_attempt', finished)
    job = studio.create({'models':['oracle','sloppy'], 'tasks':list(studio.tasks), 'concurrency':1}, start=False)
    thread = threading.Thread(target=studio.execute, args=(job['id'],))
    thread.start()
    try:
        assert entered.wait(5)
        paused = studio.pause(job['id'])
        assert paused['pause_requested'] and paused['active_attempts'] == 1
        release.set()
        assert drained.wait(5)
        assert not second.wait(.2), 'A new task began while paused'
        saved = studio.job(job['id'])
        assert saved['pause_requested'] and saved['active_attempts'] == 0
        assert saved['completed'] == 1 and len(saved['results']) == 1
        first = deepcopy(saved['results'][0])
        getattr(studio, action)(job['id'])
        thread.join(5)
        assert not thread.is_alive()
        result = studio.job(job['id'])
        assert result['results'][0] == first
        assert result['status'] == ('completed' if action == 'resume' else 'cancelled')
        assert result['completed'] == (2 if action == 'resume' else 1)
        assert calls == (['oracle','sloppy'] if action == 'resume' else ['oracle'])
        assert studio.runtime.active_agents == 0
    finally:
        release.set()
        studio.cancelled[job['id']].set()
        thread.join(5)


def test_queued_pause_survives_restart_and_can_cancel_without_execution(studio):
    job = studio.create({'models':['oracle'], 'tasks':list(studio.tasks)}, start=False)
    studio.pause(job['id'])
    studio.execute(job['id'])
    assert not (studio.directory/job['id']/'execution.claimed').exists()
    restored = Studio(studio.directory, tasks=list(studio.tasks.values()), gateway_factory=studio.gateway_factory)
    assert restored.job(job['id'])['pause_requested'] is True
    assert restored.cancel(job['id'])['status'] == 'cancelled'
    assert restored.job(job['id'])['results'] == []


def test_stale_progress_cannot_undo_pause_or_resume(studio):
    job = studio.create({'models':['oracle'], 'tasks':list(studio.tasks)}, start=False)
    studio.pause(job['id'])
    studio.save(job)
    assert studio.job(job['id'])['pause_requested'] is True
    # Keep this test synchronous: emulate a claimed worker that waits on the gate.
    (studio.directory/job['id']/'execution.claimed').touch()
    stale = deepcopy(job)
    studio.resume(job['id'])
    studio.save(stale)
    assert studio.job(job['id'])['pause_requested'] is False


@pytest.mark.parametrize('status', ['completed','failed','cancelled','interrupted'])
def test_ended_runs_reject_pause_and_resume_without_mutation(studio, status):
    job = studio.create({'models':['oracle'], 'tasks':list(studio.tasks)}, start=False)
    job['status'] = status
    studio.save(job)
    for action in ('pause','resume'):
        with pytest.raises(ValueError): getattr(studio, action)(job['id'])
    assert studio.job(job['id']) == job
