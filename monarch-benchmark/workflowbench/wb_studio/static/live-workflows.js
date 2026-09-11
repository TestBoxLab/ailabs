'use strict';
// Stable event-driven workflow lanes; historical deliveries never replay as live.
let flowIdentity=null,flowOpenedAt=Date.now(),flowMotion=true;
const flowLanes=new Map(),flowModels=new Map();
const flowStatus={pending:'Waiting',running:'Running',completed:'Done',error:'Failed',skipped:'Not reached',interrupted:'Interrupted',ungraded:'Ungraded'};
const flowText=(node,value)=>{const next=String(value??'');if(node.textContent!==next)node.textContent=next;};
function flowIsVisible(){return view==='live'&&!document.hidden&&!$('#workspace')?.classList.contains('hidden')&&!!$('#live-view')&&!$('#live-view').classList.contains('hidden');}
function flowCanMove(){return flowMotion&&flowIsVisible()&&matchMedia('(prefers-reduced-motion: no-preference)').matches;}
function flowNode(model,node){return flowModels.get(model)?.nodes.find(n=>n.node===node);}
function flowInspect(n){
  if(!n)return;selected=n;taskId=n.task;$('#task-select').value=taskId;setOutputMode('output');revealSelection();
  for(const lane of flowLanes.values())for(const cell of lane.cells.values())cell.querySelector('button').setAttribute('aria-pressed',String(cell._node.node===n.node&&cell._node.model===n.model));
}
function flowInspectAttempt(a){const r=job?.results.find(x=>x.task===a.task&&x.model===a.model);if(!r)return;taskId=a.task;$('#task-select').value=taskId;renderGraph();flowInspect(flowNode(a.model,'result'));}
function flowPulse(cell, n){
  const at=events.findLast(e=>e.id===n.eventId)?.at;
  if(!flowCanMove()||WorkflowFlow.timestamp(at)<flowOpenedAt||WorkflowFlow.timestamp(at)===null||cell._pulseAt&&Date.now()-cell._pulseAt<650)return;
  cell._pulseAt=Date.now();cell.classList.remove('receiving');void cell.offsetWidth;cell.classList.add('receiving');
  cell.addEventListener('animationend',()=>cell.classList.remove('receiving'),{once:true});
}
function flowPreview(node, value){
  if(node._value===value)return;node._value=value;
  let data=value;if(typeof value==='string'){try{data=JSON.parse(value);}catch{ /* streamed prose */ }}
  const list=Array.isArray(data)?data:data&&typeof data==='object'?Object.values(data).find(Array.isArray):null;
  if(list?.length&&list.every(x=>x&&typeof x==='object'&&!Array.isArray(x))){
    const keys=[...new Set(list.slice(0,3).flatMap(x=>Object.keys(x)))].slice(0,3);
    const out='<table class="flow-output-table"><thead><tr>'+keys.map(k=>'<th>'+esc(k)+'</th>').join('')+'</tr></thead><tbody>'+list.slice(0,3).map(row=>'<tr>'+keys.map(k=>'<td>'+esc(typeof row[k]==='object'?JSON.stringify(row[k]):row[k]??'—')+'</td>').join('')+'</tr>').join('')+'</tbody></table>';
    if(node.innerHTML!==out)node.innerHTML=out;
    return;
  }
  flowText(node,WorkflowFlow.preview(value).text);
}
function flowClock(){
  if(!flowIsVisible()||!job)return;
  for(const lane of flowLanes.values()){
    const p=flowModels.get(lane.model);if(!p)continue;
    const status=p.result?(WorkflowFlow.ungraded(p.result)?'Ungraded':p.result.passed&&p.result.termination==='completed'?'Passed':String(p.result.termination).startsWith('infra:')?'Execution issue':'Failed'):p.start===null?'Waiting':['queued','running','cancelling'].includes(job.status)?'Running':'Interrupted';
    flowText(lane.el.querySelector('.flow-lane-state'),status);
    const elapsed=p.result?p.result.seconds:p.start!==null&&status==='Running'?Math.max(0,(Date.now()-p.start)/1000):null;
    flowText(lane.el.querySelector('.flow-lane-time'),elapsed===null?'Time unavailable':PerformanceView.seconds(elapsed)+(p.result?' total':' elapsed'));
    for(const cell of lane.cells.values()){
      const n=cell._node,value=n.seconds!==null&&n.seconds!==undefined?n.seconds:n.status==='running'&&n.start!==null?Math.max(0,(Date.now()-n.start)/1000):null;
      flowText(cell.querySelector('.flow-node-time'),value===null?'':PerformanceView.seconds(value));
    }
  }
}
function renderObservatory(){
  if(!job||typeof WorkflowFlow==='undefined')return;
  const root=$('#flow-observatory');if(!root)return;
  const identity=job.id+'|'+taskId;
  if(flowIdentity!==identity){
    flowIdentity=identity;flowOpenedAt=Date.now();flowLanes.clear();flowModels.clear();$('#lanes').replaceChildren();
  }
  const live=['queued','running','cancelling'].includes(job.status);
  root.classList.toggle('motion-paused',!flowCanMove());
  const brief=state.tasks.find(t=>t.id===taskId)?.brief||'';flowText($('#task-brief'),brief);$('#task-brief').hidden=!brief||$('#task-select').selectedOptions[0]?.textContent.includes(brief);
  flowText($('#task-progress'),(job.settings.tasks.indexOf(taskId)+1)+' / '+job.settings.tasks.length);
  flowText($('#flow-description'),live?'Nodes update from the event stream. Select a node for its input and full output.':'Recorded workflow activity. Select a node for its input and full output.');
  const motion=$('#flow-motion');motion.textContent=flowMotion?'Pause motion':'Resume motion';motion.setAttribute('aria-pressed',String(!flowMotion));
  motion.onclick=()=>{flowMotion=!flowMotion;root.classList.toggle('motion-paused',!flowCanMove());renderObservatory();};
  $('#flow-latest').onclick=()=>{
    const newest=events.findLast(e=>e.task&&e.model&&job.settings.tasks.includes(e.task)&&!job.results.some(r=>r.task===e.task&&r.model===e.model)&&!events.some(end=>end.type==='attempt_finished'&&end.task===e.task&&end.model===e.model));
    if(newest&&newest.task!==taskId){taskId=newest.task;$('#task-select').value=taskId;renderGraph();}

    for(const lane of flowLanes.values())lane.body.scrollTo({top:lane.body.scrollHeight,behavior:flowCanMove()?'smooth':'instant'});
  };
  PerformanceView.paint($('#flow-metrics'),report?.run===job.id?report.performance:null,{live,inspect:flowInspectAttempt});
  for(const model of job.settings.models){
    const result=job.results.find(r=>r.task===taskId&&r.model===model);
    const p=WorkflowFlow.project(events,{task:taskId,model,result,live});flowModels.set(model,p);
    let lane=flowLanes.get(model);
    if(!lane){
      const el=document.createElement('section');el.className='flow-lane';el.dataset.model=model;el.setAttribute('aria-label',modelName(model));
      el.innerHTML='<header class="flow-lane-heading"><h4></h4><div><span class="flow-lane-state" role="status" aria-live="polite" aria-atomic="true"></span><span class="flow-lane-time"></span></div><p class="flow-relationship"></p></header><div class="flow-lane-body" tabindex="0" role="region"><p class="flow-phase"></p><button class="text-button flow-earlier" hidden>Show earlier nodes</button><ol class="flow-node-list"></ol><p class="flow-waiting">Waiting for this task to start.</p></div>';
      $('#lanes').append(el);lane={el,body:el.querySelector('.flow-lane-body'),model,cells:new Map(),start:null};flowLanes.set(model,lane);
      flowText(el.querySelector('h4'),modelName(model));lane.body.setAttribute('aria-label',modelName(model)+' workflow nodes');
      el.querySelector('.flow-earlier').onclick=()=>{lane.start=Math.max(0,lane.start-18);renderObservatory();};
    }
    flowText(lane.el.querySelector('.flow-relationship'),p.relationship);
    const phases=p.nodes.filter(n=>n.category==='step'),phase=phases.findLast(n=>n.status==='running')||phases.at(-1);
    flowText(lane.el.querySelector('.flow-phase'),phase?(phase.label||'Phase')+' · '+(flowStatus[phase.status]||phase.status):'');
    const all=p.nodes.filter(n=>n.category!=='step');
    lane.start=lane.start===null?Math.max(0,all.length-18):Math.min(lane.start,all.length);
    const shown=all.slice(lane.start),desired=new Set(shown.map(n=>n.node));
    const earlier=lane.el.querySelector('.flow-earlier');earlier.hidden=lane.start===0;flowText(earlier,'Show '+Math.min(18,lane.start)+' earlier nodes');
    lane.el.querySelector('.flow-waiting').hidden=all.length>0;
    const list=lane.el.querySelector('ol');
    for(const [id,cell] of lane.cells)if(!desired.has(id)){cell.remove();lane.cells.delete(id);}
    shown.forEach((n,index)=>{
      let cell=lane.cells.get(n.node),wasNew=!cell;
      if(!cell){
        cell=document.createElement('li');cell.className='flow-cell';cell.dataset.flowNode=n.node;cell.dataset.model=model;
        cell.innerHTML='<div class="flow-connection" aria-hidden="true"><svg viewBox="0 0 40 36"><path d="M20 0V32m-4-5 4 5 4-5"/><circle class="flow-packet" cx="20" cy="3" r="3"/></svg><span class="flow-edge-label"></span></div><article class="flow-node"><button type="button" class="flow-node-select" aria-pressed="false"><span class="flow-node-icon"></span><strong class="flow-node-label"></strong><span class="flow-node-state"></span></button><div class="flow-node-content"><span class="flow-input-heading">Input preview</span><p class="flow-input"></p><span class="flow-preview-heading">Output preview</span><div class="flow-preview"></div><span class="flow-inspect-hint">Select the node for full details</span></div><footer><span class="flow-output-label"></span><span class="flow-node-time"></span></footer></article>';
        lane.cells.set(n.node,cell);cell.querySelector('button').onclick=()=>flowInspect(cell._node);
      }
      const changed=cell._node?.eventId!==n.eventId || cell._node?.status!==n.status;cell._node=n;
      if(list.children[index]!==cell)list.insertBefore(cell,list.children[index]||null);
      cell.dataset.status=n.status;
      const prev=shown[index-1], edge=prev&&p.edges.find(e=>e.source===prev.node&&e.target===n.node);
      cell.querySelector('.flow-connection').hidden=!edge;
      cell.querySelector('.flow-connection').dataset.kind=edge?.kind||'sequence';
      flowText(cell.querySelector('.flow-edge-label'),edge?.kind==='dependency'?'Recorded dependency':n.category==='tool'?'Tool request':n.category==='result'?'Recorded verdict':'Next observed event');
      const label=n.category==='knowledge'?n.label:nodeLabel(n);
      flowText(cell.querySelector('.flow-node-label'),label);
      cell.querySelector('button').setAttribute('aria-label',label+' · '+(flowStatus[n.status]||n.status)+' · Inspect input and output');
      cell.querySelector('button').setAttribute('aria-pressed',String(selected?.node===n.node&&selected?.model===model));
      flowText(cell.querySelector('.flow-node-state'),flowStatus[n.status]||n.status);
      const symbol=n.category==='model'||n.category==='builder'?'model':n.category==='result'?'check':'tool';
      if(wasNew)cell.querySelector('.flow-node-icon').innerHTML=icon(symbol);
      const input=n.arguments!==undefined?WorkflowFlow.preview(n.arguments,180).text:n.message||'';
      flowText(cell.querySelector('.flow-input'),input);cell.querySelector('.flow-input').hidden=!input;cell.querySelector('.flow-input-heading').hidden=!input;
      const value=n.output??(n.status==='running'?'Waiting for output…':null);
      flowPreview(cell.querySelector('.flow-preview'),value);
      const summary=WorkflowFlow.preview(n.output);
      flowText(cell.querySelector('.flow-output-label'),n.category==='result'?(n.status==='ungraded'?'Ungraded outcome':'Graded outcome'):summary.label+(summary.truncated?' · preview':'')+(n.progress?' · '+n.progress.current+(n.progress.total?'/'+n.progress.total:''):''));
      if(changed)flowPulse(cell,n);
    });
    flowDependencies(lane,p,shown);
  }
  flowClock();renderWorkstreams();
}
document.addEventListener('visibilitychange',()=>{$('#flow-observatory')?.classList.toggle('motion-paused',!flowCanMove());if(flowIsVisible())flowClock();});
setInterval(flowClock,1000);


