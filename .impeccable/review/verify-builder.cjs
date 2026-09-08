// Visual review of the rebuilt architecture studio. Screenshots only; publishes nothing, spends nothing.
const {chromium} = require('C:/Users/Lucas Wakigawa/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async () => {
  const browser = await chromium.launch({headless: true, channel: 'msedge'});
  const page = await browser.newPage({viewport: {width: 1600, height: 1000}});
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto('http://127.0.0.1:8765');
  await page.getByRole('button', {name: 'Monarch setups', exact: true}).click();
  await page.locator('.bp-node').first().waitFor();
  await page.evaluate(() => localStorage.removeItem('ailabs-architecture-draft'));
  // Planner-then-worker template, worker selected so the inspector shows a runner picker.
  await page.getByRole('button', {name: 'New from template'}).click();
  await page.getByRole('button', {name: 'Planner then worker'}).click();
  await page.locator('[data-node="worker"]').click({position: {x: 30, y: 20}});
  await page.waitForTimeout(600);
  await page.screenshot({path: '.impeccable/review/builder-desktop.png', fullPage: false});
  // Drag-connect preview: start a connection from the planner and hover the output.
  const from = await page.locator('[data-out="planner"]').boundingBox();
  const to = await page.locator('[data-node="output"]').boundingBox();
  await page.mouse.move(from.x + 8, from.y + 8); await page.mouse.down();
  await page.mouse.move(to.x + 100, to.y + 60, {steps: 12});
  await page.screenshot({path: '.impeccable/review/builder-connecting.png', fullPage: false});
  await page.mouse.up();
  const edges = await page.evaluate(() => blueprint.graph.edges.map(e => e.from + '>' + e.to));
  // Versions of the published single-worker architecture.
  page.on('dialog', d => d.accept());
  await page.locator('#blueprint-library').selectOption({index: 1}).catch(() => {});
  await page.waitForTimeout(800);
  await page.screenshot({path: '.impeccable/review/builder-versions.png', fullPage: true});
  // Launcher with grouped runners and version readiness.
  await page.getByRole('button', {name: 'Run latest version'}).click().catch(() => {});
  await page.waitForTimeout(1500);
  await page.screenshot({path: '.impeccable/review/builder-launch.png', fullPage: false});
  await page.keyboard.press('Escape');
  // Activity view of the most recent run.
  await page.getByRole('button', {name: 'Back to runs'}).click();
  await page.getByRole('tab', {name: 'Activity'}).click();
  await page.waitForTimeout(800);
  await page.screenshot({path: '.impeccable/review/builder-activity.png', fullPage: false});
  await page.getByRole('button', {name: 'Monarch setups', exact: true}).click();
  await page.setViewportSize({width: 390, height: 844});
  await page.waitForTimeout(600);
  await page.screenshot({path: '.impeccable/review/builder-mobile.png', fullPage: true});
  console.log(JSON.stringify({errors, edges, overflow: await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)}));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
