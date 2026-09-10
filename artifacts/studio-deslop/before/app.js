'use strict';
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const knownNumber=n=>n!==null&&n!==undefined&&n!==''&&Number.isFinite(Number(n));
const money=n=>!knownNumber(n)?'Not available':Number(n).toLocaleString('en-US',{style:'currency',currency:'USD',minimumFractionDigits:2,maximumFractionDigits:Number(n)>0&&Number(n)<.01?4:2});
const human=s=>String(s).replaceAll('_',' ').replaceAll('.',' / ');
const icon=(kind='check')=>'<svg viewBox="0 0 24 24" aria-hidden="true">'+(kind==='check'?'<path d="m5 12 4 4 10-10"/>':kind==='tool'?'<path d="m4 17 9-9m1-5a6 6 0 0 0 7 7l-4 4-4-4-7 10-3-3 10-7-4-4z"/>':'<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z"/>')+'</svg>';
const emptyOutput=$('#output').innerHTML;
function clearSelection(restoreFocus=false) {
  selected=null; $('.workspace').classList.remove('has-inspector');
  $('#inspector-title').textContent='Output'; $('#inspector-meta').textContent='Select an action or result';
  $('#output').innerHTML=emptyOutput;
  if(restoreFocus) {
    const opener=selectionOpener?.isConnected?selectionOpener:$('#comparison-title');
    opener.focus({preventScroll:true});
  }
}
function revealSelection() {
  if(!$('#inspector').contains(document.activeElement))selectionOpener=document.activeElement;
  renderOutput(); bindEvidence();
  $('#inspector-title').focus({preventScroll:true});
  if(innerWidth<=1100)$('#inspector').scrollIntoView({behavior:'smooth',block:'start'});
}
let report, openSequence=0, reportSequence=0, launchStep=0, launching=false, launchOpening=false, launchRequest=null;
let toastTimer, reportRefreshTimer, selectionOpener, pendingJobId=null, renderFrame=null;
const analysisPending=new Set(), seenEvents=new Set();
let state, job, events=[], stream, taskId, selected, outputMode='formatted', view='report', selectedTasks=new Set(), selectedModels=new Set();
function toast(text) {
  clearTimeout(toastTimer);
  $('#toast').textContent=text; $('#toast').classList.remove('hidden');
  toastTimer=setTimeout(()=>$('#toast').classList.add('hidden'),6000);
}
async function api(path,body) {
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
  if(!response.ok) {
    const issue=new Error(response.status===403?'Your Studio session changed. Reload the workspace before trying again.':data.error||'Studio could not complete this request. Try again.');
    issue.status=response.status; issue.uncertain=write&&response.status>=500; throw issue;
  }
  return data;
}
function budget(data){state.budget=data;$('#budget-available').textContent=money(data.available)+' left';$('#budget-detail').textContent=money(data.actual)+' estimated · '+money(data.held)+' held / $300';$('#budget-fill').style.width=Math.min(100,(Number(data.actual)+Number(data.held))/3)+'%'}
function renderJobs() {
  const focusId=document.activeElement?.dataset?.job;
  const query=($('#run-search')?.value||'').trim().toLowerCase();
  const rows=state.jobs.filter(j=>(j.title+' '+j.status).toLowerCase().includes(query));
  $('#job-count').textContent=query?rows.length+' / '+state.jobs.length:state.jobs.length;
  $('#jobs').innerHTML=rows.length?rows.map(j=>'<button class="job '+(job?.id===j.id?'active':'')+'" data-job="'+esc(j.id)+'" data-status="'+esc(j.status)+'" aria-current="'+(job?.id===j.id?'true':'false')+'"><strong>'+esc(j.title)+'</strong><small><span class="dot"></span>'+esc(j.status)+' · '+j.completed+'/'+j.total+' attempts</small></button>').join(''):'<p class="jobs-empty">'+(query?'No runs match your search.':'No runs yet. Start with a few tasks and compare the outcomes.')+'</p>';
  $$('[data-job]').forEach(b=>b.onclick=()=>openJob(b.dataset.job));
  if(focusId)$$('[data-job]').find(b=>b.dataset.job===focusId)?.focus({preventScroll:true});
}
function syncJob(value){job=value;const index=state.jobs.findIndex(j=>j.id===job.id);if(index<0)state.jobs.unshift(job);else state.jobs[index]=job;renderJobs();$('#comparison-title').textContent=job.title;$('#comparison-meta').textContent=job.settings.tasks.length+' '+plural(job.settings.tasks.length,'task')+' · '+job.settings.models.length+' '+plural(job.settings.models.length,'approach')+' · '+money(job.settings.maximum_usd)+' maximum';$('#job-status').textContent=job.status;$('#job-status').className='status '+job.status;$('#cancel-run').classList.toggle('hidden',!['queued','running','cancelling'].includes(job.status));$('#cancel-run').disabled=job.status==='cancelling';$('#result-count').textContent=job.results.length;$('#stream-note').textContent=['queued','running','cancelling'].includes(job.status)?'Live updates':'Recorded execution';$('#run-message').textContent=job.error||'';$('#run-message').classList.toggle('hidden',!job.error)}
async function openJob(id) {
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
    taskId=job.settings.tasks[0];
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
      if(event.type==='finished') { syncJob(event.job); budget(event.budget); source.close(); queueReportRefresh(id,sequence); }
      else if(event.type==='attempt_finished') {
        if(!job.results.some(r=>r.task===event.task&&r.model===event.model)) {job.results.push(event);job.completed++;syncJob(job);}
        queueReportRefresh(id,sequence);
      } else if(event.type==='running'&&['queued','running'].includes(job.status)) {job.status='running';syncJob(job);}
      else if(event.type==='cancelling') {job.status='cancelling';syncJob(job);}
      else if(event.type==='billing')budget(event.budget);
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
    if(view==='results')renderResults();
    if(window.builderLive)builderLive(job,events);
    if(selected&&!selected.report) {
      const latest=nodeList(selected.model).find(n=>n.node===selected.node);
      if(latest&&JSON.stringify(latest)!==JSON.stringify(selected)){selected=latest;renderOutput();bindEvidence();}
    }
  });
}

