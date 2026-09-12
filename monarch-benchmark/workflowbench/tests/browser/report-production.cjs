// Read-only acceptance for Lucas's specified production run. No mocked responses.
// STUDIO_AUTH_USER/PASSWORD are inherited from the environment and never written.
// Set REPORT_REQUIRE_AUTHORED=1 after publication; omit it to capture a baseline.
// REPORT_DIAGNOSTIC_ONLY=1 reads only the report UI at 390px; REPORT_SURFACES=narrow runs narrow acceptance.
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const BASE = 'https://ailabs-studio-production.up.railway.app';
const RUN = 'f2799405-f9b3-4fb2-8e41-a517e9c39260';
const EXPECTED = 106;
const tag = (process.env.REPORT_EVIDENCE_TAG || new Date().toISOString()).replace(/[^a-zA-Z0-9_-]/g, '-');
const OUT = path.resolve(__dirname, '../../.tmp/report-production', tag);
const strict = process.env.REPORT_REQUIRE_AUTHORED === '1';
const diagnosticOnly = process.env.REPORT_DIAGNOSTIC_ONLY === '1';
const surfaces = [['desktop',1440,'light'],['narrow',390,'light'],['dark',1440,'dark']].filter(s=>!process.env.REPORT_SURFACES || process.env.REPORT_SURFACES.split(',').includes(s[0]));
const username = process.env.STUDIO_AUTH_USER;
const password = process.env.STUDIO_AUTH_PASSWORD;
const clean = value => {
  let text = String(value);
  for (const secret of [username, password, username && password && Buffer.from(username + ':' + password).toString('base64')].filter(Boolean)) text = text.split(secret).join('[redacted]');
  return text.replace(/https?:\/\/[^\s/]+@/g, 'https://[redacted]@');
};
let playwright;
for (const name of [process.env.PLAYWRIGHT_MODULE, 'playwright', 'C:/Users/Lucas Wakigawa/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'].filter(Boolean)) {
  try { playwright = require(name); break; } catch {}
}
const evidence = {run:RUN, url:BASE + '/#run/' + RUN, report_url:BASE + '/#report/' + RUN + '?audience=engine-team',
  recorded_at:new Date().toISOString(), expected_attempts:EXPECTED, require_authored:strict,
  status:'checking', checks:[], surfaces:[], blocked_requests:[], page_errors:[], artifacts:[]};
