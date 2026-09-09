// Product graph module review. Two bounded live preparations (max $0.30 each) and one bounded run (max $2.00 reserved,
// expected under $0.10 actual) on the real providers; everything else is DOM assertion. Publishes nothing outside the local studio.
const {chromium} = require('C:/Users/Lucas Wakigawa/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const checks = [];
function check(name, ok, detail) { checks.push({name, ok: !!ok, detail}); }
(async () => {
  const browser = await chromium.launch({headless: true, channel: 'msedge'});
  const page = await browser.newPage({viewport: {width: 1600, height: 1000}});
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
  page.on('dialog', d => d.accept());
  const text = sel => page.locator(sel).textContent();
  await page.goto('http://127.0.0.1:8765');
  await page.evaluate(() => localStorage.removeItem('ailabs-architecture-draft'));
  await page.getByRole('button', {name: 'Monarch setups', exact: true}).click();
  await page.locator('.bp-node').first().waitFor();
  await page.waitForTimeout(500);

  // Product graphs tab
  await page.getByRole('tab', {name: 'Product graphs'}).click();
  check('graphs panel shown, architecture panel hidden', await page.evaluate(() => !document.getElementById('pg-panel').classList.contains('hidden') && document.getElementById('arch-panel').classList.contains('hidden')));
  // Prepared versions cost money: when the graph already holds two usable versions, keep them and skip the preparation steps.
  const ready = await page.evaluate(() => { const g = productGraphs.find(x => x.name === "Catalog basics"); return g && g.versions.filter(v => ["complete", "incomplete"].includes(v.status)).length >= 2 ? g.id : null; });
  if (ready) { await page.locator("#pg-library").selectOption(ready); await page.waitForTimeout(400); check("reused the prepared graph (no new spend)", true); const plan3 = await text("#pg-plan"); check("nothing new after v2", plan3.startsWith("Nothing new to research"), plan3); await page.screenshot({path: ".impeccable/review/pg-version2.png", fullPage: true}); }
  else {
  // Reuse the graph whose version 1 failed on the budget floor, so the retry path is exercised live.
    const existing = (await page.locator('#pg-library option').allTextContents()).find(t => t.startsWith('Catalog basics'));
    if (existing) { await page.locator('#pg-library').selectOption({label: existing}); await page.waitForTimeout(400); }
    else {
      await page.getByRole('button', {name: 'New product graph'}).click();
      await page.locator('#pg-name').fill('Catalog basics');
      check('default field seeded', await page.locator('[data-pg-field="path"]').count() === 1);
      await page.locator('#pg-add-field').click();
      await page.locator('[data-pg-field="path"]').last().fill('product.write_risk');
      await page.locator('[data-pg-field="description"]').last().fill('Which write actions are hard to undo and what to verify before calling them.');
      await page.locator('#pg-save').click();
      await page.locator('#pg-state', {hasText: 'Draft saved'}).waitFor();
    }
    const plan1 = await text('#pg-plan');
    check('plan names version 1 and both fields', plan1.startsWith('Version 1:') && plan1.includes('2 fields') && plan1.includes('product.write_risk'), plan1);
    check('new fields marked new', await page.locator('.pg-row .bp-chip.new').count() === 2);
    check('library lists the saved graph', (await page.locator('#pg-library option').allTextContents()).some(t => t.startsWith('Catalog basics')));
    await page.screenshot({path: '.impeccable/review/pg-draft.png'});
  
    // Live preparation of version 1
    await page.locator('#pg-prepare').click();
    check('prepare dialog names version 1', (await text('#prepare-title')).startsWith('Prepare version 1'));
    await page.locator('#prepare-budget').fill('0.30');
    check('dialog refuses a budget under the reservation floor', (await text('#prepare-error')).startsWith('Set at least $'), await text('#prepare-error'));
    await page.locator('#prepare-budget').fill('2.00');
    await page.locator('#prepare-start').click();
    await page.waitForSelector('#prepare-dialog:not([open])', {state: 'attached', timeout: 300000});
    await page.locator('.pg-version[data-pg-version="1"]').waitFor({timeout: 10000});
    const v1 = await text('.pg-version[data-pg-version="1"]');
    check('version 1 prepared (complete or incomplete)', /Complete|Incomplete/.test(v1), v1.slice(0, 200));
    check('version 1 lists both fields as researched', (v1.match(/researched in v1/g) || []).length === 2);
    const rows = await page.locator('.pg-version[data-pg-version="1"] .pg-records tbody tr').count();
    check('records table shows the corpus products', rows >= 2, String(rows));
    check('carried chips after v1', await page.locator('.pg-row .bp-chip.carried').count() === 2);
    await page.screenshot({path: '.impeccable/review/pg-version1.png', fullPage: true});
  
    // Extend: a third field, prepared as version 2
    await page.locator('#pg-add-field').click();
    await page.locator('[data-pg-field="path"]').last().fill('product.record_types');
    await page.locator('[data-pg-field="description"]').last().fill('The main record types this product manages, as a short list.');
    const plan2 = await text('#pg-plan');
    check('plan for version 2 extends v1 and carries 2', plan2.startsWith('Version 2 extends v1') && plan2.includes('2 carried'), plan2);
    await page.locator('#pg-prepare').click();
    await page.locator('#prepare-budget').fill('2.00');
    await page.locator('#prepare-start').click();
    await page.waitForSelector('#prepare-dialog:not([open])', {state: 'attached', timeout: 300000});
    await page.locator('.pg-version[data-pg-version="2"]').waitFor({timeout: 10000});
    const v2 = await text('.pg-version[data-pg-version="2"]');
    check('version 2 extends v1', v2.includes('extends v1'));
    check('version 2 carried two fields and researched one', (v2.match(/carried from v1/g) || []).length === 2 && (v2.match(/researched in v2/g) || []).length === 1);
    const plan3 = await text('#pg-plan');
    check('nothing new after v2', plan3.startsWith('Nothing new to research'), plan3);
    check('prepare explains itself when nothing is new', await page.locator('#pg-prepare.is-disabled').count() === 1);
    await page.screenshot({path: '.impeccable/review/pg-version2.png', fullPage: true});
  }
  const graphId = await page.evaluate(() => pg.id);

  // Architecture: template references the latest usable version (reused when already published, to avoid duplicate versions)
  await page.getByRole('tab', {name: 'Architectures'}).click();
  const published = await page.evaluate(() => blueprints.find(b => b.name === 'Informed worker' && b.versions?.length)?.id || null);
  if (published) { await page.locator('#blueprint-library').selectOption(published); }
  else { await page.getByRole('button', {name: 'New from template…'}).click(); await page.getByRole('menuitem', {name: 'Product graph, then act'}).click(); }
  await page.locator('[data-node="knowledge"]').waitFor();
  await page.waitForTimeout(800);
  const card = await text('[data-node="knowledge"]');
  check('product graph step names graph and version', card.includes('Catalog basics · v2') && card.includes('3 fields'), card.slice(0, 160));
  check('product graph step says what it delivers', card.includes('Delivers product.summary, product.write_risk, product.record_types'), card.slice(0, 300));
  await page.locator('[data-node="knowledge"]').click({position: {x: 30, y: 20}});
  check('inspector selects graph and version', await page.evaluate(g => document.getElementById('node-graph').value === g && document.getElementById('node-graph-version').value === '2', graphId));
  await page.screenshot({path: '.impeccable/review/pg-node.png'});
  check('publishable', (await text('#builder-problems')).startsWith('Publishable'));
  if (!published) { await page.locator('#blueprint-name').fill('Informed worker'); await page.locator('#blueprint-publish').click(); await page.locator('#builder-state', {hasText: 'published'}).waitFor({timeout: 20000}); }
  const versionRow = await text('.version-row.latest');
  check('published version binds the product graph', versionRow.includes('Catalog basics v2') && versionRow.includes('Ready to run'), versionRow.slice(0, 200));
  check('run button enabled', await page.locator('#builder-run.is-disabled').count() === 0);

  // Live run: one task, the published version only (a completed run of it is reused rather than paid for again)
  const prior = await page.evaluate(() => (state.jobs || []).find(j => j.title === 'Product graph e2e' && j.status === 'completed')?.id || null);
  if (prior) { await page.locator('#close-setup').click(); await page.evaluate(id => openJob(id), prior); await page.waitForTimeout(1500); check('reused the completed run (no new spend)', true); }
  else {
    await page.locator('#builder-run').click();
    await page.locator('#launch-dialog[open]').waitFor();
    const preselected = await page.evaluate(() => [...document.querySelectorAll('#architecture-options input')].filter(i => i.checked).map(i => i.value));
    check('exactly the published version is selected', preselected.length === 1 && preselected[0].startsWith('blueprint.'), preselected.join(','));
    await page.locator('#run-title').fill('Product graph e2e');
    await page.locator('#run-budget').fill('2.00');
    await page.locator('#launch-button').click();
    await page.waitForSelector('#launch-dialog:not([open])', {state: 'attached', timeout: 20000});
  }
  for (let i = 0; i < 120; i++) { const s = await text('#job-status'); if (['completed', 'failed', 'cancelled', 'interrupted'].includes(s.trim())) break; await page.waitForTimeout(3000); }
  const status = (await text('#job-status')).trim();
  check('run finished', status === 'completed', status);
  await page.getByRole('tab', {name: 'Activity'}).click();
  await page.waitForTimeout(800);
  const lane = await text('#lanes');
  check('activity shows the product graph delivery step', /Delivered \d+ products × 3 fields from 'Catalog basics' v2 \(product\.summary, product\.write_risk, product\.record_types\) to Worker/.test(lane), lane.slice(0, 300));
  await page.screenshot({path: '.impeccable/review/pg-activity.png'});
  await page.getByRole('tab', {name: 'Results'}).click();
  await page.waitForTimeout(300);
  const result = await text('#result-rows');
  check('result row exists', result.includes('Informed worker'), result.slice(0, 200));
  await page.evaluate(() => localStorage.removeItem('ailabs-architecture-draft'));
  console.log(JSON.stringify({errors, failed: checks.filter(c => !c.ok), passed: checks.filter(c => c.ok).length, total: checks.length, result: result.replace(/\s+/g, ' ').slice(0, 300)}, null, 1));
  await browser.close();
  process.exit(errors.length || checks.some(c => !c.ok) ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
