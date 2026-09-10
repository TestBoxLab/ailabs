"""A small explicit workflow artifact runtime for experimental workflow builders.

The builder authors a JSON DAG, which is validated and durably recorded before
any workflow action. It is deliberately distinct from Monarch's recipe runtime.
"""
import json
import re
import time
from wb_arms.api_loop import ArmResult
from wb_world.episode import EvidenceWriteError

WORKFLOW_GUIDE = '''Author a workflow as JSON, not prose. Return {"steps":[{"id":"lookup","tool":"api_fetch","arguments":{"method":"GET","url":"..."},"after":[]}]}. Tools: api_search, api_fetch, base64_encode. Each step has a unique id, arguments object and after list of preceding step IDs. Use {"$ref":"lookup.records.0.id"} as an argument value to read a previous JSON result, and include lookup in after. You may inspect catalog and GET records while building; writes occur only when the saved workflow executes. Do not wrap the JSON in commentary.'''


def parse_workflow(text):
    raw = re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip())
    plan = json.loads(raw)
    if not isinstance(plan, dict) or set(plan) != {'steps'} or not isinstance(plan['steps'], list) or not 1 <= len(plan['steps']) <= 100:
        raise ValueError('Return a workflow with 1–100 steps')
    ids, pending = set(), {}
    for step in plan['steps']:
        if not isinstance(step, dict) or set(step) - {'id', 'tool', 'arguments', 'after'}:
            raise ValueError('Invalid workflow step')
        identity = step.get('id')
        if not isinstance(identity, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', identity) or identity in ids:
            raise ValueError('Workflow step IDs must be unique')
        if step.get('tool') not in ('api_search', 'api_fetch', 'base64_encode') or not isinstance(step.get('arguments'), dict):
            raise ValueError('Each workflow step needs a supported tool and arguments')
        dependencies = step.get('after', [])
        if not isinstance(dependencies, list) or any(not isinstance(d, str) for d in dependencies) or len(set(dependencies)) != len(dependencies):
            raise ValueError('Workflow dependencies must be unique step IDs')
        ids.add(identity)
        pending[identity] = set(dependencies)
    if any(not deps <= ids or identity in deps for identity, deps in pending.items()):
        raise ValueError('Workflow dependencies must name other steps')
    order = []
    while pending:
        ready = [identity for identity, deps in pending.items() if deps <= set(order)]
        if not ready:
            raise ValueError('Workflow contains a circular dependency')
        order.extend(ready)
        for identity in ready:del pending[identity]
    return plan, order


def resolve_arguments(value, outputs, ancestors):
    if isinstance(value, dict):
        if set(value) == {'$ref'}:
            path = value['$ref']
            if not isinstance(path, str):raise ValueError('Workflow references must be strings')
            root, *keys = path.split('.')
            if root not in ancestors or root not in outputs:raise ValueError('Workflow reference is outside its dependencies')
            result = outputs[root]
            for key in keys:
                result = result[int(key)] if isinstance(result, list) and key.isdigit() else result[key]
            return result
        return {k: resolve_arguments(v, outputs, ancestors) for k,v in value.items()}
    if isinstance(value, list):return [resolve_arguments(v, outputs, ancestors) for v in value]
    return value


def discovery_executor(execute):
    def read_only(name, args):
        if name == 'api_fetch' and str(args.get('method', '')).upper() != 'GET':
            return json.dumps({'error': 'Workflow authoring permits reads only. Put writes in the workflow artifact.'})
        return execute(name, args)
    return read_only


def execute_workflow(text, *, execute, emit, record, cancel=None, deadline=None):
    result = ArmResult()
    try:
        plan, order = parse_workflow(text)
        record({'type': 'workflow_artifact', 'workflow': plan, 'order': order, 'format': 'studio-workflow-v1'})
        emit('workflow_recipe', nodes=[{'id':s['id'],'label':s['tool'],'kind':s['tool']} for s in plan['steps']], workflow=plan)
        outputs, ancestry = {}, {}
        by_id = {s['id']:s for s in plan['steps']}
        for identity in order:
            if (cancel and cancel.is_set()) or (deadline and time.monotonic() >= deadline):
                result.termination, result.error = 'timeout', 'Workflow stopped before the next action'
                break
            step = by_id[identity]
            ancestors = set(step.get('after', []))
            for parent in step.get('after', []):ancestors |= ancestry[parent]
            ancestry[identity] = ancestors
            args = resolve_arguments(step['arguments'], outputs, ancestors)
            emit('workflow_step', node='wf:'+identity, label=step['tool'], status='running', arguments=args)
            result.tool_calls += 1
            try:
                raw = execute(step['tool'], args)
            except Exception as exc:
                record({'type':'workflow_action','id':identity,'tool':step['tool'],'arguments':args,'error':type(exc).__name__})
                emit('workflow_step', node='wf:'+identity, label=step['tool'], status='error', output='Tool execution raised '+type(exc).__name__)
                raise
            try:value=json.loads(raw)
            except (TypeError, ValueError):value=raw
            outputs[identity] = value
            failed = isinstance(value, dict) and bool(value.get('error'))
            record({'type':'workflow_action','id':identity,'tool':step['tool'],'arguments':args,'output':value})
            emit('workflow_step', node='wf:'+identity, label=step['tool'], status='error' if failed else 'completed', output=value)
            if failed:
                result.termination, result.error = 'agent_error', 'Workflow action '+identity+' returned an error'
                break
        result.final_text = json.dumps(outputs, ensure_ascii=False)
    except Exception as exc:
        result.termination, result.error = ('infra:harness_crash' if isinstance(exc, EvidenceWriteError) else 'agent_error'), 'Workflow could not execute: '+type(exc).__name__
        emit('attempt_error', message=result.error)
    return result
