'use strict';
const compact=n=>Number(n).toLocaleString('en-US',{notation:'compact',maximumFractionDigits:1});
const pct=n=>(n*100).toFixed(1)+'%';
let usageData, ledgerData=null, usagePeriod='week', usageModel='',usageDay='';
function readableRunConfig(j){const c=j.settings.configuration||{},components=j.component_manifest;return '<dl><dt>Evaluation</dt><dd>'+esc(trackName(j.settings.track))+'</dd><dt>Tasks</dt><dd>'+j.settings.tasks.length+'</dd><dt>Thinking</dt><dd>'+esc([...new Set((j.settings.arms||[]).map(a=>a.runner_override?.effort||a.runner?.effort).filter(Boolean))].join(', ')||'Saved per-step settings')+'</dd><dt>Instructions</dt><dd>'+(c.prompt?'Custom instructions':'Original task instructions')+'</dd><dt>Version record</dt><dd>'+(components?'Components pinned':'Historical · component pins unavailable')+'</dd></dl>';}
function downloadData(name,value){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
document.addEventListener('click',e=>{const b=e.target.closest('[data-download-run]');if(b){const j=state.jobs.find(j=>j.id===b.dataset.downloadRun);if(j)downloadData('run-'+j.id+'-configuration.json',{settings:j.settings,components:j.component_manifest,runtime:j.runtime_manifest,execution:j.execution_manifests});}});
async function openBudget(){showWorkspaceSurface('budget');$('#budget-content').innerHTML='<p>Reading the ledger…</p>';try{[usageData,ledgerData]=await Promise.all([api('/api/usage'),api('/api/budget/ledger').catch(()=>null)]);state.budget=usageData.budget;renderBudget();}catch(e){$('#budget-content').innerHTML='<p>'+esc(e.message)+'</p><button class="button" id="retry-budget">Retry</button>';$('#retry-budget').onclick=openBudget;}}
function ledgerTable(){
 if(!ledgerData)return '<p class="empty-line">The ledger could not be read.</p>';
 const lines=ledgerData.lines||[];if(!lines.length)return '<p class="empty-line">Nothing reserved this week. A launch, a Genesis turn or a paid analysis writes a line here the moment its ceiling is reserved.</p>';
 const when=iso=>{const d=new Date(iso);return d.toLocaleDateString('en-US',{month:'short',day:'numeric'})+' '+d.toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit',hour12:false});};
 const stateWord=l=>l.state==='open'?'Reserved':l.state==='settled'?'Settled':l.state==='released'?'Released, cost unknown':'Closed';
 return '<div class="table-scroll"><table class="table ledger-table"><thead><tr><th>When</th><th>What</th><th>Who</th><th class="num">Ceiling</th><th class="num">Settled</th><th class="num">Requests</th><th>State</th></tr></thead><tbody>'+lines.map(l=>'<tr><td><time datetime="'+esc(l.created_at)+'">'+esc(when(l.created_at))+'</time></td><td>'+(l.run?'<button class="text-button" type="button" data-usage-run="'+esc(l.run)+'">'+esc(l.what)+'</button>':esc(l.what))+(l.kind==='request'?'<small>single request</small>':'')+'</td><td>'+esc(l.who)+'</td><td class="num">'+esc(money(l.maximum_usd))+'</td><td class="num">'+(l.actual_usd===null?'—':esc(money(l.actual_usd)))+'</td><td class="num">'+l.settled+' / '+l.requests+'</td><td><span class="ledger-state '+esc(l.state)+'">'+stateWord(l)+'</span></td></tr>').join('')+'</tbody></table></div>';
}
$('#nav-budget').onclick=openBudget;
function dateKey(date){return new Intl.DateTimeFormat('en-CA',{timeZone:'America/Sao_Paulo',year:'numeric',month:'2-digit',day:'2-digit'}).format(date);}
function periodRows(){const cutoff=new Date();cutoff.setUTCDate(cutoff.getUTCDate()-(Number(usagePeriod)-1));const min=usagePeriod==='week'?(usageData.budget?.week_start||dateKey(new Date())):dateKey(cutoff);return usageData.rows.filter(r=>(usagePeriod==='all'||r.day>=min)&&(!usageModel||r.model===usageModel));}
function chartDays(rows){const today=dateKey(new Date()),count=usagePeriod==='all'?Math.min(90,Math.max(7,...rows.filter(r=>r.day).map(r=>Math.ceil((Date.parse(today)-Date.parse(r.day))/86400000)+1))):usagePeriod==='week'?7:Number(usagePeriod);return Array.from({length:count},(_,i)=>new Date(Date.parse(today)-(count-1-i)*86400000).toISOString().slice(0,10));}
function familyClass(model){return 'family-'+(model==='Mixed / unattributed models'?'other':Charts.familyOf(model));}
function usageColumns(rows,metric,models){
 const values=models.map(m=>{const known=rows.filter(r=>r.model===m&&r[metric]!==null);return known.length?known.reduce((n,r)=>n+r[metric],0):null;});
 return Charts.columns({groups:models.map((m,i)=>({label:m.length>18?m.slice(0,16)+'…':m,sub:String(i+1),values:[{label:m,value:values[i]||0,family:familyClass(m).slice(7),data:{usageModel:m},aria:m+': '+(values[i]===null?'unknown':metric==='cost'?money(values[i]):compact(values[i]))}]})),format:metric==='cost'?money:compact,source:metric==='cost'?'Known task costs in USD for the selected period.':'Input and output tokens; cached input counted once.',empty:metric==='cost'?'No known cost in this period':'No recorded usage in this period'});
}
function modelLegend(models){return '<div class="usage-legend" aria-label="Model colors">'+models.map((m,i)=>'<button data-model-filter="'+esc(m)+'"><i class="model-dot '+familyClass(m)+'"></i>'+(i+1)+'. '+esc(m)+'</button>').join('')+'</div>';}
function renderBudget(){const all=usageData.rows,rows=periodRows(),models=[...new Set(rows.map(r=>r.model))].sort(),b=usageData.budget,totalTokens=rows.reduce((n,r)=>n+(r.tokens??0),0),totalCost=rows.reduce((n,r)=>n+(r.cost??0),0);const modelRows=models.map(m=>{const rs=rows.filter(r=>r.model===m);return {name:m,tokens:rs.reduce((n,r)=>n+(r.tokens??0),0),input:rs.reduce((n,r)=>n+(r.input??0),0),output:rs.reduce((n,r)=>n+(r.output??0),0),cost:rs.reduce((n,r)=>n+(r.cost??0),0),unknown:rs.filter(r=>r.tokens===null||r.cost===null).length,attempts:rs.length};});
const sentence=knownNumber(b.available)?money(b.available)+' left of '+money(b.weekly_limit)+' this week (week of '+b.week_start+', resets Monday 00:00 São Paulo); '+money(b.held)+' reserved, '+money(b.actual)+' settled. A launch reserves its ceiling first and settles from receipts.':'The ledger is not available.';
$('#budget-content').innerHTML='<p class="budget-sentence">'+esc(sentence)+'</p><p class="meta budget-cap">An attempt stops at '+esc(money(3))+' unless the plan says otherwise. Lucas approves rounds above smoke scale.</p>'
+(allowanceTable()?'<section class="budget-section"><h2>Allowances</h2>'+allowanceTable()+'</section>':'')
+'<section class="budget-section"><h2>Ledger</h2>'+ledgerTable()+'</section>'
+'<section class="budget-section"><div class="analytics-toolbar"><h2>Usage by model</h2><div class="history-filters" role="group" aria-label="Period">'+[['week','This week'],['7','7 days'],['30','30 days'],['all','All recorded']].map(([v,l])=>'<button type="button" data-usage-period="'+v+'" aria-pressed="'+String(usagePeriod===v)+'">'+l+'</button>').join('')+'</div>'+(all.length?'<label class="history-sort">Model<select id="usage-model"><option value="">All models</option>'+[...new Set(all.map(r=>r.model))].sort().map(m=>'<option value="'+esc(m)+'">'+esc(m)+'</option>').join('')+'</select></label>':'')+'<button class="text-button" id="usage-refresh" type="button">Refresh</button></div>'
+(rows.length?'<div class="analytics-chart-pair"><section class="chart-panel"><div class="chart-heading"><h3>Tokens</h3><strong>'+compact(totalTokens)+'</strong></div><div data-chart-slot="tokens"></div></section><section class="chart-panel"><div class="chart-heading"><h3>Cost</h3><strong>'+money(totalCost)+'</strong></div><div data-chart-slot="cost"></div></section></div>'+(rows.some(r=>r.tokens===null||r.cost===null)?'<p class="analytics-note">'+rows.filter(r=>r.tokens===null||r.cost===null).length+' attempts have incomplete usage.</p>':'')+'<div id="usage-inspection"></div><div class="table-scroll"><table class="history-table model-usage-table"><thead><tr><th>Model</th><th class="num">Input</th><th class="num">Output</th><th class="num">Total tokens</th><th class="num">Known cost</th><th class="num">Attempts</th><th class="num">Missing usage</th></tr></thead><tbody>'+modelRows.map(m=>'<tr><th><button class="text-button" data-model-filter="'+esc(m.name)+'"><i class="model-dot '+familyClass(m.name)+'"></i>'+esc(m.name)+'</button></th><td class="num">'+compact(m.input)+'</td><td class="num">'+compact(m.output)+'</td><td class="num">'+compact(m.tokens)+'</td><td class="num">'+money(m.cost)+'</td><td class="num">'+m.attempts+'</td><td class="num">'+m.unknown+'</td></tr>').join('')+'</tbody></table></div>':'<p class="empty-line">No paid task usage in this period. Scripted checks cost nothing; model runs appear here by model with tokens and known cost.</p><div id="usage-inspection"></div>')
+(rows.length?'<p class="analytics-note">'+esc(usageData.scope)+'</p>':'')+'</section>';
for(const metric of ['tokens','cost']){const slot=$('[data-chart-slot="'+metric+'"]');if(slot)slot.replaceWith(usageColumns(rows,metric,models));}
$$('[data-usage-period]').forEach(b=>b.onclick=()=>{usagePeriod=b.dataset.usagePeriod;usageDay='';renderBudget();});
if($('#usage-model')){$('#usage-model').value=usageModel;$('#usage-model').onchange=e=>{usageModel=e.target.value;usageDay='';renderBudget()};}
bindAllowances();$('#usage-refresh').onclick=openBudget;$$('[data-model-filter]').forEach(b=>b.onclick=()=>{usageModel=b.dataset.modelFilter===usageModel?'':b.dataset.modelFilter;renderBudget()});$$('[data-usage-model]').forEach(g=>{g.onclick=()=>inspectUsageModel(g.dataset.usageModel);g.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();g.onclick();}}});$$('#budget-content [data-usage-run]').forEach(b=>b.onclick=()=>openJob(b.dataset.usageRun));applyChartStyles();}
// The week's named allowances: a ceiling per kind of work inside the one $300 lab week.
// An allowance nobody set reads as no limit; that work draws on what the week has left.
function allowanceTable(){
 const rows=(ledgerData&&ledgerData.allowances)||[];
 if(!rows.length)return '';  // the ledger is unavailable; the Ledger section already says so once
 return '<div class="table-scroll"><table class="history-table allowance-table"><thead><tr><th>Work</th><th class="num">Weekly limit</th><th class="num">Held</th><th class="num">Settled</th><th class="num">Left</th><th></th></tr></thead><tbody>'
  +rows.map(a=>'<tr><th>'+esc(a.label)+'</th>'
   +'<td class="num">'+(a.limit_usd?esc(money(a.limit_usd)):'<span class="no-limit">No weekly limit</span>')+'</td>'
   +'<td class="num">'+esc(money(a.held_usd))+'</td><td class="num">'+esc(money(a.settled_usd))+'</td>'
   +'<td class="num">'+(a.left_usd?esc(money(a.left_usd)):'—')+'</td>'
   +'<td class="num"><button class="text-button" data-set-allowance="'+esc(a.kind)+'">'+(a.limit_usd?'Change':'Set a limit')+'</button></td></tr>').join('')
  +'</tbody></table></div>';
}
function bindAllowances(){
 $$('[data-set-allowance]').forEach(b=>b.onclick=async()=>{
  const kind=b.dataset.setAllowance,now=(ledgerData.allowances||[]).find(a=>a.kind===kind)||{};
  const answer=prompt('Weekly limit in dollars for '+now.label+'. Leave empty for no limit.',now.limit_usd||'');
  if(answer===null)return;
  try{await api('/api/budget/allowances',{kind,limit_usd:answer.trim()});await openBudget();}catch(e){toast(e.message);}
 });
}
function inspectUsageModel(model){const rows=periodRows().filter(r=>r.model===model),runs=[...new Set(rows.map(r=>r.run))];
 $('#usage-inspection').innerHTML='<section class="usage-run-list"><div class="usage-list-heading"><h3>'+esc(model)+'</h3><button class="text-button" id="close-usage-day">Close</button></div><div class="table-scroll"><table class="history-table"><thead><tr><th>Run</th><th>Tokens</th><th>Known cost</th></tr></thead><tbody>'+runs.map(id=>{const rs=rows.filter(r=>r.run===id);return '<tr><th><button class="text-button" data-usage-run="'+esc(id)+'">'+esc(rs[0].title)+'</button></th><td>'+compact(rs.reduce((n,r)=>n+(r.tokens??0),0))+'</td><td>'+money(rs.reduce((n,r)=>n+(r.cost??0),0))+'</td></tr>';}).join('')+'</tbody></table></div></section>';
 const heading=$('#usage-inspection h3');heading.tabIndex=-1;heading.focus({preventScroll:true});$$('[data-usage-run]').forEach(b=>b.onclick=()=>openJob(b.dataset.usageRun));$('#close-usage-day').onclick=()=>{$('#usage-inspection').innerHTML='';};
}

function applyChartStyles(){for(const el of $$('[data-chart-style]'))for(const item of el.dataset.chartStyle.split(';')){const colon=item.indexOf(':');if(colon>0)el.style.setProperty(item.slice(0,colon),item.slice(colon+1));}}
