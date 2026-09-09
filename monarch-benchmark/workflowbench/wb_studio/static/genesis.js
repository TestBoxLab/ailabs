'use strict';

let genesisData=null,genesisPoll=null,genesisParent=null,genesisCard=null;

const stageNames={research:'Research',hypothesis:'Hypotheses',approval:'Your review',running:'Experiments',review:'Findings',complete:'Decisions'};

async function openGenesis(){showWorkspaceSurface('genesis');try{genesisData=await api('/api/genesis');renderGenesis();if(genesisView==='library')loadLibrary();}catch(e){toast(e.message);}}

$('#nav-genesis').onclick=openGenesis;

$('#research-refresh').onclick=()=>genesisView==='library'?loadLibrary():openGenesis();

function renderGenesis(){

 const cards=genesisData.cards;if(genesisView==='board')$('#research-count').textContent=cards.length+' '+(cards.length===1?'idea':'ideas');

 if(!cards.length)$('#research-board').innerHTML='<div class="empty-state"><p>No hypotheses yet.</p><button class="button" type="button" id="research-empty-add">Add hypothesis</button></div>';else renderBoard(cards);

 $$('[data-card]').forEach(b=>b.onclick=()=>showResearchCard(b.dataset.card));
 $('#research-empty-add')?.addEventListener('click',()=>$('#research-new').click());

 renderGenesisModels();
 renderBrief();watchBoard();

 const turns=genesisData.turns;genesisParent=turns.at(-1)?.id||null;

 $('#genesis-messages').innerHTML=turns.length?turns.map(turnHtml).join(''): '<p class="genesis-welcome">Ask Genesis about a run, a source or a hypothesis.</p>';

 $('#genesis-messages').scrollTop=$('#genesis-messages').scrollHeight;
 const running=turns.find(t=>t.status==='running');if(running)pollGenesis(running.id);

}

function turnHtml(t){return '<article class="genesis-turn" data-turn="'+t.id+'"><div class="user-message"><span>You</span><p>'+esc(t.message)+'</p></div><div class="scientist-message"><span class="message-model" data-family="'+genesisFamily(t.model)+'">'+esc(genesisModelName(t.model))+'</span><div class="genesis-answer">'+genesisText(t.answer||'')+'</div><p class="genesis-turn-status">'+esc(t.status==='running'?'Responding...':t.status==='failed'?'Response interrupted.':'')+'</p><details><summary>Details</summary><div class="genesis-event-log">'+eventHtml(t)+'</div></details></div></article>';}

function eventHtml(t){return t.events.filter(e=>e.type!=='text_delta').map(e=>'<p><time>'+esc(new Date(e.at).toLocaleTimeString())+'</time> '+esc(e.action?human(e.action):e.message||human(e.type))+(e.cost_usd?' · '+money(e.cost_usd):'')+'</p>').join('');}

function pollGenesis(id){clearTimeout(genesisPoll);$('#genesis-send').disabled=true;$('#genesis-status').textContent='Working';genesisPoll=setTimeout(async()=>{try{const t=await api('/api/genesis/turns/'+id);const el=$$('[data-turn]').find(e=>e.dataset.turn===id);if(el){const messages=$('#genesis-messages'),follow=messages.scrollHeight-messages.scrollTop-messages.clientHeight<60;el.querySelector('.genesis-answer').innerHTML=genesisText(t.answer);if(follow)messages.scrollTop=messages.scrollHeight;el.querySelector('.genesis-event-log').innerHTML=eventHtml(t);el.querySelector('.genesis-turn-status').textContent=t.status==='running'?'Responding...':t.status==='failed'?'Response interrupted.':'';}if(t.status==='running')pollGenesis(id);else{$('#genesis-send').disabled=false;$('#genesis-status').textContent=t.status==='completed'?'':'Interrupted';genesisParent=id;genesisData=await api('/api/genesis');renderGenesis();}}catch(e){$('#genesis-status').textContent='Reconnecting';pollGenesis(id);}},650);}

$('#genesis-form').onsubmit=async e=>{e.preventDefault();$('#genesis-error').textContent='';$('#genesis-send').disabled=true;try{const t=await api('/api/genesis/chat',{message:$('#genesis-message').value,model:$('#genesis-model').value,effort:$('#genesis-effort').value,parent:genesisParent});$('#genesis-message').value='';if($('#genesis-messages .genesis-welcome'))$('#genesis-messages').innerHTML='';$('#genesis-messages').insertAdjacentHTML('beforeend',turnHtml(t));$('#genesis-messages').scrollTop=$('#genesis-messages').scrollHeight;pollGenesis(t.id);}catch(err){$('#genesis-error').textContent=err.message;$('#genesis-send').disabled=false;}};

