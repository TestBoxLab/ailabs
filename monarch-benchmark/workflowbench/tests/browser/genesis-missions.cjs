// Offline Genesis mission UI acceptance. No provider or benchmark requests.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
let playwright;
for (const name of [process.env.PLAYWRIGHT_MODULE, 'playwright', 'C:/Users/Lucas Wakigawa/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'].filter(Boolean)) {
  try { playwright = require(name); break; } catch {}
}
if (!playwright) throw new Error('Playwright is unavailable');
const staticDir = path.resolve(__dirname, '../../wb_studio/static');
const results = [];
const shell = () => fs.readFileSync(path.join(staticDir,'index.html'),'utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'');
const server = http.createServer((req,res) => {
  const name = req.url.split('?')[0];
  const file = name === '/' ? null : path.join(staticDir,name);
  res.setHeader('Content-Type', name.endsWith('.css')?'text/css':name.endsWith('.js')?'application/javascript':'text/html');
  if (!file) res.end(shell());
  else if (file.startsWith(staticDir) && fs.existsSync(file)) res.end(fs.readFileSync(file));
  else { res.statusCode=404;res.end('Missing fixture asset'); }
});

async function setup(browser,width=1440) {
 const page=await browser.newPage({viewport:{width,height:960},reducedMotion:'reduce'});
 await page.goto(`http://127.0.0.1:${server.address().port}`);
 await page.evaluate(()=>{
  window.$=s=>document.querySelector(s);window.$$=s=>Array.from(document.querySelectorAll(s));
  window.esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  window.option=(v,label,on)=>'<option value="'+esc(v)+'"'+(on?' selected':'')+'>'+esc(label)+'</option>';
  window.human=x=>String(x).replaceAll('_',' ');window.toast=()=>{};window.linkRecTags=()=>{};window.drawFigures=()=>{};
  window.showWorkspaceSurface=()=>{$('#genesis-panel').classList.remove('hidden');};
  window.money=x=>'$'+x;window.budget=()=>{};
  window.streams=[];window.EventSource=class extends EventTarget{constructor(url){super();this.url=url;window.streams.push(this);}close(){this.closed=true;}};
  window.calls=[];window.operations=[];window.applyArchitectureOperation=x=>operations.push(x);
  window.fixture={me:'human:lucas',models:[{id:'cheap',name:'Cheap',available:true,efforts:['low','medium','high']},{id:'gpt-6-astra',name:'GPT-6 Astra',available:true,efforts:['low','medium','high']}],config:{models:{chat:'gpt-6-astra'},effort:{chat:'medium'},effective:{chat:'gpt-6-astra'}},cards:[],threads:[{id:'thread',owner:'human:lucas',title:'Improve Monarch from recorded failures',turn_count:1}]};
  window.fixtureTurns=[{id:'origin',thread:'thread',by:'human:lucas',status:'completed',model:'gpt-6-astra',message:'Investigate Monarch and test a candidate.',answer:'The mission is recorded. I will inspect the evidence.',events:[]}];
  window.api=async(url,body)=>{calls.push({url,body});if(url==='/api/genesis')return structuredClone(fixture);if(url==='/api/genesis/threads/thread')return {turns:structuredClone(fixtureTurns)};return {};};
  localStorage.setItem('genesis.follow','0');sessionStorage.setItem('genesis-inbox-seen','1');location.hash='#genesis/t/thread';
 });
 await page.addScriptTag({path:path.join(staticDir,'genesis.js')});
 await page.evaluate(async()=>{loadWatcher=()=>{};await openGenesis();});
 await page.waitForSelector('[data-turn="origin"]');
 return page;
}
async function check(name,fn){await fn();results.push(name);console.log('PASS '+name);}
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await playwright.chromium.launch({channel:process.env.BROWSER_CHANNEL||'chrome'});
 const out=path.resolve(__dirname,'../../out/genesis-missions-browser');fs.mkdirSync(out,{recursive:true});
 try{
 await check('unavailable configured model never silently selects cheap route',async()=>{
  const p=await setup(browser);
  await p.evaluate(()=>{$('#genesis-model').value='';fixture.models[1].available=false;fixture.config.effective.chat=null;genesisData=structuredClone(fixture);renderGenesisModels();});
  assert.equal(await p.locator('#genesis-model').inputValue(),'');assert.equal(await p.locator('#genesis-send').isDisabled(),true);
  assert.match(await p.locator('#genesis-model-name').textContent(),/unavailable/i);
  await p.evaluate(()=>selectGenesisModel('cheap'));
  assert.equal(await p.locator('#genesis-send').isEnabled(),true);await p.close();
 });
 await check('initial effort follows configuration and explicit choice survives refresh',async()=>{
  const p=await setup(browser);assert.equal(await p.locator('#genesis-effort').inputValue(),'medium');
  await p.evaluate(()=>{$('#genesis-effort').value='high';renderGenesisModels();});assert.equal(await p.locator('#genesis-effort').inputValue(),'high');await p.close();
 });
 await check('mission worker arrives without wiping draft focus scroll or starting duplicate streams',async()=>{
  const p=await setup(browser);
  await p.evaluate(async()=>{
   const mission={id:'mission',title:'Investigate Monarch failures',stage:'research',kind:'research',body:'',work:{status:'queued'},mission:{status:'queued',owner:'human:lucas',thread:'thread'}};
   fixture.cards=[mission];genesisData.cards=structuredClone(fixture.cards);await renderConversation();
   $('#genesis-message').value='Keep my unfinished question';$('#genesis-message').focus();
   const sheet=new CSSStyleSheet();sheet.replaceSync('#genesis-messages{max-height:280px;scroll-behavior:auto}');document.adoptedStyleSheets=[...document.adoptedStyleSheets,sheet];
   $('#genesis-messages').insertAdjacentHTML('afterbegin','<p>'+('Earlier evidence<br>'.repeat(70))+'</p>');$('#genesis-messages').scrollTop=40;
   fixtureTurns.push({id:'worker',thread:'thread',purpose:'Genesis mission',card:'mission',by:'human:lucas',model:'gpt-6-astra',status:'running',message:'Inspect evidence and prepare a candidate.',answer:'',events:[{id:1,type:'tool_completed',action:'edit_architecture',detail:JSON.stringify({operation:{type:'add_node'},saved:false})}]});
   fixture.cards[0].mission.status='working';fixture.cards[0].work={status:'working',turn:'worker'};
  });
  await p.waitForSelector('[data-turn="worker"]',{timeout:6000});
  assert.equal(await p.locator('#genesis-message').inputValue(),'Keep my unfinished question');
  assert.equal(await p.evaluate(()=>document.activeElement.id),'genesis-message');
  assert.equal(await p.locator('#genesis-messages').evaluate(e=>e.scrollTop),40);
  assert.equal(await p.evaluate(()=>operations.length),1);assert.equal(await p.evaluate(()=>streams.length),0);
  assert.equal(await p.locator('#genesis-send').isEnabled(),true);
  await p.evaluate(()=>{fixtureTurns[1].status='completed';fixtureTurns[1].answer='Evidence inspected; candidate saved.';fixture.cards[0].mission.status='waiting';fixture.cards[0].mission.wait_for='experiment';fixture.cards[0].work.status='waiting';});
  await p.waitForFunction(()=>document.querySelector('[data-turn="worker"] .genesis-answer').textContent.includes('Evidence inspected'));
  assert.equal(await p.evaluate(()=>operations.length),1);
  assert.match(await p.locator('#tracking-list').textContent(),/Waiting on experiment/);
  await p.screenshot({path:path.join(out,'mission-1440.png')});await p.close();
 });
 await check('mission waiting and blocked states retain stop control',async()=>{
  const p=await setup(browser,390);
  for(const status of ['waiting','blocked']){
   const output=await p.evaluate(status=>{const c={mission:{status,wait_for:'experiment',summary:'Billing verification required'},work:{status:status==='blocked'?'failed':'waiting'}};return {action:nextAction(c),detail:workDetail(c)};},status);
   assert.match(output.detail,/id="research-stop"/);assert.doesNotMatch(output.action,/Waiting for an answer/);
  }
  await p.screenshot({path:path.join(out,'mission-390.png')});await p.close();
 });
 console.log(`Genesis missions: ${results.length} scenarios passed.`);
 }finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
