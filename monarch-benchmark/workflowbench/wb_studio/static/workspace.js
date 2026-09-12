'use strict';
// Navigation and evidence views share the existing Studio API and immutable records.
let workspaceSurface = 'runs', historyPage = 0, expandedRuns = new Set();
const historyPageSize = 15, graphLogCache = new Map();
const trackName = value => value === 'create-and-run' ? 'Workflow configuration' : 'Agentic requests';
const chevron = '<svg class="icon small" aria-hidden="true"><use href="/vendor/lucide/sprite.svg#chevron-right"/></svg>';
function showWorkspaceSurface(surface, updateHash=true) {
 queueMicrotask(()=>document.dispatchEvent(new Event('genesis:surface')));
  workspaceSurface=surface;
  for(const [selector,name] of [['#reports-panel','reports'],['#report-panel','report'],['#genesis-panel','genesis'],['#runs-panel','runs'],['.workspace','detail'],['#setup-panel','studio'],['#runtime-panel','runtime'],['#benchmarks-panel','benchmarks'],['#budget-panel','budget'],['#launch-panel','launch']])$(selector).classList.toggle('hidden',surface!==name);
  $('.page-heading').classList.toggle('hidden',['studio','launch','genesis','report','detail'].includes(surface));
  const titles={reports:['Reports',''],report:['Report',''],genesis:['Genesis',''],budget:['Budget',''],runs:['Runs',''],detail:['Run',''],runtime:['Settings',''],benchmarks:['Benchmarks','Versioned YAML artifacts for benchmark runs.']};
  if(titles[surface]){$('#page-title').textContent=titles[surface][0];$('#page-description').textContent=titles[surface][1];}
  for(const [selector,name] of [['#nav-reports','reports'],['#nav-genesis','genesis'],['#nav-runs','runs'],['#open-setup','studio'],['#nav-runtime','runtime'],['#nav-benchmarks','benchmarks'],['#nav-budget','budget']])$(selector).setAttribute('aria-current',surface===name||(name==='runs'&&surface==='detail')||(name==='reports'&&surface==='report')?'page':'false');
  if(updateHash&&location.hash!=='#'+surface&&!location.hash.startsWith('#'+surface+'/'))history.pushState(null,'','#'+surface);
  document.title='AI Labs — '+(surface==='launch'?'New run':surface==='detail'?($('#comparison-title').textContent.trim()||'Run'):titles[surface]?.[0]||'Architecture studio');
  if(surface==='runs')renderHistory();
}
window.showWorkspaceSurface=showWorkspaceSurface;
let historyStatus='',historyTrack='',historySince='';
const ACTIVE_STATUS=['queued','running','pausing','paused','cancelling'],FAILED_STATUS=['failed','cancelled','interrupted'];
function historyFiltered(){
  const q=$('#history-search').value.toLowerCase().trim(),sort=$('#history-sort').value;
  const rows=(state?.jobs||[]).filter(j=>{const s=runStatus(j);const ok=!historyStatus||(historyStatus==='active'?ACTIVE_STATUS.includes(s):historyStatus==='failed'?FAILED_STATUS.includes(s):s===historyStatus);const since=!historySince||Date.parse(j.created_at)>=Date.now()-Number(historySince)*86400000;return ok&&since&&(!historyTrack||j.settings.track===historyTrack)&&[j.title,j.id,...(j.settings.models||[]),...(j.settings.arms||[]).map(a=>a.name)].join(' ').toLowerCase().includes(q);});
  return rows.sort((a,b)=>sort==='name'?a.title.localeCompare(b.title):(sort==='oldest'?1:-1)*a.created_at.localeCompare(b.created_at));
}
function dayLabel(iso){const d=new Date(iso),today=new Date(),key=x=>x.toDateString();if(key(d)===key(today))return 'Today';const y=new Date(today);y.setDate(y.getDate()-1);if(key(d)===key(y))return 'Yesterday';return d.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});}
const clock=iso=>new Date(iso).toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit',hour12:false});
let runCounts=null,runCountsPending=null;
function loadRunCounts(){if(!runCountsPending)runCountsPending=api('/api/jobs/counts').then(d=>{runCounts=d.items;}).catch(()=>{runCounts={};}).finally(()=>{runCountsPending=null;renderHistory();});}
const countCell=(c,value)=>'<td class="num">'+(c?value(c):'…')+'</td>';
function runCost(j){const results=j.results||[];return results.length&&results.every(r=>r.cost_usd!==null&&r.cost_usd!==undefined&&!(r.flags||[]).some(f=>['billing=unknown','cost_missing'].includes(f)))?results.reduce((n,r)=>n+Number(r.cost_usd),0):null;}
function historyRow(j){
  const valid=(j.results||[]).filter(r=>!String(r.termination).startsWith('infra:')),passed=valid.filter(r=>r.passed).length,open=expandedRuns.has(j.id);
  const arms=j.settings.arms||j.settings.models.map(id=>({id,name:id}));
  const passedCell=valid.length?'<span class="passed-cell '+(passed===valid.length?'all':passed?'some':'none')+'">'+passed+' / '+valid.length+'</span>':'<span class="neutral">Not assessed</span>';
  return '<tr class="history-row" data-run-row="'+esc(j.id)+'" tabindex="0"><th scope="row"><div class="run-cell"><button class="run-expander" data-expand-run="'+esc(j.id)+'" aria-expanded="'+open+'" aria-controls="run-detail-'+esc(j.id)+'" aria-label="Run configuration">'+chevron+'</button><div><button class="run-open" data-open-run="'+esc(j.id)+'">'+esc(j.title)+'</button><small class="run-setups">'+esc(arms.map(a=>a.name||a.id).join(', '))+' · '+j.settings.tasks.length+' '+(j.settings.tasks.length===1?'task':'tasks')+'</small></div></div></th><td><span class="status '+esc(j.status)+'">'+esc(runStatus(j))+'</span></td><td>'+trackName(j.settings.track)+'</td><td>'+j.completed+' / '+j.total+'</td><td>'+passedCell+'</td>'+countCell(runCounts?.[j.id],c=>c.turns===null?'—':Number(c.turns).toFixed(1))+countCell(runCounts?.[j.id],c=>c.violations+' / '+c.attempts)+'<td class="num">'+esc(money(runCost(j)))+'</td><td><time datetime="'+esc(j.created_at)+'" title="'+esc(new Date(j.created_at).toLocaleString())+'">'+esc(clock(j.created_at))+'</time></td></tr>'+
    '<tr id="run-detail-'+esc(j.id)+'" class="history-expanded '+(open?'':'hidden')+'"><td colspan="9"><div class="run-expansion"><div><h3>Setups</h3>'+arms.map(a=>'<p>'+esc(a.name||a.id)+'</p>').join('')+'</div><dl><dt>Concurrent agents</dt><dd>'+esc(j.settings.concurrency||1)+'</dd><dt>Spending limit</dt><dd>'+esc(money(j.settings.maximum_usd))+'</dd><dt>Run ID</dt><dd><code>'+esc(j.id)+'</code></dd></dl><div><div class="run-config-summary">'+readableRunConfig(j)+'<button class="text-button" data-download-run="'+esc(j.id)+'">Download configuration</button></div>'+(j.error?'<p class="fail">'+esc(j.error)+'</p>':'')+'</div></div></td></tr>';
}
function renderHistory(){
  if(!state)return;
  if(!runCounts&&!runCountsPending)loadRunCounts();
  const rows=historyFiltered(),pages=Math.max(1,Math.ceil(rows.length/historyPageSize));historyPage=Math.min(historyPage,pages-1);
  const focus=document.activeElement?.dataset?.expandRun,byName=$('#history-sort').value==='name';
  let lastDay=null,html='';
  for(const j of rows.slice(historyPage*historyPageSize,(historyPage+1)*historyPageSize)){
    const day=dayLabel(j.created_at);
    if(!byName&&day!==lastDay){lastDay=day;const n=rows.filter(x=>dayLabel(x.created_at)===day).length;html+='<tr class="history-day"><th colspan="9" scope="colgroup">'+esc(day)+'<span>'+n+' '+(n===1?'run':'runs')+'</span></th></tr>';}
    html+=historyRow(j);
  }
  $('#history-rows').innerHTML=html||'<tr><td colspan="9">'+(state.jobs.length?'<div class="empty-state"><p>No runs match this search.</p><button class="text-button" type="button" data-history-clear>Show every run</button></div>':'<div class="empty-state"><h3>No runs yet</h3><p>A run is one task set against one or more setups. Every attempt is graded afterwards by the scripted checker, never by the model that did the work.</p><button class="button primary" data-new-run>New run</button></div>')+'</td></tr>';
  $$('[data-new-run]').forEach(b=>b.onclick=()=>openLaunch());$$('[data-history-clear]').forEach(b=>b.onclick=clearHistoryFilters);
  $('#history-count').textContent=rows.length===state.jobs.length&&pages<=1?'':rows.length+' of '+state.jobs.length+' runs';
  $('#history-pager').hidden=pages<=1;$('#history-page').textContent=(historyPage+1)+' / '+pages;$('#history-prev').disabled=historyPage===0;$('#history-next').disabled=historyPage+1>=pages;
  $$('[data-expand-run]').forEach(b=>b.onclick=()=>{expandedRuns.has(b.dataset.expandRun)?expandedRuns.delete(b.dataset.expandRun):expandedRuns.add(b.dataset.expandRun);renderHistory();$('#history-rows [data-expand-run="'+b.dataset.expandRun+'"]').focus({preventScroll:true});});
  $$('[data-run-row]').forEach(row=>row.onclick=e=>{if(!e.target.closest('button,a'))openJob(row.dataset.runRow);});
  $$('[data-open-run]').forEach(b=>b.onclick=()=>openJob(b.dataset.openRun));
  const noTurns=runCounts&&rows.length&&rows.every(j=>!runCounts[j.id]||runCounts[j.id].turns===null);$('#runs-panel .history-table').classList.toggle('no-turns',!!noTurns);
  if(focus)$$('[data-expand-run]').find(b=>b.dataset.expandRun===focus)?.focus({preventScroll:true});
}
window.renderHistory=renderHistory;
function clearHistoryFilters(){$('#history-search').value='';historyStatus='';historyTrack='';historySince='';$$('[data-history-status],[data-history-track],[data-history-since]').forEach(x=>x.setAttribute('aria-pressed',String(!x.dataset.historyStatus&&!x.dataset.historyTrack&&!x.dataset.historySince)));$('#history-sort').value='newest';historyPage=0;renderHistory();}
$('#nav-runs').onclick=()=>showWorkspaceSurface('runs');$('#back-to-history').onclick=()=>showWorkspaceSurface('runs');
$('#history-search').addEventListener('input',()=>{historyPage=0;renderHistory();});$('#history-sort').addEventListener('change',()=>{historyPage=0;renderHistory();});
$$('[data-history-status]').forEach(b=>b.onclick=()=>{historyStatus=b.dataset.historyStatus;$$('[data-history-status]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));historyPage=0;renderHistory();});
$$('[data-history-track]').forEach(b=>b.onclick=()=>{historyTrack=b.dataset.historyTrack;$$('[data-history-track]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));historyPage=0;renderHistory();});
$$('[data-history-since]').forEach(b=>b.onclick=()=>{historySince=b.dataset.historySince;$$('[data-history-since]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));historyPage=0;renderHistory();});
$('#history-rows').addEventListener('keydown',e=>{if(e.target.closest('input,select,textarea'))return;const rows=$$('#history-rows .history-row'),i=rows.indexOf(e.target.closest('.history-row'));if(e.key==='j'||e.key==='ArrowDown'){e.preventDefault();(rows[i+1]||rows[0])?.focus();}else if(e.key==='k'||e.key==='ArrowUp'){e.preventDefault();(rows[i-1]||rows.at(-1))?.focus();}else if(e.key==='Enter'&&i>=0&&!e.target.closest('button,a')){e.preventDefault();openJob(rows[i].dataset.runRow);}});
$('#history-prev').onclick=()=>{historyPage--;renderHistory();};$('#history-next').onclick=()=>{historyPage++;renderHistory();};
$('#history-refresh').onclick=async()=>{const done=busy($('#history-refresh'),'Refreshing…');try{state.jobs=(await api('/api/jobs')).items;runCounts=null;renderHistory();}catch(e){toast(e.message);}finally{done();}};
function download(name,content,type){const url=URL.createObjectURL(new Blob([content],{type})),link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('#history-export').onclick=()=>{const cell=v=>'"'+String(v??'').replace(/^[=+@\-]/,"'$&").replaceAll('"','""')+'"';const rows=[['Run','Setups','Tasks','Status','Track','Attempts finished','Attempts','Passed','Assessed','Turns','Violations','Cost','Started','ID'],...historyFiltered().map(j=>{const valid=(j.results||[]).filter(r=>!String(r.termination).startsWith('infra:')),c=runCounts?.[j.id];return [j.title,(j.settings.arms||j.settings.models.map(id=>({name:id}))).map(a=>a.name||a.id).join('; '),j.settings.tasks.length,runStatus(j),trackName(j.settings.track),j.completed,j.total,valid.filter(r=>r.passed).length,valid.length,c?.turns??'',c?c.violations:'',runCost(j)??'',j.created_at,j.id];})];download('ai-labs-runs.csv',rows.map(r=>r.map(cell).join(',')).join('\r\n'),'text/csv;charset=utf-8');};

function providerRows(){
  const groups=new Map();
  for(const m of (state?.models||[]).filter(m=>m.kind==='API control'&&m.provider)){const g=groups.get(m.provider)||{provider:m.provider,models:0,available:false,reason:m.reason};g.models++;if(m.available)g.available=true;groups.set(m.provider,g);}
  return [...groups.values()].sort((a,b)=>a.provider.localeCompare(b.provider));
}
async function loadRuntime(){
  const [runtime,components]=await Promise.all([api('/api/runtime'),api('/api/components')]);
  $('#run-concurrency').max=runtime.max_agents;state.runtime=runtime;
  const selected=Object.fromEntries($$('[data-component-role]').map(el=>[el.dataset.componentRole,el.value]));
  $('#component-choices').innerHTML=['brain','action_builder','judge'].map(role=>'<label class="field-label" for="component-'+role+'">'+esc(role==='action_builder'?'Action builder':role==='judge'?'Judge':'Brain implementation')+'</label><select id="component-'+role+'" data-component-role="'+role+'">'+components.items.filter(c=>c.role===role).map(c=>option(c.id,c.name+' / '+c.id,c.id===(selected[role]||components.defaults[role]))).join('')+'</select>').join('');
  const providers=providerRows();
  $('#runtime-content').innerHTML='<section class="settings-section" id="settings-budget"><h2>Budget</h2><p class="budget-sentence">Reading the ledger…</p></section>'
   +'<section class="settings-section" id="settings-capacity"><h2>Capacity</h2><dl class="facts"><dt>'+(runtime.agent_metric==='allocated'?'Assigned agent slots':'Active agents')+'</dt><dd>'+runtime.active_agents+' / '+runtime.max_agents+'</dd><dt>Concurrent runs</dt><dd>Up to '+runtime.max_runs+'</dd><dt>Execution</dt><dd>'+(runtime.mode==='coordinator-workers'?'Worker pool':'Local worker')+'</dd>'+(runtime.worker_nodes||[]).map(w=>'<dt>Worker '+esc(w.worker)+'</dt><dd>'+(w.connected?'Connected':'Offline')+' · '+w.active_jobs.length+' assigned runs</dd>').join('')+'</dl></section>'
   +'<section class="settings-section" id="settings-providers"><h2>Providers</h2>'+(providers.length?'<dl class="facts">'+providers.map(p=>'<dt>'+esc(providerWords[p.provider]||p.provider)+'</dt><dd>'+'<span class="key-state '+(p.available?'present':'missing')+'">'+(p.available?'Key present':'No key')+'</span><span class="key-note">'+(p.available?p.models+' '+(p.models===1?'model':'models'):esc((p.reason||'Add the key to .env').replace(/^Add /,'add ')))+'</span></dd>').join('')+'</dl>':'<p>No API providers configured.</p>')+(providers.some(p=>!p.available)?'<p class="field-hint">Keys live in workflowbench/.env on the server; the Studio reads whether one is present and never shows its value. <button class="text-button" type="button" id="copy-env-lines">Copy the missing lines for .env</button></p>':'<p class="field-hint">Keys live in workflowbench/.env on the server. The Studio reads whether one is present and never shows its value.</p>')+'</section>'
   +'<section class="settings-section" id="settings-genesis"><h2>Genesis</h2><div id="settings-genesis-config"><p class="meta">Reading…</p></div></section>';
  $('#runtime-advanced-content').innerHTML='<h3>Provider request limits</h3><p>'+esc(runtime.limits_note)+'</p><div class="table-scroll"><table class="history-table"><thead><tr><th>Provider</th><th>Concurrent requests</th><th>Requests / minute</th><th>Tokens / minute</th><th>Active</th></tr></thead><tbody><tr><td>Default for each provider</td><td>'+runtime.default_provider_limits.concurrency+'</td><td>'+runtime.default_provider_limits.requests_per_minute+'</td><td>Not configured</td><td>—</td></tr>'+runtime.providers.map(p=>'<tr><td>'+esc(p.provider)+'</td><td>'+p.concurrency+'</td><td>'+p.requests_per_minute+'</td><td>'+esc(p.tokens_per_minute??'Not configured')+'</td><td>'+p.active+'</td></tr>').join('')+'</tbody></table></div><details class="runtime-details"><summary>Recovery and configuration</summary><p>'+esc(runtime.recovery)+'</p><p>Set STUDIO_MAX_AGENTS, STUDIO_MAX_RUNS and STUDIO_PROVIDER_LIMITS on the server. This is a shared team workspace. Workers use authenticated connections and the same central budget. Unknown work is held for investigation rather than automatically replayed.</p></details><h3>Installed components</h3><div class="table-scroll"><table class="history-table"><thead><tr><th>Role</th><th>Implementation</th><th>Version ID</th></tr></thead><tbody>'+components.items.map(c=>'<tr><td>'+esc(c.role.replace('_',' '))+'</td><td>'+esc(c.name)+'</td><td><code title="'+esc(c.sha256)+'">'+esc(c.id)+'</code></td></tr>').join('')+'</tbody></table></div><details class="runtime-details"><summary>Harness API</summary><p>Select installed component IDs, a track, task IDs, architecture versions and concurrency when creating a run. The recorded manifest freezes those choices.</p><pre>GET /api/components\nGET /api/runtime\nGET /api/jobs\nPOST /api/jobs\nGET /api/leaderboard</pre><p>Use the existing authenticated session and X-Studio-Token for writes. Server-side plugins register trusted implementations; the API does not accept executable code.</p></details>';
  if(window.renderGenesisConfig)renderGenesisConfig($('#settings-genesis-config'));
  $('#copy-env-lines')?.addEventListener('click',async()=>{const lines=providers.filter(p=>!p.available).map(p=>((p.reason||'').match(/Add ([A-Z0-9_]+) to/)||[])[1]).filter(Boolean).map(k=>k+'=');try{await navigator.clipboard.writeText(lines.join('\n')+'\n');toast('Copied '+lines.length+' lines');}catch{toast(lines.join(' '));}});
  api('/api/budget').then(b=>{const slot=$('#settings-budget .budget-sentence');if(!slot)return;slot.innerHTML=knownNumber(b?.available)?esc(money(b.available)+' left of '+money(b.weekly_limit)+' this week, '+money(b.held)+' reserved. ')+'<button class="text-button" type="button" id="open-budget-page">Open the ledger</button>':'The ledger is not available.';$('#open-budget-page')?.addEventListener('click',()=>openBudget());}).catch(()=>{const slot=$('#settings-budget .budget-sentence');if(slot)slot.textContent='The ledger is not available.';});
}
$('#nav-benchmarks').onclick=()=>window.openBenchmarks();
$('#nav-runtime').onclick=async()=>{showWorkspaceSurface('runtime');try{await loadRuntime();await loadEnterprise();}catch(e){toast(e.message);}};
async function loadEnterprise(){let value={};try{value=await api('/api/architectures/default');}catch(e){value={error:e.message};}$('#enterprise-status').innerHTML='<dl class="facts"><dt>Synced source</dt><dd>'+(value.commit?'<a href="'+esc(value.url||'https://github.com/TestBoxLab/monarch')+'" target="_blank" rel="noreferrer">'+esc(value.commit.slice(0,12))+'</a> on main':'<span class="neutral">Not resolved'+(value.error?' · '+esc(value.error):'')+'</span>')+'</dd><dt>Deployed runtime</dt><dd id="enterprise-verified">'+esc((()=>{try{const v=JSON.parse(localStorage.getItem('ailabs-enterprise-verified')||'null');return v?v.text+' (checked '+new Date(v.at).toLocaleString()+')':'Not verified yet';}catch{return 'Not verified yet';}})())+'</dd></dl><p class="field-hint">Monarch keeps its own configuration. Sync pulls GitHub main; it does not update or certify the deployed runtime. Existing runs keep their pinned version.</p>';}
$('#enterprise-sync').onclick=async()=>{const done=busy($('#enterprise-sync'),'Checking GitHub…');try{const v=await api('/api/architectures/sync',{});await loadEnterprise();$('#enterprise-status').insertAdjacentHTML('afterbegin','<p class="sync-result">'+esc(v.message)+'</p>');}catch(e){$('#enterprise-status').textContent=e.message;}finally{done();}};
$('#enterprise-verify').onclick=async()=>{const done=busy($('#enterprise-verify'),'Verifying…');try{const v=await api('/api/architectures/enterprise/verify',{});const text=v.probe.ok?'Verified. Its pinned configuration is available for eligible workflow runs.':'Could not be verified: '+(v.probe.checks.find(c=>!c.ok)?.detail||'See integration readiness.');try{localStorage.setItem('ailabs-enterprise-verified',JSON.stringify({text,at:new Date().toISOString()}));}catch{}const slot=$('#enterprise-verified');if(slot)slot.textContent=text+' (checked just now)';else $('#enterprise-status').textContent=text;}catch(e){const slot=$('#enterprise-verified');if(slot)slot.textContent=e.message;else $('#enterprise-status').textContent=e.message;}finally{done();}};
$('#run-track').onchange=()=>renderComparisonVersions().catch(e=>toast(e.message));
$('#run-concurrency').oninput=launchSize;
$('#blueprint-track').onchange=e=>{commit();blueprint.track=e.target.value;markDirty();render();renderInspector();$('#architecture-track-note').textContent=blueprint.track==='create-and-run'?'Design how a workflow is configured. Result Output receives the workflow artifact; the benchmark saves and executes it.':'Design how an agent attends to a request. Monarch Enterprise is a separate reference implementation.';};

const priorRenderPgPlan=renderPgPlan;
renderPgPlan=function(){priorRenderPgPlan();if(!pg)return;const p=pgPlan();$('#pg-plan-diff').innerHTML='<details class="pg-change-preview"><summary>Preview enrichment changes</summary><div class="change-counts"><span>'+p.fresh.length+' new</span><span>'+p.changed.length+' changed</span><span>'+p.carried.length+' carried</span><span>'+p.removed.length+' removed</span></div>'+[...p.fresh.map(f=>['Add',f.path]),...p.changed.map(f=>['Research again',f.path]),...p.removed.map(f=>['Remove',f])].map(([kind,path])=>'<p><strong>'+kind+'</strong> '+esc(path)+'</p>').join('')+'</details>';};
const priorRenderPgVersions=renderPgVersions;
renderPgVersions=function(){priorRenderPgVersions();$$('[data-pg-records]').forEach(b=>b.textContent=b.getAttribute('aria-expanded')==='true'?'Close review':'Review changes');$$('.pg-version .graph-field-list').forEach(list=>{const detail=document.createElement('details');detail.className='pg-schema-detail';detail.innerHTML='<summary>Field definitions</summary>';list.replaceWith(detail);detail.append(list);});};
function graphChanges(v){
 const before=pgRecord()?.versions.find(x=>x.version===v.parent_version),rows=[];
 const products=[...new Set([...Object.keys(before?.records||{}),...Object.keys(v.records||{})])].sort();
 const paths=[...new Set([...(before?.fields||[]).map(f=>f.path),...v.fields.map(f=>f.path)])];
 for(const product of products)for(const field of paths){const old=before?.records?.[product],next=v.records?.[product];const oldPresent=!!old&&Object.hasOwn(old,field),newPresent=!!next&&Object.hasOwn(next,field);const a=oldPresent?old[field]:undefined,b=newPresent?next[field]:undefined;
 const kind=!oldPresent&&!newPresent?'missing':!oldPresent?'added':!newPresent?'removed':JSON.stringify(a)===JSON.stringify(b)?'unchanged':'changed';rows.push({product,field,before:a,after:b,oldPresent,newPresent,kind,unresolved:newPresent&&typeof b==='string'&&b.trim().toLowerCase()==='unknown'});}
 return rows;
}
function graphValue(value,present){if(!present)return '<span class="missing-value">Not present</span>';if(value===null)return '<code>null</code>';if(typeof value==='string')return '<span>'+esc(value||'(empty string)')+'</span>';return '<pre>'+esc(JSON.stringify(value,null,2))+'</pre>';}
renderPgRecords=function(v){
 const rows=graphChanges(v),changed=rows.filter(r=>r.kind!=='unchanged');const unresolved=rows.filter(r=>r.unresolved).length,additions=rows.filter(r=>r.kind==='added').length;
 return '<section class="pg-review" data-review-version="'+v.version+'"><h4>'+(v.parent_version?'Version '+v.parent_version+' to version '+v.version:'Initial enrichment')+'</h4><p>'+additions+' added values; '+unresolved+' explicitly unknown. '+changed.length+' changed or missing values across '+Object.keys(v.records||{}).length+' products.</p><div class="pg-review-tools"><label>Find a product or field<input type="search" data-diff-search placeholder="Search changes"></label><label>Show<select data-diff-filter><option value="changes">Changed and missing</option><option value="all">All values</option><option value="added">Added</option><option value="changed">Changed</option><option value="removed">Removed</option><option value="unchanged">Unchanged</option><option value="missing">Missing</option></select></label></div><p data-diff-count role="status"></p><div class="table-scroll"><table class="diff-table"><thead><tr><th>Product / field</th><th>Before'+(v.parent_version?' / v'+v.parent_version:'')+'</th><th>After / v'+v.version+'</th><th>Change</th></tr></thead><tbody>'+rows.map(r=>'<tr data-diff-kind="'+r.kind+'" data-diff-text="'+esc((r.product+' '+r.field).toLowerCase())+'"'+(r.kind==='unchanged'?' hidden':'')+'><th scope="row">'+esc(r.product)+'<small>'+esc(r.field)+'</small></th><td data-label="Before">'+graphValue(r.before,r.oldPresent)+'</td><td data-label="After">'+graphValue(r.after,r.newPresent)+(r.unresolved?'<small class="unknown-label">Unresolved</small>':'')+'</td><td data-label="Change"><span class="change-label '+r.kind+'">'+esc(r.kind)+'</span></td></tr>').join('')+'</tbody></table></div><details class="pg-log-section"><summary data-graph-log="'+v.version+'">Research activity and logs</summary><div data-log-body><p>Open to load the recorded research.</p></div></details></section>';
};
function filterDiff(review){const q=review.querySelector('[data-diff-search]').value.toLowerCase(),kind=review.querySelector('[data-diff-filter]').value;let visible=0;review.querySelectorAll('[data-diff-kind]').forEach(row=>{row.hidden=!row.dataset.diffText.includes(q)||(kind==='changes'?row.dataset.diffKind==='unchanged':kind!=='all'&&row.dataset.diffKind!==kind);if(!row.hidden)visible++;});review.querySelector('[data-diff-count]').textContent=visible+' values shown';}
document.addEventListener('input',e=>{if(e.target.matches('[data-diff-search]'))filterDiff(e.target.closest('.pg-review'));});
document.addEventListener('change',e=>{if(e.target.matches('[data-diff-filter]'))filterDiff(e.target.closest('.pg-review'));});
document.addEventListener('click',async e=>{const summary=e.target.closest('[data-graph-log]');if(!summary)return;const graph=pg?.id,version=summary.dataset.graphLog,body=summary.parentElement.querySelector('[data-log-body]'),key=graph+'/'+version;if(!graph)return;body.textContent='Loading research activity…';try{if(!graphLogCache.has(key))graphLogCache.set(key,(await api('/api/product-graphs/'+graph+'/versions/'+version+'/events')).events);const rows=graphLogCache.get(key);if(!body.isConnected)return;body.innerHTML='<ol class="research-log">'+rows.map(r=>'<li><details><summary><span>'+esc(({step_started:'Research started',model_started:'Model request',model_finished:'Model response',node_started:'Catalog search',node_finished:'Search result',step_finished:'Research finished',billing:'Usage recorded'})[r.type]||r.type.replaceAll('_',' '))+'</span><time>'+esc(new Date(r.at).toLocaleTimeString())+'</time></summary><pre>'+esc(JSON.stringify(r,null,2))+'</pre></details></li>').join('')+'</ol>'+(rows.length?'':'<p>No research events were recorded for this version.</p>');}catch(err){body.textContent=err.message;}});
loadRuntime().catch(()=>{});
showWorkspaceSurface('runs',false);

const diagnosticsCache = new Map(), diagnosticsPending = new Set();
const originalRenderReport = renderReport;
renderReport=function(){
 originalRenderReport();if(!job||!report)return;
 const key=job.id+':'+job.completed+':'+job.status;
 const section=document.createElement('section');section.id='failure-breakdown';section.className='failure-breakdown';
 const slot=$('#failure-slot');if(slot)slot.replaceWith(section);else $('#report-view').prepend(section);
 if(diagnosticsCache.has(key)){renderDiagnostics(diagnosticsCache.get(key));return;}
 section.innerHTML='<p class="node-help">Reading recorded checks and execution events…</p>';
 if(diagnosticsPending.has(key))return;
 diagnosticsPending.add(key);
 api('/api/jobs/'+job.id+'/diagnostics').then(data=>{diagnosticsCache.set(key,data);if(job&&job.id+':'+job.completed+':'+job.status===key)renderDiagnostics(data);}).catch(e=>{if(job&&job.id+':'+job.completed+':'+job.status===key&&$('#failure-breakdown'))$('#failure-breakdown').textContent=e.message;}).finally(()=>diagnosticsPending.delete(key));
};
function renderDiagnostics(data){
 const box=$('#failure-breakdown');if(!box)return;
 const counts=data.summary,failed=counts.failed_attempts;
 box.innerHTML='<h3>Where it failed</h3>'+suspectLine(data)
  +(failed?'<div data-slot="failure-columns"></div>'+failureMix(data)
     +'<p class="failure-count" id="diagnostic-count" role="status"></p>'
     +'<div id="diagnostic-attempts">'+data.attempts.filter(a=>!a.passed).map(diagnosticAttempt).join('')+'</div>'
   :'<p>No failed attempts in the recorded outcomes.</p>')
  +(counts.unrecorded_attempts?'<p class="node-help">'+counts.unrecorded_attempts+' '+plural(counts.unrecorded_attempts,'attempt')+' have no recorded outcome.</p>':'')
  +'<details class="diagnostic-limits"><summary>Evidence limits</summary><p>'+esc(Array.isArray(data.limitations)?data.limitations.join(' '):(data.limitations||''))+'</p></details>';
 if(failed){
  const chart=Charts.failureColumns({buckets:data.buckets,failed,
   title:failed+' of '+counts.recorded_attempts+' attempts failed',
   source:'One bucket per failed attempt, read from the record.'});
  $('[data-slot="failure-columns"]',box).replaceWith(chart);
  bindBucketFilter(box,data,failed);
 }
 bindEvidence();
}
// A column filters the evidence beneath it; the mix table follows the same choice.
// Delegated, because the chart kit swaps the figure element when it refits to a
// new width and a handler bound to the old node would go with it.
function bindBucketFilter(box,data,failed){
 let chosen=null;
 const paint=()=>{
  $$('[data-bucket]',box).forEach(c=>c.setAttribute('aria-pressed',String(c.dataset.bucket===chosen)));
  $$('[data-mix-bucket]',box).forEach(c=>c.classList.toggle('chosen',!!chosen&&c.dataset.mixBucket===chosen));
  const shown=data.attempts.filter(a=>!a.passed&&(!chosen||a.bucket===chosen));
  const count=$('#diagnostic-count');
  if(count)count.textContent=chosen?shown.length+' of '+failed+' failed attempts':'';
  $('#diagnostic-attempts').innerHTML=shown.map(diagnosticAttempt).join('');
  bindEvidence();
 };
 const toggle=event=>{
  const column=event.target.closest?.('[data-bucket]');
  if(!column||!box.contains(column))return false;
  chosen=chosen===column.dataset.bucket?null:column.dataset.bucket;paint();return true;
 };
 box.addEventListener('click',toggle);
 box.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&toggle(e))e.preventDefault();});
 paint();
}
// A task every model failed the same way is a task to suspect, not a model.
function suspectLine(data){
 const suspects=data.story?.suspect_tasks||[];
 if(!suspects.length)return '';
 return '<p class="suspect-note"><strong>Suspect the task first.</strong> '
  +suspects.map(t=>esc(shortTaskLabel(t.task))+' ('+esc(String(t.mode_label||'').toLowerCase())+', every model)').join('; ')+'.</p>';
}
// How each model fails, not just how often. A table, because at six buckets and
// seven setups a stacked bar loses the baseline every comparison needs.
function failureMix(data){
 const failed=data.attempts.filter(a=>!a.passed);
 const buckets=data.buckets.filter(b=>b.count).sort((a,b)=>b.count-a.count);
 const setups=[...new Set(failed.map(a=>a.model))];
 if(buckets.length<2||setups.length<2)return '';
 const tally=new Map(setups.map(m=>[m,{total:0,by:new Map()}]));
 for(const a of failed){const row=tally.get(a.model);row.total++;row.by.set(a.bucket,(row.by.get(a.bucket)||0)+1);}
 const rows=[...tally.entries()].sort((a,b)=>b[1].total-a[1].total);
 const head='<tr><th scope="col">Model</th><th scope="col" class="num">Failed</th>'
  +buckets.map(b=>'<th scope="col" class="num" data-mix-bucket="'+esc(b.id)+'">'+esc(b.short_label||b.label)+'</th>').join('')+'</tr>';
 const body=rows.map(([model,row])=>'<tr><th scope="row">'+esc(modelName(model))+'</th><td class="num">'+row.total+'</td>'
  +buckets.map(b=>{const n=row.by.get(b.id)||0;
   return '<td class="num'+(n?'':' mix-none')+'" data-mix-bucket="'+esc(b.id)+'"'+(n?' title="'+n+' of '+row.total+'"':'')+'>'+(n?Math.round(n*100/row.total)+'%':'—')+'</td>';}).join('')+'</tr>').join('');
 return '<h4 class="mix-heading">Failure mix by model</h4><div class="table-scroll"><table class="table failure-mix">'
  +'<caption class="sr-only">Share of each model’s failed attempts by bucket</caption>'
  +'<thead>'+head+'</thead><tbody>'+body+'</tbody></table></div>';
}
function diagnosticAttempt(a){const seen=new Set();const facts=(a.observed_facts||[]).map(f=>f.text);const line=facts.find(x=>!/^(Recorded |Passed:|Failed:)/.test(x))||facts.find(x=>/^Failed:/.test(x))||a.headline||'';return '<details class="diagnostic-attempt"><summary><span class="diag-task">'+esc(shortTaskLabel(a.task))+'</span><span class="diag-line">'+esc(line)+'</span><small>'+esc(modelName(a.model))+'</small></summary><h4>'+esc(a.headline)+'</h4><p>'+esc(a.narrative)+'</p>'+(a.story?'<p class="meta">'+esc(a.story.mode_label)+(a.story.turning_point?' · '+esc(a.story.turning_point.text)+' '+evidenceButton(a.story.turning_point.event_id):'')+'</p>':'')+'<ul>'+a.observed_facts.map(f=>'<li>'+esc(f.text)+(f.event_ids||[]).filter(id=>!seen.has(id)&&seen.add(id)).map(id=>' '+evidenceButton(id)).join('')+'</li>').join('')+'</ul><details><summary>Recorded checks</summary><dl>'+a.checks.map(c=>'<dt>'+esc(c.title||c.name)+'</dt><dd>'+esc(c.passed?'Met':'Not met')+'</dd>').join('')+'</dl></details>'+(a.earliest_supported_evidence?'<p>Earliest linked evidence: '+esc(a.earliest_supported_evidence.text)+' '+evidenceButton(a.earliest_supported_evidence.event_id)+'</p>':'')+'<p class="node-help">'+esc(Array.isArray(a.limitations)?a.limitations.join(' '):(a.limitations||''))+'</p></details>';}
function applyTheme(theme){document.documentElement.dataset.theme=theme;document.documentElement.classList.toggle('dark',theme==='dark');$('#theme-toggle').textContent=theme==='dark'?'Light':'Dark';$('#theme-toggle').setAttribute('aria-label','Switch to '+(theme==='dark'?'light':'dark')+' theme');}
$('#theme-toggle').onclick=()=>{const theme=document.documentElement.dataset.theme==='dark'?'light':'dark';applyTheme(theme);try{localStorage.setItem('ailabs-theme',theme);}catch{}};
try{applyTheme(localStorage.getItem('ailabs-theme')||'light');}catch{applyTheme('light');}

$$('[data-pg-view][type=button]').forEach(button=>button.onclick=()=>{
 const mode=button.dataset.pgView;$('.pg-workspace').dataset.pgView=mode;
 $$('[data-pg-view][type=button]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));
 if(mode==='review'&&pgRecord()?.versions.length&&!pgOpenRecords.size){pgOpenRecords.add(pgRecord().versions.at(-1).version);renderPgVersions();}
});



// One router. It was inline in the popstate listener, so "go to this address" existed
// only as a side effect of the browser going back — anything else wanting to route had to
// write a second copy (feature 024, stage S5).
window.goRoute=async function(hash){
 if(!state)return;
 const route=String(hash||location.hash).replace(/^#/,'');
 try{if(route.startsWith('run/')){const id=decodeURIComponent(route.slice(4).split('/')[0]);if(typeof job!=='undefined'&&job?.id===id&&!$('.workspace').classList.contains('hidden')){if(window.syncAttemptFromHash)syncAttemptFromHash();}else await openJob(id);}else if(route==='genesis'||route.startsWith('genesis/'))await openGenesis();else if(route==='studio'||route.startsWith('studio/')){await $('#open-setup').onclick();const id=route.slice(7);if(id&&window.openStudioItem)window.openStudioItem(decodeURIComponent(id));}else if(route==='budget')await openBudget();else if(route==='launch')await openLaunch();else if(route==='benchmarks'||route.startsWith('benchmarks/'))await window.openBenchmarks(route.split('/')[1]);else if(route==='runtime')await $('#nav-runtime').onclick();else if(route==='runs')showWorkspaceSurface('runs',false);else if(route==='reports'||route==='leaderboard'||route===''||route.startsWith('report/')||route.startsWith('round/'))await window.reportRoute(location.hash);else showWorkspaceSurface('runs',false);}catch(e){toast(e.message);}
};
window.addEventListener('popstate',()=>window.goRoute(location.hash));
