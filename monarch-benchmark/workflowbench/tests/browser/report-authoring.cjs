// Focused, offline browser acceptance for feature 027. No research records are written.
// Start uv run python tests/browser/report-authoring-server.py --port 8879 --keep first; then node tests/browser/report-authoring.cjs
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const BASE = process.env.REPORT_TEST_BASE || 'http://127.0.0.1:8879';
const OUT = path.resolve(__dirname, '../../.tmp/report-authoring-browser');
let playwright;
for (const name of [process.env.PLAYWRIGHT_MODULE, 'playwright', 'C:/Users/Lucas Wakigawa/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'].filter(Boolean)) { try { playwright = require(name); break; } catch {} }
if (!playwright) throw new Error('Playwright is unavailable');
(async () => {
  fs.mkdirSync(OUT, {recursive:true});
  const report = await (await fetch(BASE + '/api/reports/run/fixture-1')).json();
  assert(report.patterns?.setups.length === 2, 'real API includes computed patterns');
  const index = await (await fetch(BASE + '/api/reports')).json();
  const cohort = index.rounds.find(c => c.runs.some(r => r.id === report.run)).id;
  const publication = {status:'completed', revision:2, summary:'Fixture: the requested updates succeeded, but extra changes made the near-miss attempts fail.',
    what_went_right:'The scripted reference selected the requested contact and produced the required update. These checks exercise the reporting interface; they do not compare model quality.',
    what_went_wrong:'The near-miss control changed data outside the requested scope. Passing the target field check alone was insufficient.',
    why:'The decisive difference is the scope of the recorded writes. The reference changed the requested field; the near-miss control also changed unrelated data. This is a controlled fixture, so it supports the checker explanation rather than a claim about model reasoning.\n\nIn a real comparison, Genesis must inspect the first divergence and contrast the same task across setups before assigning a possible mechanism.',
    next_experiment:'Compare a frozen task with a similarly structured task and inspect whether the same extra-write behavior repeats. No experiment is launched by reading this page.',
    limitations:'Fixture only. No live model was used. A reviewed interpretation is not experimental proof of causation.',
    findings:[{title:'Extra writes determine the failure', explanation:'The failed attempts retain an unsuccessful scope check.', kind:'fact', event_ids:report.failures.attempts[0].event_ids.slice(0,1)}],
    attempts:report.failures.attempts.map((a,i)=>({index:i,task:a.task,model:a.model, explanation:'Fixture interpretation of this exact recorded attempt.',expected:'Only the requested contact field changes.', observed:a.narrative, mechanism:'Additional writes are a possible failure mechanism when scope checks fail.', alternatives:'A task-data or checker mismatch must be investigated separately.',confidence:'limited',missing_evidence:'No live model reasoning was generated in this fixture.',event_ids:a.event_ids.slice(-2)}))};
  const browser = await playwright.chromium.launch({channel:process.env.BROWSER_CHANNEL || 'chrome'});
  const evidence = [];
  try {
    for (const [name,width,theme] of [['desktop',1440,'light'],['narrow',390,'light'],['dark',1440,'dark']]) {
      const context = await browser.newContext({viewport:{width,height:1000},reducedMotion:'reduce'});
      await context.addInitScript(t=>localStorage.setItem('ailabs-theme',t),theme);
      let stage='published'; const errors=[]; const methods=[];
      await context.route('**/api/reports/run/fixture-1', async route => {
        methods.push(route.request().method());
        const response=await route.fetch(); const body=await response.json();
        body.title='Fixture — Genesis authored report'; body.authored=stage==='published'?publication:null;
        body.report_work={stage,reason:stage==='repair'?'Addressing the reviewer’s evidence requests.':undefined};
        body.narrative={status:'completed',summary:'LEGACY_DUPLICATE',model:'Legacy fixture'};
        await route.fulfill({response,json:body});
      });
      await context.route('**/api/reports/round/' + cohort, async route => { const response=await route.fetch(); const body=await response.json(); body.run_analyses=body.run_analyses.map(a=>({...a,authored:a.run==='fixture-1'?publication:null})); await route.fulfill({response,json:body}); });
      const page=await context.newPage(); page.on('pageerror', e=>{ errors.push(e.message); console.error('PAGE:',e.message); });
      await page.goto(BASE+'/#report/fixture-1'); await page.waitForSelector('#report-attempt-0',{timeout:10000}).catch(async e=>{console.error(await page.locator('body').innerText());throw e;});
      assert.equal(await page.locator('.verdict').innerText(),publication.summary);
      assert(!(await page.locator('#report-article').innerText()).includes('LEGACY_DUPLICATE'));
      assert((await page.locator('#report-analysis').innerText()).includes(publication.limitations));
      assert.equal(await page.locator('.report-attempt').count(),report.failures.attempts.length);
      assert(await page.locator('.pattern-slice[role=button]').count()>=2);
      await page.locator('.pattern-slice').first().focus(); await page.keyboard.press('Enter');
      assert(await page.locator('.pattern-detail .pattern-attempts li').count()>0,'keyboard slice drilldown');
      await page.locator('.pattern-control select').selectOption('checks');
      await page.locator('.pattern-counts summary').click();
      await page.locator('[data-pattern-column]').first().click();
      assert((await page.locator('.pattern-detail').innerText()).includes('Termination:'));
      await page.locator('.pattern-control select').selectOption('behavior');
      const overflow=await page.evaluate(()=>Math.max(0,document.documentElement.scrollWidth-innerWidth)); assert(overflow<=1,name+' overflow '+overflow);
      await page.evaluate(()=>window.scrollTo(0,0));
      await page.screenshot({path:path.join(OUT,name+'.png'),fullPage:true});
      await page.locator('.report-patterns').screenshot({path:path.join(OUT,name+'-patterns.png')});
      await page.locator('#report-attempt-0 summary').click();
      assert((await page.locator('#report-attempt-0').innerText()).includes('Alternative explanations'));
      const eventButton=page.locator('#report-attempt-0 [data-evidence-event]').first(); const event=await eventButton.getAttribute('data-evidence-event');
      assert.equal(Number(event),publication.attempts[0].event_ids[0]);
      if(name==='desktop') {
        publication.attempts[0].explanation='<img src=x onerror="window.__reportUnsafe=1">'; await page.reload(); await page.waitForSelector('#report-attempt-0'); await page.locator('#report-attempt-0 summary').click();
        assert.equal(await page.locator('#report-attempt-0 img').count(),0); assert.equal(await page.evaluate(()=>window.__reportUnsafe),undefined);
        publication.attempts[0].explanation='Fixture interpretation of this exact recorded attempt.';
        stage='repair'; await page.reload(); await page.waitForSelector('[data-report-refresh]'); assert((await page.locator('.report-work').innerText()).includes('Addressing'));
        stage='published'; await page.locator('[data-report-refresh]').click(); await page.waitForSelector('#report-attempt-0');
      }
      await page.goto(BASE+'/#round/'+cohort); await page.waitForSelector('.run-analysis');
      assert((await page.locator('#report-analysis').innerText()).includes('Each interpretation applies to the named run'));
      assert(await page.locator('.pattern-slice').count()>=2);
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'round overflow');
      await page.evaluate(()=>window.scrollTo(0,0));
      await page.screenshot({path:path.join(OUT,name+'-round.png'),fullPage:true});
      assert.equal(errors.length,0,errors.join('\n')); assert(methods.every(m=>m==='GET'),'report reads must be free GETs');
      evidence.push({name,width,theme,overflow,errors,attempts:report.failures.attempts.length,checks:['authored opening','legacy suppression','limitations','all attempt details','keyboard slice drilldown','checker classification','exact counts','run-scoped round analysis','read-only refresh']});
      await context.close();
    }
    fs.writeFileSync(path.join(OUT,'evidence.json'),JSON.stringify(evidence,null,2)); console.log(JSON.stringify({status:'passed',output:OUT,evidence}));
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
