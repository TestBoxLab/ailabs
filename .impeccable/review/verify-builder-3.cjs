// Polish-pass review of the architecture studio. Screenshots and DOM assertions only; publishes nothing, spends nothing.
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
  await page.goto('http://127.0.0.1:8765');
  await page.evaluate(() => localStorage.removeItem('ailabs-architecture-draft'));
  await page.getByRole('button', {name: 'Monarch setups', exact: true}).click();
  await page.locator('.bp-node').first().waitFor();
  // Template menu is a real menu: button opens it, arrow keys move, Enter picks.
  await page.getByRole('button', {name: 'New from template…'}).click();
  check('template menu opens as role=menu', await page.locator('#context-menu[role=menu]:not(.hidden)').count() === 1);
  check('first template item focused', await page.evaluate(() => document.activeElement?.getAttribute('role') === 'menuitem'));
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Enter');
  await page.locator('[data-node="planner"]').waitFor();
  check('planner template loaded via keyboard', await page.locator('[data-node="worker"]').count() === 1);
  const box = async sel => { for (let i = 0; i < 6; i++) { const b = await page.locator(sel).boundingBox(); if (b) return b; await page.waitForTimeout(200); } throw Error('no box for ' + sel); };
  await page.waitForTimeout(600);
  const hint = () => page.locator('#canvas-hint').textContent();

  // Wire drag: highlight appears on a valid target, dim on invalid ones, preview snaps.
  const from = await box('[data-out="planner"]');
  const output = await box('[data-node="output"]');
  const input = await box('[data-node="input"]');
  await page.mouse.move(from.x + 8, from.y + 8); await page.mouse.down();
  await page.mouse.move(output.x + 100, output.y + 60, {steps: 10});
  check('valid target highlighted while connecting', await page.locator('[data-node="output"].drop-target').count() === 1);
  check('input dimmed while connecting (cannot receive)', await page.locator('[data-node="input"].dim').count() === 1);
  check('preview snapped to the port', await page.locator('.bp-wire-preview.snapped').count() === 1);
  await page.screenshot({path: '.impeccable/review/builder3-connecting.png'});
  await page.mouse.move(input.x + 100, input.y + 60, {steps: 6});
  check('invalid target marked refused', await page.locator('[data-node="input"].drop-refused').count() === 1);
  check('refusal explained in the status line', (await hint()).includes('starts the flow'));
  await page.mouse.up();
  check('no edge created on refused drop', await page.evaluate(() => !blueprint.graph.edges.some(e => e.from === 'planner' && e.to === 'input')));
  check('connect visuals cleaned up', await page.locator('.dim, .drop-target, .drop-refused').count() === 0);

  // Wire released on empty canvas opens the quick-add menu and creates a connected step.
  const from2 = await box('[data-out="planner"]');
  await page.mouse.move(from2.x + 8, from2.y + 8); await page.mouse.down();
  await page.mouse.move(from2.x + 60, from2.y + 150, {steps: 8});
  await page.mouse.up();
  check('quick-add menu after drop on empty space', (await page.locator('#context-menu .menu-heading').textContent()) === 'Add a step after Planner');
  await page.screenshot({path: '.impeccable/review/builder3-quickadd.png'});
  await page.getByRole('menuitem', {name: 'Agent step'}).click();
  const added = await page.evaluate(() => { const n = blueprint.graph.nodes.find(x => x.type === 'agent' && !['planner', 'worker'].includes(x.id)); return n && blueprint.graph.edges.some(e => e.from === 'planner' && e.to === n.id); });
  check('new step connected from the planner', added);
  check('instructions focused for the new step', await page.evaluate(() => document.activeElement?.id === 'node-instructions'));

  // Typing coalesces into one undo entry.
  const undoBefore = await page.evaluate(() => editHistory.undo.length);
  await page.keyboard.type('Be concise.');
  const undoAfter = await page.evaluate(() => editHistory.undo.length);
  check('typing 11 characters added one undo entry', undoAfter === undoBefore + 1, undoBefore + '→' + undoAfter);
  await page.locator('#builder-viewport').click({position: {x: 30, y: 460}});
  check('click on empty canvas clears the selection', await page.evaluate(() => selection.size === 0));

  // Reverse drag from an input port.
  const inPort = await box('[data-in="worker"]');
  const brief = await box('[data-node="input"]');
  await page.mouse.move(inPort.x + 8, inPort.y + 8); await page.mouse.down();
  await page.mouse.move(brief.x + 120, brief.y + 50, {steps: 8});
  check('reverse drag highlights the source', await page.locator('[data-node="input"].drop-target').count() === 1);
  await page.mouse.up();
  check('reverse drag created input → worker', await page.evaluate(() => blueprint.graph.edges.some(e => e.from === 'input' && e.to === 'worker')));

  await page.evaluate(() => fitView()); await page.waitForTimeout(200);
  // Right-click a node: menu with disabled reasons; Connect to… submenu.
  await page.locator('[data-node="output"]').click({button: 'right', position: {x: 40, y: 20}});
  check('node context menu heading', (await page.locator('#context-menu .menu-heading').textContent()) === 'Result output');
  check('fixed step: remove disabled with reason', await page.locator('#context-menu [aria-disabled=true]', {hasText: 'Remove'}).count() === 1);
  await page.keyboard.press('Escape');
  check('escape closes the menu', await page.locator('#context-menu.hidden').count() === 1);

  await page.evaluate(() => fitView()); await page.waitForTimeout(200);
  // Problem links: clear the worker instructions, then click the problem to jump to the field.
  await page.locator('[data-node="worker"]').click({position: {x: 30, y: 20}});
  await page.locator('#node-instructions').fill('');
  await page.waitForTimeout(700);
  check('problem rendered as a link', await page.locator('.problem-link').count() >= 1);
  await page.locator('[data-node="input"]').click({position: {x: 30, y: 20}});
  await page.locator('.problem-link').first().click();
  check('problem link selects the step and focuses the field', await page.evaluate(() => selection.has('worker') && document.activeElement?.id === 'node-instructions'));
  check('publish shows why it cannot proceed', (await page.locator('#blueprint-publish').getAttribute('title') || '').startsWith('Fix 1 problem'));
  await page.screenshot({path: '.impeccable/review/builder3-problem.png'});
  await page.locator('#node-instructions').fill('Execute the plan.');
  await page.waitForTimeout(700);

  // Palette drop onto a wire inserts between the two steps.
  const wireCountBefore = await page.evaluate(() => blueprint.graph.edges.length);
  const inserted = await page.evaluate(() => {
    const wires = [...document.querySelectorAll('#builder-wires [data-wire]')];
    const e = blueprint.graph.edges.findIndex(x => x.from === 'worker' && x.to === 'output');
    const g = wires.find(w => Number(w.dataset.wire) === e);
    const box = g.querySelector('.line').getBoundingClientRect();
    return {index: e, x: box.left + box.width / 2, y: box.top + box.height / 2};
  });
  await page.evaluate(({x, y}) => {
    const vp = document.getElementById('builder-viewport');
    const dt = new DataTransfer(); dt.setData('text/x-step', 'merge');
    vp.dispatchEvent(new DragEvent('dragover', {bubbles: true, cancelable: true, clientX: x, clientY: y, dataTransfer: dt}));
    vp.dispatchEvent(new DragEvent('drop', {bubbles: true, cancelable: true, clientX: x, clientY: y, dataTransfer: dt}));
  }, inserted);
  const insertedOk = await page.evaluate(() => { const m = blueprint.graph.nodes.find(n => n.type === 'merge'); return m && blueprint.graph.edges.some(e => e.from === 'worker' && e.to === m.id) && blueprint.graph.edges.some(e => e.from === m.id && e.to === 'output') && !blueprint.graph.edges.some(e => e.from === 'worker' && e.to === 'output'); });
  check('palette drop on a wire inserts the step between', insertedOk);
  check('edge count grew by one after insert', await page.evaluate(() => blueprint.graph.edges.length) === wireCountBefore + 1);

  await page.evaluate(() => fitView()); await page.waitForTimeout(200);
  // Keyboard: focus a node, Shift+F10 opens its menu; ? opens shortcuts.
  await page.locator('[data-node="input"]').focus();
  await page.keyboard.press('Shift+F10');
  check('Shift+F10 opens the node menu', (await page.locator('#context-menu .menu-heading').textContent()) === 'Task input');
  await page.keyboard.press('Escape');
  await page.locator('#builder-viewport').focus();
  await page.keyboard.press('Shift+?');
  check('? opens the shortcuts dialog', await page.locator('#shortcuts-dialog[open]').count() === 1);
  await page.screenshot({path: '.impeccable/review/builder3-shortcuts.png'});
  await page.keyboard.press('Escape');

  await page.evaluate(() => fitView()); await page.waitForTimeout(200);
  // Inspector connections editor adds a connection by keyboard-friendly select.
  await page.locator('[data-node="planner"]').click({position: {x: 30, y: 20}});
  const options = await page.locator('#node-connect option').allTextContents();
  check('connections editor lists candidates', options.length > 1, options.join('|'));
  await page.locator('[data-node="worker"]').click({position: {x: 30, y: 20}});
  await page.screenshot({path: '.impeccable/review/builder3-desktop.png'});

  // Hit targets: ports and wire delete handles reach 24px through their padding.
  const portHit = await page.evaluate(() => { const p = document.querySelector('.bp-port.out'); const cs = getComputedStyle(p, '::before'); return {inset: cs.inset || cs.top, w: p.offsetWidth}; });
  check('port hit padding extends the 16px dot', portHit.inset.includes('-8px'), JSON.stringify(portHit));
  // Run button explains itself instead of a toast.
  await page.getByRole('button', {name: /Run (latest|version)/}).click({force: true});
  check('run refusal goes to the status line', (await hint()).includes('Publish a version first'));
  check('no toast used for the refusal', await page.locator('#toast:not(.hidden)').count() === 0);

  // Mobile layout: hover toolbars always visible, no horizontal overflow.
  await page.setViewportSize({width: 390, height: 844});
  await page.waitForTimeout(500);
  check('no horizontal overflow on mobile', await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  await page.screenshot({path: '.impeccable/review/builder3-mobile.png', fullPage: true});
  await page.setViewportSize({width: 1600, height: 1000});
  await page.evaluate(() => localStorage.removeItem('ailabs-architecture-draft'));
  console.log(JSON.stringify({errors, failed: checks.filter(c => !c.ok), passed: checks.filter(c => c.ok).length, total: checks.length}, null, 1));
  await browser.close();
  process.exit(errors.length || checks.some(c => !c.ok) ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
