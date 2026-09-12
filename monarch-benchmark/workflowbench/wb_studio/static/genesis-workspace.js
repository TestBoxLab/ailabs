'use strict';
// Genesis is the working window; Studio routes hold the evidence and editable work.
const GENESIS_STARTERS = [
 {title:'Design a stronger architecture', detail:'Audit history, use the product graph, then prepare a fair comparison.', prompt:'Run [number] tasks from [benchmark task set]. First audit previous architectures and AutomationBench history, then design a novel product-graph architecture aimed at better task completion and speed than the models in their native bare harnesses. Show the evidence and tradeoffs, build the candidate in front of me, and prepare the comparable experiment with its attempt count and cost band.'},
 {title:'Investigate a run', detail:'Find the first supported divergence and what to try next.', prompt:'Investigate run [run ID]. Compare failures and successes, cite the exact recorded events, distinguish task or infrastructure limits from architecture defects, and propose the smallest experiment that could improve completion and speed.'},
 {title:'Watch an architecture take shape', detail:'Build visibly, inspect the configuration, and save a candidate.', prompt:'Inspect the existing architecture [architecture ID] and product graph. Explain a concrete improvement, show the architecture editor, build it step by step, and save a separate candidate with the evidence behind its changes.'}
];
function genesisWelcome(){
 return '<section class="genesis-welcome genesis-start"><h2>What should we discover next?</h2><p>Give Genesis an objective. Watch the research, shape an architecture, and follow the evidence into an experiment.</p><div class="genesis-starters">'+GENESIS_STARTERS.map((s,i)=>'<button type="button" data-genesis-starter="'+i+'"><strong>'+s.title+'</strong><span>'+s.detail+'</span><svg class="icon" aria-hidden="true"><use href="/vendor/lucide/sprite.svg#arrow-up-right"/></svg></button>').join('')+'</div><p class="genesis-start-note">Choose a starting point, fill in the details, and send it when ready.</p></section>';
}
function bindGenesisStarters(){
 document.querySelectorAll('[data-genesis-starter]').forEach(button=>button.onclick=()=>{
  const field=document.getElementById('genesis-message');
  field.value=GENESIS_STARTERS[Number(button.dataset.genesisStarter)].prompt;
  field.focus();const start=field.value.indexOf('['),end=field.value.indexOf(']');
  if(start>=0)field.setSelectionRange(start,end+1);
  field.dispatchEvent(new Event('input',{bubbles:true}));
 });
}
(() => {
 let latest=null,dismissed=null;
 window.genesisWindowVisible=()=>Boolean(latest && dismissed!==latest.id && !location.hash.startsWith('#genesis'));
 function visibility(){
  const container=document.getElementById('genesis-window-stage');
  const controls=document.getElementById('genesis-window-controls');
  const visible=window.genesisWindowVisible();
  const changed=document.body.classList.contains('genesis-guided')!==visible;
  document.body.classList.toggle('genesis-guided',visible);
  if(changed)requestAnimationFrame(()=>window.dispatchEvent(new Event('resize')));
  if(container)container.hidden=!visible;
  if(controls)controls.hidden=!window.genesisWindowVisible();
  document.dispatchEvent(new Event('genesis:window'));
 }
 function update(turn){
  if(!turn?.id||!window.GenesisStage)return;
  latest=turn;
  const container=document.getElementById('genesis-window-stage');
  if(!container)return;
  // The same recorded turn feeds both surfaces. No extra polling or model request.
  window.GenesisStage.sync(container,turn);
  let controls=document.getElementById('genesis-window-controls');
  if(!controls){
   controls=document.createElement('div');controls.id='genesis-window-controls';controls.className='genesis-window-controls';
   controls.innerHTML='<a class="text-button" data-window-chat href="#genesis">Conversation</a><button type="button" data-window-follow class="text-button">Stop following</button><button type="button" data-window-stop class="text-button">Stop work</button><button type="button" data-window-dismiss class="text-button" aria-label="Hide activity">Hide</button><p role="status" data-window-error></p>';
   container.after(controls);
   controls.querySelector('[data-window-follow]').onclick=()=>{document.getElementById('genesis-follow-stop')?.click();update(latest);};
   controls.querySelector('[data-window-dismiss]').onclick=()=>{dismissed=latest.id;visibility();};
   controls.querySelector('[data-window-stop]').onclick=async()=>{
    const button=controls.querySelector('[data-window-stop]');button.disabled=true;
    try{await api('/api/genesis/turns/'+encodeURIComponent(latest.id)+'/stop',{});}
    catch(error){controls.querySelector('[data-window-error]').textContent=error.message;}
    finally{button.disabled=false;}
   };
  }
  controls.querySelector('[data-window-chat]').href=turn.thread?'#genesis/t/'+encodeURIComponent(turn.thread):'#genesis';
  controls.querySelector('[data-window-stop]').hidden=turn.status!=='running';
  const followButton=controls.querySelector('[data-window-follow]');
  followButton.hidden=typeof followOn!=='function'||!followOn();
  followButton.textContent=typeof followBroken!=='undefined'&&followBroken?'Resume following':'Stop following';
  visibility();
 }
 document.addEventListener('genesis:turn',event=>update(event.detail));
 window.addEventListener('hashchange',()=>{if(latest)update(latest);});
 document.addEventListener('genesis:navigated',()=>{if(latest)update(latest);});
 document.addEventListener('genesis:surface',()=>{if(latest)visibility();});
 document.addEventListener('click',event=>{
  const link=event.target.closest('a[href^="#"]');
  if(link?.closest('.genesis-window-stage'))document.getElementById('genesis-orb-panel')?.scrollTo({top:0});
 });
})();