function flowDependencies(lane,projection,shown){
  const list=lane.el.querySelector('ol');
  let svg=lane.el.querySelector('.flow-dependencies');
  if(!svg){svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.classList.add('flow-dependencies');svg.setAttribute('role','img');svg.setAttribute('aria-label','Recorded workflow dependencies');lane.body.append(svg);}
  svg.replaceChildren();
  const body=lane.body.getBoundingClientRect();
  const height=list.offsetTop+list.offsetHeight+16;
  svg.setAttribute('viewBox','0 0 '+lane.body.clientWidth+' '+height);
  svg.setAttribute('height',height);
  for(const edge of projection.edges.filter(e=>e.kind==='dependency')){
    const source=lane.cells.get(edge.source),target=lane.cells.get(edge.target);
    if(!source||!target||shown.findIndex(n=>n.node===edge.target)===shown.findIndex(n=>n.node===edge.source)+1)continue;
    const a=source.querySelector('article').getBoundingClientRect(),b=target.querySelector('article').getBoundingClientRect();
    const x=a.left-body.left-2,y1=a.bottom-body.top+lane.body.scrollTop-12,y2=b.top-body.top+lane.body.scrollTop+20;
    const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',`M${x} ${y1}H6V${y2}H${x}m-4 -4 4 4 -4 4`);path.dataset.source=edge.source;path.dataset.target=edge.target;
    const title=document.createElementNS(svg.namespaceURI,'title');title.textContent=edge.source+' → '+edge.target;path.append(title);svg.append(path);
  }
  svg.hidden=!svg.children.length;
}
window.addEventListener('resize',()=>{if(flowIsVisible())renderObservatory();});
