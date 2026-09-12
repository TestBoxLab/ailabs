const {chromium}=require('C:/Users/Lucas Wakigawa/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');const assert=require('node:assert/strict');const path=require('node:path');
(async()=>{const browser=await chromium.launch({channel:'chrome'});try{const p=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});const errors=[];p.on('pageerror',e=>errors.push(e.message));await p.goto('http://127.0.0.1:8768/#genesis');await p.locator('[data-genesis-starter]').first().waitFor();
const draft=await p.evaluate(async()=>{
 const saved=await api('/api/blueprints/draft',{name:'UI replay — Product Graph Fast Path',notes:'Offline UI acceptance only, not a measured candidate.',track:'agentic-request',graph:TEMPLATES.single.build()});
 const receipt={presentation:true,card_id:'configuration',template:'configuration',title:'Configure the candidate in Studio',detail:'Offline replay: changing the executor instructions in the actual editor.',status:'active',route:'#studio/'+saved.id,label:'Open candidate',items:[],sources:[]};
 const t={id:'guided-ui-replay',status:'running',model:'gpt-6-astra',message:'UI replay: configure an architecture in front of me.',answer:'',events:[{id:1,type:'tool_started',action:'present',payload:JSON.stringify(receipt)},{id:2,type:'tool_completed',action:'present',detail:JSON.stringify(receipt)}]};window.guideTurn=t;document.getElementById('genesis-messages').innerHTML=turnHtml(t);localStorage.setItem('genesis.follow','1');armFollow();paintTurn(t);return saved;
});
await p.waitForFunction(id=>location.hash==='#studio/'+id&&blueprint?.id===id&&document.getElementById('setup-panel').dataset.screen==='editor',draft.id);
const changed=await p.evaluate(()=>{
 const agent=blueprint.graph.nodes.find(n=>n.type==='agent');if(!agent)throw Error('No executor in template');
 const operation={operation:'set_prompt',node:agent.id,text:'Use product knowledge to identify the relevant actions. Resolve exact record IDs from observed responses. Complete only the requested changes.'};
 const receipt={operation,id:blueprint.id,nodes:blueprint.graph.nodes.length,edges:blueprint.graph.edges.length,saved:false};guideTurn.events.push({id:3,type:'tool_started',action:'edit_architecture',payload:JSON.stringify(operation)},{id:4,type:'tool_completed',action:'edit_architecture',detail:JSON.stringify(receipt)});
 applyBuildEvents(guideTurn.id,guideTurn.events);paintTurn(guideTurn);selection=new Set([agent.id]);renderInspector();return {instructions:agent.config.instructions,dirty,provisional:provisional.has(agent.id)};
});assert.match(changed.instructions,/Resolve exact record IDs/);assert.equal(changed.dirty,true);assert.equal(changed.provisional,true);assert.equal(await p.locator('#genesis-window-stage').isVisible(),true);
await p.evaluate(()=>scrollTo({top:0,behavior:'instant'}));await p.screenshot({path:path.resolve('.impeccable/review/genesis-guided-editor.png'),fullPage:true});
// A new guided destination must not discard the provisional editor.
const guarded=await p.evaluate(()=>{followArmed=true;followBroken=false;const before=location.hash;return {moved:follow('#budget'),same:location.hash===before};});assert.equal(guarded.moved,false);assert.equal(guarded.same,true);assert.deepEqual(errors,[]);console.log(JSON.stringify({guidedRoute:true,livePromptEdit:true,provisional:true,dirtyNavigationProtected:true,errors}));
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
