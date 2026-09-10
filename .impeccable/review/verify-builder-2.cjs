const {chromium}=require('C:/Users/Lucas Wakigawa/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{const b=await chromium.launch({headless:true,channel:'msedge'});const p=await b.newPage({viewport:{width:1600,height:1000}});const errors=[];p.on('pageerror',e=>errors.push(e.message));p.on('dialog',d=>d.accept());
await p.goto('http://127.0.0.1:8765');await p.getByRole('tab',{name:'Activity'}).click();await p.waitForTimeout(800);await p.screenshot({path:'.impeccable/review/builder-activity-2.png',fullPage:false});
await p.getByRole('button',{name:'Monarch setups',exact:true}).click();await p.locator('.bp-node').first().waitFor();await p.evaluate(()=>localStorage.removeItem('ailabs-architecture-draft'));
const options=await p.locator('#blueprint-library option').allTextContents();const target=options.findIndex(o=>o.startsWith('Opus planner'));await p.locator('#blueprint-library').selectOption({index:target});await p.waitForTimeout(1000);
await p.locator('[data-node="planner"]').click({position:{x:30,y:20}});await p.waitForTimeout(500);await p.screenshot({path:'.impeccable/review/builder-published.png',fullPage:true});
await p.getByRole('button',{name:'Run latest version'}).click();await p.waitForTimeout(1500);await p.screenshot({path:'.impeccable/review/builder-launch-2.png',fullPage:false});
console.log(JSON.stringify({errors,options}));await b.close()})().catch(e=>{console.error(e);process.exit(1)});
