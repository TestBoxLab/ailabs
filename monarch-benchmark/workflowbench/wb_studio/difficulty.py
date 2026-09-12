"""Empirical task difficulty from comparable, non-scripted Studio attempts."""
from collections import defaultdict
from wb_studio.measures import wilson
from wb_world.episode import contract_hash

def difficulty(tasks,jobs):
    counts=defaultdict(lambda:[0,0])
    hashes={key:contract_hash(task) for key,task in tasks.items()}
    for job in jobs:
        for result in job.get('results',[]):
            task=result.get('task');model=result.get('model','')
            if task not in hashes or job.get('task_hashes',{}).get(task)!=hashes[task]:continue
            if model in ('oracle','sloppy') or result.get('termination','').startswith('infra:'):continue
            if type(result.get('passed')) is not bool or 'evidence_incomplete' in result.get('flags',[]):continue
            counts[task][0]+=1
            counts[task][1]+=not result['passed']
    output={}
    for task in tasks:
        n,failed=counts[task]
        if not n:
            output[task]={'level':'unrated','attempts':0,'failures':0,'failure_rate':None,'provisional':True,'description':'No comparable scored attempts yet. Scripted controls and infrastructure failures are excluded.'}
            continue
        rate=failed/n;level='hard' if rate>=2/3 else 'easy' if rate<=1/3 else 'medium'
        low, high = wilson(failed, n)
        output[task]={'level':level,'attempts':n,'failures':failed,'failure_rate':rate,'provisional':n<5,
                      'interval':[low, high],
                      'description':f'{failed} failures in {n} comparable scored attempts. '+('Early signal; fewer than five attempts. ' if n<5 else '')+'Depends on the models and setups tested; repeated attempts are not independent tasks.'}
    return output
