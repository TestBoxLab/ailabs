const {chromium}=require('C:/Users/Lucas Wakigawa/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');
const out=path.resolve('.impeccable/review');fs.mkdirSync(out,{recursive:true});
async function replay(page){return page.evaluate(()=>{
 const t={id:'ui-replay',status:'running',model:'gpt-6-astra',message:'UI replay: review architecture history and design a faster product-graph candidate.',answer:'Illustrative replay only. No benchmark is running.',created_at:new Date().toISOString(),events:[]};let id=0;
 const add=(action,result)=>{t.events.push({id:++id,type:'tool_started',action,at:new Date().toISOString(),payload:JSON.stringify(result)});t.events.push({id:++id,type:'tool_completed',action,at:new Date().toISOString(),detail:JSON.stringify(result)});};
 add('read_code',{path:'Recovered architecture catalog'});
 add('present',{presentation:true,card_id:'history',template:'research',status:'complete',title:'History reviewed. More planning was not reliably better.',detail:'Illustrative replay of the audit. Earlier permission layers sometimes blocked required writes.',items:[{label:'Candidate direction',value:'Compact product knowledge · one executor'}],sources:[{label:'Architecture audit',ref:'research/architectures/2026-09-11-product-graph-fast-path.md'}]});
 add('present',{presentation:true,card_id:'candidate',template:'architecture',status:'active',title:'Product Graph Fast Path',detail:'Reduce discovery overhead and preserve exact record bindings. Completion and latency remain hypotheses to test.',items:[{label:'Comparison',value:'Same tasks · matched native harnesses'},{label:'Status',value:'Candidate design · not evaluated'}],sources:[]});
 window.replayTurn=t;document.getElementById('genesis-messages').innerHTML=turnHtml(t);paintTurn(t,{fresh:true});document.getElementById('genesis-thread-title').textContent='Architecture research · UI replay';
 });}
(async()=>{const browser=await chromium.launch({channel:'chrome'});const findings=[];try{
 for(const width of [1440,390]){
  const page=await browser.newPage({viewport:{width,height:1000},reducedMotion:'reduce'});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8768/#genesis');await page.locator('[data-genesis-starter="0"]').waitFor();
  await page.locator('[data-genesis-starter="0"]').click();assert.match(await page.locator('#genesis-message').inputValue(),/Run \[number\] tasks/);
  await replay(page);assert.equal(await page.locator('#genesis-messages .genesis-scene-card').count(),2);
  assert.equal(await page.locator('#genesis-orb-panel').isVisible(),false);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.equal(await page.locator('#genesis-messages .genesis-stage').getAttribute('data-motion'),'off');
  await page.evaluate(()=>scrollTo({top:0,behavior:'instant'}));await page.screenshot({path:path.join(out,`genesis-stage-${width}.png`),fullPage:true});
  await page.evaluate(()=>{const source=document.querySelector('#genesis-messages .genesis-scene-sources');source.open=true;const next={...replayTurn.events.at(-1),id:99,detail:JSON.stringify({...JSON.parse(replayTurn.events.at(-1).detail),title:'Candidate updated <img src=x onerror=alert(1)>'})};replayTurn.events.push(next);paintTurn(replayTurn);});
  assert.equal(await page.locator('#genesis-messages .genesis-scene-card').count(),2);assert.equal(await page.locator('#genesis-messages img').count(),0);
  assert.equal(await page.locator('#genesis-messages .genesis-scene-sources').getAttribute('open'),'');
  await page.emulateMedia({reducedMotion:'no-preference'});await page.locator('#genesis-messages .genesis-stage').scrollIntoViewIfNeeded();
  await page.waitForFunction(()=>document.querySelector('#genesis-messages .genesis-stage').dataset.motion==='on');
  const before=await page.locator('#genesis-messages .genesis-stage-art pre:not(.genesis-matrix-rain)').textContent();await page.waitForTimeout(680);assert.notEqual(await page.locator('#genesis-messages .genesis-stage-art pre:not(.genesis-matrix-rain)').textContent(),before);
  await page.locator('#genesis-messages .genesis-stage-motion').click();const held=await page.locator('#genesis-messages .genesis-stage-art pre:not(.genesis-matrix-rain)').textContent();await page.waitForTimeout(680);assert.equal(await page.locator('#genesis-messages .genesis-stage-art pre:not(.genesis-matrix-rain)').textContent(),held);
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.evaluate(async()=>{replayTurn.status='completed';paintTurn(replayTurn);history.pushState(null,'','#budget');await goRoute('#budget');document.dispatchEvent(new Event('genesis:navigated'));});
  assert.equal(await page.locator('#genesis-orb-panel').isVisible(),true);assert.equal(await page.locator('#genesis-window-stage').isVisible(),true);assert.equal(await page.locator('[data-window-stop]').isVisible(),false);
  await page.evaluate(()=>scrollTo({top:0,behavior:'instant'}));await page.screenshot({path:path.join(out,`genesis-window-${width}.png`),fullPage:true});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.locator('[data-window-dismiss]').click();assert.equal(await page.locator('#genesis-orb-panel').isVisible(),false);
  assert.deepEqual(errors,[]);findings.push({width,checks:'starters, cards, keyed update, escaping, source state, reduced motion, live frames, pause, navigation, retained completion, dismissal, overflow, console',passed:true});await page.close();
 }
 fs.writeFileSync(path.join(out,'genesis-stage-verification.json'),JSON.stringify(findings,null,2));console.log(JSON.stringify(findings));
 }finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
