"""Durable Genesis research records and approval-bound experiment proposals."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import uuid
from datetime import datetime, timezone
from wb_results.evidence import write_json
from wb_studio.library import Library
from wb_studio.memory import Memory, MemoryFull

STATES = ('research', 'hypothesis', 'approval', 'running', 'review', 'complete')
QUESTIONS = {'source': 'What does this mean for Monarch, and which hypothesis does it support or contradict?',
             'run': 'Why did it fail where it failed, and what should we try next?',
             'hypothesis': 'Is this true on the evidence we have, and what would settle it?'}
ANALYSIS_HEADING = '## Genesis analysis'
def stamp(): return datetime.now(timezone.utc).isoformat()
def digest(value): return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def check_goal(goal):
    """A predeclared goal: the version under test, its parent version, the minimum pass-rate gain, and
    optional cost and reliability limits. Checked before the proposal is saved; frozen with its digest."""
    if not isinstance(goal,dict): raise ValueError('The goal must be an object')
    for key in ('version','parent_version'):
        if not isinstance(goal.get(key),str) or not goal[key]: raise ValueError('The goal names the version under test and its parent version')
    if goal['version']==goal['parent_version']: raise ValueError('The goal compares a version with a different parent version')
    number=lambda v:type(v) in (int,float)
    gain=goal.get('minimum_gain')
    if not number(gain) or not 0<gain<=1: raise ValueError('The goal declares minimum_gain, a pass-rate gain above 0 and up to 1')
    ratio=goal.get('maximum_cost_ratio',1)
    if not number(ratio) or ratio<=0: raise ValueError("The goal's maximum_cost_ratio is a positive number")
    floor=goal.get('minimum_pass_rate',0)
    if not number(floor) or not 0<=floor<=1: raise ValueError("The goal's minimum_pass_rate is between 0 and 1")

def _outcome(colour,label,reason): return {'colour':colour,'label':label,'reason':reason}
def hypothesis_outcome(card, job):
    """Colour of a hypothesis card, derived only from its recorded run, never from a claim.

    white, "Untested": no run was dispatched for the card, or the run has not finished.
    neutral, "Invalid": the run cannot judge the goal: its record is unavailable, it did not finish
      normally, no goal was declared in the proposal before dispatch, the version under test or its
      parent version has no attempts in the run, Bare was not shown alongside, or any attempt of either
      version stopped on an infrastructure failure. An infrastructure failure therefore never yields red.
    green, "Met goal": the run completed with Bare shown; the version under test gained at least
      goal.minimum_gain in pass rate over the parent version; its cost is known and at most
      goal.maximum_cost_ratio (default 1) times the parent's; and its own pass rate reached
      goal.minimum_pass_rate (default 0), the reliability limit.
    red, "Net negative": the run completed and the version under test passed a smaller share of tasks
      than its parent version.
    neutral, "Inconclusive": everything else: a gain below the minimum, a cost unknown or above the
      limit, or a pass rate under the reliability limit.
    """
    from wb_studio.leaderboard import known_cost
    if not card.get('job'): return _outcome('white','Untested','No run has tested this hypothesis.')
    if job is None: return _outcome('neutral','Invalid','The run record is unavailable.')
    status=job.get('status')
    if status in ('queued','running','cancelling'): return _outcome('white','Untested','The run has not finished.')
    if status!='completed': return _outcome('neutral','Invalid','The run did not finish normally ('+str(status)+').')
    goal=(card.get('proposal') or {}).get('goal')
    if not isinstance(goal,dict) or not goal: return _outcome('neutral','Invalid','No goal was declared before the run.')
    rows=job.get('results') or []
    def tally(arm):
        mine=[r for r in rows if r.get('model')==arm or str(r.get('model','')).startswith(arm+'--')]
        costs=[known_cost(r) for r in mine]
        return {'attempts':len(mine),'passed':sum(bool(r.get('passed')) for r in mine),
                'infrastructure':sum(str(r.get('termination','')).startswith('infra:') for r in mine),
                'cost':None if not mine or None in costs else sum(costs)}
    candidate,parent=tally(str(goal.get('version'))),tally(str(goal.get('parent_version')))
    if not candidate['attempts'] or not parent['attempts']: return _outcome('neutral','Invalid','The version under test or its parent version has no attempts in the run.')
    infrastructure=candidate['infrastructure']+parent['infrastructure']
    if infrastructure: return _outcome('neutral','Invalid',str(infrastructure)+' attempt(s) stopped on an infrastructure failure; not a model-quality measurement.')
    if not any(a.get('kind')=='native' and a.get('version')=='without-monarch' for a in job.get('settings',{}).get('arms',[])): return _outcome('neutral','Invalid','Bare was not shown alongside.')
    rate=lambda t:t['passed']/t['attempts']
    gain=rate(candidate)-rate(parent)
    summary=f"Pass rate {rate(candidate):.0%} against {rate(parent):.0%} for the parent version"
    if gain<0: return _outcome('red','Net negative',summary+'.')
    minimum=goal.get('minimum_gain',0)
    if gain<minimum: return _outcome('neutral','Inconclusive',summary+f'; the declared minimum gain is {minimum:.0%}.')
    if candidate['cost'] is None or parent['cost'] is None: return _outcome('neutral','Inconclusive',summary+'; cost is not known for both versions.')
    ratio=goal.get('maximum_cost_ratio',1)
    if candidate['cost']>parent['cost']*ratio: return _outcome('neutral','Inconclusive',summary+f"; cost ${candidate['cost']:.2f} is above {ratio} times the parent's ${parent['cost']:.2f}.")
    floor=goal.get('minimum_pass_rate',0)
    if rate(candidate)<floor: return _outcome('neutral','Inconclusive',summary+f'; under the reliability limit of {floor:.0%}.')
    return _outcome('green','Met goal',summary+f"; cost ${candidate['cost']:.2f} against ${parent['cost']:.2f}; Bare shown.")

# Memory tools the model may use; pin stays with people in the interface. Their errors come back as plain sentences.
MEMORY_ACTIONS={
    'memory_read':lambda m,p:m.read(p.get('card')),
    'memory_add':lambda m,p:m.add(p.get('text'),p.get('record'),p.get('section','Recent')),
    'memory_replace':lambda m,p:m.replace(p.get('old'),p.get('new'),p.get('record')),
    'memory_remove':lambda m,p:m.remove(p.get('old')),
    'note_write':lambda m,p:m.note_write(p.get('card'),p.get('text')),
    'record_search':lambda m,p:m.search(p.get('query'),p.get('limit',10))}

class Genesis:
    def __init__(self, studio):
        self.studio=studio
        self.root=studio.directory/'genesis'
        self.root.mkdir(exist_ok=True)
        self.lock=threading.RLock()
        self.active={}
        self.library=Library(self.root/'library')
        self.memory=Memory(self.root/'memory')
        from wb_studio.genesis_autonomy import Autonomy
        self.autonomy=Autonomy(self.root)
        from wb_studio.genesis_skills import Skills
        self.skills=Skills(self.root/'skills')
        from wb_studio.genesis_watcher import Watcher
        self.watcher=Watcher(studio,self)
        from wb_studio.genesis_config import Config
        self.config=Config(self.root)  # feature 022: the model each step of Genesis's work uses
        from wb_studio.genesis_access import Access
        self.access=Access(self.root)  # feature 022, lane B: people, keys, the envelope
    def recover_interrupted(self):
        """Called only by the single owning web process, never worker constructors."""
        for turn in self.listing('turns'):
            if turn['status']=='running':
                self.event(turn['id'],'failed',message='The server restarted during this turn. Inspect its events before retrying; uncertain charges remain reserved.')
                self.studio.ledger.finish_run('genesis-'+turn['id'])
        for card in self.listing('cards'):
            if card['stage']=='running' and not card.get('job'):
                card.update(stage='review',error='The server restarted during this operation. Inspect retained evidence before proposing a new attempt.')
                write_json(self.path('cards',card['id']),card)

    def path(self, kind, identity):
        if kind not in ('cards','turns','threads') or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',str(identity)): raise ValueError('Unknown Genesis record')
        folder=self.root/kind;folder.mkdir(exist_ok=True)
        return folder/(identity+'.json')
    def read(self, kind, identity): return json.loads(self.path(kind,identity).read_text(encoding='utf8'))
    def listing(self, kind): return sorted([json.loads(p.read_text(encoding='utf8')) for p in (self.root/kind).glob('*.json')],key=lambda r:r.get('created_at',''))
    def state(self):
        from wb_studio.genesis_harness import model_routes
        cards=self.listing('cards')
        from wb_studio import genesis_ranking
        cards=genesis_ranking.with_scores(self,cards)  # feature 022: each card carries its elo and games
        for card in cards:
            job=None
            if card.get('job'):
                try:
                    job=self.studio.job(card['job']);card['run_status']=job['status']
                    if card['stage']=='running' and card['run_status'] not in ('queued','running','cancelling'):
                        card['stage']='review'
                        if card.get('plan') and self.autonomy.read()['cards']=='act':
                            card['question']="The run finished. Read the grader's results with read_run and write the verdict on this card: supported, not supported or inconclusive, every sentence tagged [rec:...], exploratory notes in a separate block."
                            card['work']={'status':'queued','queued_at':stamp()};card['auto']=True
                            self.autonomy.record('debrief',card=card['id'],job=card.get('job'),status=card['run_status'])
                        with self.lock: write_json(self.path('cards',card['id']),card)
                except FileNotFoundError: card['run_status']='unavailable'
            card['outcome']=hypothesis_outcome(card,job)
        analyzed=[]
        for job in self.studio.jobs():
            file=self.studio.directory/job['id']/'analysis.json'
            if file.exists():
                data=json.loads(file.read_text(encoding='utf8'))
                analyzed.append({'run':job['id'],'title':job['title'],'status':data.get('status','completed')})
        analyzed += [{'run':a['run'],'title':a.get('summary') or a['run'],'status':a['status']} for a in [json.loads(p.read_text(encoding='utf8')) for p in (self.root/'analyses').glob('*.json')]]
        routes=model_routes()
        return {'cards':cards,'turns':self.listing('turns')[-30:],'threads':self.threads(),'models':routes,'analyzed':analyzed,'stages':STATES,'watcher':self.watcher.status(),'autonomy':self.autonomy.read(),'config':{**self.config.read(),'effective':self.config.effective(routes)}}
    def card(self,payload):
        with self.lock:
            identity=payload.get('id') or uuid.uuid4().hex
            path=self.path('cards',identity)
            old=self.read('cards',identity) if path.exists() else None
            if old and payload.get('revision')!=old['revision']: raise ValueError('This research card changed. Reload before editing.')
            if old and old.get('job'):
                if payload.get('stage') not in ('review','complete') or payload.get('proposal')!=old.get('proposal'): raise ValueError('A dispatched proposal cannot be edited')
                status=self.studio.job(old['job'])['status']
                if status not in ('completed','failed','cancelled','interrupted') or payload.get('stage') not in ('review','complete') or payload.get('proposal')!=old.get('proposal'):
                    raise ValueError('A dispatched proposal cannot be edited')
                archive=self.root/'card-history'/identity;archive.mkdir(parents=True,exist_ok=True)
                write_json(archive/(str(old['revision'])+'.json'),old)
                record={**old,'stage':payload['stage'],'body':str(payload.get('body',old['body']))[:20000],'revision':old['revision']+1,'updated_at':stamp(),
                        'review':payload.get('review',old.get('review')),'settlement':payload.get('settlement',old.get('settlement')),'hypothesis':payload.get('hypothesis',old.get('hypothesis'))}  # feature 022: a card that ran still takes its review and settlement
                write_json(path,record);return record
            if old and old['stage']=='running': raise ValueError('A dispatched proposal cannot be edited')
            title=str(payload.get('title','')).strip()
            if not title or len(title)>140: raise ValueError('Give the research card a short title')
            stage=payload.get('stage','hypothesis')
            if stage not in STATES or stage=='running': raise ValueError('Choose a research stage; running is set by dispatch')
            proposal=payload.get('proposal')
            if proposal is not None and not isinstance(proposal,dict): raise ValueError('The experiment proposal must be an object')
            if proposal:
                forbidden={'request_id','approved','approval','benchmark'}&set(proposal)
                if forbidden: raise ValueError('Proposal cannot set approval or server-owned identities')
                if proposal.get('goal') is not None: check_goal(proposal['goal'])
            kept=old or {}
            record={'id':identity,'title':title,'body':str(payload.get('body',''))[:20000],
                    'stage':stage,'kind':payload.get('kind',kept.get('kind','hypothesis')),'revision':kept.get('revision',0)+1,
                    'created_at':kept.get('created_at',stamp()),'updated_at':stamp(),
                    'evidence':payload.get('evidence',kept.get('evidence',[])),'parent':payload.get('parent',kept.get('parent')),'proposal':proposal,
                    'proposal_digest':digest(proposal) if proposal else None,'approval':None}
            # Intake and watcher fields; an edit that omits them (the model's save_research) keeps the old values.
            record.update(question=payload.get('question',kept.get('question')),auto=bool(payload.get('auto',kept.get('auto',False))),work=payload.get('work',kept.get('work')),position=payload.get('position',kept.get('position')),
                          plan=payload.get('plan',kept.get('plan')),default=payload.get('default',kept.get('default')),blocks=payload.get('blocks',kept.get('blocks')),answer=payload.get('answer',kept.get('answer')),waiting=payload.get('waiting',kept.get('waiting')),brief=payload.get('brief',kept.get('brief')),
                          hypothesis=payload.get('hypothesis',kept.get('hypothesis')),settlement=payload.get('settlement',kept.get('settlement')),review=payload.get('review',kept.get('review')),
                          patch=payload.get('patch',kept.get('patch')),audience=payload.get('audience',kept.get('audience')))  # feature 022 records, kept whole
            # A queued card is a card the watcher will take: queued and not auto cannot both be true.
            if (record.get('work') or {}).get('status')=='queued' and record.get('kind') not in ('question','brief'): record['auto']=True
            body=record['body'];record['analysis']=payload.get('analysis') or (body.split(ANALYSIS_HEADING,1)[1].strip() if ANALYSIS_HEADING in body else kept.get('analysis'))
            if old:
                archive=self.root/'card-history'/identity;archive.mkdir(parents=True,exist_ok=True)
                write_json(archive/(str(old['revision'])+'.json'),old)
            write_json(path,record)
        if not old: self.autonomy.record('card',card=identity,card_kind=record.get('kind'),stage=record['stage'],title=record['title'][:80],by=payload.get('by'))
        elif old['stage']!=record['stage']: self.autonomy.record('stage',card=identity,before=old['stage'],after=record['stage'],by=payload.get('by'))
        return record
    def intake(self,kind,title,body,evidence,payload=None):
        """A card someone or a trigger dropped for Genesis to work: queued for the watcher, with its question."""
        payload=payload or {}
        auto=payload.get('auto') is not False
        # A card a person does not want worked is filed without a queue entry; queued and not auto cannot both be true.
        return self.card({'kind':kind,'title':title[:140],'body':body,'evidence':evidence,'stage':'research','question':str(payload.get('question') or QUESTIONS[kind]),
                          'auto':auto,'work':{'status':'queued','queued_at':stamp()} if auto else None})
    def drop(self,payload):
        """Classify dropped text: a link becomes a library source, a run id a run card, anything else a hypothesis."""
        from wb_studio.genesis_watcher import fetch_page
        from wb_studio.library import _source_type
        text=str(payload.get('text','')).strip()
        if not text or len(text)>20000: raise ValueError('Drop a link, a run id or a hypothesis up to 20,000 characters')
        if re.fullmatch(r'https?://\S+',text):
            from wb_studio.genesis_ingest import fetch_source
            fetched=fetch_source(text)  # feature 022: the whole text, not 600 characters
            title,abstract=fetched['title'],fetched['note']
            kind=_source_type(text);kind='blog' if kind=='other' else kind
            source=self.library.add({'title':title or text,'url':text,'source_type':kind,'abstract':abstract,'original':fetched['text'] or None})
            return self.intake('source',source['title'],text,[{'kind':'library','id':source['id']}],payload)
        if re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',text):
            try: job=self.studio.job(text)
            except (ValueError,FileNotFoundError,OSError): job=None
            if job: return self.intake('run',str(job.get('title') or text),text,[{'kind':'run','id':text}],payload)
        return self.intake('hypothesis',text.splitlines()[0],text,[],payload)
    def work(self,card):
        """One free-work turn on a dropped card, reserved through chat at the per-card ceiling."""
        from wb_studio.genesis_harness import model_routes
        route=self.config.route_for('reading',routes=model_routes())
        if not route: raise ValueError('No model route is available')
        ids=', '.join(str(e.get('kind',''))+' '+str(e.get('id') or e.get('run') or '') for e in card.get('evidence',[])) or 'none'
        message=('Work this research card without being asked. Card id: '+card['id']+', revision '+str(card['revision'])+', kind: '+str(card.get('kind'))+'.\n'
                 'Title: '+card['title']+'\nQuestion: '+str(card.get('question') or QUESTIONS['hypothesis'])+'\nEvidence ids: '+ids+'\nBody:\n'+card['body'][:8000]+'\n\n'
                 'Do only free work: read records with read_run, record_search when it exists, library_read, search_research for metadata, and the code tools when they exist. '
                 'Answer the question on the evidence. Then write the analysis back to this card with save_research: id "'+card['id']+'", revision '+str(card['revision'])+', stage "review", the same title, '
                 'and body = the original body followed by a "'+ANALYSIS_HEADING+'" section that cites record ids. When a source in the evidence has its full text available, library_analyze it. '
                 'When the evidence supports an experiment, call propose_experiment with a Studio launch payload (tasks, models or architectures, bare_models, maximum_usd, track, optional goal); the Studio computes the plan and its numbers; it launches by itself only at smoke scale within your allowances, otherwise it waits for a person. '
                 'When you need a decision from the lab, call ask_question with one question and a suggested default, then finish the turn; the card resumes when a person answers. '+self.autonomy_words())
        identity=uuid.uuid4().hex
        self.autonomy.record('work',card=card['id'],turn=identity)
        with self.lock:
            card=self.read('cards',card['id'])
            card['work']={'status':'working','turn':identity,'started_at':stamp(),'revision':card['revision']}
            write_json(self.path('cards',card['id']),card)
        try: return self.chat({'id':identity,'message':message,'model':route['id'],'maximum_usd':os.environ.get('STUDIO_GENESIS_CARD_USD','2.00'),'purpose':'Genesis watcher','card':card['id']})
        except Exception as exc:
            with self.lock:
                card=self.read('cards',card['id']);card['work'].update(status='failed',finished_at=stamp(),reason='The turn could not start ('+type(exc).__name__+'): '+str(exc)[:200])
                write_json(self.path('cards',card['id']),card)
            raise
    def finish_card(self,turn):
        """Called when a watcher turn ends: done, or failed with the turn's message."""
        with self.lock:
            try: card=self.read('cards',turn['card'])
            except (ValueError,FileNotFoundError): return
            work=card.get('work') or {}
            if work.get('turn')!=turn['id'] or work.get('status') not in ('working','waiting'): return
            if work.get('status')=='waiting':
                work['finished_at']=stamp();card['work']=work;write_json(self.path('cards',card['id']),card);self.watcher.notify();return
            work.update(status='failed' if turn['status']=='failed' else 'done',finished_at=stamp());work.pop('reason',None)
            if turn['status']=='failed': work['reason']=next((e.get('message') for e in reversed(turn['events']) if e['type']=='failed'),'Genesis could not complete this turn.')
            elif card['revision']==work.get('revision'): work['reason']='Genesis finished without writing an analysis'
            card['work']=work;write_json(self.path('cards',card['id']),card)
        self.watcher.notify()
    def stop_work(self,identity):
        with self.lock:
            card=self.read('cards',identity)
            work=card.get('work') or {}
            if work.get('status') not in ('queued','working'): return card
            work.update(status='stopped',finished_at=stamp());card['work']=work
            write_json(self.path('cards',identity),card)
        process=self.active.get(work.get('turn'))
        if process is not None and process.poll() is None: process.kill()
        return card
    def decline(self,identity,payload):
        """A person declines a plan or a card waiting in Needs you; the card closes with the reason on it."""
        reason=str(payload.get('reason') or '').strip()[:600]
        by=payload.get('by') or 'human:studio'
        with self.lock:
            card=self.read('cards',identity)
            if card.get('job'): raise ValueError('This experiment already ran; write the verdict instead')
            work=card.get('work') or {}
            if work.get('status') in ('queued','working','waiting'): work.update(status='stopped',finished_at=stamp());card['work']=work
            card.update(stage='complete',waiting=None,decision={'outcome':'declined','by':by,'at':stamp(),'reason':reason},revision=card['revision']+1,updated_at=stamp())
            write_json(self.path('cards',identity),card)
        process=self.active.get((card.get('work') or {}).get('turn'))
        if process is not None and process.poll() is None: process.kill()
        self.autonomy.record('declined',card=identity,reason=reason[:200],by=by)
        return card
    def work_now(self,identity):
        """A person asks for a queued card to be worked at once, under the same allowances the watcher applies."""
        card=self.read('cards',identity)
        if (card.get('work') or {}).get('status')!='queued': raise ValueError('Only a queued card can be worked now')
        if self.autonomy.read()['paused']: raise ValueError('Genesis is paused; turn it back on first')
        if self.watcher._cards('working'): raise ValueError('Genesis is already working on a card; it takes this one next')
        reason=self.watcher.refusal()
        if reason: raise ValueError(reason)
        return self.work(card)
    def stop_turn(self,identity):
        """A person stops a running turn; the turn is recorded as failed with the reason."""
        turn=self.read('turns',identity)
        if turn.get('status')!='running': return turn
        process=self.active.get(identity)
        if process is not None and process.poll() is None: process.kill()
        self.event(identity,'failed',message='Stopped by a person')
        return self.read('turns',identity)
    def approve(self,identity,payload):
        with self.lock:
            card=self.read('cards',identity)
            if card.get('job') or card.get('approval'): return card
            if card['stage']!='approval' or not card.get('proposal'): raise ValueError('Submit a concrete experiment proposal for review first')
            if payload.get('revision')!=card['revision'] or payload.get('digest')!=card['proposal_digest']: raise ValueError('The proposal changed. Review its current configuration before approving.')
            operation=card['proposal'].get('operation','run')
            if operation not in ('run','prepare','analyze'): raise ValueError('Unknown proposal operation')
            if operation!='run':
                if operation=='prepare':
                    from wb_studio import product_graphs
                    draft=next((g for g in product_graphs.listing(self.studio) if g['id']==card['proposal'].get('graph')),None)
                    if not draft or draft['revision']!=card['proposal'].get('graph_revision'): raise ValueError('The product graph draft changed. Propose its current revision.')
                card.update(stage='running',approval={'digest':card['proposal_digest'],'at':stamp(),'revision':card['revision']})
                write_json(self.path('cards',identity),card)
                threading.Thread(target=self.execute_preparation,args=(identity,),daemon=True).start()
                return card
            from wb_studio.genesis_plugins import gate_launch
            ok,reason=gate_launch(self,card)  # feature 022: a person's approval waits for the Reviewer too
            if not ok: raise ValueError(reason)
            return self._dispatch(card,by=str(payload.get('by') or 'human:studio'))
    def _dispatch(self,card,by):
        """One path for every launch. Studio validates all frozen versions and reserves the weekly envelope; the request id makes repeated approvals idempotent."""
        identity=card['id']
        request={**card['proposal'],'request_id':'genesis-'+identity+'-'+str(card['revision'])}
        job=self.studio.create(request)
        card.update(stage='running',job=job['id'],waiting=None,approval={'digest':card['proposal_digest'],'at':stamp(),'revision':card['revision'],'by':by})
        write_json(self.path('cards',identity),card)
        self.autonomy.record('launch',card=identity,job=job['id'],by=by,maximum_usd=str(card['proposal'].get('maximum_usd')))
        return card
    def autonomy_words(self):
        a=self.autonomy.read()
        return ('Autonomy now: cards '+a['cards']+', runs '+a['runs']+(', paused' if a['paused'] else '')+'. Smoke scale is at most '+str(a['smoke_attempts'])+' attempts per competitor; your per-card ceiling is $'+str(a['card_usd'])+' and the daily allowance $'+str(a['daily_usd'])+'.')
    def propose_experiment(self,payload):
        """The model's plan. The Studio computes every number; a smoke plan within the allowances launches at once, anything else waits for a person."""
        from wb_studio.genesis_autonomy import plan_lines
        if self.autonomy.read()['runs']=='off': raise ValueError('The Runs dial is off: Genesis may not propose a run today.')
        proposal={k:payload[k] for k in ('title','tasks','models','architectures','bare_models','maximum_usd','track','concurrency','configuration','goal') if k in payload}
        proposal['operation']='run'
        if proposal.get('goal') is not None: check_goal(proposal['goal'])
        plan=plan_lines(self.studio,proposal)
        existing=self.read('cards',payload['card']) if payload.get('card') else None
        if existing and (existing.get('job') or existing['stage']=='running'): raise ValueError('This card already has a run.')
        base={'id':existing['id'],'revision':existing['revision'],'title':existing['title'],'body':existing['body'],'kind':existing.get('kind','hypothesis'),'evidence':existing.get('evidence',[]),'parent':existing.get('parent'),'question':existing.get('question')} if existing else {'title':str(payload.get('title') or 'Experiment')[:140],'body':str(payload.get('body','')),'kind':'hypothesis','evidence':payload.get('evidence',[])}
        record=self.card({**base,'stage':'approval','proposal':proposal,'plan':plan,'auto':False,'by':'genesis'})
        self.autonomy.record('plan',card=record['id'],lines=plan['lines'],maximum_usd=plan['maximum_usd'],attempts=plan['attempts'])
        ok,reason=self.autonomy.may_launch(plan,self.watcher.today_usd(),self.watcher.card_usd,self.watcher.cap_usd)
        if ok:
            from wb_studio.genesis_plugins import gate_launch
            ok,reason=gate_launch(self,self.read('cards',record['id']))  # feature 022: the Reviewer's acceptance, once that chamber exists
        if ok:
            with self.lock:
                launched=self._dispatch(self.read('cards',record['id']),by='genesis:smoke')
            return {'card':launched['id'],'stage':launched['stage'],'job':launched.get('job'),'plan':plan,'launched':True}
        with self.lock:
            record=self.read('cards',record['id']);record['waiting']=reason;write_json(self.path('cards',record['id']),record)
        self.autonomy.record('waiting',card=record['id'],reason=reason)
        return {'card':record['id'],'stage':'approval','plan':plan,'launched':False,'reason':reason}
    def ask_question(self,payload):
        """A free question card in Your review; the card it blocks waits until a person answers."""
        question=str(payload.get('question','')).strip()
        if not question or len(question)>600: raise ValueError('Ask one question of up to 600 characters')
        blocks=payload.get('card')
        default=str(payload.get('default') or '').strip() or None
        q=self.card({'title':question[:140],'body':question,'kind':'question','stage':'approval','question':question,'default':default,'blocks':blocks,'auto':False,'by':'genesis'})
        if blocks:
            with self.lock:
                card=self.read('cards',blocks);work=card.get('work') or {}
                work.update(status='waiting',reason='Waiting for an answer: '+question[:80]);card['work']=work
                write_json(self.path('cards',blocks),card)
        self.autonomy.record('question',card=q['id'],blocks=blocks,question=question[:200],default=default)
        return {'card':q['id'],'blocks':blocks,'status':'asked'}
    def answer_question(self,identity,payload):
        with self.lock:
            q=self.read('cards',identity)
            if q.get('kind')!='question': raise ValueError('Not a question card')
            if q.get('answer'): return q
            answer=str(payload.get('answer') or q.get('default') or '').strip()
            if not answer: raise ValueError('Write an answer or accept the suggested one')
            q.update(answer=answer,stage='complete',revision=q['revision']+1,updated_at=stamp());write_json(self.path('cards',identity),q)
            blocked=q.get('blocks')
            if blocked:
                try: card=self.read('cards',blocked)
                except (ValueError,FileNotFoundError): card=None
                if card:
                    card['body']=(card['body']+'\n\nQuestion: '+q['question']+'\nAnswer from the lab: '+answer)[:20000]
                    card['work']={'status':'queued','queued_at':stamp()};card['auto']=True;card['revision']+=1;card['updated_at']=stamp()
                    write_json(self.path('cards',blocked),card)
        self.autonomy.record('answer',card=identity,blocks=blocked,answer=answer[:200],by=str(payload.get('by') or 'human:studio'))
        self.watcher.notify()
        return q
    def execute_preparation(self,identity):
        card=self.read('cards',identity);p=card['proposal']
        try:
            if p['operation']=='prepare':
                from wb_studio import product_graphs
                result=product_graphs.prepare(self.studio,p['graph'],maximum_usd=str(p['maximum_usd']),revision=p['graph_revision'])
                artifact={'kind':'product_graph','id':result['id'],'version':result['version'],'sha256':result['sha256']}
            else:
                from wb_studio.analysis import review
                result=review(self.studio,p['run'],maximum_usd=p['maximum_usd'])
                artifact={'kind':'analysis','run':p['run'],'status':result.get('status')}
            card.update(stage='review',artifact=artifact)
        except Exception as exc:
            card.update(stage='review',error='Preparation stopped ('+type(exc).__name__+'). Inspect its retained evidence before proposing another attempt.')
        with self.lock: write_json(self.path('cards',identity),card)

    def event(self,identity,kind,**data):
        with self.lock:
            turn=self.read('turns',identity)
            event={'id':len(turn['events'])+1,'type':kind,'at':stamp(),**data}
            turn['events'].append(event)
            if kind in ('completed','failed'): turn['status']=kind
            # The answer is what the model writes in its last response; text written between tool calls stays in the events.
            if kind=='model_started': turn['answer']=''
            if kind=='text_delta': turn['answer']+=data.get('text','')
            write_json(self.path('turns',identity),turn)
        if kind in ('completed','failed'):
            cost=sum((float(e.get('cost_usd') or 0) for e in turn['events'] if e.get('type')=='usage'),0.0)
            self.autonomy.record('turn-'+kind,card=turn.get('card'),turn=identity,cost_usd=round(cost,4),message=(data.get('message') or '')[:200] if kind=='failed' else None)
        if kind in ('completed','failed') and turn.get('card'): self.finish_card(turn)
        if kind in ('completed','failed'):
            from wb_studio.genesis_plugins import on_turn
            on_turn(self,turn)  # feature 022: plugins react to a finished turn; they never fail it
        return event
    def chat(self,payload):
        from wb_studio.genesis_harness import start_turn, model_routes
        text=str(payload.get('message','')).strip()
        limit=220000 if str(payload.get('purpose') or '').startswith('Genesis extraction') else 16000  # a whole source fits an extraction turn
        if not text or len(text)>limit: raise ValueError('Write a message up to '+format(limit,',')+' characters')
        routes=model_routes()
        model=next((r for r in routes if r['id']==payload.get('model')),None) if payload.get('model') else self.config.route_for('chat',routes=routes)
        if not model or not model['available']: raise ValueError('Choose an available Genesis model route')
        from wb_arms import providers
        from wb_studio.gateways import resolve_effort
        provider=providers.get(model['id'])
        effort=payload.get('effort','medium' if provider.adapter!='openai' else 'default')
        effort=resolve_effort(provider,effort) or 'default'
        maximum=str(payload.get('maximum_usd','2'))
        identity=payload.get('id') or uuid.uuid4().hex
        if self.path('turns',identity).exists(): raise ValueError('This turn id is already taken')
        purpose=str(payload.get('purpose') or 'Genesis conversation')
        thread=self.thread_for(payload,text) if purpose=='Genesis conversation' else None
        self.studio.ledger.reserve_run('genesis-'+identity,maximum,metadata={'purpose':purpose,'model':model['id'],'by':'person' if purpose=='Genesis conversation' else 'genesis'})
        turn={'id':identity,'status':'running','model':model['id'],'effort':effort,'message':text,'answer':'','created_at':stamp(),'events':[],'maximum_usd':maximum,'parent':payload.get('parent'),'card':payload.get('card'),'purpose':purpose,'thread':thread['id'] if thread else None,'by':payload.get('by') or 'human:studio'}
        write_json(self.path('turns',identity),turn)
        if thread:
            with self.lock:
                thread=self.read('threads',thread['id']);thread['turns'].append(identity);thread['updated_at']=stamp();write_json(self.path('threads',thread['id']),thread)
        self.autonomy.record('turn',card=payload.get('card'),turn=identity,model=model['id'],purpose=purpose,maximum_usd=str(maximum))
        threading.Thread(target=start_turn,args=(self,turn),daemon=True).start()
        return turn
    # ---- threads: a conversation belongs to a person and keeps its turns in order (feature 022, lane B) ----
    def thread_for(self,payload,text):
        """The thread named in the payload, or a new one titled by the first message."""
        (self.root/'threads').mkdir(exist_ok=True)
        wanted=payload.get('thread')
        if wanted:
            path=self.path('threads',wanted)
            if path.exists(): return self.read('threads',wanted)
        identity=wanted if wanted and re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',str(wanted)) else uuid.uuid4().hex
        thread={'id':identity,'owner':payload.get('by') or 'human:studio','title':(text.splitlines()[0] if text else 'Conversation')[:80],'created_at':stamp(),'updated_at':stamp(),'turns':[],'card':payload.get('card')}
        write_json(self.path('threads',identity),thread)
        return thread
    def threads(self,owner=None):
        """A person's conversations, newest first, with the count of turns."""
        out=[]
        for t in self.listing('threads'):
            if owner and t.get('owner')!=owner: continue
            out.append({**t,'turn_count':len(t.get('turns',[]))})
        return sorted(out,key=lambda t:t.get('updated_at',''),reverse=True)
    def thread(self,identity):
        """One thread with its turns in order."""
        t=self.read('threads',identity)
        turns=[]
        for tid in t.get('turns',[]):
            try: turns.append(self.read('turns',tid))
            except (FileNotFoundError,ValueError): continue
        return {**t,'turns':turns}
    def card_history(self,identity):
        """Every earlier revision of a card, oldest first: revision, stage, title, when."""
        folder=self.root/'card-history'/identity
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',str(identity)) or not folder.exists(): return []
        rows=[]
        for path in sorted(folder.glob('*.json'),key=lambda p:int(p.stem) if p.stem.isdigit() else 0):
            try: old=json.loads(path.read_text(encoding='utf8'))
            except ValueError: continue
            rows.append({'revision':old.get('revision'),'stage':old.get('stage'),'title':old.get('title'),'updated_at':old.get('updated_at'),'work':(old.get('work') or {}).get('status')})
        return rows
    def tool(self,action,payload):
        # Model-facing capabilities intentionally exclude approval and paid launch.
        from wb_studio import blueprints, code_index, product_graphs
        if action=='research_state': return self.state()
        if action=='list_runs': return [{'id':j['id'],'title':j['title'],'status':j['status'],'results':j.get('results',[])} for j in self.studio.jobs()]
        if action=='read_run':
            job=self.studio.job(payload['id'])
            analysis=self.studio.directory/job['id']/'analysis.json'
            events=self.studio.events(job['id'])
            if payload.get('task'): events=[e for e in events if e.get('task')==payload['task']]
            if payload.get('after') is not None: events=[e for e in events if e['id']>int(payload['after'])]
            limit=max(1,min(500,int(payload.get('limit',100))))
            page=events[:limit]
            return {'job':job,'events':page,'next_after':page[-1]['id'] if len(events)>limit else None,'remaining_events':max(0,len(events)-limit), 'analysis':json.loads(analysis.read_text(encoding='utf8')) if analysis.exists() else None,'genesis_analyses':[json.loads(p.read_text(encoding='utf8')) for p in (self.root/'analyses').glob('*.json') if json.loads(p.read_text(encoding='utf8')).get('run')==job['id']]}
        if action=='catalog':
            from wb_studio.task_sets import task_sets
            from wb_studio.app import ROOT
            return {'architectures':blueprints.listing(self.studio),'product_graphs':product_graphs.listing(self.studio),'task_sets':task_sets(self.studio,ROOT),'models':self.studio.models(),'creation_contracts':{
                'save_architecture':{'name':'Name','track':'agentic-request or create-and-run','revision':'0 for new; current revision for edit','graph':{'nodes':[{'id':'input','type':'input','label':'Task input','x':60,'y':100,'config':{}},{'id':'worker','type':'agent','label':'Worker','x':360,'y':100,'config':{'mode':'act or advise','instructions':'Specific methodology','runner':{'provider':'Choose catalog provider','model':'Choose catalog model','effort':'medium'}}},{'id':'output','type':'output','label':'Result Output','x':660,'y':100,'config':{}}],'edges':[{'from':'input','to':'worker'},{'from':'worker','to':'output'}]}},
                'publish_architecture':{'id':'saved draft ID','revision':'saved revision'},
                'save_product_graph':{'name':'Name','revision':'0 or current revision','fields':[{'path':'product.summary','type':'string','description':'What evidence to collect'}],'instructions':'Research instructions','runner':{'provider':'API provider from catalog','model':'Rate-carded model','effort':'medium'}},
                'product_graph_node':{'id':'knowledge','type':'product-graph','label':'Product knowledge','x':360,'y':350,'config':{'graph':'prepared graph ID','version':1}},
                'connections':'Product graphs have no incoming edges and connect only to agents. All processing nodes must reach Result Output. Use output for workflow results; no workflow or Monarch nodes.'},'proposal_operations':{'run':'Studio launch payload','prepare':'operation, graph, graph_revision, maximum_usd','analyze':'operation, run, maximum_usd'}}
        if action=='search_research':
            from urllib.parse import urlencode
            from urllib.request import Request,urlopen
            query=str(payload.get('query','')).strip()
            if not query or len(query)>500: raise ValueError('Provide a short research query')
            req=Request('https://api.crossref.org/works?'+urlencode({'query':query,'rows':8}),headers={'User-Agent':'AILabs-Genesis/1.0 (research discovery)'})
            with urlopen(req,timeout=20) as response: data=json.loads(response.read(2_000_000))
            return [{'title':r.get('title',[]),'url':r.get('URL'),'doi':r.get('DOI'),'published':r.get('published'),'cited_by':r.get('is-referenced-by-count'),'abstract':r.get('abstract'),'note':'Metadata only; not a full-paper review'} for r in data['message']['items']]
        if action=='record_analysis':
            job=self.studio.job(payload['run'])
            key=digest({'run':job['id'],'results':job.get('results',[]),'events':self.studio.events(job['id'])})
            folder=self.root/'analyses';folder.mkdir(exist_ok=True)
            file=folder/(key+'.json')
            with self.lock:
                if file.exists(): return {'reused':True,**json.loads(file.read_text(encoding='utf8'))}
                events={e['id'] for e in self.studio.events(job['id'])}
                findings=payload.get('findings',[])
                if not findings or any(not f.get('event_ids') or not set(f['event_ids'])<=events or f.get('kind') not in ('fact','hypothesis') for f in findings): raise ValueError('Each finding must cite existing events and distinguish fact from hypothesis')
                result={'run':job['id'],'fingerprint':key,'findings':findings,'summary':str(payload.get('summary','')),'created_at':stamp(),'status':'completed','basis':'Genesis interpretation; citations require review'}
                write_json(file,result);return result
        if action=='save_research': return self.card(payload)
        if action=='library_list': return self.library.listing(**{k:payload.get(k) for k in ('published_from','published_to','discovered_from','discovered_to','topic','status')})
        if action=='library_read': return self.library.read(payload['id'])
        if action=='library_save': return self.library.add(payload)
        if action=='library_analyze': return self.library.analyze(payload['id'],payload)
        if action=='library_use': return self.library.use(payload['id'],payload)
        if action=='library_reclassify': return self.library.reclassify(payload['id'],{**payload,'by':'genesis'})
        if action=='propose_experiment': return self.propose_experiment(payload)
        if action=='skill_list': return self.skills.listing()
        if action=='skill_read': return self.skills.read(payload.get('name'))
        if action=='skill_write':
            out=self.skills.write(payload.get('name'),payload.get('text'));self.autonomy.record('skill',name=out['name'],size=out['size'],by='genesis');return out
        if action=='skill_remove':
            out=self.skills.remove(payload.get('name'));self.autonomy.record('skill-removed',name=out['name'],by='genesis');return out
        if action=='ask_question': return self.ask_question(payload)
        if action=='activity': return self.autonomy.tail(int(payload.get('limit',50)),payload.get('card'))
        if action=='record_search':
            from wb_studio import genesis_memory_suite
            try: return genesis_memory_suite.record_search(self,payload)  # feature 022: words and meaning, each hit saying why
            except (ValueError,FileNotFoundError) as exc: return {'error':str(exc)}
        if action in MEMORY_ACTIONS:
            try: return MEMORY_ACTIONS[action](self.memory,payload)
            except (MemoryFull,ValueError,FileNotFoundError) as exc: return {'error':str(exc)}
        if action=='save_architecture': return blueprints.save_draft(self.studio,payload)
        if action=='publish_architecture': return blueprints.publish(self.studio,payload)
        if action=='save_product_graph': return product_graphs.save_draft(self.studio,payload)
        if action in code_index.TOOLS: return code_index.TOOLS[action](self.studio,payload)  # read-only, internal audience
        from wb_studio.genesis_plugins import dispatch
        found,value=dispatch(self,action,payload)  # feature 022: tools added by plugin modules
        if found: return value
        raise ValueError('Genesis cannot perform that action. Experiments require approval in the interface.')
