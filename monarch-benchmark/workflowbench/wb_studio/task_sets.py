"""Saved task sets are offered only when their frozen tasks match this catalog."""
from wb_world.episode import load_task_file, contract_hash


def task_sets(studio, root):
    items=[]
    for directory in sorted((root/'tasks').iterdir()):
        if not directory.is_dir(): continue
        files=sorted(directory.glob('*.json'))
        if not files: continue
        records=[]
        try:
            for path in files:
                task=load_task_file(path)
                if task['task'] not in studio.tasks or contract_hash(task)!=contract_hash(studio.tasks[task['task']]):
                    break
                records.append(task['task'])
            else:
                if records: items.append({'id':directory.name,'name':directory.name.replace('-',' ').replace('_',' ').capitalize(),'tasks':records})
        except (ValueError, KeyError): continue
    # Deterministic category-balanced sample; the job freezes every selected hash.
    if len(studio.tasks) >= 50:
        from collections import defaultdict
        buckets=defaultdict(list)
        for identity, task in sorted(studio.tasks.items()):
            buckets[task.get('category') or task.get('domain') or identity.split('.')[0]].append(identity)
        selected=[]
        while len(selected)<50:
            for category in sorted(buckets):
                if buckets[category] and len(selected)<50: selected.append(buckets[category].pop(0))
        items.insert(0, {'id':'catalog-50','name':'Balanced sample from current catalog','tasks':selected})
    return {'items':items}