function proposalReview(c){

 const p=c.proposal;if(!p)return '';const operation=p.operation||'run';

 const rows=operation==='prepare'?[['Product graph',p.graph],['Draft revision',p.graph_revision]]:operation==='analyze'?[['Run',p.run]]:[['Evaluation',trackName(p.track)],['Tasks',p.tasks?.length||0],['Architectures',(p.architectures||[]).join(', ')],['Models',(p.models||[]).map(modelName).join(', ')],['Concurrent agents',p.concurrency||1]];

 if(operation==='run')rows.push(['Goal',goalText(p.goal)]);

 rows.push(['Maximum spend',money(p.maximum_usd)]);

 return '<section class="proposal-review"><h3>'+({run:'Experiment',prepare:'Product graph preparation',analyze:'Run analysis'}[operation]||'Proposal')+'</h3><dl>'+rows.map(([label,value])=>'<dt>'+esc(label)+'</dt><dd>'+esc(value??'Not specified')+'</dd>').join('')+'</dl><details><summary>Exact configuration</summary><pre>'+esc(JSON.stringify(p,null,2))+'</pre></details><p>Approval applies to this revision. Budget and runtime checks still apply.</p>'+(c.stage==='approval'&&!c.approval?'<button class="button primary" id="proposal-approve">Approve '+(operation==='run'?'experiment':operation==='prepare'?'preparation':'analysis')+'</button>':'')+'</section>';

}

function showResearchCard(id){

 const c=genesisData.cards.find(c=>c.id===id);genesisCard=c;const box=$('#research-detail');box.classList.remove('hidden');

 const editable=c.stage!=='running'&&(!c.job||['completed','failed','cancelled','interrupted'].includes(c.run_status));

 box.innerHTML='<header><h2>'+esc(c.title)+'</h2><button class="text-button" id="research-close">Close</button></header>'+researchBody(c)+outcomeLine(c)+(c.evidence?.length?'<h3>Evidence</h3><ul>'+c.evidence.map(x=>'<li>'+esc(typeof x==='string'?x:JSON.stringify(x))+'</li>').join('')+'</ul>':'')+proposalReview(c)+(c.artifact?'<p class="research-artifact">'+esc(c.artifact.kind==='product_graph'?'Product graph version '+c.artifact.version+' prepared.':'Analysis '+c.artifact.status)+ '</p>':'')+(c.error?'<p role="alert">'+esc(c.error)+'</p>':'')+(c.job?'<button class="button primary" id="research-open-run">Observe experiment</button>':'')+(editable?'<details class="research-edit-details"><summary>Edit research card</summary><label>Notes<textarea id="research-notes" rows="6">'+esc(c.body)+'</textarea></label><div class="research-edit"><label>Stage<select id="research-stage">'+Object.entries(stageNames).filter(([key])=>key!=='running'&&(!c.job||['review','complete'].includes(key))).map(([key,name])=>option(key,name,key===c.stage)).join('')+'</select></label><button class="button" id="research-move">Save changes</button></div></details>':'')+'<p id="research-error" role="alert"></p>';

 $('#research-close').onclick=()=>box.classList.add('hidden');if($('#research-open-run'))$('#research-open-run').onclick=()=>openJob(c.job);
 if($('#research-stop'))$('#research-stop').onclick=async()=>{try{await api('/api/genesis/cards/'+c.id+'/stop',{});await openGenesis();showResearchCard(c.id);}catch(e){toast(e.message);}};pollWork(c);

 if($('#research-move'))$('#research-move').onclick=async()=>{try{await api('/api/genesis/cards',{...c,body:$('#research-notes').value,stage:$('#research-stage').value});await openGenesis();showResearchCard(c.id);}catch(e){$('#research-error').textContent=e.message;}};

 if($('#proposal-approve'))$('#proposal-approve').onclick=async()=>{const b=$('#proposal-approve');b.disabled=true;try{const result=await api('/api/genesis/cards/'+c.id+'/approve',{revision:c.revision,digest:c.proposal_digest});if(result.job)await openJob(result.job);else{await openGenesis();showResearchCard(c.id);}}catch(e){$('#research-error').textContent=e.message;b.disabled=false;}};

 box.focus({preventScroll:true});box.scrollIntoView({behavior:'smooth',block:'nearest'});

}

$('#research-new').onclick=()=>{const box=$('#research-detail');box.classList.remove('hidden');box.innerHTML='<header><h2>New hypothesis</h2><button class="text-button" id="research-close">Cancel</button></header><form id="research-new-form"><label>What might improve?<input id="research-title" maxlength="140" required></label><label>Evidence and proposed change<textarea id="research-body" rows="5" required></textarea></label><button class="button primary">Save hypothesis</button><p id="research-error" role="alert"></p></form>';$('#research-close').onclick=()=>box.classList.add('hidden');$('#research-new-form').onsubmit=async e=>{e.preventDefault();try{await api('/api/genesis/cards',{title:$('#research-title').value,body:$('#research-body').value,stage:'hypothesis'});box.classList.add('hidden');await openGenesis();}catch(err){$('#research-error').textContent=err.message;}};$('#research-title').focus();};


