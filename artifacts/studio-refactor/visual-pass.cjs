const {chromium}=require('C:/Users/Lucas Wakigawa/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:"chrome"});const page=await browser.newPage({viewport:{width:1440,height:1050},deviceScaleFactor:1});
 const errors=[],checks=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/**',route=>route.request().method()==='POST'&&!route.request().url().endsWith('/api/blueprints/validate')?route.abort():route.continue());
 const snap=async(name)=>{await page.screenshot({path:'artifacts/studio-refactor/'+name+'.png',fullPage:true});checks.push({name,overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)});};
 await page.goto('http://127.0.0.1:8766');await page.waitForSelector('#history-rows [data-expand-run]');await snap('desktop-runs');
 await page.locator('[data-expand-run]').first().click();await snap('desktop-expanded');
 await page.locator('[data-open-run]').first().click();await page.waitForSelector('.diagnostic-attempt');await snap('desktop-diagnostics');
 await page.locator('.diagnostic-attempt').first().click();await snap('desktop-task-analysis');
 await page.locator('#theme-toggle').click();await snap('desktop-dark-analysis');
 await page.locator('#theme-toggle').click();await page.locator('#open-setup').click();await page.waitForSelector('.bp-node');await snap('desktop-architecture');
 await page.getByRole('tab',{name:'Product graphs',exact:true}).click();await page.locator('button[data-pg-view=review]').click();await page.waitForSelector('[data-pg-records]');await snap('desktop-graph-changes');
 await page.locator('[data-graph-log]').first().click();await page.waitForSelector('.research-log');await snap('desktop-graph-logs');
 await page.locator('#nav-leaderboard').click();await page.waitForSelector('#leaderboard-content table');await snap('desktop-leaderboard');
 await page.locator('#nav-runtime').click();await page.waitForSelector('#runtime-content table');await snap('desktop-runtime');
 await page.setViewportSize({width:390,height:844});await page.locator('#nav-runs').click();await snap('mobile-runs');
 await page.locator('#open-setup').click();await page.getByRole('tab',{name:'Product graphs',exact:true}).click();await page.locator('button[data-pg-view=review]').click();await snap('mobile-graph');
 await page.locator('#nav-runs').click();await page.locator('[data-open-run]').first().click();await page.waitForSelector('.diagnostic-attempt');await snap('mobile-diagnostics');
 fs.writeFileSync('artifacts/studio-refactor/visual-pass.json',JSON.stringify({errors,checks},null,2));console.log(JSON.stringify({errors,checks}));await browser.close();
})().catch(e=>{console.error(e);process.exit(1);});

