const {chromium}=require('C:/Users/Lucas Wakigawa/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict');

function receipt(){return {
  presentation:true,card_id:'audit',template:'architecture',status:'active',
  title:'Product Graph Fast Path with a deliberately long title that must remain inside the compact Genesis instrument',
  detail:'A long evidence-grounded description checks wrapping while live updates continue without closing reader-controlled disclosures.',
  items:[{label:'Candidate direction',value:'Compact product knowledge, exact bindings, one executor and comparable native harness runs'}],
  sources:[{label:'Architecture audit',ref:'research/architectures/2026-09-11-product-graph-fast-path.md'}]
};}

(async()=>{
  const browser=await chromium.launch({channel:'chrome'}),results=[];
  try{
    for(const width of [1440,390])for(const dark of [false,true]){
      const page=await browser.newPage({viewport:{width,height:900},reducedMotion:'reduce'}),errors=[];
      page.on('pageerror',error=>errors.push(error.message));
      await page.goto('http://127.0.0.1:8768/#genesis');
      await page.locator('[data-genesis-starter]').first().waitFor();
      if(dark)await page.locator('#theme-toggle').click();
      await page.evaluate(card=>{
        const turn={id:'audit-turn',thread:'audit-thread',status:'running',model:'gpt-6-astra',message:'Audit Genesis.',answer:'',events:[
          {id:1,type:'tool_started',action:'read_code',at:new Date().toISOString(),payload:{path:'research/architectures'}},
          {id:2,type:'tool_completed',action:'read_code',at:new Date().toISOString(),detail:'Architecture history read.'},
          {id:3,type:'tool_started',action:'present',at:new Date().toISOString(),payload:card},
          {id:4,type:'tool_completed',action:'present',at:new Date().toISOString(),detail:JSON.stringify(card)}
        ]};
        window.auditTurn=turn;
        document.getElementById('genesis-messages').innerHTML=turnHtml(turn);
        paintTurn(turn,{fresh:true});
        history.pushState(null,'','#budget');goRoute('#budget');document.dispatchEvent(new Event('genesis:navigated'));
      },receipt());
      const panel=page.locator('#genesis-orb-panel');await panel.waitFor({state:'visible'});
      const stage=panel.locator('.genesis-stage'),work=stage.locator('.genesis-stage-work'),log=stage.locator('.genesis-stage-log');
      assert.equal(await work.getAttribute('open'),null);assert.equal(await log.getAttribute('open'),null);
      const workSummary=work.locator(':scope > summary'),logSummary=log.locator(':scope > summary');
      await workSummary.click();await logSummary.click();
      await page.evaluate(()=>GenesisStage.sync(document.getElementById('genesis-window-stage'),auditTurn));
      assert.equal(await work.getAttribute('open'),'');assert.equal(await log.getAttribute('open'),'');
      assert.match(await stage.locator('.genesis-stage-narration h3').evaluate(e=>getComputedStyle(e).fontFamily),/IBM Plex Mono/);
      assert.notEqual(await panel.evaluate(e=>getComputedStyle(e).backgroundImage),'none');
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
      const box=await panel.boundingBox();assert.ok(box.x>=0&&box.x+box.width<=width+1);
      if(width===390){
        for(const locator of [workSummary,logSummary,page.locator('[data-window-chat]'),page.locator('[data-window-stop]'),page.locator('[data-window-dismiss]')])
          assert.ok((await locator.boundingBox()).height>=44);
      }else{
        const main=await page.locator('#main-content').boundingBox();assert.ok(main.x+main.width<=box.x+1);
      }
      await workSummary.focus();assert.equal(await workSummary.evaluate(e=>document.activeElement===e),true);
      assert.equal(await stage.getAttribute('data-motion'),'off');
      await page.locator('[data-window-dismiss]').click();assert.equal(await panel.isVisible(),false);assert.equal(await page.locator('body').evaluate(e=>e.classList.contains('genesis-guided')),false);
      assert.deepEqual(errors,[]);results.push({width,theme:dark?'dark':'light',passed:true});await page.close();
    }
    console.log(JSON.stringify(results));
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1});


