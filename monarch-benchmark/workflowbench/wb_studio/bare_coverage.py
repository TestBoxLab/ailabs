"""Historical native Bare coverage; never a license to reuse unverified evidence."""
from wb_world.episode import contract_hash
from wb_studio.runtime_registry import resolve_api_control

def coverage(studio, payload):
    tasks = payload.get('tasks', [])
    if not isinstance(tasks, list) or any(t not in studio.tasks for t in tasks):
        raise ValueError('Choose catalog tasks')
    rows = []
    for candidate in studio._runner_arms(payload.get('models', [])):
        if candidate['kind'] != 'runner':
            continue
        model = resolve_api_control(candidate['runner'])['key']
        effort = candidate['runner']['effort']
        found = {}
        for job in studio.jobs():
            settings = job['settings']
            if settings.get('track', 'agentic-request') != payload.get('track', 'agentic-request'):
                continue
            if settings.get('configuration', {}).get('prompt'):
                continue
            for arm in settings.get('arms', []):
                manifest = job.get('runner_manifests', {}).get(arm['id'], {})
                if arm.get('kind') != 'native' or arm.get('version') != 'without-monarch':
                    continue
                runner = arm.get('runner', {})
                if runner.get('model') != model or runner.get('effort') != effort:
                    continue
                if not all(manifest.get(k) for k in ('harness_version', 'model_version', 'tools_sha256', 'world_sha256')):
                    continue
                for result in job.get('results', []):
                    task = result.get('task')
                    if task not in tasks or result.get('model') != arm['id']:
                        continue
                    if job.get('task_hashes', {}).get(task) != contract_hash(studio.tasks[task]):
                        continue
                    if result.get('termination') not in ('completed', 'agent_error', 'turn_limit', 'deadline') or type(result.get('passed')) is not bool:
                        continue
                    found[task] = job['id']
        rows.append({'model': candidate['id'], 'completed': len(found), 'missing': [t for t in tasks if t not in found], 'runs': found})
    return {'items': rows, 'reuse': False, 'note': 'Historical matching task/model/thinking records. Automatic reuse requires full current evaluation and harness identity verification.'}