function genesisFamily(id){const name=String(id).toLowerCase();return name.includes('claude')?'claude':name.includes('gpt')?'gpt':name.includes('gemini')?'gemini':name.includes('kimi')?'kimi':name.includes('glm')?'glm':'other';}
function genesisModelName(id){const route=genesisData?.models.find(m=>m.id===id);const name=String(route?.name||id).split('/').at(-1),labels={'claude-opus-4-8':'Claude Opus 4.8','claude-opus-5':'Claude Opus 5','gemini-3.7-flash':'Gemini 3.7 Flash','gpt-5.6-sol':'GPT-5.6 Sol','gpt-5.6-terra':'GPT-5.6 Terra','glm-5p3':'GLM 5.3','glm-5.3':'GLM 5.3','kimi-k3':'Kimi K3'};return labels[name]||name;}
function renderGenesisModels(){
 const models=genesisData.models,chosen=models.find(m=>m.id===$('#genesis-model').value&&m.available)||models.find(m=>m.available)||models[0];
 $('#genesis-model-options').innerHTML=models.map(m=>'<button type="button" data-genesis-model="'+esc(m.id)+'" data-family="'+genesisFamily(m.name||m.id)+'" '+(!m.available?'disabled':'')+'><span class="family-mark"></span><span>'+esc(genesisModelName(m.name||m.id))+'</span>'+(m.provider==='fireworks'?'<small>Fireworks</small>':!m.available?'<small>Unavailable</small>':'')+'</button>').join('');
 $$('[data-genesis-model]').forEach(b=>b.onclick=()=>{selectGenesisModel(b.dataset.genesisModel);$('#genesis-model-picker').open=false;$('#genesis-model-picker summary').focus();});
 if(chosen)selectGenesisModel(chosen.id);
}
function selectGenesisModel(id){
 const model=genesisData.models.find(m=>m.id===id);if(!model)return;$('#genesis-model').value=id;$('#genesis-model-name').textContent=genesisModelName(model.name||id);$('#genesis-model-picker').dataset.family=genesisFamily(model.name||id);
 const prior=$('#genesis-effort').value,levels=model.efforts||['default'];$('#genesis-effort').innerHTML=levels.map(e=>option(e,({default:'Default',xhigh:'Extra high',max:'Maximum'})[e]||e[0].toUpperCase()+e.slice(1),false)).join('');$('#genesis-effort').value=levels.includes(prior)?prior:levels.includes('medium')?'medium':levels[0];$('#genesis-effort').disabled=levels.length===1;$('#genesis-effort').title=levels.length===1?'This provider uses its default thinking setting':'';
 $$('[data-genesis-model]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.genesisModel===id)));
}
$('#genesis-message').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();if(!$('#genesis-send').disabled)$('#genesis-form').requestSubmit();}});
$('#genesis-message').addEventListener('input',()=>{const box=$('#genesis-message');box.style.height='auto';box.style.height=Math.min(180,box.scrollHeight)+'px';});
document.addEventListener('click',event=>{if(!event.target.closest('#genesis-model-picker'))$('#genesis-model-picker').open=false;});
$('#genesis-model-picker').addEventListener('keydown',event=>{const choices=$$('[data-genesis-model]:not(:disabled)');if(event.key==='Escape'){$('#genesis-model-picker').open=false;$('#genesis-model-picker summary').focus();}else if(['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();$('#genesis-model-picker').open=true;const index=choices.indexOf(document.activeElement);choices[(index+(event.key==='ArrowDown'?1:choices.length-1)+choices.length)%choices.length]?.focus();}});

function genesisText(text){return String(text).split(/```[^\n]*\n([\s\S]*?)```/g).map((part,i)=>{if(i%2)return '<pre><code>'+esc(part)+'</code></pre>';const inline=t=>esc(t).replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/`([^`]+)`/g,'<code>$1</code>');return part.split(/\n\s*\n/).filter(Boolean).map(block=>{const lines=block.split('\n');if(lines.every(l=>/^[-*] /.test(l)))return '<ul>'+lines.map(l=>'<li>'+inline(l.slice(2))+'</li>').join('')+'</ul>';if(/^#{1,6} /.test(block))return '<h4>'+inline(block.replace(/^#{1,6} /,''))+'</h4>';return '<p>'+lines.map(inline).join('<br>')+'</p>';}).join('');}).join('');}

/* Hypothesis record: colour and label come from the server's written rules. */
function outcomeLabel(c){return c.outcome&&(c.proposal||c.outcome.colour!=='white')?'<span class="outcome-label">'+esc(c.outcome.label)+'</span>':'';}
function outcomeLine(c){return c.outcome&&(c.proposal||c.outcome.colour!=='white')?'<p class="research-outcome '+esc(c.outcome.colour)+'"><strong>'+esc(c.outcome.label)+'</strong> '+esc(c.outcome.reason)+'</p>':'';}
function goalText(g){if(!g)return 'Not declared';const parts=[esc(g.version)+' over '+esc(g.parent_version)+': at least '+Math.round(g.minimum_gain*100)+' points more pass rate'];if(g.maximum_cost_ratio!==undefined)parts.push('cost within '+g.maximum_cost_ratio+' times the parent');if(g.minimum_pass_rate)parts.push('pass rate at least '+Math.round(g.minimum_pass_rate*100)+'%');return parts.join('; ');}

/* Library: sources read, their analyses, and where each technique was used. */
let libraryData=null,genesisView='board';
const statusNames={saved:'Saved',analyzed:'Analyzed'},sourceNames={paper:'Paper',blog:'Blog',repo:'Repository',docs:'Documentation',other:'Other'};
function showGenesisView(view){genesisView=view;$('#genesis-board-view').classList.toggle('hidden',view!=='board');$('#genesis-library-view').classList.toggle('hidden',view!=='library');$('#genesis-memory-view').classList.toggle('hidden',view!=='memory');$$('#genesis-panel [role=tab][data-view]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.view===view)));if(view==='library')loadLibrary();else if(view==='memory')loadMemory();else if(genesisData)renderGenesis();}
$$('#genesis-panel [role=tab][data-view]').forEach(b=>b.onclick=()=>showGenesisView(b.dataset.view));
function libraryQuery(){const params=new URLSearchParams();for(const [key,value] of new FormData($('#library-filters')))if(value)params.set(key,value);return params.toString();}
async function loadLibrary(){try{const query=libraryQuery();libraryData=await api('/api/genesis/library'+(query?'?'+query:''));renderResearchLibrary();}catch(e){toast(e.message);}}
$('#library-filters').addEventListener('change',loadLibrary);
$('#library-filters').addEventListener('reset',()=>setTimeout(loadLibrary));
async function importLedger(){try{const result=await api('/api/genesis/library/import',{});toast(result.imported+(result.imported===1?' source':' sources')+' imported');await loadLibrary();}catch(e){toast(e.message);}}
function libraryDate(value){return value?'<time datetime="'+esc(value)+'">'+esc(value)+'</time>':'<span class="library-mark">Unknown</span>';}
function libraryText(text,id,pane){if(!text)return '';const long=text.length>1200;return genesisText(long?text.slice(0,1200)+'...':text)+(long?'<button class="text-button" type="button" data-read-source="'+esc(id)+'" data-pane="'+pane+'">Read in full</button>':'');}
function libraryRow(r){
 const original=(r.full_text_available?'':'<p class="library-mark">Full text unavailable. Showing the abstract.</p>')+(libraryText(r.original||r.abstract,r.id,'original')||'<p class="library-mark">No text saved.</p>');
 const analysis=libraryText(r.analysis,r.id,'analysis')||'<p class="library-mark">Not analyzed.</p>';
 const uses=r.used_in.length?'<div class="library-used"><h4>Used in</h4><ul>'+r.used_in.map(u=>'<li><strong>'+esc(u.version_id)+'</strong> · '+esc(u.blueprint)+(u.where?' · '+esc(u.where):'')+(u.why?'<br>'+esc(u.why):'')+(u.experiment_ids.length?'<br>'+u.experiment_ids.map(id=>'<button class="text-button" type="button" data-open-experiment="'+esc(id)+'">'+esc(id)+'</button>').join(' '):'')+'</li>').join('')+'</ul></div>':'';
 return '<tr class="library-row"><th scope="row"><div class="library-title"><button class="run-expander" type="button" data-expand-source="'+esc(r.id)+'" aria-expanded="false" aria-controls="library-detail-'+esc(r.id)+'" aria-label="Source details">'+chevron+'</button><div>'+(r.url?'<a href="'+esc(r.url)+'" target="_blank" rel="noopener">'+esc(r.title)+'</a>':esc(r.title))+(r.full_text_available?'':'<span class="library-mark">Full text unavailable</span>')+(r.new_evidence?'<span class="library-mark new-evidence">New evidence since analysis</span>':'')+'</div></div></th><td>'+libraryDate(r.published_at)+'</td><td>'+libraryDate(r.discovered_at)+'</td><td>'+(r.authors.length?esc(r.authors.join(', ')):'<span class="library-mark">Unknown</span>')+'</td><td>'+esc(sourceNames[r.source_type]||r.source_type)+'</td><td>'+esc(r.topic)+'</td><td><span class="library-status" data-status="'+esc(r.status)+'">'+esc(statusNames[r.status]||r.status)+'</span></td></tr>'
 +'<tr id="library-detail-'+esc(r.id)+'" class="library-detail hidden"><td colspan="7"><div class="library-tabs" role="tablist"><button type="button" role="tab" aria-selected="true" data-pane-for="'+esc(r.id)+'" data-pane="original">Original</button><button type="button" role="tab" aria-selected="false" data-pane-for="'+esc(r.id)+'" data-pane="analysis">Genesis analysis</button></div><div class="library-pane" data-pane="original">'+original+'</div><div class="library-pane hidden" data-pane="analysis">'+analysis+'</div>'+uses+'</td></tr>';
}
function renderResearchLibrary(){
 const rows=libraryData.items,filtered=libraryQuery()!=='';
 const topic=$('#library-filters [name=topic]'),chosen=topic.value;topic.innerHTML='<option value="">All topics</option>'+libraryData.topics.map(t=>option(t,t,t===chosen)).join('');
 if(genesisView==='library')$('#research-count').textContent=rows.length+' '+(rows.length===1?'source':'sources');
 $('#library-list').innerHTML=rows.length?'<table class="library-table"><thead><tr><th scope="col">Source</th><th scope="col">Published</th><th scope="col">Discovered</th><th scope="col">Authors</th><th scope="col">Type</th><th scope="col">Topic</th><th scope="col">Status</th></tr></thead><tbody>'+rows.map(libraryRow).join('')+'</tbody></table>':'<div class="library-empty"><p>'+(filtered?'No sources match these filters.':'No sources in the library yet.')+'</p><button class="button" type="button" id="'+(filtered?'library-clear':'library-import')+'">'+(filtered?'Clear filters':'Import the research ledger')+'</button></div>';
 if($('#library-import'))$('#library-import').onclick=importLedger;
 if($('#library-clear'))$('#library-clear').onclick=()=>$('#library-filters').reset();
 $$('[data-expand-source]').forEach(b=>b.onclick=()=>{const open=b.getAttribute('aria-expanded')!=='true';b.setAttribute('aria-expanded',String(open));$('#library-detail-'+b.dataset.expandSource).classList.toggle('hidden',!open);});
 $$('[data-pane-for]').forEach(b=>b.onclick=()=>{const box=$('#library-detail-'+b.dataset.paneFor);box.querySelectorAll('[data-pane-for]').forEach(t=>t.setAttribute('aria-selected',String(t===b)));box.querySelectorAll('.library-pane').forEach(p=>p.classList.toggle('hidden',p.dataset.pane!==b.dataset.pane));});
 $$('[data-read-source]').forEach(b=>b.onclick=()=>openReader(b.dataset.readSource,b.dataset.pane));
 $$('[data-open-experiment]').forEach(b=>b.onclick=()=>openJob(b.dataset.openExperiment));
}
function openReader(id,pane){const r=libraryData.items.find(x=>x.id===id);if(!r)return;$('#library-reader-title').textContent=pane==='analysis'?r.title+': Genesis analysis':r.title;$('#library-reader-body').innerHTML=genesisText(pane==='analysis'?r.analysis:(r.original||r.abstract));$('#library-reader').showModal();}
$('#library-reader-close').onclick=()=>$('#library-reader').close();

/* Feature 019: cards are inputs. Drop a link, a hypothesis or a run id; Genesis works it. */
let genesisWatcherTimer=null,genesisWorkTimer=null,memoryData=null;
const workWords={queued:'Queued',working:'Working',done:'Done',failed:'Failed',stopped:'Stopped'};
function workChip(c){const w=c.work;if(!w||!w.status)return '';const text=w.status==='queued'&&w.reason?w.reason:(workWords[w.status]||w.status);return '<span class="work-chip '+esc(w.status)+'">'+esc(text)+'</span>';}
function splitAnalysis(body){const marker=/\n## Genesis analysis\s*\n/;const m=String(body||'').split(marker);return {body:m[0],analysis:m.slice(1).join('\n')};}
function briefCards(){return (genesisData?.cards||[]).filter(c=>c.kind==='brief').sort((a,b)=>(b.created_at||'').localeCompare(a.created_at||''));}
function renderBrief(){const box=$('#genesis-brief');if(!box)return;const brief=briefCards()[0];box.innerHTML=brief?'<article class="block genesis-brief"><header><span>Daily brief</span><span>'+esc((brief.created_at||'').slice(0,10))+'</span></header><div class="block-body">'+genesisText(brief.body||'')+(brief.evidence?.length?'<p class="meta">'+brief.evidence.length+(brief.evidence.length===1?' record':' records')+'</p>':'')+'</div></article>':'';}
async function loadWatcher(){const box=$('#genesis-watcher');if(!box)return;try{const w=await api('/api/genesis/watcher');const working=w.working?genesisData?.cards.find(c=>c.id===w.working):null;const queue=(w.queue||[]).length;
 const state=w.paused?'Paused':working?'Working on '+(working.title||w.working):queue?'Waiting: '+(w.reason||'the next card starts on the next wake'):'Idle';
 box.innerHTML='<span class="watcher-state '+(w.paused?'paused':working?'working':'idle')+'">'+esc(state)+'</span>'+pgMetaLike([queue+(queue===1?' queued':' queued'),money(w.today_usd||0)+' of '+money(w.cap_usd||0)+' today',w.last_wake?'last wake '+new Date(w.last_wake).toLocaleTimeString():''])+'<button class="text-button" type="button" id="watcher-toggle">'+(w.paused?'Resume':'Pause')+'</button>';
 $('#watcher-toggle').onclick=async()=>{try{await api('/api/genesis/watcher',{paused:!w.paused});await loadWatcher();}catch(e){toast(e.message);}};
 }catch(e){box.innerHTML='<span class="meta">'+esc(e.message)+'</span>';}}
function pgMetaLike(parts){return '<span class="meta">'+parts.filter(Boolean).map(esc).join('<span class="sep">·</span>')+'</span>';}
function watchBoard(){clearInterval(genesisWatcherTimer);if(genesisView!=='board'||workspaceSurface!=='genesis')return;loadWatcher();genesisWatcherTimer=setInterval(async()=>{if(workspaceSurface!=='genesis'||genesisView!=='board'){clearInterval(genesisWatcherTimer);return;}const before=JSON.stringify((genesisData?.cards||[]).map(c=>[c.id,c.work?.status,c.revision]));try{genesisData=await api('/api/genesis');}catch{return;}const after=JSON.stringify((genesisData.cards||[]).map(c=>[c.id,c.work?.status,c.revision]));if(before!==after){renderGenesis();if(genesisCard)showResearchCard(genesisCard.id);}loadWatcher();},10000);}
$('#genesis-drop')?.addEventListener('submit',async e=>{e.preventDefault();const text=$('#drop-text').value.trim();if(!text)return;const button=$('#drop-submit');button.disabled=true;try{await api('/api/genesis/drop',{text,question:$('#drop-question').value.trim()||undefined});$('#drop-text').value='';$('#drop-question').value='';await openGenesis();toast('Added to the board. Genesis picks it up on its next wake.');}catch(err){toast(err.message);}finally{button.disabled=false;}});
function workDetail(c){
 const w=c.work;if(!w||!w.status)return '';
 const parts=[workWords[w.status]||w.status,w.started_at?'started '+new Date(w.started_at).toLocaleTimeString():'',w.finished_at?'finished '+new Date(w.finished_at).toLocaleTimeString():'',w.reason||''];
 return '<section class="research-work"><h3>Genesis</h3>'+pgMetaLike(parts)+(w.status==='working'?'<button class="text-button" type="button" id="research-stop">Stop</button><div class="genesis-event-log" id="research-work-events"></div>':'')+'</section>';
}
async function pollWork(c){clearTimeout(genesisWorkTimer);const id=c.work?.turn;if(!id||c.work.status!=='working')return;try{const t=await api('/api/genesis/turns/'+id);const box=$('#research-work-events');if(box)box.innerHTML=eventHtml(t)+(t.answer?'<div class="genesis-answer">'+genesisText(t.answer)+'</div>':'');if(t.status==='running')genesisWorkTimer=setTimeout(()=>pollWork(c),2500);else{genesisData=await api('/api/genesis');renderGenesis();showResearchCard(c.id);}}catch{}}

/* Memory: what Genesis carries into every turn, and the record it can search. */
async function loadMemory(){const box=$('#memory-core');if(!box)return;box.innerHTML='<p class="node-help">Loading</p>';try{memoryData=await api('/api/genesis/memory');renderMemory();}catch(e){box.innerHTML='<div class="empty-state"><p>'+esc(e.message)+'</p></div>';}loadSchedule();}
function memoryBlock(name,text,size,budget){const pct=budget?Math.min(100,Math.round(100*(size||0)/budget)):0;return '<article class="block memory-block"><header><span>'+esc(name)+'</span><span>'+(size||0)+' of '+(budget||0)+' characters</span></header><div class="block-body"><progress max="100" value="'+pct+'" aria-label="'+esc(name)+' budget"></progress><pre>'+esc(text||'(empty)')+'</pre></div></article>';}
function soulBlock(text,size,budget){const pct=budget?Math.min(100,Math.round(100*(size||0)/budget)):0;return '<article class="block memory-block memory-soul"><header><span>SOUL.md, who Genesis is: voice, priorities, what it never does. Only people edit it.</span><span id="soul-count">'+(size||0)+' of '+(budget||0)+' characters</span></header><div class="block-body"><progress id="soul-progress" max="100" value="'+pct+'" aria-label="SOUL.md budget"></progress><textarea id="soul-text" rows="14" maxlength="'+(budget||2500)+'" aria-label="SOUL.md" spellcheck="false">'+esc(text||'')+'</textarea><div class="memory-soul-actions"><button class="button" type="button" id="soul-save" disabled>Save</button><button class="text-button" type="button" id="soul-reset" hidden>Discard changes</button></div></div></article>';}
function renderMemory(){const m=memoryData||{};const budgets=m.budgets||{};const lab=m.lab??m.LAB??'',monarch=m.monarch??m.MONARCH??'',soul=m.soul??'';
 $('#memory-core').innerHTML=soulBlock(soul,budgets['SOUL.md']?.size??soul.length,budgets['SOUL.md']?.budget??2500)+memoryBlock('LAB.md, what Genesis has learned about the lab',lab,budgets['LAB.md']?.size??budgets.lab?.size??lab.length,budgets['LAB.md']?.budget??budgets.lab?.budget??2500)+memoryBlock('MONARCH.md, the current build, written by the daily index',monarch,budgets.monarch?.size??monarch.length,budgets.monarch?.budget??2500);
 const ta=$('#soul-text'),save=$('#soul-save'),reset=$('#soul-reset');const saved=soul.replace(/\r\n/g,'\n').trim();const budget=budgets['SOUL.md']?.budget??2500;
 const sync=()=>{const cur=ta.value.replace(/\r\n/g,'\n').trim();const dirty=cur!==saved;save.disabled=!dirty||!cur;reset.hidden=!dirty;$('#soul-count').textContent=cur.length+' of '+budget+' characters';$('#soul-progress').value=Math.min(100,Math.round(100*cur.length/budget));};
 ta.addEventListener('input',sync);reset.onclick=()=>{ta.value=soul;sync();};
 save.onclick=async()=>{save.disabled=true;try{await api('/api/genesis/memory',{op:'soul',text:ta.value,record:'human:studio'});toast('Identity saved');await loadMemory();}catch(err){toast(err.message);sync();}};
 const history=(m.history||[]).slice(-20).reverse();$('#memory-history').innerHTML=history.length?'<h3>Recent edits</h3><ul class="memory-history">'+history.map(h=>'<li><span class="meta">'+esc((h.at||'').slice(0,16).replace('T',' '))+' · '+esc(h.op||'')+'</span> '+esc((h.after||h.before||'').slice(0,160))+'</li>').join('')+'</ul>':'';}
$('#memory-pin-form')?.addEventListener('submit',async e=>{e.preventDefault();const text=$('#memory-pin-text').value.trim();if(!text)return;try{await api('/api/genesis/memory',{op:'pin',text,record:'human'});$('#memory-pin-text').value='';await loadMemory();}catch(err){toast(err.message);}});
$('#record-search-form')?.addEventListener('submit',async e=>{e.preventDefault();const q=$('#record-query').value.trim();const box=$('#record-results');if(!q)return;box.innerHTML='<p class="node-help">Searching</p>';try{const r=await api('/api/genesis/record?q='+encodeURIComponent(q));const hits=r.hits||r.items||r;box.innerHTML=hits.length?'<ul class="record-hits">'+hits.map(h=>'<li><span class="meta">'+esc(h.kind||'')+' · '+esc(h.id||'')+(h.date?' · '+esc(String(h.date).slice(0,10)):'')+'</span><p>'+esc(h.snippet||h.title||'')+'</p></li>').join('')+'</ul>':'<div class="empty-state"><p>Nothing in the record matches.</p></div>';}catch(err){box.innerHTML='<div class="empty-state"><p>'+esc(err.message)+'</p></div>';}});
async function loadSchedule(){const box=$('#memory-schedule');if(!box)return;try{const [s,code]=await Promise.all([api('/api/genesis/schedule'),api('/api/genesis/code-index').catch(()=>null)]);const jobs=s.jobs||[];const words={'code-index':'Monarch code index','genesis-sleep':'Nightly consolidation'};
 box.innerHTML='<h3>Daily jobs</h3><table class="table schedule-table"><thead><tr><th>Job</th><th>Runs at</th><th>Last run</th><th>Result</th><th></th></tr></thead><tbody>'+jobs.map(j=>'<tr><th scope="row">'+esc(words[j.name]||j.name)+'</th><td>'+String(j.hour).padStart(2,'0')+':00 São Paulo</td><td>'+esc(j.finished_at?j.finished_at.slice(0,16).replace('T',' '):'never')+'</td><td>'+esc(j.status?(j.status==='failed'?'Failed: '+(j.error||''):'Completed'):'')+'</td><td><button class="text-button" type="button" data-run-job="'+esc(j.name)+'">Run now</button></td></tr>').join('')+'</tbody></table>'
 +(code?'<p class="meta">'+esc(['Monarch '+(code.ref||''),(code.commit||'').slice(0,12),code.built_at?'indexed '+code.built_at.slice(0,16).replace('T',' '):'not indexed yet',code.graphify?.available===false?'Graphify not installed':''].filter(Boolean).join(' · '))+'</p>':'');
 $$('[data-run-job]').forEach(b=>b.onclick=async()=>{b.disabled=true;b.textContent='Running';try{const r=await api('/api/genesis/schedule/'+b.dataset.runJob+'/run',{});toast(r.status==='failed'?'Failed: '+r.error:'Done');}catch(e){toast(e.message);}await loadSchedule();await loadMemory();});
 }catch(e){box.innerHTML='<p class="meta">'+esc(e.message)+'</p>';}}

function researchBody(c){const parts=splitAnalysis(c.body);return (c.question?'<p class="research-question">'+esc(c.question)+'</p>':'')+'<div class="research-body">'+genesisText(parts.body)+'</div>'+(parts.analysis?'<section class="research-analysis"><h3>Genesis analysis</h3>'+genesisText(parts.analysis)+'</section>':'')+workDetail(c);}

/* The board: columns you can scroll, cards you can drag between stages and reorder, a card added in place. */
const MANUAL_STAGES=['research','hypothesis','review','complete'];
let dragCardId=null;
function cardOrder(a,b){const pa=a.position??Number.MAX_SAFE_INTEGER,pb=b.position??Number.MAX_SAFE_INTEGER;return pa-pb||(a.created_at||'').localeCompare(b.created_at||'');}
function cardHtml(c){const draggable=c.kind!=='brief'&&c.stage!=='running';return '<button class="research-card '+esc(c.outcome?.colour||'white')+'" data-card="'+c.id+'"'+(draggable?' draggable="true"':'')+'><strong>'+esc(c.title)+'</strong><p>'+esc(splitAnalysis(c.body).body.slice(0,170))+'</p>'+(c.proposal?'<span class="proposal-signal">Experiment proposed</span>':'')+(c.run_status?'<small>'+esc(c.run_status)+'</small>':'')+outcomeLabel(c)+workChip(c)+'</button>';}
function renderBoard(cards){
 $('#research-board').innerHTML=Object.entries(stageNames).map(([stage,label])=>{const rows=cards.filter(c=>c.stage===stage&&c.kind!=='brief').sort(cardOrder);return '<section class="research-column" data-stage="'+stage+'"><header><h3>'+label+'</h3><span>'+rows.length+'</span></header><div class="column-cards" data-stage="'+stage+'">'+rows.map(cardHtml).join('')+'</div>'+(MANUAL_STAGES.includes(stage)?'<button class="text-button column-add" type="button" data-add-stage="'+stage+'">Add a card</button>':'')+'</section>';}).join('');
 $$('.research-card[draggable]').forEach(el=>{el.addEventListener('dragstart',e=>{dragCardId=el.dataset.card;el.classList.add('dragging');e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('text/plain',dragCardId);});el.addEventListener('dragend',()=>{el.classList.remove('dragging');dragCardId=null;$$('.drop-slot').forEach(s=>s.remove());$$('.research-column.drop-target').forEach(c=>c.classList.remove('drop-target'));});});
 $$('.research-column').forEach(col=>{
  const stage=col.dataset.stage,cardsBox=col.querySelector('.column-cards');
  col.addEventListener('dragover',e=>{if(!dragCardId)return;const card=genesisData.cards.find(c=>c.id===dragCardId);if(!canMove(card,stage)){e.dataTransfer.dropEffect='none';return;}e.preventDefault();e.dataTransfer.dropEffect='move';col.classList.add('drop-target');placeSlot(cardsBox,e.clientY);});
  col.addEventListener('dragleave',e=>{if(!col.contains(e.relatedTarget)){col.classList.remove('drop-target');col.querySelectorAll('.drop-slot').forEach(s=>s.remove());}});
  col.addEventListener('drop',async e=>{e.preventDefault();const id=dragCardId||e.dataTransfer.getData('text/plain');const slot=col.querySelector('.drop-slot');const index=slot?[...cardsBox.children].filter(el=>el.classList.contains('research-card')||el.classList.contains('drop-slot')).indexOf(slot):cardsBox.querySelectorAll('.research-card').length;col.classList.remove('drop-target');slot?.remove();await moveCard(id,stage,index);});
 });
 $$('[data-add-stage]').forEach(b=>b.onclick=()=>inlineAdd(b.dataset.addStage));
}
function canMove(card,stage){if(!card||card.kind==='brief'||card.stage==='running'||stage==='running')return false;if(stage==='approval'&&!card.proposal)return false;if(card.job)return ['review','complete'].includes(stage);return true;}
function placeSlot(box,y){box.querySelectorAll('.drop-slot').forEach(s=>s.remove());const slot=document.createElement('div');slot.className='drop-slot';const cards=[...box.querySelectorAll('.research-card:not(.dragging)')];const after=cards.find(el=>{const r=el.getBoundingClientRect();return y<r.top+r.height/2;});if(after)box.insertBefore(slot,after);else box.appendChild(slot);}
async function moveCard(id,stage,index){
 const card=genesisData.cards.find(c=>c.id===id);if(!card||!canMove(card,stage))return;
 const siblings=genesisData.cards.filter(c=>c.stage===stage&&c.id!==id&&c.kind!=='brief').sort(cardOrder);
 const prev=siblings[index-1]?.position,next=siblings[index]?.position;
 const position=prev!==undefined&&next!==undefined?(prev+next)/2:prev!==undefined?prev+10:next!==undefined?next-10:index*10;
 const before={stage:card.stage,position:card.position};card.stage=stage;card.position=position;renderBoard(genesisData.cards);$$('[data-card]').forEach(b=>b.onclick=()=>showResearchCard(b.dataset.card));
 try{const saved=await api('/api/genesis/cards',{...card,stage,position});Object.assign(card,saved);}
 catch(e){Object.assign(card,before);renderBoard(genesisData.cards);$$('[data-card]').forEach(b=>b.onclick=()=>showResearchCard(b.dataset.card));toast(e.message);}
}
function inlineAdd(stage){
 const col=$('.research-column[data-stage="'+stage+'"]');if(!col||col.querySelector('.column-add-form'))return;
 const form=document.createElement('form');form.className='column-add-form';form.innerHTML='<label class="sr-only" for="add-'+stage+'">Card title</label><input id="add-'+stage+'" maxlength="140" placeholder="What might improve?" required><div><button class="button small" type="submit">Add</button><button class="text-button" type="button" data-cancel>Cancel</button></div>';
 col.querySelector('.column-cards').after(form);form.querySelector('input').focus();
 form.querySelector('[data-cancel]').onclick=()=>form.remove();
 form.onsubmit=async e=>{e.preventDefault();const title=form.querySelector('input').value.trim();if(!title)return;try{if(stage==='research')await api('/api/genesis/drop',{text:title});else await api('/api/genesis/cards',{title,body:'',stage});await openGenesis();}catch(err){toast(err.message);}};
}
