/* Genesis live stage: visual narration over the stored event stream, never a second runner. */
(function () {
  'use strict';
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const human = value => String(value || '').replace(/[_-]/g, ' ').replace(/^./, c => c.toUpperCase());
  const text = (value, limit = 1200) => String(value ?? '').slice(0, limit);
  const phases = {
    thinking:{title:'Thinking through the next move',caption:'Neural field'},
    research:{title:'Following the evidence',caption:'Signal search'},
    architecture:{title:'Shaping the architecture',caption:'Product graph'},
    configuration:{title:'Preparing the setup',caption:'Configuration'},
    execution:{title:'Putting the plan to work',caption:'Execution'},
    result:{title:'Turn complete',caption:'Recorded result'},
    warning:{title:'Attention needed',caption:'Attention'}
  };
  function matrixFrame(phase,seconds=0){return window.GenesisMatrix?.layers(phase,seconds,96,38).body||'';}
  function paintMatrix(root,phase,seconds){
    const layers=window.GenesisMatrix?.layers(phase,seconds,96,38);if(!layers)return;
    patchText(root.querySelector('.genesis-stage-art pre'),layers.body);
    patchText(root.querySelector('.genesis-matrix-rain'),layers.rain);
  }
  const instances = new Map();
  let paused = false, timer = null;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const observer = window.IntersectionObserver ? new IntersectionObserver(entries => {
    for (const entry of entries) { const state = instances.get(entry.target); if (state) state.visible = entry.isIntersecting; }
    reconcile();
  }, {threshold:0.01}) : null;

  function receipt(event) {
    if (event.type !== 'tool_completed' || event.action !== 'present') return null;
    let value = event.detail ?? event.result;
    if (typeof value === 'string') { try { value = JSON.parse(value); } catch (_) { return null; } }
    if (!value || value.presentation !== true || !/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/.test(value.card_id || '') || !phases[value.template]) return null;
    return {...value, title:text(value.title,120), detail:text(value.detail), status:['active','complete','blocked'].includes(value.status) ? value.status : 'active'};
  }
  function phaseFor(action) {
    if (/architect|graph|node|prompt|build/.test(action)) return 'architecture';
    if (/search|read|research|library|history|code_|inspect|compare|memory|fetch|browse/.test(action)) return 'research';
    if (/config|plan|propose|setup|select|show|budget|verify/.test(action)) return 'configuration';
    if (/launch|run|execute|test|experiment|patch|repair/.test(action)) return 'execution';
    return 'thinking';
  }
  function timeLabel(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '' : date.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'});
  }
  function eventLine(event) {
    if (event.type === 'tool_started') return {kind:'working', label:human(event.action), detail:'Started', evidence:[{label:'Payload',value:event.payload ?? 'No payload recorded.'}]};
    if (event.type === 'tool_completed') {
      const card = receipt(event);
      return {kind:'recorded',label:card ? card.title : human(event.action),detail:card ? 'Card updated' : 'Response recorded', evidence:[...(event.payload != null ? [{label:'Payload',value:event.payload}] : []),{label:'Result',value:event.detail ?? event.result ?? 'No result recorded.'}]};
    }
    if (event.type === 'model_started') return {kind:'thinking',label:'Model request',detail:text(event.model,80)};
    if (['failed','interrupted','error','request_error','tool_error'].includes(event.type)) return {kind:'blocked',label:'Work interrupted',detail:text(event.reason || event.message || event.detail,180)};
    if (event.type === 'completed') return {kind:'recorded',label:'Turn finished',detail:''};
    if (event.type === 'cancelled' || event.type === 'stopped') return {kind:'blocked',label:'Turn stopped',detail:text(event.reason,180)};
    return null;
  }
  function model(turn) {
    const cards = new Map(), logs = [], openTools = [];
    let phase = 'thinking', heading = phases.thinking.title, detail = 'Waiting for the next recorded event.', current = null;
    let toolCount = 0;
    for (const [index,event] of (turn.events || []).entries()) {
      const card = receipt(event);
      if (card) { cards.delete(card.card_id); cards.set(card.card_id,card); current=card; phase=card.status === 'blocked' ? 'warning' : card.template; heading=card.title; detail=card.detail; }
      else if (event.type === 'tool_started' && event.action !== 'present') {
        toolCount++; openTools.push(event.action); current=null; phase=phaseFor(event.action || ''); heading=human(event.action); detail='Tool call in progress. Its response will appear in the activity stream.';
      } else if (event.type === 'tool_completed' && event.action !== 'present') {
        const pending=openTools.lastIndexOf(event.action); if(pending>=0) openTools.splice(pending,1);
        detail='Response recorded. Genesis is evaluating the next step.';
      } else if (event.type === 'model_started') {
        phase='thinking'; current=null; heading=phases.thinking.title; detail='The model is working with the available evidence.';
      } else if (['failed','interrupted','error','request_error','tool_error'].includes(event.type)) {
        phase='warning'; heading='Work interrupted'; detail=text(event.reason || event.message || event.detail,300);
      }
      const line=eventLine(event);
      if(line) logs.push({...line,key:String(event.id ?? index),at:timeLabel(event.at)});
    }
    const running=['running','queued'].includes(turn.status);
    if(!running) {
      const interrupted=['failed','interrupted','error','cancelled','stopped'].includes(turn.status);
      if(interrupted && phase!=='warning') detail='This turn ended without a normal completion. Inspect the activity stream for the last recorded response.';
      phase=interrupted ? 'warning' : 'result';
      heading=phase === 'warning' ? (['cancelled','stopped'].includes(turn.status) ? 'Turn stopped' : 'Turn interrupted') : 'Turn complete';
      detail=phase === 'warning' ? detail : 'The response and recorded work are ready to inspect.';
    }
    return {phase,heading,detail,current,cards:[...cards.values()],logs,eventCount:logs.length,toolCount,running};
  }
  function safeRoute(value) {
    if(typeof value !== 'string' || value.length>200 || value.includes('..')) return '';
    const exact=['#reports','#runs','#budget','#runtime','#studio','#launch','#leaderboard','#genesis','#genesis/board','#genesis/library','#genesis/memory','#genesis/activity','#genesis/digest','#genesis/settings'];
    if(exact.includes(value)) return value;
    return /^#(?:run|report|round|studio|genesis\/t)\/[A-Za-z0-9._@+-]{1,120}(?:\/[A-Za-z0-9._@+-]{1,120}){0,3}$/.test(value) ? value : '';
  }
  function cardBody(card) {
    const items=Array.isArray(card.items) ? card.items.slice(0,6) : [];
    const sources=Array.isArray(card.sources) ? card.sources.slice(0,6) : [];
    const route=safeRoute(card.route);
    const status={active:'In progress',complete:'Recorded',blocked:'Needs attention'}[card.status];
    return '<div class="genesis-scene-card-head"><h4>'+escape(card.title)+'</h4><span class="genesis-scene-card-status">'+status+'</span></div>'+
      (card.detail ? '<p class="genesis-scene-card-detail">'+escape(card.detail)+'</p>' : '')+
      (items.length ? '<dl class="genesis-scene-facts">'+items.map(item=>'<div><dt>'+escape(text(item?.label,80))+'</dt><dd>'+escape(text(item?.value,240))+'</dd></div>').join('')+'</dl>' : '')+
      (sources.length ? '<details class="genesis-scene-sources"><summary>Sources ('+sources.length+')</summary><ul>'+sources.map(source=>'<li><span>'+escape(text(source?.label,100))+'</span><code>'+escape(text(source?.ref,240))+'</code></li>').join('')+'</ul></details>' : '')+
      (route ? '<a class="genesis-scene-open" href="'+escape(route)+'" data-genesis-goto="'+escape(route)+'">'+escape(text(card.label || 'Open in workspace',120))+'<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M5 12h14m-6-6 6 6-6 6"/></svg></a>' : '');
  }
  function html(turn) {
    const data=model(turn);
    return '<section class="genesis-stage" data-stage-turn="'+escape(turn.id)+'" data-phase="'+data.phase+'" data-running="'+data.running+'" data-motion="off" aria-label="Genesis work in progress">'+
      '<div class="genesis-stage-toolbar"><span class="genesis-stage-state">'+(data.running ? 'Live activity' : 'Recorded activity')+'</span><button class="genesis-stage-motion" type="button" aria-pressed="false">Pause animation</button></div>'+
      '<div class="genesis-stage-scene"><div class="genesis-stage-art" aria-hidden="true"><div class="genesis-matrix-field"><pre>'+escape(matrixFrame(data.phase))+'</pre><pre class="genesis-matrix-rain"></pre></div><span class="genesis-stage-art-caption">'+phases[data.phase].caption+'</span></div><div class="genesis-stage-narration"><h3>'+escape(data.heading)+'</h3><p>'+escape(data.detail)+'</p><span class="genesis-stage-count">'+data.toolCount+' tool '+(data.toolCount===1?'call':'calls')+' recorded</span></div></div>'+
      '<details class="genesis-stage-work"'+(data.cards.length?'':' hidden')+'><summary><span>Work details</span><span class="genesis-stage-work-count">'+data.cards.length+' '+(data.cards.length===1?'card':'cards')+'</span></summary><div class="genesis-stage-cards"></div></details><details class="genesis-stage-log"><summary><span>Activity stream</span><span class="genesis-stage-log-count">'+data.eventCount+' events</span></summary><ol tabindex="0" aria-label="Recorded Genesis activity"></ol></details></section>';
  }
  function patchText(element,value) { if(element && element.textContent!==value) element.textContent=value; }
  function keyed(parent,rows,keyOf,create,update) {
    const existing=new Map([...parent.children].map(child=>[child.dataset.key,child]));
    let previous=null;
    for(const row of rows) {
      const key=keyOf(row); let element=existing.get(key);
      if(!element) {element=create(row);element.dataset.key=key;}
      if((previous ? previous.nextElementSibling : parent.firstElementChild)!==element) parent.insertBefore(element,previous ? previous.nextElementSibling : parent.firstElementChild);
      update(element,row); existing.delete(key); previous=element;
    }
    for(const element of existing.values()) element.remove();
  }
  function sync(container,turn) {
    if(!container) return;
    let root=container.matches?.('.genesis-stage') ? container : container.querySelector('.genesis-stage');
    if(!root || root.dataset.stageTurn!==String(turn.id)) { destroy(container); container.innerHTML=html(turn); root=container.querySelector('.genesis-stage'); }
    let state=instances.get(root);
    if(!state) {
      state={root,visible:!observer,frame:0,localPaused:false,data:null}; instances.set(root,state); observer?.observe(root);
      root.querySelector('.genesis-stage-motion').addEventListener('click',()=>{state.localPaused=!state.localPaused;reconcile();});
    }
    const data=model(turn), phaseChanged=state.data?.phase!==data.phase;
    state.data=data; root.dataset.phase=data.phase; root.dataset.running=String(data.running);
    root.setAttribute('aria-label',data.running ? 'Genesis work in progress' : 'Genesis recorded work');
    patchText(root.querySelector('.genesis-stage-state'),data.running ? 'Live activity' : 'Recorded activity');
    patchText(root.querySelector('.genesis-stage-narration h3'),data.heading);
    patchText(root.querySelector('.genesis-stage-narration p'),data.detail);
    patchText(root.querySelector('.genesis-stage-count'),data.toolCount+' tool '+(data.toolCount===1?'call':'calls')+' recorded');
    patchText(root.querySelector('.genesis-stage-art-caption'),phases[data.phase].caption);
    if(phaseChanged) {state.frame=0;paintMatrix(root,data.phase,0);}
    const cards=root.querySelector('.genesis-stage-cards'); cards.hidden=!data.cards.length;
    root.querySelector('.genesis-stage-work').hidden=!data.cards.length;
    patchText(root.querySelector('.genesis-stage-work-count'),data.cards.length+' '+(data.cards.length===1?'card':'cards'));
    keyed(cards,data.cards,card=>card.card_id,()=>document.createElement('article'),(element,card)=>{
      const signature=JSON.stringify(card);
      element.className='genesis-scene-card';element.dataset.template=card.template;element.dataset.status=card.status;
      if(element._signature!==signature) {
        const sourcesOpen=element.querySelector('details')?.open;
        element.innerHTML=cardBody(card);element._signature=signature;
        if(sourcesOpen && element.querySelector('details')) element.querySelector('details').open=true;
      }
    });
    const list=root.querySelector('.genesis-stage-log ol'),atBottom=list.scrollHeight-list.scrollTop-list.clientHeight<30;
    keyed(list,data.logs,line=>line.key,()=>document.createElement('li'),(element,line)=>{
      const signature=JSON.stringify(line); if(element._signature===signature)return;
      element.dataset.kind=line.kind;
      const opened=element.querySelector('details')?.open;
      const row='<time>'+escape(line.at)+'</time><span class="genesis-stage-log-label">'+escape(line.label)+'</span><span class="genesis-stage-log-detail">'+escape(line.detail)+'</span>';
      element.dataset.inspectable=String(Boolean(line.evidence));
      element.innerHTML=line.evidence ? '<details class="genesis-event-evidence"><summary class="genesis-stage-log-row">'+row+'</summary><div class="genesis-event-evidence-body">'+line.evidence.map(part=>'<p>'+escape(part.label)+'</p><pre>'+escape(typeof part.value==='string' ? part.value : JSON.stringify(part.value,null,2))+'</pre>').join('')+'</div></details>' : row;
      if(opened && element.querySelector('details')) element.querySelector('details').open=true;
      element._signature=signature;
    });
    patchText(root.querySelector('.genesis-stage-log-count'),data.eventCount+' events');
    if(atBottom) list.scrollTop=list.scrollHeight;
    reconcile(); return root;
  }
  function reconcile() {
    let active=false;
    for(const [root,state] of instances) {
      if(!root.isConnected) {observer?.unobserve(root);instances.delete(root);continue;}
      const held=paused || state.localPaused || reduced.matches;
      state.animating=Boolean(state.data?.running && state.visible && !held && !document.hidden);
      root.dataset.motion=state.animating ? 'on' : 'off';active ||= state.animating;
      const button=root.querySelector('.genesis-stage-motion');
      button.hidden=!state.data?.running;
      button.disabled=reduced.matches || paused;
      button.setAttribute('aria-pressed',String(held));
      patchText(button,reduced.matches ? 'Reduced motion' : held ? 'Resume animation' : 'Pause animation');
    }
    if(active && !timer) timer=window.setInterval(()=>{
      for(const [root,state] of instances) if(state.animating && root.isConnected) {
        state.frame+=.08;paintMatrix(root,state.data.phase,state.frame);
      }
      if([...instances.keys()].some(root=>!root.isConnected)) reconcile();
    },80);
    else if(!active && timer) {clearInterval(timer);timer=null;}
  }
  function destroy(container) {
    for(const [root] of instances) if(root===container || container?.contains(root)) {observer?.unobserve(root);instances.delete(root);}
    reconcile();
  }
  document.addEventListener('visibilitychange',reconcile);
  reduced.addEventListener?.('change',reconcile);
  window.GenesisStage={html,sync,destroy,setPaused(value){paused=Boolean(value);reconcile();}};
}());
