'use strict';
function runStatus(value){return value.pause_requested&&["queued","running"].includes(value.status)?(value.active_attempts?"pausing":"paused"):value.status;}
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const knownNumber=n=>n!==null&&n!==undefined&&n!==''&&Number.isFinite(Number(n));
const money=n=>!knownNumber(n)?'Not available':Number(n).toLocaleString('en-US',{style:'currency',currency:'USD',minimumFractionDigits:2,maximumFractionDigits:Number(n)>0&&Number(n)<.01?4:2});
const human=s=>String(s).replaceAll('_',' ').replaceAll('.',' / ');
const icon=(kind='check')=>'<svg class="icon" aria-hidden="true"><use href="/vendor/lucide/sprite.svg#'+(kind==='check'?'check':kind==='tool'?'zap':'sparkles')+'"/></svg>';
const emptyOutput=$('#output').innerHTML;
function clearSelection(restoreFocus=false) {
  selected=null; $('.workspace').classList.remove('has-inspector');
  $('#inspector-title').textContent='Output'; $('#inspector-meta').textContent='Select an action or result';
  $('#output').innerHTML=emptyOutput; setOutputMode('output');
  if(restoreFocus) {
    const opener=selectionOpener?.isConnected?selectionOpener:$('#comparison-title');
    opener.focus({preventScroll:true});
  }
}
function revealSelection() {
  if(!$('#inspector').contains(document.activeElement))selectionOpener=document.activeElement;
  if(!$('.workspace').classList.contains('has-inspector')&&selected?.result?.passed===false)setOutputMode('checks');
  renderOutput(); bindEvidence();
  $('#inspector-title').focus({preventScroll:true});
  if(innerWidth<=1100)$('#inspector').scrollIntoView({behavior:'smooth',block:'start'});
}
let report, openSequence=0, reportSequence=0, launchStep=0, launching=false, launchOpening=false, launchRequest=null;
let toastTimer, reportRefreshTimer, selectionOpener, pendingJobId=null, renderFrame=null;
const analysisPending=new Set(), seenEvents=new Set();
let state, job, events=[], stream, taskId, selected, outputMode='output', view='report', selectedTasks=new Set(), selectedModels=new Set(), selectedArchitectureIds=new Set(), launchTaskSets=[], runDraftLoaded=false, restoredTaskSet=null;
function toast(text) {
  clearTimeout(toastTimer);
  $('#toast').textContent=text; $('#toast').classList.remove('hidden');
  toastTimer=setTimeout(()=>$('#toast').classList.add('hidden'),6000);
}
async function api(path,body,recovered=false) {
  const write=body!==undefined;
  let response;
  try {
    response=await fetch(path,write?{method:'POST',headers:{'Content-Type':'application/json','X-Studio-Token':state?.token||''},body:JSON.stringify(body)}:{signal:AbortSignal.timeout(30000)});
  } catch (error) {
    const issue=new Error(error.name==='TimeoutError'?'Studio took too long to respond. Try again.':'Cannot reach Studio. Check the local server and try again.');
    issue.uncertain=write; throw issue;
  }
  let data;
  try { data=await response.json(); } catch {
    const issue=new Error('Studio returned an unreadable response. Reload the workspace to check its status.');
    issue.uncertain=write; throw issue;
  }
  // A definite pre-dispatch refusal is safe to recover once after a local restart.
  if(write && response.status===403 && data.error==='Origin or session refused' && !recovered) {
    const previous=state?.token;
    const fresh=await api('/api/state');
    if(fresh.token && fresh.token!==previous) { state.token=fresh.token; return api(path,body,true); }
  }
  if(!response.ok) {
    const issue=new Error(response.status===403?'Your Studio session changed. Reload the workspace before trying again.':data.error||'Studio could not complete this request. Try again.');
    issue.status=response.status; issue.uncertain=write&&response.status>=500; throw issue;
  }
  return data;
}
function budget(data){state.budget=data;const chip=$('#budget-chip-value');if(chip){chip.textContent=knownNumber(data?.available)?money(data.available)+' left':'Not available';$('#nav-budget').classList.toggle('blocked',!!data?.blocked);}}
const providerWords={anthropic:'Anthropic',openai:'OpenAI',gemini:'Gemini',fireworks:'Fireworks',zai:'Z.ai'};
function capacityNote(){
 const wanted=Number($('#run-concurrency').value)||1,runtime=state.runtime,hostMax=runtime?.max_agents;
 if(hostMax&&wanted>hostMax)return 'This host runs '+hostMax+' at once.';
 const providers=new Map();for(const id of preserveArchitectureModels()?[]:selectedModels){const m=state.models.find(m=>m.id===id.split('@')[0]);if(m?.provider)providers.set(m.provider,(providers.get(m.provider)||0)+1);}
 const limits=Object.fromEntries((runtime?.providers||[]).map(p=>[p.provider,p.concurrency])),fallback=runtime?.default_provider_limits?.concurrency??2;
 const bound=[...providers.keys()].map(p=>({p,limit:limits[p]??fallback})).filter(x=>wanted>x.limit).sort((a,b)=>a.limit-b.limit)[0];
 if(bound)return (providerWords[bound.p]||bound.p)+' allows '+bound.limit+' at once on this host; the rest of the '+wanted+' wait for a slot.';
 return hostMax?'Up to '+hostMax+' at once on this host.':'Provider limits also apply.';
}
function renderJobs() {
  if(window.renderHistory)window.renderHistory();
  const focusId=document.activeElement?.dataset?.job;
  const query=($('#run-search')?.value||'').trim().toLowerCase();
  const rows=state.jobs.filter(j=>(j.title+' '+j.status).toLowerCase().includes(query));
  $('#job-count').textContent=query?rows.length+' / '+state.jobs.length:state.jobs.length;
  $('#jobs').innerHTML=rows.length?rows.map(j=>'<button class="job '+(job?.id===j.id?'active':'')+'" data-job="'+esc(j.id)+'" data-status="'+esc(j.status)+'" aria-current="'+(job?.id===j.id?'true':'false')+'"><strong>'+esc(j.title)+'</strong><small><span class="dot"></span>'+esc(['queued','running','cancelling'].includes(j.status)?j.completed+' of '+j.total+' finished':j.status)+'</small></button>').join(''):'<p class="jobs-empty">'+(query?'No runs match your search.':'No runs yet. Start with a few tasks and compare the outcomes.')+'</p>';
  $$('[data-job]').forEach(b=>b.onclick=()=>openJob(b.dataset.job));
  if(focusId)$$('[data-job]').find(b=>b.dataset.job===focusId)?.focus({preventScroll:true});
}
function syncJob(value){job=value;const index=state.jobs.findIndex(j=>j.id===job.id);if(index<0)state.jobs.unshift(job);else state.jobs[index]=job;renderJobs();$('#comparison-title').textContent=job.title;$('#run-details').classList.remove('hidden');$('#comparison-meta').innerHTML='<dt>Tasks</dt><dd>'+job.settings.tasks.length+'</dd><dt>Setups</dt><dd>'+job.settings.models.length+'</dd><dt>Spending limit</dt><dd>'+esc(money(job.settings.maximum_usd))+'</dd>';const paused=job.pause_requested&&['queued','running'].includes(job.status);$('#job-status').textContent=paused?(job.active_attempts?'Pausing…':'Paused'):job.status;$('#pause-run').classList.toggle('hidden',paused||!['queued','running'].includes(job.status));$('#resume-run').classList.toggle('hidden',!paused);$('#pause-run').disabled=false;$('#resume-run').disabled=false;$('#job-status').className='status '+job.status;$('#cancel-run').classList.toggle('hidden',!['queued','running','cancelling'].includes(job.status));$('#cancel-run').disabled=job.status==='cancelling';$('#result-count').textContent=job.results.length;$('#stream-note').textContent=runStatus(job)==='paused'?'Paused':['queued','running','cancelling'].includes(job.status)?'Live updates':'Recorded execution';const controlNote=paused?(job.active_attempts?'Pausing after active tasks finish. No new tasks will start.':'Paused. Resume to continue the remaining tasks.'):job.status==='cancelling'?'Cancelling. Active requests may take a moment to finish.':'';$('#run-message').textContent=controlNote||job.error||'';$('#run-message').classList.toggle('hidden',!controlNote&&!job.error)}
async function openJob(id) {
  if(window.showWorkspaceSurface)window.showWorkspaceSurface('detail',false);
  const runHash='#run/'+encodeURIComponent(id);if(location.hash!==runHash)history.pushState(null,'',runHash);
  const sequence=++openSequence;
  clearTimeout(reportRefreshTimer);
  if(stream)stream.close();
  pendingJobId=id; clearSelection();
  $('.comparison').setAttribute('aria-busy','true');
  setConnection('Loading run…','loading');
  $('#connection-error').classList.add('hidden');
  try {
    const [next,account]=await Promise.all([api('/api/jobs/'+id),api('/api/jobs/'+id+'/report')]);
    if(sequence!==openSequence)return;
    clearSelection(); events=[]; seenEvents.clear(); report=account; job=next; syncJob(job);
    taskId=job.settings.tasks[0];if(['queued','running','cancelling'].includes(job.status))view='live';
    $('#task-select').innerHTML=job.settings.tasks.map(t=>'<option value="'+esc(t)+'">'+esc(taskTitle(t))+'</option>').join('');
    $('#empty').classList.add('hidden'); switchView(view);
    renderGraph(); renderResults(); renderReport();
    setConnection('Connected','connected');
    const source=new EventSource('/api/jobs/'+id+'/events'); stream=source;
    source.onopen=()=>{if(sequence===openSequence)setConnection('Connected','connected');};
    source.onmessage=e=>{
      if(sequence!==openSequence)return;
      let event;
      try { event=JSON.parse(e.data); } catch { setConnection('Unreadable update','error'); return; }
      if(seenEvents.has(event.id))return;
      seenEvents.add(event.id); events.push(event);
      if(event.type==='run_control') {job.pause_requested=event.pause_requested;job.active_attempts=event.active_attempts;job.status=event.status;syncJob(job);}
      else if(event.type==='finished') { syncJob(event.job); api('/api/budget').then(budget).catch(()=>{}); source.close(); queueReportRefresh(id,sequence); }
      else if(event.type==='attempt_finished') {
        if(!job.results.some(r=>r.task===event.task&&r.model===event.model)) {job.results.push(event);job.completed++;syncJob(job);}
        queueReportRefresh(id,sequence);
      } else if(event.type==='running'&&['queued','running'].includes(job.status)) {job.status='running';syncJob(job);}
      else if(event.type==='cancelling') {job.status='cancelling';syncJob(job);}
      else if(event.type==='billing'&&['queued','running','cancelling'].includes(job.status))api('/api/budget').then(budget).catch(()=>{});
      scheduleEventRender();
    };
    source.onerror=()=>{
      if(sequence!==openSequence)return;
      if(!['queued','running','cancelling'].includes(job.status)) {source.close();setConnection('Connected','connected');}
      else setConnection('Reconnecting…','loading');
    };
  } catch(error) {
    if(sequence!==openSequence)return;
    showConnectionError('Could not open this run. '+error.message);
  } finally { if(sequence===openSequence)$('.comparison').removeAttribute('aria-busy'); }
}
function queueReportRefresh(id,sequence) {
  clearTimeout(reportRefreshTimer);
  reportRefreshTimer=setTimeout(()=>refreshReport(id,sequence),120);
}
async function refreshReport(id,sequence) {
  const revision=++reportSequence;
  try {
    const next=await api('/api/jobs/'+id+'/report');
    if(sequence!==openSequence||revision!==reportSequence)return;
    report=next; renderReport();
  } catch(error) {if(sequence===openSequence)toast('Findings could not refresh. '+error.message);}
}
function scheduleEventRender() {
  if(renderFrame!==null)return;
  renderFrame=requestAnimationFrame(()=>{
    renderFrame=null;
    if(view==='live')renderGraph();
    if(window.renderObservatory)window.renderObservatory();
    if(view==='results')renderResults();
    if(window.builderLive)builderLive(job,events);
    if(selected&&outputMode!=='output'){renderOutput();bindEvidence();}
    if(selected&&!selected.report) {
      const latest=nodeList(selected.model).find(n=>n.node===selected.node);
      if(latest&&JSON.stringify(latest)!==JSON.stringify(selected)){selected=latest;renderOutput();bindEvidence();}
    }
  });
}

