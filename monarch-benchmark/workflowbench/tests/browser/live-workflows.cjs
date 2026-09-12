'use strict';
const fs=require('node:fs'),path=require('node:path'),{spawn}=require('node:child_process'),assert=require('node:assert/strict');
let playwright;for(const p of [process.env.PLAYWRIGHT_MODULE,'playwright','C:/Users/Lucas Wakigawa/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'].filter(Boolean)){try{playwright=require(p);break;}catch{}}
const ROOT=path.resolve(__dirname,'../..'),OUT=path.resolve(ROOT,'../../.tmp/live-workflows');fs.mkdirSync(OUT,{recursive:true});
const PORT=Number(process.env.BROWSER_PORT||8779),BASE=process.env.LIVE_WORKFLOW_BASE||'http://127.0.0.1:'+PORT;
async function server(){
  if(process.env.LIVE_WORKFLOW_BASE)return null;
  const child=spawn(process.platform==='win32'?'uv.exe':'uv',['run','--python','3.13','python','tests/browser/live-workflows-server.py','--port',String(PORT)],{cwd:ROOT,stdio:['ignore','pipe','pipe'],windowsHide:true});
  await new Promise((resolve,reject)=>{let out='';const timer=setTimeout(()=>reject(new Error(out)),90000);child.stdout.on('data',d=>{out+=d;if(out.includes('READY')){clearTimeout(timer);resolve();}});child.stderr.on('data',d=>out+=d);child.on('exit',code=>{clearTimeout(timer);reject(new Error('Fixture exit '+code+' '+out));});});return child;
}
async function open(browser,viewport,motion='reduce',theme='light'){
  const context=await browser.newContext({viewport,reducedMotion:motion});await context.addInitScript(t=>localStorage.setItem('ailabs-theme',t),theme);
  const p=await context.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.message));p.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  await p.goto(BASE+'/#run/fixture-live');await p.waitForSelector('.flow-node');return {p,context,errors};
}
async function audit(p,errors){assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'page must not overflow');assert.deepEqual(errors,[]);}
(async()=>{
 const service=await server();let browser;
 try{
  browser=await playwright.chromium.launch({channel:'chrome',headless:true});
  const {p,context,errors}=await open(browser,{width:1440,height:1100},'no-preference');
  await p.waitForFunction(()=>document.querySelector('.performance-progress').textContent==='1 / 6 recorded');
  assert.equal(await p.locator('.flow-lane').count(),2);
  assert.equal(await p.locator('.flow-cell.receiving').count(),0,'initial journal does not animate');
  await p.evaluate(()=>{window.savedFlowNode=document.querySelector('[data-flow-node="demo:model"]');window.savedMetric=document.querySelector('.performance-outcomes .performance-row');window.savedFlowNode.querySelector('button').focus();});
  await p.request.post(BASE+'/test/advance');
  await p.waitForFunction(()=>document.querySelector('[data-flow-node="demo:model"] .flow-preview').textContent.includes('two contact records'));
  assert.equal(await p.evaluate(()=>savedFlowNode===document.querySelector('[data-flow-node="demo:model"]')),true,'stream updates retain node identity');
  assert.equal(await p.evaluate(()=>savedFlowNode.contains(document.activeElement)),true,'streaming preserves focus');
  assert.equal(await p.locator('[data-flow-node="demo:tool"] .flow-output-table tbody tr').count(),2,'structured output is visible');
  await p.locator('#flow-motion').click();assert.equal(await p.locator('#flow-motion').getAttribute('aria-pressed'),'true');
  assert.equal(await p.locator('#flow-observatory').evaluate(n=>n.classList.contains('motion-paused')),true);
  const before=await p.locator('[data-flow-node="demo:model"] .flow-preview').innerText();
  await p.evaluate(()=>{const e=events.findLast(e=>e.type==='model_delta');stream.onmessage({data:JSON.stringify(e)});});
  assert.equal(await p.locator('[data-flow-node="demo:model"] .flow-preview').innerText(),before,'SSE reconnect delivery is idempotent');
  await p.locator('[data-flow-node="demo:tool"] button').click();await p.waitForSelector('#attempt-dialog[open]');
  assert.match(await p.locator('#output').innerText(),/Lisa Park/);await p.locator('#close-inspector').click();
  await p.request.post(BASE+'/test/advance');
  await p.waitForFunction(()=>document.querySelector('.performance-progress').textContent==='2 / 6 recorded');
  assert.equal(await p.evaluate(()=>savedMetric===document.querySelector('.performance-outcomes .performance-row')),true,'chart rows persist as values arrive');
  assert.match(await p.locator('.performance-outcomes').innerText(),/1 passed \/ 1 recorded/);
  assert.equal(await p.locator('[data-flow-node="demo:model"]').getAttribute('data-status'),'completed');
  await p.locator('.performance-detail>summary').click();assert.match(await p.locator('.performance-table').innerText(),/12.5s/);await p.locator('.performance-detail>summary').click();
  await p.evaluate(()=>{
    window.beforeRegression=events.slice();window.savedFlowNode=document.querySelector('[data-flow-node="demo:model"]');savedFlowNode.querySelector('button').focus();
    for(let i=0;i<24;i++)events.push({id:'regression:'+i,task:taskId,model:'sloppy',type:'node_finished',node:'regression:'+i,status:'completed',output:'Recorded '+i});
    renderGraph();
  });
  assert.equal(await p.evaluate(()=>savedFlowNode.isConnected&&savedFlowNode.contains(document.activeElement)),true,'24 arrivals retain the focused node');
  await p.evaluate(()=>{events.push({id:'regression:recipe',task:taskId,model:'sloppy',type:'workflow_recipe',nodes:[{id:'a',label:'Read'},{id:'b',label:'Independent'},{id:'c',label:'Write'}],edges:[{source:'a',target:'c'}]});renderGraph();});
  assert.equal(await p.locator('.flow-dependencies path[data-source="wf:a"][data-target="wf:c"]').count(),1,'nonadjacent dependency is drawn');
  await p.evaluate(()=>{events=beforeRegression;renderGraph();});
  const initialTask=await p.locator('#task-select').inputValue();
  await p.locator('#flow-latest').click();
  assert.notEqual(await p.locator('#task-select').inputValue(),initialTask,'Latest activity opens the active task');
  await p.locator('#task-select').selectOption(initialTask);
  const collapsed=p.locator('.workstream.collapsed').first();
  await collapsed.locator('.stream-toggle').click();assert.equal(await collapsed.count(),0,'Expand opens the finished output');
  const passedCard=p.locator('.workstream.passed').first();await passedCard.locator('.stream-toggle').click();assert.equal(await passedCard.locator('.block-body').isVisible(),false,'Collapse hides finished output');
  await audit(p,errors);
  const nodeTop=await p.locator('.flow-node').first().evaluate(n=>n.getBoundingClientRect().top);
  assert.ok(nodeTop<750,'workflow activity appears in the first desktop viewport: '+nodeTop);
  await p.screenshot({path:path.join(OUT,'desktop.png'),fullPage:true});
  const mobile=await open(browser,{width:390,height:844});await audit(mobile.p,mobile.errors);
  assert.equal(await mobile.p.locator('#flow-observatory').evaluate(n=>n.classList.contains('motion-paused')),true);
  for(const selector of ['#flow-motion','#flow-latest','#task-select','#fit-view'])assert.ok(await mobile.p.locator(selector).evaluate(n=>n.getBoundingClientRect().height)>=44,selector+' touch target');
  await mobile.p.screenshot({path:path.join(OUT,'mobile.png'),fullPage:true});
  const dark=await open(browser,{width:1440,height:1100},'reduce','dark');await audit(dark.p,dark.errors);await dark.p.screenshot({path:path.join(OUT,'dark.png'),fullPage:true});
  await p.goto(BASE+'/#report/fixture-1/performance');await p.waitForSelector('#report-performance .performance-figures');
  await audit(p,errors);await p.screenshot({path:path.join(OUT,'report.png'),fullPage:true});
  await p.locator('#report-performance .performance-detail>summary').click();
  await p.locator('#report-performance .performance-samples summary').first().click();
  await p.locator('#report-performance .performance-samples a').first().click();
  await p.waitForSelector('#attempt-dialog[open]');
  await context.close();await mobile.context.close();await dark.context.close();
  fs.writeFileSync(path.join(OUT,'checks.json'),JSON.stringify({status:'passed',fixtures:'offline only',viewports:[1440,390],checks:['persistent nodes','focus retention over 24 arrivals','nonadjacent dependency','latest active task','44px mobile controls','workflow in initial viewport','structured output','pause motion','duplicate SSE','node inspector','persisted live metric refresh','stable chart rows','failed time separate','reduced motion','permanent report','sample evidence link','no overflow or console errors']},null,2));
  console.log('Live workflow browser checks passed. Screenshots: '+OUT);
 }finally{if(browser)await browser.close();if(service){await fetch(BASE+'/test/shutdown',{method:'POST'}).catch(()=>service.kill());service.stdout.destroy();service.stderr.destroy();}}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