function check(name, passed, detail) {
  evidence.checks.push({name, passed:Boolean(passed), ...(detail === undefined ? {} : {detail})});
}
function save() {
  fs.mkdirSync(OUT, {recursive:true});
  fs.writeFileSync(path.join(OUT, 'evidence.json'), JSON.stringify(evidence, (key,value) => typeof value==='string' ? clean(value) : value, 2));
}
async function screenshot(page, name, target) {
  const filename = name + '.png';
  await (target || page).screenshot({path:path.join(OUT, filename), ...(target ? {} : {fullPage:true})});
  evidence.artifacts.push(filename);
}
async function overflowDetails(page) {
  // Geometry and CSS only: never collect text, values, URLs, attributes, or HTML.
  return page.evaluate(() => {
    const round=n=>Math.round(n*10)/10;
    function selector(node) {
      const parts=[];
      for (let n=node; n && parts.length<4; n=n.parentElement) {
        let part=n.tagName.toLowerCase();
        if(n.id) { parts.unshift(part+'#'+CSS.escape(n.id)); break; }
        part += Array.from(n.classList).slice(0,3).map(c=>'.'+CSS.escape(c)).join('');
        if(n.parentElement) part += ':nth-child('+(Array.from(n.parentElement.children).indexOf(n)+1)+')';
        parts.unshift(part);
      }
      return parts.join(' > ');
    }
    const all=Array.from(document.querySelectorAll('#report-article, #report-article *'));
    const rows=[];
    for (const node of all) {
      const rect=node.getBoundingClientRect();
      if(!rect.width || !rect.height || (rect.right<=innerWidth+1 && rect.left>=-1 && node.scrollWidth<=node.clientWidth+1)) continue;
      const style=getComputedStyle(node);
      let clip=node.parentElement;
      while(clip && !['hidden','clip','auto','scroll'].includes(getComputedStyle(clip).overflowX)) clip=clip.parentElement;
      const clipping=clip ? {selector:selector(clip),overflow_x:getComputedStyle(clip).overflowX,width:round(clip.getBoundingClientRect().width)} : null;
      rows.push({selector:selector(node),width:round(rect.width),left:round(rect.left),right:round(rect.right),
        client_width:node.clientWidth,scroll_width:node.scrollWidth,excess:round(Math.max(0,rect.right-innerWidth,-rect.left)),
        overflow_x:style.overflowX,display:style.display,position:style.position,white_space:style.whiteSpace,
        min_width:style.minWidth,max_width:style.maxWidth,flex_shrink:style.flexShrink,clipping_ancestor:clipping});
    }
    rows.sort((a,b)=>(a.clipping_ancestor ? 1 : 0)-(b.clipping_ancestor ? 1 : 0) || b.excess-a.excess);
    return {viewport_width:innerWidth,document_width:document.documentElement.scrollWidth,
      overflow:Math.max(0,document.documentElement.scrollWidth-innerWidth),
      matching_elements:rows.length,limit:32,offenders:rows.slice(0,32)};
  });
}
async function guardReads(context) {
  await context.route('**/*', async route => {
    const req=route.request(), url=new URL(req.url());
    if(url.origin!==BASE || !['GET','HEAD','OPTIONS'].includes(req.method())) {
      evidence.blocked_requests.push({method:req.method(),origin:url.origin,path:url.pathname});
      return route.abort('blockedbyclient');
    }
    await route.continue();
  });
}
async function diagnoseNarrow(credentials) {
  const browser=await playwright.chromium.launch({channel:process.env.BROWSER_CHANNEL || 'chrome'});
  const context=await browser.newContext({httpCredentials:credentials,viewport:{width:390,height:1000},reducedMotion:'reduce',serviceWorkers:'block'});
  try {
    await guardReads(context);
    await context.addInitScript(()=>localStorage.setItem('ailabs-theme','light'));
    const page=await context.newPage();
    page.on('pageerror',error=>evidence.page_errors.push({surface:'narrow',message:clean(error.message)}));
    await page.goto(BASE+'/#report/'+RUN+'?audience=engine-team',{waitUntil:'domcontentloaded',timeout:60000});
    await page.locator('#report-article .report-head').waitFor({timeout:60000});
    const geometry=await overflowDetails(page);
    evidence.surfaces.push({name:'narrow',width:390,theme:'light',report_overflow:geometry.overflow,overflow_diagnostics:geometry});
    check('390px report layout fits viewport',geometry.overflow<=1,geometry.overflow);
    check('No browser page errors',evidence.page_errors.length===0,evidence.page_errors);
    check('No UI attempted a mutation',evidence.blocked_requests.filter(r=>!['GET','HEAD','OPTIONS'].includes(r.method)).length===0,evidence.blocked_requests);
    await screenshot(page,'narrow-report');
    await page.screenshot({path:path.join(OUT,'narrow-viewport.png')});
    evidence.artifacts.push('narrow-viewport.png');
    evidence.status=evidence.checks.every(c=>c.passed)?'diagnostic-recorded':'diagnostic-failed';
    evidence.acceptance_complete=false;
    evidence.failed_checks=evidence.checks.filter(c=>!c.passed).map(c=>c.name);
    if(evidence.failed_checks.length) process.exitCode=1;
  } finally { await context.close(); await browser.close(); }
}
async function getJson(request, suffix) {
  const response = await request.get(BASE + suffix, {timeout:60000, maxRedirects:0});
  if (!response.ok()) throw new Error('GET ' + suffix + ' returned HTTP ' + response.status());
  return response.json();
}
function verifyPatterns(data, attempts) {
  const source = new Map(attempts.map((a,i) => [RUN + ':' + i, a]));
  const columnChecks = [];
  for (const [scope, columns] of [['all', data.setups || []], ...(data.domains || []).map(d => [d.id, d.setups || []])]) {
    for (const c of columns) for (const mode of ['behavior','checks']) {
      const slices = c[mode] || [];
      const refs = slices.flatMap(s => s.attempts || []);
      const keys = refs.map(r => r.key);
      columnChecks.push({scope, setup:c.id, mode, total:c.total,
        count:slices.reduce((n,s) => n + s.count, 0), percent:slices.reduce((n,s) => n + (s.percent || 0), 0),
        distinct:new Set(keys).size === keys.length,
        exact:refs.every(r => { const a=source.get(r.key); return a && r.run===RUN && r.task===a.task && r.model===a.model; })});
    }
  }
  check('Every pattern slice has the declared denominator, exact unique source references, and percentages totaling 100',
    columnChecks.length > 0 && columnChecks.every(c => c.count===c.total && c.percent===(c.total ? 100 : 0) && c.distinct && c.exact), columnChecks);
  check('Setup pattern denominators cover all 106 recorded attempts', (data.setups || []).reduce((n,c) => n+c.total, 0) === EXPECTED);
  check('Behavior and checker bases are explicitly distinct', Boolean(data.behavior_basis && data.checks_basis && data.behavior_basis!==data.checks_basis));
}
async function main() {
  if (!username || !password) throw new Error('STUDIO_AUTH_USER and STUDIO_AUTH_PASSWORD must be set; no credentials were read from files.');
  if (!playwright) throw new Error('Playwright is unavailable; set PLAYWRIGHT_MODULE to the installed module.');
  fs.mkdirSync(OUT, {recursive:true});
  const credentials = {username, password, origin:BASE};
  const request = await playwright.request.newContext({httpCredentials:{...credentials, send:'always'}});
  let browser;
  try {
    if (diagnosticOnly) return await diagnoseNarrow(credentials);
    if (!surfaces.length) throw new Error('REPORT_SURFACES must select desktop, narrow, or dark.');
    const job = await getJson(request, '/api/jobs/' + RUN);
    const report = await getJson(request, '/api/reports/run/' + RUN + '?audience=engine-team');
    const diagnostic = await getJson(request, '/api/jobs/' + RUN + '/diagnostics');
    const attempts = diagnostic.attempts || [];
    const authored = report.authored;
    const available = ['authored','report_work','patterns'].filter(k => Object.hasOwn(report,k));
    const deployment = available.length===3 ? 'report-authoring' : 'legacy-or-partial';
    const stage = report.report_work?.stage || 'unavailable';
    evidence.deployment = deployment;
    evidence.report = {title:report.title, status:report.status, fields:available, work_stage:stage,
      work_reason:report.report_work?.reason, authored_status:authored?.status || null,
      revision:authored?.revision, review_verdict:authored?.review?.verdict,
      draft_sha256:authored?.draft_sha256, evidence_sha256:authored?.evidence_sha256,
      result_count:(job.results || []).length, diagnostic_count:attempts.length,
      report_attempt_count:report.failures?.attempts?.length, authored_count:authored?.attempts?.length || 0};
    check('Exact requested run is loaded', job.id===RUN && report.run===RUN);
    check('All 106 recorded result rows are retained', (job.results || []).length===EXPECTED, (job.results || []).length);
    check('Canonical diagnostics covers 106 attempts', attempts.length===EXPECTED, attempts.length);
    check('Report evidence covers 106 attempts', report.failures?.attempts?.length===EXPECTED, report.failures?.attempts?.length);
    if (report.patterns) verifyPatterns(report.patterns, attempts);
    if (strict) check('New report contract is deployed', deployment==='report-authoring', available);
    if (authored) {
      const rows = authored.attempts || [];
      const strings = ['explanation','expected','observed','mechanism','alternatives','missing_evidence'];
      const byIndex = new Map(rows.map(a=>[a.index,a]));
      check('Publication has complete analysis for all 106 unique original attempts', rows.length===EXPECTED && byIndex.size===EXPECTED && attempts.every((a,i)=>byIndex.has(i)));
      const failures = rows.flatMap(a => {
        const source = attempts[a.index];
        const allowed = new Set(source?.event_ids || []);
        const reasons=[];
        if (!source || source.task!==a.task || source.model!==a.model) reasons.push('source identity');
        if (strings.some(k=>typeof a[k]!=='string' || !a[k].trim())) reasons.push('incomplete prose');
        if (!['limited','moderate','strong'].includes(a.confidence)) reasons.push('confidence');
        if (!Array.isArray(a.event_ids) || a.event_ids.some(id=>!Number.isInteger(id) || !allowed.has(id))) reasons.push('citation outside this attempt');
        if (!a.event_ids?.length && !a.missing_evidence?.trim()) reasons.push('uncited without limitation');
        return reasons.length ? [{index:a.index,reasons}] : [];
      });
      check('Every authored attempt has complete prose and citations to its exact canonical attempt', failures.length===0, failures);
      const allEvents = new Set(attempts.flatMap(a=>a.event_ids || []));
      check('Every finding cites retained source events', Boolean(authored.findings?.length) && authored.findings.every(f=>f.event_ids?.length && f.event_ids.every(id=>allEvents.has(id))));
      check('Publication has the complete report narrative', ['summary','what_went_right','what_went_wrong','why','next_experiment','limitations'].every(k=>typeof authored[k]==='string' && authored[k].trim()));
      check('Publication is completed and separately approved', authored.status==='completed' && authored.review?.verdict==='accept', {status:authored.status,review:authored.review?.verdict});
      check('Publication retains draft and evidence fingerprints', /^[a-f0-9]{64}$/.test(authored.draft_sha256 || '') && /^[a-f0-9]{64}$/.test(authored.evidence_sha256 || ''));
    } else if (strict) check('Genesis has published the report', false, {stage});

    browser = await playwright.chromium.launch({channel:process.env.BROWSER_CHANNEL || 'chrome'});
    for (const [name,width,theme] of surfaces) {
      const context = await browser.newContext({httpCredentials:credentials, viewport:{width,height:1000}, reducedMotion:'reduce', serviceWorkers:'block'});
      await context.addInitScript(t=>localStorage.setItem('ailabs-theme',t), theme);
      await context.route('**/*', async route => {
        const req=route.request(), url=new URL(req.url());
        if (url.origin!==BASE || !['GET','HEAD','OPTIONS'].includes(req.method())) {
          evidence.blocked_requests.push({method:req.method(),origin:url.origin,path:url.pathname});
          return route.abort('blockedbyclient');
        }
        await route.continue();
      });
      const page=await context.newPage();
      page.on('pageerror', error=>evidence.page_errors.push({surface:name,message:clean(error.message)}));
      const surface={name,width,theme};
      evidence.surfaces.push(surface);
      try {
        await page.goto(BASE + '/#run/' + RUN, {waitUntil:'domcontentloaded',timeout:60000});
        await page.locator('#result-count').filter({hasText:String(EXPECTED)}).waitFor({timeout:60000});
        surface.run_overflow=await page.evaluate(()=>Math.max(0,document.documentElement.scrollWidth-innerWidth));
        check(name + ': run view shows 106 recorded results', Number(await page.locator('#result-count').innerText())===EXPECTED);
        await screenshot(page, name+'-run');
        await page.goto(BASE + '/#report/' + RUN + '?audience=engine-team', {waitUntil:'domcontentloaded',timeout:60000});
        await page.locator('#report-article .report-head').waitFor({timeout:60000});
        surface.overflow_diagnostics=await overflowDetails(page);
        surface.report_overflow=surface.overflow_diagnostics.overflow;
        check(name + ': report layout fits viewport', surface.report_overflow<=1, surface.report_overflow);
        check(name + ': run layout fits viewport', surface.run_overflow<=1, surface.run_overflow);
        if (authored) {
          check(name + ': opening uses the real publication summary', (await page.locator('#report-article .verdict').innerText()).trim()===authored.summary.trim());
          check(name + ': every authored attempt is rendered', await page.locator('.report-attempt').count()===EXPECTED);
          check(name + ': limitations appear in full analysis', (await page.locator('#report-analysis').innerText()).includes(authored.limitations));
          surface.authored_attempts=await page.locator('.report-attempt').count();
        }
        if (report.patterns) {
          await page.locator('.pattern-slice[role=button]').first().focus();
          await page.keyboard.press('Enter');
          await page.locator('.pattern-detail .pattern-attempts li').first().waitFor();
          check(name + ': keyboard opens exact pattern attempts', await page.locator('.pattern-detail .pattern-attempts li').count()>0);
          await page.locator('.pattern-control select').selectOption('checks');
          await page.locator('.pattern-counts summary').click();
          await page.locator('[data-pattern-column]').first().click();
          check(name + ': checker slice shows recorded termination', (await page.locator('.pattern-detail').innerText()).includes('Termination:'));
          await page.locator('.pattern-control select').selectOption('behavior');
          await screenshot(page, name+'-patterns', page.locator('.report-patterns'));
        }
        await page.evaluate(()=>window.scrollTo(0,0));
        await screenshot(page, name+'-report');
        if (authored && name==='desktop') {
          const citation=authored.attempts.find(a=>a.event_ids?.length);
          if (citation) {
            const row=page.locator('#report-attempt-'+citation.index);
            await row.locator('summary').click();
            check('Detailed attempt reveals alternatives and missing evidence', (await row.innerText()).includes(citation.alternatives) && (await row.innerText()).includes(citation.missing_evidence));
            await screenshot(page, 'desktop-attempt', row);
            const event=citation.event_ids[0];
            await row.locator('[data-evidence-event="'+event+'"]').click();
            try {
              await page.waitForFunction(id=>{
                const trace=document.querySelector('#trace-detail');
                const dialog=document.querySelector('#evidence-dialog');
                return (trace && trace.textContent.includes('Event '+id+' ·')) || (dialog?.open && dialog.textContent.includes('Raw record #'+id));
              }, event, {timeout:20000});
              check('A publication citation opens its exact recorded event in the real UI', true, {index:citation.index,event_id:event});
            } catch {
              check('A publication citation opens its exact recorded event in the real UI', false, {index:citation.index,event_id:event});
            }
            await screenshot(page, 'desktop-citation');
          }
        }
      } catch (error) {
        check(name+': browser verification completed', false, clean(error.message));
        await screenshot(page,name+'-failure').catch(()=>{});
      } finally { await context.close(); }
    }
    check('No browser page errors', evidence.page_errors.length===0, evidence.page_errors);
    check('No UI attempted a mutation', evidence.blocked_requests.filter(r=>!['GET','HEAD','OPTIONS'].includes(r.method)).length===0, evidence.blocked_requests);
    const failed=evidence.checks.filter(c=>!c.passed);
    evidence.status=failed.length ? 'failed' : authored ? 'published-verified' : deployment==='legacy-or-partial' ? 'baseline-recorded' : 'unpublished-recorded';
    evidence.acceptance_complete=evidence.status==='published-verified';
    evidence.failed_checks=failed.map(c=>c.name);
    if (failed.length) process.exitCode=1;
  } finally {
    if (browser) await browser.close();
    await request.dispose();
  }
}
main().catch(error=>{
  evidence.status='failed';
  evidence.error=clean(error.message);
  process.exitCode=1;
}).finally(()=>{
  save();
  console.log(JSON.stringify({status:evidence.status,acceptance_complete:evidence.acceptance_complete || false,
    deployment:evidence.deployment,work_stage:evidence.report?.work_stage,authored_count:evidence.report?.authored_count,
    checks:evidence.checks.length,failed_checks:evidence.failed_checks,error:evidence.error,output:OUT}));
});