function nodeLabel(node){if(node.category==='result')return 'Verify task outcome';if(node.category==='workflow')return (node.product?human(String(node.product).replace(/^bench-/,''))+': ':'')+(node.label||node.node);if(node.category==='builder')return node.label||'Workflow builder';if(node.category==='model')return 'Generate next response';if(node.label==='api_search')return 'Find application actions';if(node.label==='base64_encode')return 'Encode message content';if(node.label==='api_fetch'){const a=node.arguments||{};let service='application';try{const host=new URL(a.url).hostname;service=host.includes('salesforce')?'Salesforce':host.includes('gmail')?'Gmail':host.split('.')[0]}catch{}const verb={GET:'Read',POST:'Create',PATCH:'Update',PUT:'Update',DELETE:'Delete'}[a.method]||'Call';return verb+' '+service+(service==='Gmail'?' message':' record')}return human(node.label||'Response')}
const WORKFLOW_STATUS={pending:'pending',running:'running',succeeded:'completed',failed:'error',skipped:'skipped',blocked:'error'};
function nodeList(model){const nodes=[];for(const e of events.filter(x=>x.task===taskId&&x.model===model)){if(e.type==='step_started'){nodes.push({...e,node:'step:'+e.step,status:'running',category:'step'})}else if(e.type==='step_finished'){const old=nodes.find(n=>n.node==='step:'+e.step);if(old)Object.assign(old,e,{node:'step:'+e.step});else nodes.push({...e,node:'step:'+e.step,category:'step'})}else if(['node_started','model_started'].includes(e.type)){nodes.push({...e,status:'running',category:e.category||(e.type==='model_started'?'model':'tool')})}else if(['node_finished','model_finished'].includes(e.type)){let old=nodes.find(n=>n.node===e.node);if(old)Object.assign(old,e);else nodes.push({...e,category:e.category||(e.type==='model_finished'?'model':'tool')})}else if(e.type==='workflow_recipe'){for(const w of e.nodes||[]){const id='wf:'+w.id;if(!nodes.find(n=>n.node===id))nodes.push({...w,node:id,model,task:taskId,status:'pending',workflowStatus:'pending',category:'workflow'})}}else if(e.type==='workflow_step'){const old=nodes.find(n=>n.node===e.node);const status=WORKFLOW_STATUS[e.status]||'running';if(old)Object.assign(old,e,{status,workflowStatus:e.status});else nodes.push({...e,status,workflowStatus:e.status,category:'workflow'})}}
const result=job?.results.find(r=>r.task===taskId&&r.model===model);if(result){nodes.forEach(n=>{if(n.status==='running')n.status='error';if(n.status==='pending'){n.status='skipped';n.workflowStatus='not reached'}});}if(result)nodes.push({node:'result',model,task:taskId,label:'Task result',status:result.passed?'completed':'error',category:'result',output:result.output,result});return nodes}
function renderGraph(){if(!job)return;const focusNode=document.activeElement?.dataset?.node;const focusModel=document.activeElement?.dataset?.model;{const brief=state.tasks.find(t=>t.id===taskId)?.brief||'',title=$('#task-select').selectedOptions[0]?.textContent||'';$('#task-brief').textContent=brief.trim()===title.trim()?'':brief;$('#task-brief').classList.toggle('hidden',!$('#task-brief').textContent);}$('#task-progress').textContent=(job.settings.tasks.indexOf(taskId)+1)+' / '+job.settings.tasks.length;$('#lanes').innerHTML=job.settings.models.map(model=>{const info=state.models.find(m=>m.id===model);const nodes=nodeList(model);return '<section class="lane" aria-label="'+esc(modelName(model))+'"><div class="lane-heading"><span class="model-icon">'+icon(armKind(model)==='version'?'model':'tool')+'</span><div><strong>'+esc(modelName(model))+'</strong><small>'+esc(armKind(model)==='version'?'Published architecture · steps run in order':armKind(model)==='enterprise'?'Monarch Enterprise · builds the workflow, then runs it':info?.kind||'Setup')+'</small></div></div><div class="lane-nodes">'+(nodes.length?nodes.map(n=>n.category==='step'?'<div class="lane-step '+esc(n.status)+'"><strong>'+esc(n.label)+'</strong><small>'+esc(n.status==='running'?'Running this step':n.status==='error'?'Stopped with an error':'Step finished')+'</small></div>':'<button class="node '+esc(n.status)+(selected?.node===n.node&&selected?.model===model?' selected':'')+'" data-node="'+esc(n.node)+'" data-model="'+esc(model)+'"><div class="node-head">'+icon(n.category==='model'||n.category==='builder'?'model':'check')+'<span>'+esc(nodeLabel(n))+'</span></div><p>'+esc(n.category==='result'?(n.result.passed?'All task checks passed':n.result.error||'One or more task checks failed'):n.category==='workflow'?(n.message||workflowWords(n)):n.arguments?JSON.stringify(n.arguments):n.output||(n.status==='running'?'Waiting for the response…':n.status==='error'?'The request stopped before a response arrived.':'Chose the next application actions without a written reply.'))+'</p><div class="node-foot"><span>'+esc(n.category==='result'?'Verified task checks':n.category==='model'?'Model response':n.category==='builder'?'Workflow builder':n.category==='workflow'?'Workflow node'+((n.kind||n.node_kind)?' · '+(n.kind||n.node_kind):''):'Application action')+'</span><span>'+esc(n.category==='workflow'?workflowWords(n):n.status==='running'?'Running':n.status==='error'?'Attention':'Done')+'</span></div></button>').join(''):'<div class="lane-waiting">Waiting for this task</div>')+'</div></section>'}).join('');$$('[data-node]').forEach(b=>b.onclick=()=>{selected=nodeList(b.dataset.model).find(n=>n.node===b.dataset.node);revealSelection();renderGraph()});if(focusNode){const target=$$('[data-node]').find(b=>b.dataset.node===focusNode&&b.dataset.model===focusModel);target?.focus({preventScroll:true});}}
function workflowWords(n){const w=n.workflowStatus||n.status;const words={pending:'Waiting to run',running:'Running',succeeded:'Done',failed:'Failed',skipped:'Skipped',blocked:'Blocked','not reached':'Not reached'};return (words[w]||human(w))+(n.progress?' · '+n.progress.current+(n.progress.total?'/'+n.progress.total:''):'')}
function pretty(value,depth=0){if(value&&typeof value==='object'&&!Array.isArray(value)&&!Object.keys(value).length)return '<p>No response body returned.</p>';if(depth>5)return '<pre>'+esc(JSON.stringify(value,null,2))+'</pre>';if(value===null||value===undefined)return '<span>Not available</span>';if(typeof value==='string'){try{return pretty(JSON.parse(value),depth)}catch{}return textDocument(value)}if(typeof value!=='object')return esc(value);if(Array.isArray(value)){if(!value.length)return '<p>No records returned.</p>';if(value.every(v=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.values(v).every(x=>x===null||typeof x!=='object'))){const allKeys=[...new Set(value.flatMap(v=>Object.keys(v)))],keys=allKeys.slice(0,8);return '<div class="collection-label">'+(value.length>100||allKeys.length>8?'Showing '+Math.min(100,value.length)+' of '+value.length+' records and '+keys.length+' of '+allKeys.length+' fields. Open Raw evidence for the complete output.':value.length+' records')+'</div><div class="table-scroll"><table><thead><tr>'+keys.map(k=>'<th>'+esc(human(k))+'</th>').join('')+'</tr></thead><tbody>'+value.slice(0,100).map(v=>'<tr>'+keys.map(k=>'<td>'+esc(v[k])+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>';}return '<div class="collection-label">'+value.length+' records</div>'+value.slice(0,100).map(v=>'<section class="record">'+pretty(v,depth+1)+'</section>').join('')+(value.length>100?'<p>Showing the first 100 records. Copy raw evidence for the full output.</p>':'')}return '<dl>'+Object.entries(value).map(([k,v])=>'<dt>'+esc(human(k))+'</dt><dd>'+pretty(v,depth+1)+'</dd>').join('')+'</dl>'}
function textDocument(value){return value.split(/\n\s*\n/).map(block=>{if(/^#{1,3}\s/.test(block))return '<h3>'+esc(block.replace(/^#{1,3}\s/,''))+'</h3>';if(block.split('\n').every(l=>/^[-*]\s/.test(l)))return '<ul>'+block.split('\n').map(l=>'<li>'+esc(l.slice(2))+'</li>').join('')+'</ul>';return '<p>'+esc(block).replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/`([^`]+)`/g,'<code>$1</code>').replaceAll('\n','<br>')+'</p>'}).join('')}
function renderOutput(){
  if(!selected)return;
  document.querySelector('.workspace').classList.add('has-inspector');
  $('#inspector-title').textContent=selected.category==='result'?'Task output':nodeLabel(selected);
  $('#inspector-meta').textContent=modelName(selected.model)+' · '+selected.status;
  const task=selected.task||taskId,model=selected.model,box=$('#output');
  const result=selected.result||job?.results.find(r=>r.task===task&&r.model===model)||null;
  const account=selected.report||report?.attempts.find(a=>a.task===task&&a.model===model)||null;
  box.setAttribute('aria-labelledby','inspector-tab-'+outputMode);
  if(outputMode==='checks')box.innerHTML=checksView(result,account);
  else if(outputMode==='trace'){box.innerHTML=traceView(task,model);architectureFigure(box,task,model);}
  else if(outputMode==='timeline')box.replaceChildren(timelineView(task,model));
  else box.innerHTML=outputView(result,account);
}
function rawRecord(){const raw={arguments:selected.arguments,output:selected.output,status:selected.status,...(selected.result?{checks:selected.result.checks,termination:selected.result.termination,flags:selected.result.flags,unexpected_changes:selected.result.unexpected_changes}:{})};return '<details class="finding-section"><summary>Raw record</summary><pre>'+esc(JSON.stringify(raw,null,2))+'</pre></details>';}
function outputView(result,account){
  if(selected.category!=='result')return (selected.output!==null&&selected.output!==undefined?pretty(selected.output):'<p>No output received yet.</p>')+(selected.arguments?'<h4>Input</h4>'+pretty(selected.arguments):'')+rawRecord();
  return (result?.error?'<p class="fail">'+esc(result.error)+'</p>':'')+(result&&result.output!==null&&result.output!==undefined?pretty(result.output):'<p>No output received yet.</p>')+(account?reportDetails(account):'')+rawRecord();
}
function changeValue(value){
  if(value===null||value===undefined)return '<span class="muted">none</span>';
  if(value==='<object>')return 'the record';
  if(typeof value==='object')return '<dl class="compact">'+Object.entries(value).map(([k,v])=>'<div><dt>'+esc(human(k))+'</dt><dd>'+esc(v&&typeof v==='object'?JSON.stringify(v):v)+'</dd></div>').join('')+'</dl>';
  return esc(value);
}
function checkRow(title,expected,observed,record,field,passed){
  const state=passed===true?'passed':passed===false?'failed':'unknown';
  return '<tr class="check-row '+state+'"><th scope="row">'+esc(title)+(record||field?'<small>'+esc([record,field].filter(Boolean).join(' · '))+'</small>':'')+'</th><td>'+esc(expected)+'</td><td>'+esc(observed)+'</td><td><span class="verdict '+state+'">'+(state==='passed'?'Passed':state==='failed'?'Failed':'Not evaluated')+'</span></td></tr>';
}
function checksView(result,account){
  if(!result)return '<p>No verdict recorded yet.</p>';
  const changes=account?.changes||(result.unexpected_changes||[]).map(c=>({service:human(c.service||''),record:null,field:c.path,op:c.op,before:c.before,after:c.after}));
  const rows=(result.checks||[]).map((c,i)=>{
    if(c.type==='allowed_changes_only')return checkRow('Nothing else changed','No changes outside the permitted scope',changes.length?changes.length+' recorded':'None recorded',null,null,c.passed);
    const r=(account?.requirements||[]).find(x=>x.check_index===i);
    return checkRow(r?.title||human(c.type),r?.expected||'Not named',r?.observed||'Not recorded',r?.record,r?.field,c.passed);
  });
  if(!rows.length)return '<p>No checks recorded for this attempt.</p>';
  return '<table class="checks-table"><thead><tr><th scope="col">Check</th><th scope="col">Expected</th><th scope="col">Observed</th><th scope="col">Verdict</th></tr></thead><tbody>'+rows.join('')+'</tbody></table>'
    +(changes.length?'<h4>Changes outside the permitted scope</h4><table class="changes-table"><thead><tr><th scope="col">Record</th><th scope="col">Field</th><th scope="col">Before</th><th scope="col">After</th></tr></thead><tbody>'+changes.map(ch=>'<tr><td>'+esc([ch.service,ch.record].filter(Boolean).join(' '))+'</td><td>'+esc(ch.field||ch.op)+'</td><td>'+changeValue(ch.before)+'</td><td>'+changeValue(ch.after)+'</td></tr>').join('')+'</tbody></table>':'');
}
function checkName(type,task,model,index){
  if(type==='allowed_changes_only')return 'changes outside scope';
  const r=report?.attempts.find(a=>a.task===task&&a.model===model)?.requirements.find(x=>x.check_index===index);
  return r?[r.record,r.field].filter(Boolean).join(' ')||r.title:human(type);
}
function callWords(e){
  const a=e.arguments||{};
  if(e.label==='api_search')return 'search "'+(a.query||'')+'"';
  if(e.label==='api_fetch'){let path=String(a.url||'');try{const u=new URL(a.url);path=u.hostname.split('.')[0]+' '+u.pathname.split('/').filter(Boolean).slice(-2).join('/');}catch{}return (a.method||'GET')+' '+path;}
  return e.label||e.node||'tool';
}
function eventLabel(e){
  if(!e)return 'Event';
  const start=e.type==='node_finished'?events.find(x=>x.type==='node_started'&&x.node===e.node&&x.task===e.task&&x.model===e.model)||e:e;
  switch(e.type){
    case 'node_started':return (e.category==='builder'?'Builder: ':'Tool call: ')+callWords(e);
    case 'node_finished':return (e.status==='error'?'Tool error: ':e.category==='builder'?'Builder result: ':'Tool result: ')+callWords(start);
    case 'model_started':return 'Model turn'+(e.turn!==undefined?' '+(Number(e.turn)+1):'');
    case 'model_finished':return e.status==='error'?'Model error':'Model reply';
    case 'step_started':return 'Step started: '+(e.label||e.step);
    case 'step_finished':return (e.status==='error'?'Step failed: ':'Step finished: ')+(e.label||e.step);
    case 'workflow_step':return 'Workflow node: '+(e.label||e.node)+(e.status?' · '+e.status:'');
    case 'attempt_started':return 'Attempt started';
    case 'attempt_finished':{const failed=(e.checks||[]).map((c,i)=>c.passed===false?checkName(c.type,e.task,e.model,i):null).filter(Boolean);return failed.length?'Check failed: '+failed.join(', '):e.passed?'Verdict: passed':'Verdict: '+human(e.termination||'failed');}
    case 'attempt_error':return 'Error: '+(e.message||e.error||'attempt stopped');
    case 'billing':return 'Usage recorded';
    default:return human(e.type);
  }
}
function evidenceButton(id){const event=events.find(e=>e.id===Number(id));return '<button class="text-button" data-evidence="'+esc(String(id))+'">'+esc(event?eventLabel(event):'Event '+id)+'</button>';}
function attemptEvents(task,model){return events.filter(e=>e.task===task&&e.model===model&&e.type!=='run_control');}
function traceView(task,model){
  const rows=attemptEvents(task,model);
  if(!rows.length)return '<p>No events recorded for this attempt.</p>';
  const start=Date.parse(rows[0].at);
  return '<div class="trace-figure" data-trace-figure></div><ol class="trace-list">'+rows.map(e=>'<li><button class="trace-event" data-evidence="'+e.id+'"><span>'+esc(eventLabel(e))+'</span><time datetime="'+esc(e.at)+'">+'+((Date.parse(e.at)-start)/1000).toFixed(1)+'s</time></button></li>').join('')+'</ol>';
}
function timelineView(task,model){
  const rows=attemptEvents(task,model),start=rows.length?Date.parse(rows[0].at):0,t=e=>(Date.parse(e.at)-start)/1000;
  const lanes=new Map(),open=new Map(),lane=(key,label)=>{if(!lanes.has(key))lanes.set(key,{label,spans:[]});return lanes.get(key);};
  for(const e of rows){
    if(e.type==='model_started')open.set('model',e);
    else if(e.type==='model_finished'){const s=open.get('model')||e;lane('model','Model').spans.push({start:t(s),end:t(e),status:e.status==='error'?'error':'model',label:'Model reply'});open.delete('model');}
    else if(e.type==='node_started')open.set(e.node,e);
    else if(e.type==='node_finished'){const s=open.get(e.node)||e;lane(e.node,callWords(s)).spans.push({start:t(s),end:t(e),status:e.status==='error'?'error':'observed',label:eventLabel(s)});open.delete(e.node);}
  }
  const last=rows.length?t(rows.at(-1)):0;
  for(const [key,s] of open)lane(key,key==='model'?'Model':callWords(s)).spans.push({start:t(s),end:last,status:'running',label:'Still running'});
  const p=document.createElement('p');
  if(!lanes.size){p.textContent='No tool calls recorded for this attempt.';return p;}
  if(!window.Charts){p.textContent='Chart kit not loaded.';return p;}
  return Charts.timeline({title:'Tool calls by node over time',source:'run '+job.id+' · '+modelName(model)+' · '+shortTaskLabel(task),lanes:[...lanes.values()],end:Math.max(last,.1)});
}
function stepMeasures(task,model){
  const out={};
  for(const e of events.filter(x=>x.task===task&&x.model===model&&x.step)){
    const s=out[e.step]||(out[e.step]={cost:null,seconds:null,status:'',unknown:false});
    if(e.type==='step_started'){s.startedAt=e.at;s.status='running';}
    if(e.type==='step_finished'){s.status=e.status==='error'?'error':'completed';if(s.startedAt)s.seconds=(Date.parse(e.at)-Date.parse(s.startedAt))/1000;}
    if(e.type==='billing'){const usd=e.billing?.actual_usd;if(knownNumber(usd)&&!s.unknown)s.cost=(s.cost||0)+Number(usd);else{s.unknown=true;s.cost=null;}}
  }
  return out;
}
const blueprintCache=new Map();
async function architectureFigure(box,task,model){
  const slot=box.querySelector('[data-trace-figure]'),arm=job?.settings?.arms?.find(a=>a.id===model);
  if(!slot||!arm||arm.kind!=='version'||!window.Charts?.architecture)return;
  const key=arm.blueprint+'/'+arm.number;
  if(!blueprintCache.has(key))blueprintCache.set(key,api('/api/blueprints').then(list=>list.items.find(b=>b.id===arm.blueprint)?.versions.find(v=>v.version===arm.number)?.graph||null).catch(()=>null));
  const graph=await blueprintCache.get(key);
  if(!graph||!slot.isConnected||outputMode!=='trace')return;
  const steps=stepMeasures(task,model),live=['queued','running','cancelling'].includes(job.status);
  const active=live?Object.keys(steps).find(id=>steps[id].status==='running')||null:null;
  slot.replaceChildren(Charts.architecture({title:arm.name,source:'version '+arm.number+' · '+(live?'running':'recorded'),graph,steps,active}));
}
$('.inspector-tabs').addEventListener('keydown',e=>{
  const tabs=$$('[data-output]'),index=tabs.indexOf(document.activeElement);
  if(index<0||!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;
  e.preventDefault();const next=e.key==='Home'?0:e.key==='End'?tabs.length-1:(index+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;
  tabs[next].click();tabs[next].focus();
});
function renderResults() {
  if(!job)return;
  const focused=document.activeElement?.dataset?.index;
  const results=job.results, total=results.length, assessed=results.filter(r=>!String(r.termination||'').startsWith('infra:')), passed=assessed.filter(r=>r.passed).length;
  const known=results.filter(r=>knownNumber(r.cost_usd)), cost=known.reduce((a,r)=>a+Number(r.cost_usd),0);
  const unresolved=results.some(r=>!knownNumber(r.cost_usd)||r.flags?.includes('billing=unknown'));
  $('#results-summary').innerHTML='<div class="result-stat"><strong>'+passed+' / '+assessed.length+'</strong><span>Evaluated attempts passed</span></div><div class="result-stat"><strong>'+money(known.length?cost:null)+'</strong><span>Known cost estimate'+(unresolved?' · incomplete billing':'')+'</span></div><div class="result-stat"><strong>'+job.completed+' / '+job.total+'</strong><span>Attempts finished'+(total-assessed.length?' · '+(total-assessed.length)+' execution issues':'')+'</span></div>';
  $('#result-rows').innerHTML=results.map((r,i)=>'<tr><td><button class="result-link" data-index="'+i+'">'+esc(taskTitle(r.task))+'<small>'+esc(modelName(r.model))+'</small></button></td><td class="'+(String(r.termination||'').startsWith('infra:')?'neutral':r.passed?'pass':'fail')+'">'+(r.passed?'Passed':r.termination==='completed'?'Checks failed':esc(human(r.termination||'Not evaluated')))+'</td><td>'+(knownNumber(r.seconds)?Number(r.seconds).toFixed(1)+'s':'Not available')+'</td><td>'+money(r.cost_usd)+(r.flags?.includes('billing=unknown')?' + held':'')+'</td><td>'+(knownNumber(r.tool_calls)?r.tool_calls:'Not available')+'</td></tr>').join('')||'<tr><td colspan="5" class="results-empty"><strong>No finished attempts yet</strong><p>'+(['queued','running','cancelling'].includes(job.status)?'Results appear here as work finishes. Open Activity to follow the current task.':'This run ended before an attempt finished. Check the run message and activity for details.')+'</p></td></tr>';
  $$('[data-index]').forEach(button=>button.onclick=()=>{
    const r=results[Number(button.dataset.index)];taskId=r.task;$('#task-select').value=taskId;
    selected={node:'result',model:r.model,label:'Task result',category:'result',status:r.passed?'completed':'error',output:r.output,result:r};
    revealSelection();
  });
  if(focused!==undefined)$$('[data-index]').find(b=>b.dataset.index===focused)?.focus({preventScroll:true});
}
function switchView(next) {
  view=next;
  $$('[data-view]').forEach(b=>{
    const active=b.dataset.view===view;
    b.classList.toggle('active',active); b.setAttribute('aria-selected',String(active));b.tabIndex=active?0:-1;
  });
  for(const key of ['report','live','results'])$('#'+key+'-view').classList.toggle('hidden',!job||view!==key);
  if(view==='live')renderGraph(); else if(view==='results')renderResults(); else renderReport();
}
function taskTitle(id){return state.tasks.find(t=>t.id===id)?.title||human(id)}
function modelName(id){const arm=job?.settings?.arms?.find(a=>a.id===id);if(arm)return arm.name;const [base,effort]=id.split('@');return (state.models.find(m=>m.id===base)?.name||base)+(effort?' · '+effort+' reasoning':'')}
function armKind(id){const arm=job?.settings?.arms?.find(a=>a.id===id);return arm?arm.kind:state.models.find(m=>m.id===id.split('@')[0])?.kind||'Setup'}
function filteredTasks(){const q=$('#task-search').value.trim().toLowerCase(),category=$('#task-category').value;return state.tasks.filter(t=>(!category||t.category===category)&&(!$('#task-difficulty').value||(t.difficulty?.level||'unrated')===$('#task-difficulty').value)&&(t.title+' '+t.brief+' '+(t.applications||[]).join(' ')).toLowerCase().includes(q))}
function renderTaskOptions(){const filtered=filteredTasks();$('#task-options').innerHTML=filtered.length?filtered.map(t=>'<label class="task-option"><input type="checkbox" value="'+esc(t.id)+'" '+(selectedTasks.has(t.id)?'checked':'')+'><span><strong>'+esc(t.title)+'</strong><small>'+esc(t.category)+' · '+esc((t.applications||[]).join(' + '))+'</small></span>'+'</label>').join(''):'<p class="jobs-empty">No requests match these filters.</p>';$$('#task-options input').forEach(i=>i.onchange=()=>{i.checked?selectedTasks.add(i.value):selectedTasks.delete(i.value);$('#task-set').value='custom';launchSize()});launchSize()}
function preserveArchitectureModels(){return selectedArchitectureIds.size>0&&$('#architecture-choice').value!=='default-monarch-enterprise'&&$('#architecture-model-mode').value==='saved';}
function armCount(){if(preserveArchitectureModels())return selectedArchitectureIds.size;return $('#architecture-choice').value==='default-monarch-enterprise'?1:selectedModels.size*(1+($('#include-bare').checked?1:0))}
function requestFloor(){let floor=0;for(const id of preserveArchitectureModels()?[]:selectedModels){const m=state.models.find(x=>x.id===id.split('@')[0]);floor=Math.max(floor,Number(m?.request_ceiling_usd||state.capabilities?.controls?.find(c=>c.id===m?.control)?.request_ceiling_usd||0));}for(const id of selectedArchitectureIds){floor=Math.max(floor,Number(state.capabilities?.versions?.find(v=>v.id===id)?.request_ceiling_usd||0));}return floor;}
function launchSize() {
  if(!state)return;

  $('#selected-count').textContent=selectedTasks.size+' '+(selectedTasks.size===1?'task':'tasks')+' selected';
  renderTaskSelection();
  renderBareWarning();
  clearTimeout(bareCoverageTimer);bareCoverageTimer=setTimeout(checkBareCoverage,250);
  const arms=armCount(), floor=requestFloor(), amount=Number($('#run-budget').value);
  const low=floor>0&&amount<floor;
  $('#launch-size').textContent=selectedTasks.size*arms?selectedTasks.size*arms+' '+plural(selectedTasks.size*arms,'attempt')+' planned':(selectedTasks.size?selectedTasks.size+' tasks selected · choose setups next':(launchStep===0?'Choose an architecture and models':'Choose the work to test'));
  $('#budget-floor').textContent=low?'Set at least '+money(floor)+' to cover the largest single request reservation.':knownNumber(state.budget?.available)&&amount>Number(state.budget.available)?'Only '+money(state.budget.available)+' remains in this week’s capacity.':'';
  $('#run-capacity-note').textContent=capacityNote();
  const error=launchIssue();
  $('#launch-validation').textContent=launchStep===2?error:'';
  $('#launch-button').disabled=launching||!!error;
  $('#launch-button').textContent=launching?'Starting…':'Start run · '+money(amount)+' max';
  $('#launch-next').disabled=launching||(launchStep===0?!arms||!$('#architecture-choice').value||!!bareLaunchError():!selectedTasks.size||selectedTasks.size>800);
  $('#launch-back').disabled=launching;
  $$('[data-launch-step]').forEach(b=>b.disabled=launching||(Number(b.dataset.launchStep)>0&&(!armCount()||!$('#architecture-choice').value))||(Number(b.dataset.launchStep)>1&&!selectedTasks.size));
  $('#clear-tasks').disabled=!selectedTasks.size;
  const matching=filteredTasks(), all=matching.length&&matching.every(t=>selectedTasks.has(t.id));
  $('#select-all').textContent=all?'Deselect matching':'Select matching';$('#select-all').disabled=!matching.length;
  const outside=[...selectedTasks].filter(id=>!matching.some(t=>t.id===id)).length;
  $('#task-match-count').textContent=matching.length+' matching'+(outside?' · '+outside+' selected outside filters':'');
  if(launchStep===2)renderLaunchReview();
}
const plural=(n,word)=>n===1?word:word+'s';
function launchIssue() {
  if(!selectedTasks.size)return 'Choose at least one task.';
  if(selectedTasks.size>800)return 'Select no more than 800 tasks.';
  if(!$('#architecture-choice').value)return 'Choose an architecture.';
  if(bareLaunchError())return bareLaunchError();
  const arms=armCount();if(!arms)return 'Add at least one setup to compare.';
  if(arms>12)return 'Compare up to 12 setups in one run.';
  if(!$('#run-title').value.trim())return 'Name this run before starting.';
  const amount=Number($('#run-budget').value);
  if(!Number.isFinite(amount)||amount<=0||amount>300||!$('#run-budget').validity.valid)return 'Use a budget between $0.01 and $300, with at most two decimal places.';
  if(amount<requestFloor())return 'Increase the budget to cover the largest request reservation.';
  if(knownNumber(state.budget?.available)&&amount>Number(state.budget.available))return 'The budget exceeds this week’s available capacity.';
  if(!$('#run-concurrency').validity.valid)return 'Choose a concurrent agent count within the workspace capacity.';
  if(!$('#run-turns').value||!$('#run-turns').validity.valid)return 'Use a turn limit between 1 and 50.';
  return '';
}
function evaluationWords(){return $('#run-track').value==='create-and-run'?'Build and execute workflows':'Complete agentic requests';}
function launchSetupRows(){if(preserveArchitectureModels())return [...selectedArchitectureIds].map(id=>({id,name:state.capabilities?.versions.find(v=>v.id===id)?.name||id,detail:'Published models and thinking settings',version:true}));const v=state.capabilities?.versions.find(v=>selectedArchitectureIds.has(v.id));if(v?.id==='default-monarch-enterprise')return [{id:v.id,name:v.name,detail:'Monarch configuration',version:true}];const rows=[...selectedModels].map(id=>{const [base,effort]=id.split('@'),m=state.models.find(x=>x.id===base);return {id,name:m?.name||base,detail:(v?v.name:'API control')+(effort?' · '+effort+' thinking':''),model:m,effort};});return rows.concat($('#include-bare').checked?rows.map(r=>({...r,id:r.id+'-bare',detail:'Bare · native harness · '+(r.effort||'default')+' thinking',bare:true})):[]);}

function renderLaunchReview(){
 const rows=launchSetupRows();
 $('#launch-review').innerHTML='<div class="review-equation"><strong>'+selectedTasks.size+'</strong> '+plural(selectedTasks.size,'task')+' <span>×</span> <strong>'+rows.length+'</strong> '+plural(rows.length,'setup')+' <span>=</span> <strong>'+selectedTasks.size*rows.length+'</strong> '+plural(selectedTasks.size*rows.length,'attempt')+'</div><div class="review-line"><div><strong>'+esc(evaluationWords())+'</strong><p>'+esc(($('#task-set').value==='custom'?'Custom task selection':$('#task-set').selectedOptions[0]?.textContent)||'Custom task selection')+'</p></div><button type="button" class="text-button" data-review-edit="1">Edit tasks</button></div><div class="review-setups">'+rows.map(r=>'<div><strong>'+esc(r.name)+'</strong><span>'+esc(r.detail)+'</span></div>').join('')+'<button type="button" class="text-button" data-review-edit="0">Edit setup & models</button></div>';
 $$('[data-review-edit]').forEach(b=>b.onclick=()=>setLaunchStep(Number(b.dataset.reviewEdit)));

}
function setLaunchStep(step,focus=true) {
  if(step>0&&(!armCount()||!$('#architecture-choice').value||bareLaunchError()))return;
  if(step>1&&!selectedTasks.size)return;
  launchStep=Math.max(0,Math.min(2,step));
  if(launchStep===2&&!$('#run-title').value.trim())$('#run-title').value=selectedTasks.size+' '+plural(selectedTasks.size,'task')+' · '+evaluationWords();
  $$('[data-launch-panel]').forEach(p=>p.classList.toggle('hidden',Number(p.dataset.launchPanel)!==launchStep));
  $$('[data-launch-step]').forEach(b=>{b.setAttribute('aria-current',Number(b.dataset.launchStep)===launchStep?'step':'false');b.disabled=launching;});
  $('#launch-back').classList.toggle('hidden',launchStep===0);$('#launch-next').classList.toggle('hidden',launchStep===2);$('#launch-button').classList.toggle('hidden',launchStep!==2);
  $('#launch-next').textContent=launchStep===0?'Choose tasks':'Review run';
  launchSize();
  $('#form-error').textContent='';
  if(focus){const heading=$('[data-launch-panel="'+launchStep+'"] .step-heading');heading.tabIndex=-1;heading.focus();window.scrollTo({top:0,behavior:'instant'});}
}
$('#run-budget').oninput=launchSize;$('#run-concurrency').oninput=launchSize;
async function openLaunch(options={}) {
 if(!state||launching||(launchOpening&&workspaceSurface==='launch'))return;
 launchOpening=true;
 if(workspaceSurface!=='launch'){window.showWorkspaceSurface?.('launch');setLaunchStep(0,false);$('#launch-title').focus();}
 $('#launch-loading').classList.remove('hidden');$('#launch-next').disabled=true;
 try{
  const [latest,matrix,sets,runtime]=await Promise.all([api('/api/state'),api('/api/capabilities'),api('/api/task-sets').catch(()=>({items:[]})),api('/api/runtime').catch(()=>null)]);
  state.models=latest.models.filter(m=>!['oracle','sloppy'].includes(m.id));state.tasks=latest.tasks;state.token=latest.token;state.capabilities=matrix;budget(latest.budget);state.runtime=runtime;if(runtime?.max_agents)$('#run-concurrency').max=runtime.max_agents;
  restoreRunDraft();
  selectedModels=new Set([...selectedModels].filter(id=>state.models.some(m=>m.available&&m.id===id.split('@')[0])));
  selectedTasks=new Set([...selectedTasks].filter(id=>state.tasks.some(t=>t.id===id)));
  $('#task-category').innerHTML='<option value="">All categories</option>'+[...new Set(state.tasks.map(t=>t.category))].sort().map(c=>'<option value="'+esc(c)+'">'+esc(c)+'</option>').join('');
  const sample=sets.items.find(t=>t.id==='catalog-50');if(sample)sets.items.unshift({id:'catalog-10',name:'10-task sample',tasks:sample.tasks.slice(0,10)});
  launchTaskSets=sets.items;const current=restoredTaskSet||$('#task-set').value;restoredTaskSet=null;
  $('#task-set').innerHTML='<option value="">Choose a saved selection…</option>'+sets.items.map(t=>'<option value="'+esc(t.id)+'">'+esc(t.name)+' · '+t.tasks.length+' tasks</option>').join('')+'<option value="custom">Choose individual tasks</option>';
  if([...$('#task-set').options].some(o=>o.value===current))$('#task-set').value=current;
  if(options.version){const v=matrix.versions.find(v=>v.id===options.version);if(v){$('#run-track').value=v.track||'agentic-request';selectedArchitectureIds=new Set([v.id]);}}
  await renderComparisonVersions();renderTaskOptions();
  if(!sets.items.length){$('#task-set').value='custom';$('#task-browser').open=true;}
  $('#form-error').textContent='';
 }catch(error){$('#form-error').textContent='Could not load run choices. '+error.message;}
 finally{launchOpening=false;$('#launch-loading').classList.add('hidden');launchSize();}
}

$('#new-comparison').onclick=openLaunch;$('#empty-start').onclick=openLaunch;$('#close-dialog').onclick=cancelLaunch;$('#task-search').oninput=renderTaskOptions;$('#select-all').onclick=()=>{$('#task-set').value='custom';const ids=filteredTasks().map(t=>t.id);const all=ids.every(id=>selectedTasks.has(id));ids.forEach(id=>all?selectedTasks.delete(id):selectedTasks.add(id));renderTaskOptions()};$('#task-select').onchange=e=>{taskId=e.target.value;clearSelection();renderGraph()};$('#fit-view').onclick=()=>$('#graph-scroll').scrollTo({top:0,left:0,behavior:'smooth'});$$('[data-view]').forEach(b=>b.onclick=()=>switchView(b.dataset.view));$$('[data-output]').forEach(b=>b.onclick=()=>{setOutputMode(b.dataset.output);renderOutput();bindEvidence()});$('#copy-output').onclick=async()=>{
  if(!selected)return toast('Select an output first');
  const raw={arguments:selected.arguments,output:selected.output,status:selected.status,...(selected.result?{checks:selected.result.checks,termination:selected.result.termination,flags:selected.result.flags,unexpected_changes:selected.result.unexpected_changes,report:selected.report}:{})};
  try {await navigator.clipboard.writeText(outputMode==='raw'?JSON.stringify(raw,null,2):typeof selected.output==='string'?selected.output:JSON.stringify(selected.output??null,null,2));toast('Output copied');}
  catch {toast('Clipboard access is unavailable. Select and copy the text in the evidence panel.');}
};
for(const action of ['pause','resume'])$('#'+action+'-run').onclick=async()=>{
  if(!job||$('#'+action+'-run').disabled)return;
  const id=job.id;$('#pause-run').disabled=true;$('#resume-run').disabled=true;
  try{const next=await api('/api/jobs/'+id+'/'+action,{});if(job?.id===id)syncJob(next);}
  catch(error){toast(error.message);if(job?.id===id)syncJob(job);}
};
$('#cancel-run').onclick=async()=>{
  if(!job||$('#cancel-run').disabled)return;
  const id=job.id;$('#cancel-run').disabled=true;
  try {const next=await api('/api/jobs/'+id+'/cancel',{});if(job?.id===id)syncJob(next);toast(next.status==='cancelled'?'Run cancelled':'Cancelling active work');}
  catch(error){toast(error.message);if(job?.id===id)$('#cancel-run').disabled=false;}
};
$('#launch-form').onsubmit=async e=>{
  e.preventDefault();if(launching)return;
  if(launchStep<2){if(!$('#launch-next').disabled)setLaunchStep(launchStep+1);return;}
  const issue=launchIssue();if(issue){$('#form-error').textContent=issue;$('#form-error').focus();return;}
  const payload={title:$('#run-title').value.trim(),tasks:[...selectedTasks],models:preserveArchitectureModels()?[]:[...selectedModels],architectures:selectedVersions(),comparison_models:!preserveArchitectureModels()&&selectedArchitectureIds.size>0&&$('#architecture-choice').value!=='default-monarch-enterprise',bare_models:$('#include-bare').checked?bareSelections().map(x=>x.selection):[],maximum_usd:$('#run-budget').value,track:$('#run-track').value,concurrency:Number($('#run-concurrency').value),components:Object.fromEntries($$('[data-component-role]').map(e=>[e.dataset.componentRole,e.value])),configuration:{prompt:$('#run-prompt').value,max_turns:Number($('#run-turns').value)}};
  const fingerprint=JSON.stringify(payload);
  if(launchRequest&&launchRequest.fingerprint!==fingerprint){$('#form-error').textContent='The previous start has an uncertain response. Restore those selections and retry, or reload the workspace to find the run before starting another.';return;}
  if(!launchRequest)launchRequest={id:crypto.randomUUID().replaceAll('-',''),fingerprint};
  launching=true;launchSize();$('#form-error').textContent='';
  try {
    const created=await api('/api/jobs',{...payload,request_id:launchRequest.id});
    launchRequest=null;try{localStorage.removeItem('ailabs-run-draft');}catch{}$('#close-setup')?.click();
    await openJob(created.id);
  } catch(error) {
    if(!error.uncertain)launchRequest=null;
    $('#form-error').textContent=error.message+(error.uncertain?' Retry with the same selections to recover this run without starting a duplicate.':'');$('#form-error').focus();
  } finally {launching=false;launchSize();}
};
function setConnection(text,status){$('#connection').textContent=text;$('#connection').dataset.status=status;}
function showConnectionError(message){setConnection('Connection unavailable','error');$('#connection-error-detail').textContent=message;$('#connection-error').classList.remove('hidden');}
async function initialize() {
  const button=$('#retry-connection');button.disabled=true;
  try {
    const latest=await api('/api/state');state=latest;budget(state.budget);setConnection('Connected','connected');$('#connection-error').classList.add('hidden');
    renderJobs();renderSetups();
    if(pendingJobId)await openJob(pendingJobId);else if(location.hash.startsWith('#run/'))await openJob(decodeURIComponent(location.hash.slice(5)));else if(location.hash==='#launch')await openLaunch();else if(location.hash==='#genesis')await openGenesis();else if(location.hash==='#budget')await openBudget();else if(location.hash==='#studio')await $('#open-setup').onclick();else if(location.hash==='#runtime')await $('#nav-runtime').onclick();else if(location.hash==='#runs')window.showWorkspaceSurface('runs');else if(window.reportRoute&&(location.hash===''||location.hash==='#'||location.hash==='#reports'||location.hash==='#leaderboard'||location.hash.startsWith('#report/')||location.hash.startsWith('#round/')))await window.reportRoute(location.hash);else if(window.showWorkspaceSurface)window.showWorkspaceSurface('runs');
  } catch(error){showConnectionError(error.message);}
  finally {button.disabled=false;}
}
$('#retry-connection').onclick=initialize;
$('#run-search').oninput=renderJobs;
$('#close-inspector').onclick=()=>clearSelection(true);
$('#launch-next').onclick=()=>setLaunchStep(launchStep+1);
$('#launch-back').onclick=()=>setLaunchStep(launchStep-1);
$$('[data-launch-step]').forEach(b=>b.onclick=()=>setLaunchStep(Number(b.dataset.launchStep)));
$('#run-title').oninput=launchSize;$('#run-turns').oninput=launchSize;
$('#clear-tasks').onclick=()=>{selectedTasks.clear();$('#task-set').value='custom';renderTaskOptions();};
$('#reset-task-filters').onclick=()=>{$('#task-search').value='';$('#task-category').value='';$('#task-difficulty').value='';renderTaskOptions();$('#task-search').focus();};
$('.tabs').addEventListener('keydown',e=>{
  const tabs=$$('[data-view]'),index=tabs.indexOf(document.activeElement);
  if(index<0||!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;
  e.preventDefault();const next=e.key==='Home'?0:e.key==='End'?tabs.length-1:(index+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;
  tabs[next].click();tabs[next].focus();
});
window.addEventListener('DOMContentLoaded', initialize, {once:true});
function actionSummary(node){const account=report?.attempts.find(a=>a.task===taskId&&a.model===node.model);return account?.actions.find(a=>a.node===node.node)?.detail||(node.category==='model'?'Considering the request and the evidence collected so far.':node.status==='running'?'This action is in progress.':'Open the recorded response for this action.')}
function shortTaskLabel(id) {
  const title=taskTitle(id).split(/(?<=[.!?])\s/)[0];
  if(title.length<=90)return title.replace(/[.]$/, '');
  return title.slice(0,87).replace(/\s+\S*$/, '')+'…';
}
function outcomeFinding(a) {
  if(a.infrastructure)return a.summary||'Execution stopped before assessment';
  if(a.unexpected_changes?.length)return a.change_summaries?.[0]||'Changes outside the request';
  const missed=a.requirements.filter(c=>!c.passed);
  return missed.length?'Not met: '+missed[0].title:a.passed?'All requirements met':'Task checks failed';
}
function criticalAnalysis(a) {
  const review=report?.analysis;
  const heading=a.passed?'Why it succeeded':'How it failed';
  if(!review||review.status!=='completed')return '<section class="critical-analysis"><h3>'+heading+'</h3><p>'+(review?.status==='failed'?'Analysis could not complete. Review retained billing before retrying.':'The checks establish the verdict. The failure mechanism has not been reviewed yet.')+'</p><button type="button" class="button" data-review-run '+(analysisPending.has(job.id)||review?.status==='failed'?'disabled':'')+'>'+(analysisPending.has(job.id)?'Analyzing…':'Analyze evidence')+'</button><small>Paid review uses this run’s remaining budget.</small></section>';
  const ids=new Set(a.event_ids);
  const findings=review.findings.filter(f=>f.event_ids.some(id=>ids.has(id)));
  return '<section class="critical-analysis"><h3>'+heading+'</h3>'+(findings.length?findings.map((f,i)=>'<details class="finding-section" '+(i===0?'open':'')+'><summary>'+esc(f.title)+'</summary><span class="finding-kind">'+(f.kind==='fact'?'Observed evidence':'Hypothesis — untested')+'</span><p>'+esc(f.explanation)+'</p><div class="finding-evidence">'+f.event_ids.map(evidenceButton).join('')+'</div></details>').join(''):'<p>No cited finding covers this attempt.</p>')+'<details class="finding-section"><summary>Test the explanation</summary><p>'+esc(review.next_experiment)+'</p></details><details class="finding-section"><summary>Uncertainty</summary><p>'+esc(review.limitations)+'</p><small>'+esc(review.basis||'Model interpretation; citations require review')+'. The recorded verdict is unchanged.</small></details></section>';
}
function reportDetails(a){
  const brief=state.tasks.find(t=>t.id===a.task)?.brief||taskTitle(a.task);
  return '<div class="finding-heading"><h3>'+esc(outcomeFinding(a))+'</h3></div>'+criticalAnalysis(a)
    +'<details class="finding-section"><summary>Task instructions</summary><p>'+esc(brief)+'</p></details>'
    +'<details class="finding-section"><summary>Assessment</summary><p>'+esc(a.summary)+'</p><p class="report-caveat">'+esc(a.limitations)+'</p></details>'
    +'<details class="finding-section"><summary>Next question</summary><p>'+esc(a.next_question)+'</p></details>';
}
let evidenceReturn=null;
function showEvidencePopup(title,html,back=null) {
  const dialog=$('#evidence-dialog');
  $('#evidence-title').textContent=title;
  $('#evidence-body').innerHTML=html;
  $('#evidence-back').hidden=!back;
  $('#evidence-back').onclick=()=>{if(back)showEvidencePopup(back.title,back.html);};
  bindEvidence();
  if(!dialog.open){evidenceReturn=document.activeElement;dialog.showModal();}
  $('#evidence-close').focus();
}
$('#evidence-close').onclick=()=>$('#evidence-dialog').close();
$('#evidence-dialog').addEventListener('close',()=>{if(evidenceReturn?.isConnected)evidenceReturn.focus({preventScroll:true});evidenceReturn=null;});
$('#expand-output').onclick=()=>showEvidencePopup($('#inspector-title').textContent,$('#output').innerHTML);
function selectReport(index) {
  const a=report?.attempts[index];if(!a)return;
  const result=job.results.find(r=>r.task===a.task&&r.model===a.model);
  if(!result)return toast('The result is still arriving. Try again shortly.');
  taskId=a.task;$('#task-select').value=taskId;
  selected={node:'result',category:'result',model:a.model,status:a.passed?'completed':'error',output:result.output,result,report:a};
  revealSelection();
}
function setOutputMode(mode) {
  outputMode=mode;
  $$('[data-output]').forEach(b=>{const active=b.dataset.output===mode;b.classList.toggle('active',active);b.setAttribute('aria-selected',String(active));b.tabIndex=active?0:-1;});
}
function bindEvidence() {
  $$('[data-review-run]').forEach(b=>b.onclick=()=>{b.disabled=true;b.textContent='Analyzing…';$('#analyze-run')?.click();});
  $$('[data-evidence]').forEach(b=>b.onclick=()=>{
    const event=events.find(e=>e.id===Number(b.dataset.evidence));
    if(!event)return toast('Evidence is still loading. Try again shortly.');
    const action=report?.attempts.flatMap(a=>a.actions).find(a=>Number(a.event_id)===event.id);
    const node=nodeList(event.model).find(n=>n.node===event.node);
    const input=event.arguments!==undefined?event.arguments:node?.arguments;
    const output=event.output!==undefined?event.output:node?.output;
    const back=$('#evidence-dialog').open?{title:$('#evidence-title').textContent,html:$('#evidence-body').innerHTML}:null;
    showEvidencePopup(action?.title||eventLabel(event),
      (action?.detail?'<p class="evidence-description">'+esc(action.detail)+'</p>':'')
      +(input!==undefined?'<h3>Input</h3>'+pretty(input):'')
      +(output!==undefined?'<h3>Output</h3>'+pretty(output):'')
      +'<details class="finding-section"><summary>Raw record #'+event.id+'</summary><pre>'+esc(JSON.stringify(event,null,2))+'</pre></details>',back);

  });
}
function renderReport(){if(!job||!report)return;const focused=document.activeElement?.dataset?.report;const reviewOpen=$('#reasoning-review')?.open;const attempts=report.attempts,valid=attempts.filter(a=>!a.infrastructure);const modelRows=job.settings.models.map(m=>{const rows=attempts.filter(a=>a.model===m),measured=rows.filter(a=>!a.infrastructure),passed=measured.filter(a=>a.passed).length;return '<div class="comparison-bar"><strong>'+esc(modelName(m))+'</strong><progress class="outcome-track" max="100" value="'+(measured.length?passed/measured.length*100:0)+'" aria-label="Requirements met"></progress><span>'+passed+' / '+measured.length+' met</span>'+(rows.some(a=>a.infrastructure)?'<small class="fail">'+rows.filter(a=>a.infrastructure).length+' execution issues</small>':'')+'</div>'}).join('');const analysis=report.analysis;$('#report-view').innerHTML='<div class="report-intro"><h3>'+ (attempts.length?'Task outcomes':['queued','running','cancelling'].includes(job.status)?'The work is underway':'No evaluated outcomes')+'</h3><p>'+(attempts.length?valid.filter(a=>a.passed).length+' of '+valid.length+' passed. '+(attempts.length-valid.length?attempts.length-valid.length+' attempts could not be evaluated.':''):(['queued','running','cancelling'].includes(job.status)?'Task outcomes appear as each attempt finishes. You can follow the activity while they run.':'This run ended before any task could be evaluated. Check the run message and Activity for what happened.'))+'</p></div>'+(job.settings.models.length>1?'<div class="comparison-bars">'+modelRows+'</div>':'')+'<div class="outcome-list">'+attempts.map((a,i)=>'<button class="outcome-card" data-report="'+i+'"><div class="outcome-top"><span class="outcome-label '+(a.infrastructure?'neutral':a.passed?'pass':'fail')+'">'+(a.infrastructure?'Execution issue':a.passed?'Requirements met':'Needs investigation')+'</span><small>'+esc(modelName(a.model))+'</small></div><h4>'+esc(shortTaskLabel(a.task))+'</h4><p>'+esc(outcomeFinding(a))+'</p><span class="outcome-arrow" aria-hidden="true">→</span></button>').join('')+'</div><details id="reasoning-review" class="analysis-section" '+(reviewOpen?'open':'')+'><summary>Reasoning review'+(analysis?.status==='completed'?' · Available':analysis?.status==='failed'?' · Failed':analysisPending.has(job.id)?' · Running':' · Optional')+'</summary>'+(analysis?.status==='completed'?'<p>'+esc(analysis.summary)+'</p>'+analysis.findings.map(f=>'<article class="analysis-finding"><h4>'+esc(f.title)+' <small>'+esc(f.kind)+'</small></h4><p>'+esc(f.explanation)+'</p>'+f.event_ids.map(evidenceButton).join('')+'</article>').join('')+'<h4>Next experiment</h4><p>'+esc(analysis.next_experiment)+'</p><p class="report-caveat">'+esc(analysis.limitations)+' · '+esc(analysis.model)+' / '+esc(analysis.effort)+'</p>':analysis?.status==='failed'?'<p class="fail">'+esc(analysis.error)+'</p>':'<button class="button" id="analyze-run" '+(!attempts.length||analysisPending.has(job.id)||['queued','running','cancelling'].includes(job.status)?'disabled':'')+'>Analyze this run · Gemini medium</button><p class="report-caveat">Paid analysis uses the remaining run budget and weekly limit. Interpretations do not change task verdicts.</p>')+'</details>';$$('[data-report]').forEach(b=>b.onclick=()=>selectReport(Number(b.dataset.report)));bindEvidence();if(focused!==undefined)$$('[data-report]').find(b=>b.dataset.report===focused)?.focus({preventScroll:true});if($('#analyze-run'))$('#analyze-run').onclick=async()=>{
  const reviewId=job.id;if(analysisPending.has(reviewId))return;
  analysisPending.add(reviewId);const button=$('#analyze-run');button.disabled=true;button.textContent='Reading the execution…';
  try {
    const analysis=await api('/api/jobs/'+reviewId+'/analyze',{});
    if(job?.id===reviewId)report.analysis=analysis;
    budget((await api('/api/state')).budget);
  } catch(error) {toast(error.message);}
  finally {analysisPending.delete(reviewId);if(job?.id===reviewId){renderReport();if(selected?.report){renderOutput();bindEvidence();}}}
};}
$('#task-category').onchange=renderTaskOptions;
function renderSetups(){}

function difficultyBadge(task){const d=task.difficulty||{level:'unrated',attempts:0,description:'No comparable scored attempts yet.'};const heights=[5,9,14];const filled={easy:1,medium:2,hard:3,unrated:0}[d.level];return '<span class="difficulty-badge '+esc(d.level)+'" title="'+esc(d.description)+'" aria-label="'+esc(d.level+' difficulty. '+d.description)+'"><svg viewBox="0 0 22 18" aria-hidden="true">'+heights.map((h,i)=>'<rect x="'+(i*7)+'" y="'+(17-h)+'" width="5" height="'+h+'" rx="1" class="'+(i<filled?'filled':'')+'"/>').join('')+'</svg><span>'+esc(d.level)+(d.provisional&&d.attempts?'*':'')+'<small>'+d.attempts+' '+plural(d.attempts,'attempt')+'</small></span></span>'}
$('#task-difficulty').onchange=renderTaskOptions;

function readinessText(r){return ({adapter_required:'Execution integration pending',preparation_required:'Verification needed',blocked:'Blocked',unsupported:'Unsupported configuration',source_required:'Historical source not recovered'}[r.runtime]||r.runtime)+(r.reasons&&r.reasons.length?' · '+r.reasons[0]:'')}
async function renderComparisonVersions(preselect){
 if(!state.capabilities)state.capabilities=await api('/api/capabilities');
 const track=$('#run-track').value;
 const eligible=state.capabilities.versions.filter(v=>v.id!=='without-monarch'&&(v.track||(v.id==='default-monarch-enterprise'?'create-and-run':'agentic-request'))===track);
 selectedArchitectureIds=new Set([...selectedArchitectureIds].filter(id=>eligible.some(v=>v.id===id&&v.readiness.launchable)));
 if(preselect&&eligible.some(v=>v.id===preselect&&v.readiness.launchable))selectedArchitectureIds.add(preselect);
 const seen=new Set(),models=state.models.filter(m=>{const key=[m.provider,m.configuration?.model||m.name,m.configuration?.effort||'catalog'].join('|');if(seen.has(key))return false;seen.add(key);return true;});
 const modelOptions=kind=>models.filter(m=>kind==='native'?m.kind==='Native harness':m.kind!=='Native harness').map(m=>'<option value="model:'+esc(m.id)+'" '+(!m.available?'disabled':'')+'>'+esc(m.name)+(m.available?'':' — unavailable')+'</option>').join('');
 const selected=$('#setup-catalog').value;
 $('#setup-catalog').innerHTML='<option value="">Choose a model…</option>'+modelOptions('api');
 const chosen=[...selectedArchitectureIds][0]||$('#architecture-choice').value;$('#architecture-choice').innerHTML='<option value="">Choose an architecture…</option>'+eligible.map(v=>'<option value="'+esc(v.id)+'" '+(!v.readiness.launchable?'disabled':'')+'>'+esc(v.name)+(v.readiness.launchable?'':' — unavailable')+'</option>').join('')+'<option value="without-monarch">API control · no architecture</option>';if([...$('#architecture-choice').options].some(o=>o.value===chosen&&!o.disabled))$('#architecture-choice').value=chosen;

 if([...$('#setup-catalog').options].some(o=>o.value===selected&&!o.disabled))$('#setup-catalog').value=selected;
 $('#comparison-readiness').innerHTML=[...models.filter(m=>!m.available).map(m=>'<p><strong>'+esc(m.name)+'</strong><br>'+esc(m.kind==='Native harness'?'The isolated native runtime is not ready yet.':m.reason||'Connection required.')+'</p>'),...eligible.filter(v=>!v.readiness.launchable).map(v=>'<p><strong>'+esc(v.name)+'</strong><br>'+esc(v.readiness.reasons?.[0]||'Verify the runtime in Settings.')+'</p>')].join('')||'<p>All configured setups are available.</p>';
 $$('[data-track]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.track===track));
 renderSelectedSetups();setupChoiceChanged();updateArchitectureNote();launchSize();
}
function selectedVersions(){return selectedArchitectureIds.size?[...selectedArchitectureIds]:['without-monarch'];}
function setupChoiceChanged(){
 const key=$('#setup-catalog').value,m=key.startsWith('model:')?state.models.find(m=>m.id===key.slice(6)):null;
 $('#setup-effort-label').classList.toggle('hidden',!m?.efforts?.length);
 $('#setup-effort').innerHTML=(m?.efforts||[]).map(e=>'<option value="'+esc(e)+'" '+(e===m.default_effort?'selected':'')+'>'+esc(e)+(e===m.default_effort?' · default':'')+'</option>').join('');
 $('#add-setup').disabled=!key||armCount()>=12;
 $('#setup-choice-note').textContent=!key?'':m?(m.kind==='Native harness'?'Bare runs the task in the model’s native harness, without a workflow methodology.':'API control uses the lab’s API loop. It is measured separately from native Bare.'):'Choose a model to run this architecture.';
}
function renderSelectedSetups(){
 $('#add-setup').disabled=!$('#setup-catalog').value||armCount()>=12;
 const rows=launchSetupRows().filter(r=>r.model&&!r.bare);
 $('#selected-setups').innerHTML=rows.length?'<div class="setup-list">'+rows.map(r=>'<div class="selected-setup"><div><strong>'+esc(r.name)+'</strong><small>'+esc(r.detail)+'</small></div>'+(r.model?.efforts?.length?'<label>Reasoning<select data-setup-effort="'+esc(r.id)+'">'+r.model.efforts.map(e=>'<option value="'+esc(e)+'" '+(e===r.effort?'selected':'')+'>'+esc(e)+'</option>').join('')+'</select></label>':'<span class="setup-fixed">Saved settings</span>')+'<button type="button" class="text-button" data-remove-setup="'+esc(r.id)+'" aria-label="Remove '+esc(r.name)+'">Remove</button></div>').join('')+'</div>':'<div class="setup-empty"><h4>No models selected</h4></div>';
 $$('[data-remove-setup]').forEach(b=>b.onclick=()=>{selectedModels.delete(b.dataset.removeSetup);selectedArchitectureIds.delete(b.dataset.removeSetup);renderSelectedSetups();launchSize();});
 $$('[data-setup-effort]').forEach(input=>input.onchange=()=>{const old=input.dataset.setupEffort,next=old.split('@')[0]+'@'+input.value;if(selectedModels.has(next)&&next!==old){$('#setup-error').textContent='That model and reasoning level are already in this run.';renderSelectedSetups();return;}selectedModels.delete(old);selectedModels.add(next);$('#setup-error').textContent='';renderSelectedSetups();launchSize();});
}
$('#setup-catalog').onchange=setupChoiceChanged;
$('#add-setup').onclick=()=>{
 const key=$('#setup-catalog').value;if(!key)return;
 if(key.startsWith('version:')){const id=key.slice(8);if(selectedArchitectureIds.has(id)){$('#setup-error').textContent='That architecture is already in this run.';return;}selectedArchitectureIds.add(id);}
 else{const base=key.slice(6),m=state.models.find(m=>m.id===base),id=base+(m.efforts?.length?'@'+$('#setup-effort').value:'');if(selectedModels.has(id)){$('#setup-error').textContent='That setup is already in this run. Choose a different model or reasoning level.';return;}selectedModels.add(id);}
 $('#setup-error').textContent='';$('#setup-catalog').value='';setupChoiceChanged();renderSelectedSetups();launchSize();
};
$$('[data-track]').forEach(b=>b.onclick=()=>{$('#run-track').value=b.dataset.track;renderComparisonVersions();});
function chooseTaskSelection(id){
 const choice=launchTaskSets.find(t=>t.id===id);
 $('#task-set').value=choice?id:'custom';
 if(choice)selectedTasks=new Set(choice.tasks);
 $('#task-browser').open=!choice;
 renderTaskOptions();
 if(!choice)$('#task-search').focus();
}
function renderTaskSelection(){
 const ids=[...selectedTasks], choice=launchTaskSets.find(t=>t.id===$('#task-set').value);
 const exact=choice&&choice.tasks.length===ids.length&&choice.tasks.every(id=>selectedTasks.has(id));
 if(choice&&!exact)$('#task-set').value='custom';
 const categories=new Map();
 const tasks=ids.map(id=>state.tasks.find(t=>t.id===id)).filter(Boolean);
 tasks.forEach(t=>categories.set(t.category||'Other',(categories.get(t.category||'Other')||0)+1));
 $('#task-set-description').textContent=tasks.length?[...categories].map(([name,n])=>n+' '+name).join(' · ')+'.':'Choose a sample or browse the catalog below.';
 $('#task-set-description').textContent+=(exact&&choice.id==='catalog-50'?' Leaderboard-eligible when every setup finishes.':tasks.length?' Not eligible for the leaderboard.':'');
 $('#selected-task-preview').hidden=!tasks.length;
 $('#selected-task-summary').textContent='Inspect '+tasks.length+' selected '+(tasks.length===1?'request':'requests');
 $('#selected-task-list').innerHTML=tasks.map(t=>'<details class="selected-request"><summary>'+esc(t.title)+'<small>'+esc((t.applications||[]).join(' · '))+'</small></summary><p>'+esc(t.brief||'No task brief available.')+'</p></details>').join('');
 $$('[data-task-preset]').forEach(b=>{const id=b.dataset.taskPreset;const active=id==='custom'?$('#task-set').value==='custom':exact&&choice.id==='catalog-'+id;b.setAttribute('aria-pressed',String(!!active));b.disabled=id!=='custom'&&!launchTaskSets.some(t=>t.id==='catalog-'+id);});
}
$('#task-set').onchange=()=>chooseTaskSelection($('#task-set').value);
$$('[data-task-preset]').forEach(b=>b.onclick=()=>chooseTaskSelection(b.dataset.taskPreset==='custom'?'custom':'catalog-'+b.dataset.taskPreset));
$('#launch-panel').addEventListener('keydown',e=>{if(e.key==='Escape'&&!e.defaultPrevented){e.preventDefault();cancelLaunch();}});

function cancelLaunch(){
 // Cancel leaves the wizard; the selections stay on this browser and come back next time.
 const value={includeBare:$('#include-bare').checked,tasks:[...selectedTasks],models:[...selectedModels],architectures:[...selectedArchitectureIds],fields:Object.fromEntries(['run-track','run-title','run-budget','run-concurrency','run-prompt','run-turns','task-set','architecture-choice','architecture-model-mode'].map(id=>[id,$('#'+id).value]))};
 try{localStorage.setItem('ailabs-run-draft',JSON.stringify(value));}catch{}
 if(workspaceSurface==='launch')window.showWorkspaceSurface?.('runs');
 $('#new-comparison').focus();
}
function restoreRunDraft(){
 if(runDraftLoaded)return;runDraftLoaded=true;
 try{const draft=JSON.parse(localStorage.getItem('ailabs-run-draft')||'null');if(!draft)return;$('#include-bare').checked=!!draft.includeBare;selectedTasks=new Set(draft.tasks||[]);selectedModels=new Set(draft.models||[]);selectedArchitectureIds=new Set(draft.architectures||[]);restoredTaskSet=draft.fields?.['task-set']||null;for(const [id,value] of Object.entries(draft.fields||{})){if(['run-track','run-title','run-budget','run-concurrency','run-prompt','run-turns','architecture-choice'].includes(id))$('#'+id).value=value;} }catch{}
}

function bareSelections(){return [...selectedModels].map(id=>{const [base,level]=id.split('@'),model=state.models.find(m=>m.id===base),effort=level||model?.configuration?.effort||model?.default_effort;const native=state.models.find(m=>m.native_runner?.model===(model?.control||base)&&((m.efforts||[]).includes(effort)||m.native_runner.effort===effort));return {id,effort,native,selection:native?native.id+((native.efforts||[]).length?'@'+effort:''):null};});}
function bareLaunchError(){if(!$('#include-bare').checked)return '';if($('#run-prompt').value.trim())return 'Bare must use the original task instructions. Remove additional instructions or turn off Bare.';if(!selectedArchitectureIds.size)return 'Choose an experimental architecture before adding Bare.';if(bareSelections().some(x=>!x.native?.available))return 'A matching native Bare harness is unavailable. Turn off Bare to run the architecture alone.';return '';}
function renderBareWarning(){
 if(!state)return;const on=$('#include-bare').checked,rows=bareSelections();
 $('#bare-warning').textContent=!on?'':!rows.length?'Choose models to check their Bare comparisons.':rows.some(x=>!x.native?.available)?'Matching Bare is unavailable for '+rows.filter(x=>!x.native?.available).map(x=>modelName(x.id)).join(', ')+'. An API control is not a native Bare baseline.':'Bare runs the same tasks with the same model and thinking setting, without this architecture.';
 if(!on)$('#bare-coverage-note').textContent='';
}
function updateArchitectureNote(){const id=$('#architecture-choice').value,experimental=!!id&&!['default-monarch-enterprise','without-monarch'].includes(id);$('#architecture-model-mode').hidden=!experimental;$('#architecture-model-mode-label').hidden=!experimental;$('#comparison-model-section').hidden=!id||id==='default-monarch-enterprise'||preserveArchitectureModels();$('#architecture-choice-note').textContent=id==='default-monarch-enterprise'?'Monarch owns its model configuration. Change it in Monarch.':id==='without-monarch'?'Runs the lab API loop without an architecture. This is a control, not native Bare.':id?(preserveArchitectureModels()?'Uses each node\'s published model and thinking setting.':'Selected models replace the model in every agent node for this run.'):'Choose an architecture before adding models.';$('#setup-catalog').disabled=!id||id==='default-monarch-enterprise';}
$('#architecture-choice').onchange=()=>{const id=$('#architecture-choice').value;selectedArchitectureIds=new Set(id&&id!=='without-monarch'?[id]:[]);if(id==='default-monarch-enterprise'){selectedModels.clear();$('#include-bare').checked=false;}updateArchitectureNote();renderSelectedSetups();launchSize();};
$('#include-bare').onchange=launchSize;
$('#architecture-model-mode').onchange=()=>{if(preserveArchitectureModels())$('#include-bare').checked=false;updateArchitectureNote();renderSelectedSetups();launchSize();};

let bareCoverageKey='',bareCoverageText='',bareCoverageTimer;
async function checkBareCoverage(){
 const payload={models:[...selectedModels],tasks:[...selectedTasks],track:$('#run-track').value},key=JSON.stringify(payload);
 if(!payload.models.length||!payload.tasks.length){bareCoverageText='';return;}
 if(key===bareCoverageKey)return;bareCoverageKey=key;bareCoverageText='Checking previous Bare runs…';
 try{const report=await api('/api/bare-coverage',payload);if(key!==bareCoverageKey)return;
 const missing=report.items.reduce((n,r)=>n+r.missing.length,0);bareCoverageText=missing?'Warning: '+missing+' task/model comparisons have no recorded Bare result with the same task definition, model and thinking. Enabling Bare schedules fresh attempts and adds cost.': 'Matching Bare results are recorded for these tasks and thinking settings. Enabling Bare runs them again; historical results are not automatically reused.';
 }catch{if(key===bareCoverageKey)bareCoverageText='Previous Bare coverage could not be verified. Do not assume a baseline already exists.';}
 if(key===bareCoverageKey){$('#bare-coverage-note').textContent=$('#include-bare').checked?bareCoverageText:'';}
}
