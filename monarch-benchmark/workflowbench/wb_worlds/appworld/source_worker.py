"""Private source process: no AppWorld imports occur in WorkflowBench's environment."""
import json
from pathlib import Path
import sys


def main(request):
    import appworld
    appworld.update_root(request['root'])
    operation = request['operation']
    if operation == 'version':
        from importlib.metadata import version
        return {'version': version('appworld'), 'code_version': appworld.__version__}
    if operation == 'evaluate':
        from appworld.evaluator import evaluate_task
        return evaluate_task(task_id=request['task_id'], experiment_name=request['experiment'],
                             suppress_errors=True, save_report=False).to_dict(stats_only=False)
    if operation == 'snapshot':
        from appworld.collections.models import ModelCollection
        from appworld.apps import get_all_apps
        models = ModelCollection.load(from_db_home_path=request['dbs'],
            to_db_home_path=':memory:workflowbench-snapshot', load_apps=get_all_apps())
        try:
            result = {}
            for app, classes in models.items():
                result[app] = {name: sorted([row.to_dict() for row in model.all()],
                    key=lambda row: row.get('id', 0))
                    for name, model in classes.items() if name != 'SQLModel'}
            return result
        finally:
            models.close()
    raise ValueError(f'Unknown private AppWorld operation: {operation}')


if __name__ == '__main__':
    print('WORKFLOWBENCH_RESULT=' + json.dumps(main(json.load(sys.stdin)), default=str))