function nodeLabel(node){if(node.category==='result')return 'Verify task outcome';if(node.category==='model')return 'Generate next response';if(node.label==='api_search')return 'Find application actions';if(node.label==='base64_encode')return 'Encode message content';if(node.label==='api_fetch'){const a=node.arguments||{};let service='application';try{const host=new URL(a.url).hostname;service=host.includes('salesforce')?'Salesforce':host.includes('gmail')?'Gmail':host.split('.')[0]}catch{}const verb={GET:'Read',POST:'Create',PATCH:'Update',PUT:'Update',DELETE:'Delete'}[a.method]||'Call';return verb+' '+service+(service==='Gmail'?' message':' record')}return human(node.label||'Response')}
function nodeList(model){const nodes=[];for(const e of events.filter(x=>x.task===taskId&&x.model===model)){if(e.type==='step_started'){nodes.push({...e,node:'step:'+e.step,status:'running',category:'step'})}else if(e.type==='step_finished'){const old=nodes.find(n=>n.node==='step:'+e.step);if(old)Object.assign(old,e,{node:'step:'+e.step});else nodes.push({...e,node:'step:'+e.step,category:'step'})}else if(['node_started','model_started'].includes(e.type)){nodes.push({...e,status:'running',category:e.type==='model_started'?'model':'tool'})}else if(['node_finished','model_finished'].includes(e.type)){let old=nodes.find(n=>n.node===e.node);if(old)Object.assign(old,e);else nodes.push({...e,category:e.type==='model_finished'?'model':'tool'})}}
const result=job?.results.find(r=>r.task===taskId&&r.model===model);if(result){nodes.forEach(n=>{if(n.status==='running')n.status='error'});}if(result)nodes.push({node:'result',model,task:taskId,label:'Task result',status:result.passed?'completed':'error',category:'result',output:result.output,result});return nodes}
function renderGraph(){if(!job)return;const focusNode=document.activeElement?.dataset?.node;const focusModel=document.activeElement?.dataset?.model;$('#task-brief').textContent=state.tasks.find(t=>t.id===taskId)?.brief||'';$('#task-progress').textContent=(job.settings.tasks.indexOf(taskId)+1)+' / '+job.settings.tasks.length;$('#lanes').innerHTML=job.settings.models.map(model=>{const info=state.models.find(m=>m.id===model);const nodes=nodeList(model);return '<section class="lane" aria-label="'+esc(modelName(model))+'"><div class="lane-heading"><span class="model-icon">'+icon(armKind(model)==='version'?'model':'tool')+'</span><div><strong>'+esc(modelName(model))+'</strong><small>'+esc(armKind(model)==='version'?'Published architecture · steps run in order':info?.kind||'Runner')+'</small></div></div><div class="lane-nodes">'+(nodes.length?nodes.map(n=>n.category==='step'?'<div class="lane-step '+esc(n.status)+'"><strong>'+esc(n.label)+'</strong><small>'+esc(n.status==='running'?'Running this step':n.status==='error'?'Stopped with an error':'Step finished')+(n.output&&n.status!=='running'?' · '+esc(String(n.output).slice(0,220)):'')+'</small></div>':'<button class="node '+esc(n.status)+(selected?.node===n.node&&selected?.model===model?' selected':'')+'" data-node="'+esc(n.node)+'" data-model="'+esc(model)+'"><div class="node-head">'+icon(n.category==='model'?'model':'check')+'<span>'+esc(nodeLabel(n))+'</span></div><p>'+esc(n.category==='result'?(n.result.passed?'All task checks passed':n.result.error||'One or more task checks failed'):n.arguments?JSON.stringify(n.arguments):n.output||(n.status==='running'?'Waiting for the response…':n.status==='error'?'The request stopped before a response arrived.':'Chose the next application actions without a written reply.'))+'</p><div class="node-foot"><span>'+esc(n.category==='result'?'Verified task checks':n.category==='model'?'Model response':'Application action')+'</span><span>'+esc(n.status==='running'?'Running':n.status==='error'?'Attention':'Done')+'</span></div></button>').join(''):'<div class="lane-waiting">Waiting for this task</div>')+'</div></section>'}).join('');$$('[data-node]').forEach(b=>b.onclick=()=>{selected=nodeList(b.dataset.model).find(n=>n.node===b.dataset.node);revealSelection();renderGraph()});if(focusNode){const target=$$('[data-node]').find(b=>b.dataset.node===focusNode&&b.dataset.model===focusModel);target?.focus({preventScroll:true});}}
function pretty(value,depth=0){if(value&&typeof value==='object'&&!Array.isArray(value)&&!Object.keys(value).length)return '<p>No response body returned.</p>';if(depth>5)return '<pre>'+esc(JSON.stringify(value,null,2))+'</pre>';if(value===null||value===undefined)return '<span>Not available</span>';if(typeof value==='string'){try{return pretty(JSON.parse(value),depth)}catch{}return textDocument(value)}if(typeof value!=='object')return esc(value);if(Array.isArray(value)){if(!value.length)return '<p>No records returned.</p>';if(value.every(v=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.values(v).every(x=>x===null||typeof x!=='object'))){const allKeys=[...new Set(value.flatMap(v=>Object.keys(v)))],keys=allKeys.slice(0,8);return '<div class="collection-label">'+(value.length>100||allKeys.length>8?'Showing '+Math.min(100,value.length)+' of '+value.length+' records and '+keys.length+' of '+allKeys.length+' fields. Open Raw evidence for the complete output.':value.length+' records')+'</div><div class="table-scroll"><table><thead><tr>'+keys.map(k=>'<th>'+esc(human(k))+'</th>').join('')+'</tr></thead><tbody>'+value.slice(0,100).map(v=>'<tr>'+keys.map(k=>'<td>'+esc(v[k])+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>';}return '<div class="collection-label">'+value.length+' records</div>'+value.slice(0,100).map(v=>'<section class="record">'+pretty(v,depth+1)+'</section>').join('')+(value.length>100?'<p>Showing the first 100 records. Copy raw evidence for the full output.</p>':'')}return '<dl>'+Object.entries(value).map(([k,v])=>'<dt>'+esc(human(k))+'</dt><dd>'+pretty(v,depth+1)+'</dd>').join('')+'</dl>'}
function textDocument(value){return value.split(/\n\s*\n/).map(block=>{if(/^#{1,3}\s/.test(block))return '<h3>'+esc(block.replace(/^#{1,3}\s/,''))+'</h3>';if(block.split('\n').every(l=>/^[-*]\s/.test(l)))return '<ul>'+block.split('\n').map(l=>'<li>'+esc(l.slice(2))+'</li>').join('')+'</ul>';return '<p>'+esc(block).replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/`([^`]+)`/g,'<code>$1</code>').replaceAll('\n','<br>')+'</p>'}).join('')}
function renderOutput(){if(!selected)return;document.querySelector('.workspace').classList.add('has-inspector');$('#inspector-title').textContent=selected.category==='result'?'Task output':nodeLabel(selected);$('#inspector-meta').textContent=modelName(selected.model)+' · '+selected.status;let raw={arguments:selected.arguments,output:selected.output,status:selected.status,...(selected.result?{checks:selected.result.checks,termination:selected.result.termination,flags:selected.result.flags,unexpected_changes:selected.result.unexpected_changes,report:selected.report}: {})};if(outputMode==='raw')$('#output').innerHTML='<pre>'+esc(JSON.stringify(raw,null,2))+'</pre>';else if(selected.report){$('#output').innerHTML=reportDetails(selected.report);}else{$('#output').innerHTML=(selected.result?.error?'<p class="fail">'+esc(selected.result.error)+'</p>':'')+(selected.output!==null&&selected.output!==undefined?pretty(selected.output):'<p>No output received yet.</p>')+(selected.result?'<h4>Task checks</h4>'+(selected.result.checks||[]).map(c=>'<div class="check"><span>'+esc(human(c.type))+'</span><strong class="'+(c.passed?'pass':'fail')+'">'+(c.passed?'Passed':'Failed')+'</strong></div>').join(''):'');if(selected.result?.unexpected_changes?.length)$('#output').insertAdjacentHTML('beforeend','<h4>Unexpected changes</h4>'+pretty(selected.result.unexpected_changes));if(selected.arguments)$('#output').insertAdjacentHTML('beforeend','<h4>Input</h4>'+pretty(selected.arguments));}}
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
function armKind(id){const arm=job?.settings?.arms?.find(a=>a.id===id);return arm?arm.kind:state.models.find(m=>m.id===id.split('@')[0])?.kind||'Runner'}
function filteredTasks(){const q=$('#task-search').value.trim().toLowerCase(),category=$('#task-category').value;return state.tasks.filter(t=>(!category||t.category===category)&&(!$('#task-difficulty').value||(t.difficulty?.level||'unrated')===$('#task-difficulty').value)&&(t.title+' '+t.brief+' '+(t.applications||[]).join(' ')).toLowerCase().includes(q))}
function renderTaskOptions(){const filtered=filteredTasks();$('#task-options').innerHTML=filtered.length?filtered.map(t=>'<label class="task-option"><input type="checkbox" value="'+esc(t.id)+'" '+(selectedTasks.has(t.id)?'checked':'')+'><span><strong>'+esc(t.title)+'</strong><small>'+esc(t.category)+' · '+esc((t.applications||[]).join(' + '))+'</small></span>'+difficultyBadge(t)+'</label>').join(''):'<p class="jobs-empty">No requests match these filters.</p>';$$('#task-options input').forEach(i=>i.onchange=()=>{i.checked?selectedTasks.add(i.value):selectedTasks.delete(i.value);launchSize()});launchSize()}
function armCount(){const without=$('#without-monarch')?.checked;const versionsChecked=$$('#architecture-options input:checked:not(:disabled)').filter(i=>i.value!=='without-monarch').length;return (without?selectedModels.size:0)+versionsChecked}
function requestFloor(){const without=$('#without-monarch')?.checked;let floor=0;if(without)for(const id of selectedModels){const m=state.models.find(x=>x.id===id.split('@')[0]);floor=Math.max(floor,Number(m?.request_ceiling_usd||state.capabilities?.controls?.find(c=>c.id===m?.control)?.request_ceiling_usd||0))}for(const i of $$('#architecture-options input:checked')){const v=state.capabilities?.versions?.find(v=>v.id===i.value);floor=Math.max(floor,Number(v?.request_ceiling_usd||0))}return floor}
function launchSize() {
  if(!state)return;
  $('#runner-choices').classList.toggle('hidden',!$('#without-monarch').checked);
  $('#selected-count').textContent=selectedTasks.size+' of '+state.tasks.length+' selected';
  const arms=armCount(), floor=requestFloor(), amount=Number($('#run-budget').value);
  const low=floor>0&&amount<floor;
  $('#launch-size').textContent=selectedTasks.size+' '+plural(selectedTasks.size,'task')+' × '+arms+' '+plural(arms,'approach')+' · '+selectedTasks.size*arms+' '+plural(selectedTasks.size*arms,'attempt');
  $('#budget-floor').textContent=low?'Set at least '+money(floor)+' to cover the largest single request reservation.':knownNumber(state.budget?.available)&&amount>Number(state.budget.available)?'Only '+money(state.budget.available)+' remains in this week’s capacity.':'';
  const error=launchIssue();
  $('#launch-validation').textContent=launchStep===2?error:'';
  $('#launch-button').disabled=launching||!!error;
  $('#launch-button').textContent=launching?'Starting…':'Start run · '+money(amount)+' max';
  $('#launch-next').disabled=launching||(launchStep===0?!selectedTasks.size||selectedTasks.size>800:!arms||arms>12||($('#without-monarch').checked&&!selectedModels.size));
  $('#launch-back').disabled=launching;
  $$('[data-launch-step]').forEach(b=>b.disabled=launching);
  $('#clear-tasks').disabled=!selectedTasks.size;
  const matching=filteredTasks(), all=matching.length&&matching.every(t=>selectedTasks.has(t.id));
  $('#select-all').textContent=all?'Deselect matching':'Select matching';$('#select-all').disabled=!matching.length;
  $('#task-match-count').textContent=matching.length+' matching · '+[...selectedTasks].filter(id=>!matching.some(t=>t.id===id)).length+' selected outside filters';
  if(launchStep===2)renderLaunchReview();
}
const plural=(n,word)=>n===1?word:word+'s';
function launchIssue() {
  if(!selectedTasks.size)return 'Choose at least one task.';
  if(selectedTasks.size>800)return 'Select no more than 800 tasks.';
  const arms=armCount();if(!arms||($('#without-monarch').checked&&!selectedModels.size))return 'Choose a runner for Without Monarch, or select a published architecture.';
  if(arms>12)return 'Compare no more than 12 approaches in one run.';
  if(!$('#run-title').value.trim())return 'Name this run before starting.';
  const amount=Number($('#run-budget').value);
  if(!Number.isFinite(amount)||amount<=0||amount>300||!$('#run-budget').validity.valid)return 'Use a budget between $0.01 and $300, with at most two decimal places.';
  if(amount<requestFloor())return 'Increase the budget to cover the largest request reservation.';
  if(knownNumber(state.budget?.available)&&amount>Number(state.budget.available))return 'The budget exceeds this week’s available capacity.';
  if(!$('#run-turns').value||!$('#run-turns').validity.valid)return 'Use a turn limit between 1 and 50.';
  return '';
}
function renderLaunchReview() {
  const names=selectedVersions().filter(v=>v!=='without-monarch').map(id=>state.capabilities.versions.find(v=>v.id===id)?.name||id);
  if($('#without-monarch').checked)for(const id of selectedModels)names.push(modelName(id));
  $('#launch-review').innerHTML='<dl><dt>Work</dt><dd>'+selectedTasks.size+' '+plural(selectedTasks.size,'task')+' · '+selectedTasks.size*armCount()+' '+plural(selectedTasks.size*armCount(),'attempt')+'</dd><dt>Approaches</dt><dd>'+names.map(esc).join('<br>')+'</dd><dt>Evaluation</dt><dd>One-off agentic requests</dd><dt>Weekly capacity</dt><dd>'+money(state.budget?.available)+' available</dd></dl>';
}
function setLaunchStep(step,focus=true) {
  launchStep=Math.max(0,Math.min(2,step));
  $$('[data-launch-panel]').forEach(p=>p.classList.toggle('hidden',Number(p.dataset.launchPanel)!==launchStep));
  $$('[data-launch-step]').forEach(b=>{b.setAttribute('aria-current',Number(b.dataset.launchStep)===launchStep?'step':'false');b.disabled=launching;});
  $('#launch-back').classList.toggle('hidden',launchStep===0);$('#launch-next').classList.toggle('hidden',launchStep===2);$('#launch-button').classList.toggle('hidden',launchStep!==2);
  $('#launch-next').textContent=launchStep===0?'Choose approaches':'Review run';
  launchSize();
  $('#form-error').textContent='';
  if(focus){const heading=$('[data-launch-panel="'+launchStep+'"] .step-heading');heading.tabIndex=-1;heading.focus();$('#launch-dialog').scrollTop=0;}
}
$('#run-budget').oninput=launchSize;
function runnerOption(m){if(m.efforts&&m.efforts.length)return '<div class="model-option '+(!m.available?'unavailable':'')+'"><span>'+esc(m.name)+'<small class="unavailable-reason">'+esc(m.kind)+(m.rate_card?' · '+esc(m.rate_card):'')+(!m.available?' · '+esc(m.reason):'')+'</small></span></div><div class="effort-options">'+m.efforts.map(level=>'<label><input type="checkbox" value="'+esc(m.id+'@'+level)+'" '+(!m.available?'disabled':'')+' '+(selectedModels.has(m.id+'@'+level)?'checked':'')+'>'+level.charAt(0).toUpperCase()+level.slice(1)+(level===m.default_effort?' (default)':'')+'</label>').join('')+'</div>';return '<label class="model-option '+(!m.available?'unavailable':'')+'"><input type="checkbox" value="'+esc(m.id)+'" '+(!m.available?'disabled':'')+' '+(selectedModels.has(m.id)?'checked':'')+'><span>'+esc(m.name)+(!m.available?'<span class="unavailable-reason">'+esc(m.reason)+'</span>':'')+'</span><small>'+esc(m.kind)+'</small></label>'}
async function openLaunch(options={}) {
  if(!state||launchOpening||launching)return;
  launchOpening=true;$('#new-comparison').disabled=true;
  try {
    const latest=await api('/api/state');
    state.models=latest.models.filter(m=>!['oracle','sloppy'].includes(m.id));state.tasks=latest.tasks;state.token=latest.token;budget(latest.budget);
    const available=new Set(state.models.filter(m=>m.available).flatMap(m=>m.efforts?.length?m.efforts.map(e=>m.id+'@'+e):[m.id]));
    selectedModels=new Set([...selectedModels].filter(id=>available.has(id)));
    selectedTasks=new Set([...selectedTasks].filter(id=>state.tasks.some(t=>t.id===id)));
    $('#form-error').textContent='';
    const category=$('#task-category').value;
    $('#task-category').innerHTML='<option value="">All categories · '+state.tasks.length+' tasks</option>'+[...new Set(state.tasks.map(t=>t.category))].sort().map(c=>'<option value="'+esc(c)+'">'+esc(c)+' · '+state.tasks.filter(t=>t.category===c).length+'</option>').join('');
    if([...$('#task-category').options].some(o=>o.value===category))$('#task-category').value=category;
    await renderComparisonVersions(options.version);
    const groups=[['API controls',m=>m.kind==='API control'],['Native harnesses',m=>m.kind==='Native harness'],['Saved runner configurations',m=>m.configuration]];
    $('#model-options').innerHTML=groups.map(([title,filter])=>{const rows=state.models.filter(filter);return !rows.length?'':title==='Native harnesses'?'<details class="readiness-details"><summary>Native harnesses · unavailable</summary>'+rows.map(runnerOption).join('')+'</details>':'<div class="runner-group">'+title+'</div>'+rows.map(runnerOption).join('');}).join('');
    $$('#model-options input').forEach(i=>i.onchange=()=>{i.checked?selectedModels.add(i.value):selectedModels.delete(i.value);launchSize();});
    renderTaskOptions();
    if(!$('#launch-dialog').open){setLaunchStep(0,false);$('#launch-dialog').showModal();$('#launch-title').focus();}
  } catch(error) {toast('Run setup could not load. '+error.message);}
  finally {launchOpening=false;$('#new-comparison').disabled=false;}
}

$('#new-comparison').onclick=openLaunch;$('#empty-start').onclick=openLaunch;$('#close-dialog').onclick=()=>$('#launch-dialog').close();$('#task-search').oninput=renderTaskOptions;$('#select-all').onclick=()=>{const ids=filteredTasks().map(t=>t.id);const all=ids.every(id=>selectedTasks.has(id));ids.forEach(id=>all?selectedTasks.delete(id):selectedTasks.add(id));renderTaskOptions()};$('#task-select').onchange=e=>{taskId=e.target.value;clearSelection();renderGraph()};$('#fit-view').onclick=()=>$('#graph-scroll').scrollTo({top:0,left:0,behavior:'smooth'});$$('[data-view]').forEach(b=>b.onclick=()=>switchView(b.dataset.view));$$('[data-output]').forEach(b=>b.onclick=()=>{setOutputMode(b.dataset.output);renderOutput();bindEvidence()});$('#copy-output').onclick=async()=>{
  if(!selected)return toast('Select an output first');
  const raw={arguments:selected.arguments,output:selected.output,status:selected.status,...(selected.result?{checks:selected.result.checks,termination:selected.result.termination,flags:selected.result.flags,unexpected_changes:selected.result.unexpected_changes,report:selected.report}:{})};
  try {await navigator.clipboard.writeText(outputMode==='raw'?JSON.stringify(raw,null,2):typeof selected.output==='string'?selected.output:JSON.stringify(selected.output??null,null,2));toast('Output copied');}
  catch {toast('Clipboard access is unavailable. Select and copy the text in the evidence panel.');}
};
$('#cancel-run').onclick=async()=>{
  if(!job||$('#cancel-run').disabled)return;
  const id=job.id;$('#cancel-run').disabled=true;
  try {const next=await api('/api/jobs/'+id+'/cancel',{});if(job?.id===id)syncJob(next);toast('Stopping after the current request');}
  catch(error){toast(error.message);if(job?.id===id)$('#cancel-run').disabled=false;}
};
$('#launch-form').onsubmit=async e=>{
  e.preventDefault();if(launching)return;
  if(launchStep<2){if(!$('#launch-next').disabled)setLaunchStep(launchStep+1);return;}
  const issue=launchIssue();if(issue){$('#form-error').textContent=issue;$('#form-error').focus();return;}
  const payload={title:$('#run-title').value.trim(),tasks:[...selectedTasks],models:$('#without-monarch').checked?[...selectedModels]:[],architectures:selectedVersions(),maximum_usd:$('#run-budget').value,configuration:{prompt:$('#run-prompt').value,max_turns:Number($('#run-turns').value)}};
  const fingerprint=JSON.stringify(payload);
  if(launchRequest&&launchRequest.fingerprint!==fingerprint){$('#form-error').textContent='The previous start has an uncertain response. Restore those selections and retry, or reload the workspace to find the run before starting another.';return;}
  if(!launchRequest)launchRequest={id:crypto.randomUUID().replaceAll('-',''),fingerprint};
  launching=true;launchSize();$('#form-error').textContent='';
  try {
    const created=await api('/api/jobs',{...payload,request_id:launchRequest.id});
    launchRequest=null;$('#launch-dialog').close();$('#close-setup')?.click();
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
    if(pendingJobId||state.jobs.length)await openJob(pendingJobId||state.jobs[0].id);
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
$('#clear-tasks').onclick=()=>{selectedTasks.clear();renderTaskOptions();};
$('#reset-task-filters').onclick=()=>{$('#task-search').value='';$('#task-category').value='';$('#task-difficulty').value='';renderTaskOptions();$('#task-search').focus();};
$('.tabs').addEventListener('keydown',e=>{
  const tabs=$$('[data-view]'),index=tabs.indexOf(document.activeElement);
  if(index<0||!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;
  e.preventDefault();const next=e.key==='Home'?0:e.key==='End'?tabs.length-1:(index+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;
  tabs[next].click();tabs[next].focus();
});
initialize();
function actionSummary(node){const account=report?.attempts.find(a=>a.task===taskId&&a.model===node.model);return account?.actions.find(a=>a.node===node.node)?.detail||(node.category==='model'?'Considering the request and the evidence collected so far.':node.status==='running'?'This action is in progress.':'Open the recorded response for this action.')}
function reportDetails(a){return '<h3>'+esc(a.title)+'</h3><p>'+esc(a.summary)+'</p><h4>Requirements</h4>'+a.requirements.map(c=>'<div class="check"><span>'+esc(c.title)+'</span><strong class="'+(c.passed?'pass':'fail')+'">'+(c.passed?'Met':'Missed')+'</strong></div>').join('')+(a.unexpected_changes.length?'<h4>Changes outside the request</h4>'+(a.change_summaries||[]).map(c=>'<p>'+esc(c)+'</p>').join(''):'')+'<h4>What happened</h4><ol class="evidence-story">'+a.actions.map(x=>'<li><strong>'+esc(x.title)+'</strong><p>'+esc(x.detail)+'</p><button class="text-button" data-evidence="'+x.event_id+'">Open evidence #'+x.event_id+'</button></li>').join('')+'</ol><h4>Next question</h4><p>'+esc(a.next_question)+'</p><p class="report-caveat">'+esc(a.limitations)+'</p>'}
function selectReport(index) {
  const a=report?.attempts[index];if(!a)return;
  const result=job.results.find(r=>r.task===a.task&&r.model===a.model);
  if(!result)return toast('The result is still arriving. Try again shortly.');
  setOutputMode('formatted');taskId=a.task;$('#task-select').value=taskId;
  selected={node:'result',category:'result',model:a.model,status:a.passed?'completed':'error',output:result.output,result,report:a};
  revealSelection();
}
function setOutputMode(mode) {
  outputMode=mode;
  $$('[data-output]').forEach(b=>{b.classList.toggle('active',b.dataset.output===mode);b.setAttribute('aria-pressed',String(b.dataset.output===mode));});
}
function bindEvidence() {
  $$('[data-evidence]').forEach(b=>b.onclick=()=>{
    const event=events.find(e=>e.id===Number(b.dataset.evidence));
    if(!event)return toast('Evidence is still loading. Try again shortly.');
    if(event.task){taskId=event.task;$('#task-select').value=taskId;}
    selected=nodeList(event.model).find(n=>n.node===event.node)||{node:'event:'+event.id,model:event.model,category:'evidence',label:'Evidence #'+event.id,status:event.status||event.type,output:event};
    setOutputMode('raw');revealSelection();
  });
}
function renderReport(){if(!job||!report)return;const focused=document.activeElement?.dataset?.report;const attempts=report.attempts,valid=attempts.filter(a=>!a.infrastructure);const modelRows=job.settings.models.map(m=>{const rows=attempts.filter(a=>a.model===m),measured=rows.filter(a=>!a.infrastructure),passed=measured.filter(a=>a.passed).length;return '<div class="comparison-bar"><strong>'+esc(modelName(m))+'</strong><div class="outcome-track"><div data-width="'+ (measured.length?passed/measured.length*100:0)+'"></div></div><span>'+passed+' / '+measured.length+' met</span><small>'+rows.filter(a=>a.infrastructure).length+' execution issues</small></div>'}).join('');const analysis=report.analysis;$('#report-view').innerHTML='<div class="report-intro"><h3>'+ (attempts.length?'What this run tells us':['queued','running','cancelling'].includes(job.status)?'The work is underway':'No evaluated outcomes')+'</h3><p>'+(attempts.length?valid.filter(a=>a.passed).length+' of '+valid.length+' evaluated attempts met the task requirements. '+(attempts.length-valid.length?attempts.length-valid.length+' attempts could not be evaluated.':'Open an outcome to see which requirements and actions made the difference.'):(['queued','running','cancelling'].includes(job.status)?'Task outcomes appear as each attempt finishes. You can follow the activity while they run.':'This run ended before any task could be evaluated. Check the run message and Activity for what happened.'))+'</p></div><div class="comparison-bars">'+modelRows+'</div><div class="outcomes-heading"><h3>Task outcomes</h3><span>'+job.settings.tasks.length+' selected '+plural(job.settings.tasks.length,'request')+'</span></div><div class="outcome-list">'+attempts.map((a,i)=>'<button class="outcome-card" data-report="'+i+'"><div class="outcome-top"><span class="outcome-label '+(a.infrastructure?'neutral':a.passed?'pass':'fail')+'">'+(a.infrastructure?'Execution issue':a.passed?'Requirements met':'Needs investigation')+'</span><small>'+esc(modelName(a.model))+'</small></div><h4>'+esc(taskTitle(a.task))+'</h4><p>'+esc(a.summary)+'</p><div class="requirement-strip">'+a.requirements.slice(0,3).map(c=>'<span class="'+(c.passed?'pass':'fail')+'">'+icon(c.passed?'check':'tool')+esc(c.title)+'</span>').join('')+(a.requirements.length>3?'<span>+'+(a.requirements.length-3)+' more requirements</span>':'')+'</div><div class="outcome-link">Read findings &amp; evidence <span aria-hidden="true">→</span></div></button>').join('')+'</div><section class="analysis-section"><div><h3>Reasoning review</h3><p>A separate reading of the execution: supported explanations, uncertainty, and the next experiment.</p></div>'+(analysis?.status==='completed'?'<p>'+esc(analysis.summary)+'</p>'+analysis.findings.map(f=>'<article class="analysis-finding"><h4>'+esc(f.title)+' <small>'+esc(f.kind)+'</small></h4><p>'+esc(f.explanation)+'</p>'+f.event_ids.map(i=>'<button class="text-button" data-evidence="'+i+'">Evidence #'+i+'</button>').join('')+'</article>').join('')+'<h4>Next experiment</h4><p>'+esc(analysis.next_experiment)+'</p><p class="report-caveat">'+esc(analysis.limitations)+' · '+esc(analysis.model)+' / '+esc(analysis.effort)+'</p>':analysis?.status==='failed'?'<p class="fail">'+esc(analysis.error)+'</p>':'<button class="button" id="analyze-run" '+(!attempts.length||analysisPending.has(job.id)||['queued','running','cancelling'].includes(job.status)?'disabled':'')+'>Analyze this run · Gemini medium</button><p class="report-caveat">Uses the remaining run budget and the shared weekly limit. Sol medium analysis is not connected yet. Model interpretations retain the original task verdict.</p>')+'</section>';$$('[data-width]').forEach(b=>b.style.width=b.dataset.width+'%');$$('[data-report]').forEach(b=>b.onclick=()=>selectReport(Number(b.dataset.report)));bindEvidence();if(focused!==undefined)$$('[data-report]').find(b=>b.dataset.report===focused)?.focus({preventScroll:true});if($('#analyze-run'))$('#analyze-run').onclick=async()=>{
  const reviewId=job.id;if(analysisPending.has(reviewId))return;
  analysisPending.add(reviewId);const button=$('#analyze-run');button.disabled=true;button.textContent='Reading the execution…';
  try {
    const analysis=await api('/api/jobs/'+reviewId+'/analyze',{});
    if(job?.id===reviewId)report.analysis=analysis;
    budget((await api('/api/state')).budget);
  } catch(error) {toast(error.message);}
  finally {analysisPending.delete(reviewId);if(job?.id===reviewId)renderReport();}
};}
$('#task-category').onchange=renderTaskOptions;
function renderSetups(){}

function difficultyBadge(task){const d=task.difficulty||{level:'unrated',attempts:0,description:'No comparable scored attempts yet.'};const heights=[5,9,14];const filled={easy:1,medium:2,hard:3,unrated:0}[d.level];return '<span class="difficulty-badge '+esc(d.level)+'" title="'+esc(d.description)+'" aria-label="'+esc(d.level+' difficulty. '+d.description)+'"><svg viewBox="0 0 22 18" aria-hidden="true">'+heights.map((h,i)=>'<rect x="'+(i*7)+'" y="'+(17-h)+'" width="5" height="'+h+'" rx="1" class="'+(i<filled?'filled':'')+'"/>').join('')+'</svg><span>'+esc(d.level)+(d.provisional&&d.attempts?'*':'')+'<small>'+d.attempts+' '+plural(d.attempts,'attempt')+'</small></span></span>'}
$('#task-difficulty').onchange=renderTaskOptions;

function readinessText(r){return ({adapter_required:'Execution integration pending',blocked:'Blocked',unsupported:'Unsupported configuration',source_required:'Historical source not recovered'}[r.runtime]||r.runtime)+(r.reasons&&r.reasons.length?' · '+r.reasons[0]:'')}
async function renderComparisonVersions(preselect) {
  const previous=new Set(selectedVersions()),matrix=await api('/api/capabilities');state.capabilities=matrix;
  $$('[data-comparison-version],#unavailable-versions').forEach(e=>e.remove());
  const blocked=matrix.versions.filter(v=>v.id!=='without-monarch'&&!v.readiness.launchable);
  const details=document.createElement('details');details.id='unavailable-versions';details.className='readiness-details';
  details.innerHTML='<summary>Unavailable versions ('+blocked.length+')</summary>';
  for(const v of matrix.versions) {
    if(v.id==='without-monarch')continue;
    const row=document.createElement('label');row.className='model-option'+(v.readiness.launchable?'':' unavailable');row.dataset.comparisonVersion=v.id;
    const checked=v.readiness.launchable&&(preselect?preselect===v.id:previous.has(v.id));
    row.innerHTML='<input type="checkbox" value="'+esc(v.id)+'" '+(v.readiness.launchable?'':'disabled')+(checked?' checked':'')+'><span>'+esc(v.name)+'<span class="unavailable-reason">'+esc(v.readiness.launchable?(v.kind==='custom'?'Published architecture · uses its saved steps and runners':v.description):readinessText(v.readiness))+'</span></span>';
    (v.readiness.launchable?$('#architecture-options'):details).append(row);
  }
  if(blocked.length)$('#architecture-options').append(details);
  if(preselect)$('#without-monarch').checked=false;
  $$('#architecture-options input').forEach(i=>i.onchange=launchSize);
  $('#comparison-readiness').textContent=(blocked.length?blocked.length+' versions cannot launch yet. ':'')+'Native Claude Code and Codex runners: '+(matrix.native_preflight.status==='blocked'?'blocked pending verified isolation and trace capture.':matrix.native_preflight.status+'.')+' Ready API controls and published architectures remain available.';
  launchSize();
}

function selectedVersions(){return $$('#architecture-options input:checked:not(:disabled)').map(i=>i.value)}
$('#without-monarch').onchange=()=>{launchSize();$('#runner-choices').classList.toggle('not-used',!$('#without-monarch').checked);};

