// Offline regression for the two measured production report overflows at 390px.
'use strict';
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const playwright=require(process.env.PLAYWRIGHT_MODULE || 'C:/Users/Lucas Wakigawa/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const ROOT=path.resolve(process.env.LOCAL_REPORT_ROOT || path.join(__dirname,'../../wb_studio/static'));
const OUT=path.resolve(__dirname,'../../.tmp/report-overflow',process.env.REPORT_EVIDENCE_TAG || 'primary');
const HTML=`<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="/vendor/radix-colors/radix-colors.css"><link rel="stylesheet" href="/tokens.css"><link rel="stylesheet" href="/ui.css"><link rel="stylesheet" href="/charts.css"><link rel="stylesheet" href="/report.css">
<style>body{margin:0;padding:16px}#nav-reports{display:none}.story-modes th{white-space:nowrap}</style></head><body><button id="nav-reports">Reports</button>
<article class="report" id="report-article"><section class="report-section" id="report-story"><h2>Observed behavior</h2><table class="table story-modes"><thead><tr><th>Outcome</th><th>Monarch with Claude Sonnet</th><th>Monarch with Gemini Pro</th></tr></thead><tbody><tr><th>Requested result missing</th><td>24 / 53</td><td>25 / 53</td></tr></tbody></table></section><section class="report-section" id="report-cost"><h2>Tokens by kind</h2></section></article>
<script>window.$=(s,r=document)=>r.querySelector(s);window.$$=(s,r=document)=>Array.from(r.querySelectorAll(s));window.esc=s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');</script><script src="/charts.js"></script><script src="/reports.js"></script>
<script>const fixture={run:'overflow-fixture',lab_setups:[],order:['m'],setups:{m:{id:'m',name:'Monarch with Gemini Pro',pass:{rate:0,low:0,high:0,passed:0},cost:{per_attempt:null,per_pass:null,total:null,unknown_attempts:1,tokens:{uncached:1000,cache_write:200,cached:300,output:400}},time:{median:null}}}};document.querySelector('#report-cost').append(costBlock(fixture));bindReportActions(document.querySelector('#report-article'),fixture);</script></body></html>`;
(async()=>{
  fs.mkdirSync(OUT,{recursive:true});
  const browser=await playwright.chromium.launch({channel:process.env.BROWSER_CHANNEL || 'chrome'});
  const errors=[];
  try {
    const context=await browser.newContext({viewport:{width:390,height:1000},reducedMotion:'reduce'});
    await context.route('**/*',async route=>{
      const url=new URL(route.request().url());
      if(url.origin!=='http://report-fixture.test') return route.abort();
      if(url.pathname==='/') return route.fulfill({contentType:'text/html',body:HTML});
      const filename=path.resolve(ROOT,'.'+decodeURIComponent(url.pathname));
      if(!filename.startsWith(ROOT+path.sep) || !fs.existsSync(filename)) return route.fulfill({status:404,body:''});
      const ext=path.extname(filename);
      await route.fulfill({contentType:({'.js':'text/javascript','.css':'text/css','.woff2':'font/woff2'})[ext] || 'application/octet-stream',body:fs.readFileSync(filename)});
    });
    const page=await context.newPage(); page.on('pageerror',e=>errors.push(e.message));
    await page.goto('http://report-fixture.test/');
    await page.waitForFunction(()=>document.querySelector('.waterfall')?.dataset.fitWidth);
    const table=await page.locator('.story-modes').evaluate(t=>({parent:t.parentElement.className,scroll:t.parentElement.scrollWidth,client:t.parentElement.clientWidth,overflow:getComputedStyle(t.parentElement).overflowX,rows:t.rows.length}));
    assert(table.parent.includes('table-scroll') && table.overflow==='auto','The retained story table must have a scroll container');
    assert(table.scroll>table.client,'Fixture exercises a genuinely wide table');
    assert.equal(table.rows,2,'All table rows remain available');
    const legend=page.locator('.report-token-legend');
    assert.deepEqual(await legend.locator('li').allTextContents(),['Uncached input','Cache writes','Cache reads','Output']);
    async function verifyWidth() {
      const value=await page.evaluate(()=>({overflow:Math.max(0,document.documentElement.scrollWidth-innerWidth),labels:Array.from(document.querySelectorAll('.report-token-legend li')).map(n=>{const r=n.getBoundingClientRect();return {left:r.left,right:r.right,font:parseFloat(getComputedStyle(n).fontSize)};}),svgLegend:getComputedStyle(document.querySelector('.waterfall .legend')).display}));
      assert.equal(value.overflow,0,'Report does not expand the viewport');
      assert(value.labels.every(r=>r.left>=0 && r.right<=390 && r.font>=12),'All legend labels remain readable within the narrow viewport');
      assert.equal(value.svgLegend,'none','Report uses one visible legend');
      return value;
    }
    const geometry=await verifyWidth();
    await page.setViewportSize({width:800,height:1000});
    await page.waitForFunction(()=>Number(document.querySelector('.waterfall')?.dataset.fitWidth)>358);
    await page.setViewportSize({width:390,height:1000});
    await page.waitForFunction(()=>Number(document.querySelector('.waterfall')?.dataset.fitWidth)<=358);
    await verifyWidth();
    assert.equal(await page.locator('.waterfall .legend text').count(),4,'Underlying SVG keeps all legend labels for standalone chart export');
    assert.equal(errors.length,0,errors.join('\n'));
    await page.screenshot({path:path.join(OUT,'narrow.png'),fullPage:true});
    const evidence={status:'passed',root:ROOT,width:390,geometry,table,errors,checks:['wide story table scrolls','table data retained','all four legend labels visible','zero viewport overflow','legend survives chart resize','underlying SVG legend retained']};
    fs.writeFileSync(path.join(OUT,'evidence.json'),JSON.stringify(evidence,null,2));
    console.log(JSON.stringify({status:'passed',output:OUT,checks:evidence.checks}));
    await context.close();
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
