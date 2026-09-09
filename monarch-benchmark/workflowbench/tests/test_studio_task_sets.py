"""Task-set offers must not substitute changed catalog tasks into frozen sets."""
from copy import deepcopy
from collections import Counter
import json
from types import SimpleNamespace
from wb_studio.app import ROOT
from wb_studio.task_sets import task_sets
from wb_world.episode import load_suite


def test_frozen_set_is_excluded_if_any_catalog_task_changed(tmp_path):
    task=deepcopy(load_suite(ROOT/'tasks')[0])
    directory=tmp_path/'tasks'/'saved';directory.mkdir(parents=True)
    (directory/'task.json').write_text(json.dumps(task),encoding='utf8')
    studio=SimpleNamespace(tasks={task['task']:deepcopy(task)})
    offered=task_sets(studio,tmp_path)['items']
    assert offered[0]['tasks']==[task['task']]
    studio.tasks[task['task']]['prompt'][0]['content']+=' Changed requirements.'
    assert task_sets(studio,tmp_path)['items']==[]
    assert json.loads((directory/'task.json').read_text())==task


def test_balanced_sample_is_unique_repeatable_and_spans_categories(tmp_path):
    (tmp_path/'tasks').mkdir()
    tasks={f'{category}.{i:03d}':{'category':category} for category in ('finance','sales','support') for i in range(30)}
    first=task_sets(SimpleNamespace(tasks=tasks),tmp_path)['items'][0]
    reverse=task_sets(SimpleNamespace(tasks=dict(reversed(list(tasks.items())))),tmp_path)['items'][0]
    assert first==reverse
    assert len(first['tasks'])==len(set(first['tasks']))==50
    counts=Counter(i.split('.')[0] for i in first['tasks'])
    assert counts=={'finance':17,'sales':17,'support':16}
    assert set(first['tasks'])<=tasks.keys()


def test_small_catalog_does_not_claim_a_fifty_task_sample(tmp_path):
    (tmp_path/'tasks').mkdir()
    assert task_sets(SimpleNamespace(tasks={'one':{}}),tmp_path)['items']==[]
