"use strict";
// Live view: one block per attempt. Everything on a block comes from recorded
// events; the knowledge pulse and the cursor move only for events observed live.
let observatoryRun=null;
function renderWorkstreams(){
 const root=$('#run-observatory');if(!root||!job)return;
 if(observatoryRun!==job.id){observatoryRun=job.id;root.replaceChildren();}
 if(!root.firstChild)root.innerHTML='<div class="observatory-heading"><h3></h3><span class="observatory-count"></span></div><div class="workstreams"></div>';
 const tasks=job.settings.tasks,pairs=[];for(const task of tasks)for(const model of job.settings.models)pairs.push({task,model,events:events.filter(e=>e.task===task&&e.model===model)});
 const started=pairs.filter(p=>p.events.some(e=>['model_started','step_started','attempt_started','result'].includes(e.type)));
 const active=started.filter(p=>!p.events.some(e=>['attempt_finished','result'].includes(e.type))),complete=started.filter(p=>!active.includes(p));
 const live=['queued','running','pausing','cancelling'].includes(job.status),displayed=[...active,...complete];
 root.querySelector('h3').textContent=runStatus(job)==='paused'?'Paused':live?'Live':'';
 root.querySelector('.observatory-count').textContent=complete.length+' / '+pairs.length+' finished'+(live?' · '+active.length+' active':'');
 const streams=root.querySelector('.workstreams'),keys=new Set(displayed.map(p=>JSON.stringify([p.task,p.model])));
 for(const child of Array.from(streams.children))if(!keys.has(child.dataset.stream))child.remove();
 if(!displayed.length){streams.innerHTML='<p class="board-empty">Waiting for the first task to start.</p>';return;}
 for(const p of displayed){
  const key=JSON.stringify([p.task,p.model]),es=p.events,last=es.at(-1),done=es.findLast(e=>['attempt_finished','result'].includes(e.type));
  let card=Array.from(streams.children).find(c=>c.dataset.stream===key);
  if(!card){
   card=document.createElement('article');card.className='block workstream';card.dataset.stream=key;
   card.innerHTML='<header><span class="stream-model"></span><span class="sep">·</span><span class="stream-task"></span><span class="stream-progress"></span><button class="stream-toggle" type="button" aria-expanded="true" hidden>Collapse</button></header><div class="block-body"><p class="stream-knowledge meta" hidden></p><div class="stream-output" tabindex="0" aria-label="Attempt output"><span class="stream-text"></span><span class="stream-cursor" aria-hidden="true" hidden></span></div><footer><span class="stream-step meta"></span><button class="text-button" type="button">Inspect task</button></footer></div><p class="stream-state" role="status"></p>';
   streams.append(card);
   card.querySelector('.stream-toggle').onclick=()=>{card.dataset.expanded=card.classList.contains('collapsed')?'1':'0';renderObservatory();};
   card.querySelector('footer button').onclick=()=>{const r=job.results.find(x=>x.task===p.task&&x.model===p.model);taskId=p.task;$('#task-select').value=taskId;if(r){selected={node:'result',model:p.model,task:p.task,label:'Task result',category:'result',status:r.passed?'completed':'error',output:r.output,result:r};setOutputMode('trace');revealSelection();}else{renderGraph();$('#flow-description').scrollIntoView({block:'start'});}};
  }
  const signal=es.findLast(e=>e.type==='knowledge_delivered'),modelEvent=es.findLast(e=>e.type==='model_started');
  const deltas=modelEvent?es.filter(e=>e.type==='model_delta'&&e.node===modelEvent.node).map(e=>e.text).join(''):'';
  const finished=es.findLast(e=>e.type==='model_finished'&&e.node===modelEvent?.node),output=done?.output??finished?.output??deltas;
  const step=es.findLast(e=>e.type==='step_started'),status=done?(done.passed?'Passed':'Failed'):!live?'Stopped before completion':last?.type==='node_started'?'Working in the application':output?'Writing the result':'Working on the request';
  const collapsed=!!done&&(card.dataset.expanded==='0'||(!!done.passed&&card.dataset.expanded!=='1'));
  card.classList.toggle('live',!done&&live);card.classList.toggle('collapsed',collapsed);card.classList.toggle('passed',!!done&&!!done.passed);card.classList.toggle('failed',!!done&&!done.passed);
  const toggle=card.querySelector('.stream-toggle');toggle.hidden=!done;toggle.textContent=collapsed?'Expand':'Collapse';toggle.setAttribute('aria-expanded',String(!collapsed));
  const set=(selector,text)=>{const el=card.querySelector(selector);if(el.textContent!==text)el.textContent=text;};
  set('.stream-model',modelName(p.model));set('.stream-task',shortTaskLabel(p.task));set('.stream-progress',(tasks.indexOf(p.task)+1)+' / '+tasks.length);
  const failedChecks=done&&!done.passed?(done.checks||[]).map((c,i)=>c.passed===false?checkName(c.type,p.task,p.model,i):null).filter(Boolean):[];set('.stream-step',failedChecks.length?'Failed: '+failedChecks.join(', '):step?.label?'Step '+step.label:'');set('.stream-state',status);const knowledge=card.querySelector('.stream-knowledge');set('.stream-knowledge',signal?signal.label+' · '+signal.products+' products attached':'');knowledge.hidden=!signal;
  const outputBox=card.querySelector('.stream-output'),follow=outputBox.scrollHeight-outputBox.scrollTop-outputBox.clientHeight<40;
  set('.stream-text',output||(done?'':'Waiting for output…'));card.querySelector('.stream-cursor').hidden=!!done||!live;
  if(follow)outputBox.scrollTop=outputBox.scrollHeight;
 }
}
const originalSwitchView=switchView;switchView=function(name){originalSwitchView(name);$('#flow-observatory')?.classList.toggle('motion-paused',!flowCanMove());};