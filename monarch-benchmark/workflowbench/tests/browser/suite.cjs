// Browser checks for the Studio. One command, one fixture server, both themes.
//
//   node tests/browser/suite.cjs            # run every check, write snapshots
//   node tests/browser/suite.cjs --only runs
//
// Needs Playwright (PLAYWRIGHT_MODULE points at its node_modules entry) and a
// Chrome channel. The fixture server is tests/browser/server.py; it serves a
// temporary workspace with scripted runs, so nothing here costs money.
'use strict';
const path = require('node:path');
const fs = require('node:fs');
const { spawn } = require('node:child_process');

const ROOT = path.resolve(__dirname, '..', '..');
const SNAPSHOTS = path.join(__dirname, 'snapshots');
const PORT = Number(process.env.BROWSER_PORT || 8766);
const BASE = `http://127.0.0.1:${PORT}`;
const only = (() => { const i = process.argv.indexOf('--only'); return i > 0 ? process.argv[i + 1] : null; })();

function loadPlaywright() {
  const candidates = [process.env.PLAYWRIGHT_MODULE, 'playwright',
    'C:/Users/Lucas Wakigawa/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'].filter(Boolean);
  for (const c of candidates) { try { return require(c); } catch { /* next */ } }
  throw new Error('Playwright not found. Set PLAYWRIGHT_MODULE to its node_modules path.');
}

async function portIsFree() {
  try { await fetch(BASE + '/api/state', { signal: AbortSignal.timeout(1500) }); return false; } catch { return true; }
}

function startServer() {
  const uv = process.platform === 'win32' ? 'uv.exe' : 'uv';
  const child = spawn(uv, ['run', 'python', 'tests/browser/server.py', '--port', String(PORT)], { cwd: ROOT, stdio: ['ignore', 'pipe', 'pipe'] });
  return new Promise((resolve, reject) => {
    let out = '';
    const timer = setTimeout(() => reject(new Error('fixture server did not start:\n' + out)), 120000);
    child.stdout.on('data', d => { out += d; if (out.includes('READY')) { clearTimeout(timer); resolve(child); } });
    child.stderr.on('data', d => { out += d; });
    child.on('exit', code => { clearTimeout(timer); reject(new Error('fixture server exited ' + code + '\n' + out)); });
  });
}

const checks = [];
const check = (name, fn) => checks.push({ name, fn });
const assert = (condition, message) => { if (!condition) throw new Error(message); };

let step = '';
const at = name => { step = name; };
async function page(browser, theme, url) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
  if (theme) await context.addInitScript(t => localStorage.setItem('ailabs-theme', t), theme);
  const p = await context.newPage();
  const errors = [];
  p.on('pageerror', e => errors.push(e.message));
  p.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  p.on('response', r => { if (r.status() >= 400 && r.url().includes('/api/')) errors.push('HTTP ' + r.status() + ' ' + r.url().replace(BASE, '')); });
  await p.goto(BASE + url);
  await p.waitForSelector('#connection[data-status=connected]');
  return { p, context, errors };
}

async function noOverflowNoErrors(p, errors, name) {
  assert(!(await p.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)), name + ': horizontal overflow');
  assert(errors.length === 0, name + ': page errors ' + errors.join(' | '));
}

async function snapshot(p, name) {
  fs.mkdirSync(SNAPSHOTS, { recursive: true });
  await p.screenshot({ path: path.join(SNAPSHOTS, name + '.png'), fullPage: true });
}

for (const theme of ['light', 'dark']) {
  for (const [name, hash, ready] of [
    ['runs', '#runs', '#history-rows [data-open-run]'],
    ['studio', '#studio', '#studio-library-rows'],
    ['genesis', '#genesis', '#genesis-panel:not(.hidden) #genesis-form'],
    ['budget', '#budget', '#budget-content'],
    ['leaderboard', '#leaderboard', '#reports-panel:not(.hidden)'],
    ['settings', '#runtime', '#runtime-panel:not(.hidden)'],
    ['launch', '#launch', '#launch-panel:not(.hidden)'],
  ]) {
    check(`${name} renders (${theme})`, async browser => {
      const { p, context, errors } = await page(browser, theme, '/' + hash);
      try {
        await p.waitForSelector(ready, { timeout: 15000 });
        assert((await p.evaluate(() => document.documentElement.classList.contains('dark'))) === (theme === 'dark'), 'theme class');
        await noOverflowNoErrors(p, errors, name);
        await snapshot(p, `${name}-${theme}`);
      } finally { await context.close(); }
    });
  }
}

check('run row opens the run; expander shows configuration; no ghost height after the side panel closes', async browser => {
  const { p, context, errors } = await page(browser, 'light', '/#runs');
  try {
    at('expand'); await p.waitForSelector('#history-rows [data-open-run]');
    await p.locator('[data-expand-run]').first().click();
    await p.waitForSelector('.history-expanded:not(.hidden)');
    assert((await p.locator('.history-expanded:not(.hidden)').innerText()).includes('Setups'), 'expansion shows setups');
    at('row click'); await p.locator('.history-row td').nth(2).click();
    await p.waitForSelector('.workspace:not(.hidden)');
    assert((await p.evaluate(() => location.hash.startsWith('#run/'))), 'route is #run/<id>');
    at('results tab'); await p.locator('[data-view=results]').click();
    await p.waitForSelector('.results-table [data-index]');
    await p.locator('.results-table [data-index]').first().click();
    await p.waitForSelector('#attempt-dialog[open]');
    assert(await p.evaluate(() => /^#run\/[^/]+\/[^/]+\/[^/]+$/.test(location.hash)), 'the route carries the open attempt: ' + await p.evaluate(() => location.hash));
    await snapshot(p, 'run-inspector-light');
    at('close inspector'); await p.locator('#close-inspector').click();
    await p.waitForFunction(() => !document.querySelector('#attempt-dialog').open);
    assert(await p.evaluate(() => /^#run\/[^/]+$/.test(location.hash)), 'closing the attempt returns the route to the run');
    const ghost = await p.evaluate(() => document.documentElement.scrollHeight - Math.max(innerHeight, document.querySelector('main').getBoundingClientRect().bottom + scrollY));
    assert(ghost < 48, 'ghost height below main: ' + ghost);
    await noOverflowNoErrors(p, errors, 'run');
  } finally { await context.close(); }
});

check('new run is a route: Escape cancels and returns to runs, draft survives', async browser => {
  const { p, context, errors } = await page(browser, 'light', '/#runs');
  try {
    await p.route('**/api/jobs', r => r.request().method() === 'POST' ? r.abort() : r.continue());
    at('open wizard'); await p.locator('#new-comparison').click();
    await p.waitForSelector('#launch-panel:not(.hidden)');
    assert(await p.evaluate(() => location.hash === '#launch'), 'hash is #launch');
    assert(await p.evaluate(() => document.title.includes('New run')), 'title says New run');
    assert(await p.evaluate(() => document.querySelector('#bare-warning').textContent === ''), 'no Bare warning while Bare is off');
    at('cancel'); await p.locator('#close-dialog').click();
    await p.waitForSelector('#runs-panel:not(.hidden)');
    assert(await p.evaluate(() => document.querySelector('#launch-panel').classList.contains('hidden')), 'wizard hidden after Cancel');
    await p.locator('#new-comparison').click();
    await p.waitForSelector('#launch-panel:not(.hidden)');
    at('escape stays'); await p.locator('#task-search').press('Escape');
    assert(await p.evaluate(() => !document.querySelector('#launch-panel').classList.contains('hidden')), 'Escape in a field does not throw the page away');
    assert((await p.locator('#launch-panel [data-launch-panel]:not(.hidden)').count()) === 3, 'the run is one page with three sections');
    assert((await p.locator('#launch-button').isVisible()), 'Start run is always in reach');
    assert(/#\d+$/.test(await p.locator('#run-title').inputValue()) || (await p.locator('#run-title').inputValue()) === '', 'the run name is numbered: ' + await p.locator('#run-title').inputValue());
    await p.locator('#close-dialog').click(); await p.waitForSelector('#runs-panel:not(.hidden)');
    await noOverflowNoErrors(p, errors, 'launch');
  } finally { await context.close(); }
});

check('theme toggle persists across reload', async browser => {
  const { p, context, errors } = await page(browser, null, '/#runs');
  try {
    await p.locator('#theme-toggle').click();
    assert(await p.evaluate(() => document.documentElement.classList.contains('dark')), 'dark after toggle');
    await p.reload();
    await p.waitForSelector('#connection[data-status=connected]');
    assert(await p.evaluate(() => document.documentElement.classList.contains('dark')), 'dark after reload');
    await noOverflowNoErrors(p, errors, 'theme');
  } finally { await context.close(); }
});

for (const theme of ['light', 'dark']) {
  check(`chart kit renders every chart (${theme})`, async browser => {
    const { p, context, errors } = await page(browser, theme, '/#runs');
    try {
      const counts = await p.evaluate(() => {
        const main = document.querySelector('main');
        main.innerHTML = '';
        const rows = [{ label: 'Informed worker / v1', sub: 'Claude Opus 4.8', value: .8, low: .49, high: .94, detail: '8 / 10 · 80%' }, { label: 'Bare Claude Opus 4.8', baseline: true, value: .6, low: .31, high: .83, detail: '6 / 10 · 60%' }, { label: 'GPT-5.6 Sol', value: .7, low: .4, high: .89, detail: '7 / 10 · 70%' }, { label: 'Kimi K3', value: null }];
        const figures = [
          Charts.dotWhisker({ title: 'Informed worker passes 8 of 10, Bare 6 of 10', source: 'run-1 · 10 tasks · frozen set abc123', rows, ceiling: 1, ceilingLabel: 'answer key' }),
          Charts.scatter({ title: 'Cost against pass rate', source: 'run-1', xLog: true, pareto: true, points: [{ label: 'Informed worker', x: .12, y: .8, low: .49, high: .94, link: 'a' }, { label: 'Informed worker · high', x: .4, y: .9, link: 'a' }, { label: 'Bare Opus', baseline: true, x: .09, y: .6 }, { label: 'GPT-5.6 Sol', x: .05, y: .7 }] }),
          Charts.bars({ title: 'Where it failed', source: 'run-1', rows: [{ label: 'Changes outside permitted scope', value: 3, denominator: 5, cls: 'fail' }, { label: 'Requirements unmet', value: 2, denominator: 5, cls: 'fail' }, { label: 'Infrastructure', value: 0, denominator: 5, cls: 'neutral' }] }),
          Charts.columns({ title: 'Tokens per model', groups: [{ label: 'claude-opus-4-8', values: [{ label: 'claude', value: 253000 }] }, { label: 'gemini-3.7-flash', values: [{ label: 'gemini', value: 143000 }] }] }),
          Charts.strips({ title: 'Seconds to finish', rows: [{ label: 'Informed worker', values: [4, 7, 12, 30, 8], median: 8 }, { label: 'Bare Opus', baseline: true, values: [3, 5, 9, 11], median: 7 }] }),
          Charts.waterfall({ title: 'Tokens by kind', rows: [{ label: 'Informed worker', parts: { uncached: 120000, cache_write: 20000, cached: 80000, output: 30000 } }, { label: 'Bare Opus', parts: { uncached: 90000, cache_write: 0, cached: 0, output: 20000 } }] }),
          Charts.trend({ title: 'Monarch over releases', series: [{ label: 'Monarch stock', family: 'monarch', points: [{ x: 'v1.2', y: .5, low: .3, high: .7 }, { x: 'v1.3', y: .6, low: .4, high: .78 }, { x: 'v1.4', y: .75, low: .55, high: .88 }] }] }),
          Charts.timeline({ title: 'Attempt timeline', lanes: [{ label: 'model', spans: [{ start: 0, end: 2.1, status: 'model', label: 'turn 1' }, { start: 4, end: 6.5, status: 'model', label: 'turn 2' }] }, { label: 'salesforce', spans: [{ start: 2.2, end: 3.9, label: 'GET contacts' }, { start: 6.6, end: 8, status: 'error', label: 'PATCH contact' }] }], end: 8.5 }),
          Charts.matrix({ tasks: [{ id: 't1', title: 'Update the contact city' }, { id: 't2', title: 'Close the opportunity' }], setups: [{ id: 'a', name: 'Informed worker' }, { id: 'b', name: 'Bare Opus', baseline: true }], cells: { 't1 a': { rate: 1, reps: [true] }, 't1 b': { rate: 0, reps: [false] }, 't2 a': { rate: .5, reps: [true, false] }, 't2 b': { rate: 1, reps: [true, true], infra: false } } }),
        ];
        for (const f of figures) main.appendChild(f);
        return figures.map(f => f.querySelectorAll('rect,line,path,text,td').length);
      });
      assert(counts.length === 9 && counts.every(n => n > 3), 'every chart drew marks: ' + counts.join(','));
      assert(!(await p.evaluate(() => document.querySelector('[style]'))), 'no inline styles from the kit');
      await noOverflowNoErrors(p, errors, 'charts');
      await snapshot(p, `charts-${theme}`);
    } finally { await context.close(); }
  });
}

check('reports are the front door: index, run report, round report, back', async browser => {
  const { p, context, errors } = await page(browser, 'light', '/');
  try {
    at('front door'); await p.waitForSelector('#reports-panel:not(.hidden) .round-card');
    assert(await p.evaluate(() => document.querySelector('#nav-reports').getAttribute('aria-current') === 'page'), 'Reports nav is current');
    at('open report'); await p.locator('[data-open-report]').first().click();
    await p.waitForSelector('#report-article .verdict');
    assert(await p.evaluate(() => location.hash.startsWith('#report/')), 'route is #report/<id>');
    const order = await p.evaluate(() => [...document.querySelectorAll('#report-article h2')].map(h => h.textContent));
    assert(order.join('|') === 'Verdict|Findings|What went right and wrong|Pass rate|By category|Where it failed|What it cost|What to keep in mind|How it was measured', 'section order: ' + order.join('|'));
    assert(await p.evaluate(() => document.querySelectorAll('#report-article figure.chart svg').length >= 2), 'figures drawn');
    assert(await p.evaluate(() => document.querySelector('#report-article .grade').textContent.trim().length > 0), 'grade shown');
    assert(await p.evaluate(() => !document.querySelector('[style]')), 'no inline styles');
    await snapshot(p, 'report-run-light');
    at('round report'); await p.goBack();
    await p.waitForSelector('#reports-panel:not(.hidden) .round-card');
    await p.locator('[data-open-round]').first().click();
    await p.waitForSelector('#report-article .standings');
    assert(await p.evaluate(() => location.hash.startsWith('#round/')), 'route is #round/<id>');
    await snapshot(p, 'report-round-light');
    at('reload restores'); await p.reload();
    await p.waitForSelector('#report-article .standings');
    await noOverflowNoErrors(p, errors, 'reports');
  } finally { await context.close(); }
});

check('report: a contents list, sections with an address, the page titled by the report, and no overflow on a phone', async browser => {
  const { p, context, errors } = await page(browser, 'light', '/#reports');
  try {
    await p.waitForSelector('.reports-table [data-open-report]');
    await p.locator('.reports-table [data-open-report]').first().click();
    await p.waitForSelector('#report-article .report-contents a');
    assert(!(await p.title()).endsWith('Report'), 'the page is titled by the report: ' + await p.title());
    at('section link'); await p.locator('.report-contents a[href$="/cost"]').click();
    await p.waitForFunction(() => location.hash.endsWith('/cost'));
    assert(await p.evaluate(() => !document.querySelector('#report-panel').classList.contains('hidden')), 'a section address stays on the report');
    const back = await p.locator('#report-article .section-link').first().getAttribute('href');
    assert(/^#report\/[^/]+\/verdict$/.test(back), 'section headings carry their address: ' + back);
    at('round'); await p.goto(BASE + '/#reports'); await p.waitForSelector('.reports-table [data-open-round]');
    await p.locator('[data-open-round]').first().click(); await p.waitForSelector('#report-article .standings');
    assert(!(await p.locator('#report-article').innerText()).includes('Not counted in the standings'), 'a pilot round does not list its own runs as excluded');
    assert((await p.locator('#report-article .standings thead th').first().innerText()) === 'Rank', 'standings carry a rank column');
    at('audience in the address'); await p.locator('#report-article [data-audience=internal]').click(); await p.waitForFunction(() => location.hash.includes('audience=internal'));
    assert((await p.locator('#report-article .internal-mark').count()) === 1, 'the internal view is banded');
    assert((await p.locator('#report-article figure.chart .chart-take a').count()) >= 2, 'a figure can be taken away as SVG or CSV');
    assert((await p.locator('#report-article .report-terms-fold').count()) === 1 && !(await p.locator('#report-article .report-terms-fold').getAttribute('open')), 'terms fold away');
    const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, reducedMotion: 'reduce' });
    const q = await phone.newPage(); await q.goto(BASE + '/#reports'); await q.waitForSelector('.reports-table [data-open-report]');
    await q.locator('.reports-table [data-open-report]').first().click(); await q.waitForSelector('#report-article figure.chart svg'); await q.waitForTimeout(400);
    const overflow = await q.evaluate(() => document.documentElement.scrollWidth - innerWidth);
    assert(overflow <= 1, 'run report overflows on a phone by ' + overflow + 'px');
    const fit = await q.evaluate(() => [...document.querySelectorAll('#report-article figure.chart')].map(f => f.dataset.fitWidth || 'none'));
    assert(fit.some(v => v !== 'none' && Number(v) < 720), 'charts are drawn again at the column width: ' + fit.join(','));
    await phone.close();
    await noOverflowNoErrors(p, errors, 'report');
  } finally { await context.close(); }
});

check('vocabulary: no approach, runner or purpose in visible text\', runner or purpose in visible text', async browser => {
  const { p, context } = await page(browser, 'light', '/#runs');
  try {
    const leaks = [];
    for (const hash of ['#runs', '#studio', '#budget', '#leaderboard', '#runtime', '#launch']) {
      await p.evaluate(h => { location.hash = h; }, hash);
      await p.waitForTimeout(400);
      const text = await p.locator('main').innerText();
      for (const word of [/\bapproach(es)?\b/i, /\brunner\b/i, /\bpurpose\b/i]) if (word.test(text)) leaks.push(hash + ' ' + word);
    }
    assert(leaks.length === 0, 'vocabulary leaks: ' + leaks.join(', '));
  } finally { await context.close(); }
});

check('live view: finished workstream blocks collapse to a verdict line, expand on demand, no motion under reduced motion', async browser => {
  const { p, context, errors } = await page(browser, 'light', '/#runs');
  try {
    at('open run'); await p.waitForSelector('#history-rows [data-open-run]');
    await p.locator('.history-row td').nth(2).click();
    await p.waitForSelector('.workspace:not(.hidden)');
    at('activity tab'); await p.locator('[data-view=live]').click();
    await p.waitForSelector('.workstream');
    const blocks = await p.evaluate(() => [...document.querySelectorAll('.workstream')].map(b => ({
      collapsed: b.classList.contains('collapsed'), bodyHidden: getComputedStyle(b.querySelector('.block-body')).display === 'none',
      verdict: b.querySelector('.stream-state').textContent, header: b.querySelector('header').textContent, progress: b.querySelector('.stream-progress').textContent })));
    assert(blocks.length > 0, 'blocks rendered');
    assert(blocks.every(b => b.verdict === 'Failed' ? !b.collapsed && !b.bodyHidden : b.collapsed && b.bodyHidden), 'failed blocks stay open, passed blocks fold to a line: ' + JSON.stringify(blocks));
    assert(blocks.every(b => ['Passed', 'Failed'].includes(b.verdict)), 'verdict line: ' + blocks.map(b => b.verdict).join(', '));
    assert(blocks.every(b => /^\d+ \/ \d+$/.test(b.progress)), 'progress as n / m: ' + blocks.map(b => b.progress).join(', '));
    at('fold and unfold'); await p.locator('.workstream .stream-toggle').first().click();
    await p.waitForFunction(() => document.querySelector('.workstream').classList.contains('collapsed'));
    assert(await p.evaluate(() => document.querySelector('.workstream .stream-toggle').getAttribute('aria-expanded') === 'false'), 'toggle reports folded');
    await p.locator('.workstream .stream-toggle').first().click();
    await p.waitForFunction(() => !document.querySelector('.workstream').classList.contains('collapsed'));
    assert(await p.evaluate(() => getComputedStyle(document.querySelector('.workstream .block-body')).display !== 'none'), 'expanded body visible');
    assert((await p.locator('.workstream .stream-step').first().innerText()).startsWith('Failed:'), 'a failed block names the failed check');
    at('reduced motion'); await p.emulateMedia({ reducedMotion: 'reduce' });
    await p.waitForTimeout(200);
    assert(await p.evaluate(() => document.getAnimations().length === 0), 'no running animations under reduced motion');
    await snapshot(p, 'live-finished-light');
    await noOverflowNoErrors(p, errors, 'live');
  } finally { await context.close(); }
});

check('run page: a failing check and its event in two clicks from the Runs table', async browser => {
  const { p, context, errors } = await page(browser, 'light', '/#runs');
  try {
    at('runs table'); await p.waitForSelector('#history-rows [data-open-run]');
    await p.waitForFunction(() => [...document.querySelectorAll('#history-rows td.num')].every(td => td.textContent !== '…'));
    const header = await p.locator('.history-table thead').innerText();
    assert(/violations/i.test(header), 'runs table has Violations: ' + header);
    assert(await p.evaluate(() => document.querySelector('#runs-panel .history-table').classList.contains('no-turns') && getComputedStyle(document.querySelector('#runs-panel .history-table thead th:nth-child(6)')).display === 'none'), 'the Turns column is hidden when no run recorded turns');
    const cells = await p.evaluate(() => [...document.querySelectorAll('#history-rows .history-row')].map(r => [...r.querySelectorAll('td.num')].map(td => td.textContent)));
    assert(cells.every(c => c[0] === '—'), 'scripted checks record no model turns: ' + JSON.stringify(cells));
    assert(cells.some(c => /^[1-9]\d* \/ \d+$/.test(c[1])), 'the sloppy check counts as violations: ' + JSON.stringify(cells));
    at('click 1: open the run'); await p.locator('#history-rows .history-row').filter({ hasText: 'Answer key against sloppy' }).locator('td').nth(2).click();
    await p.waitForSelector('#report-view .matrix-cell button');
    assert((await p.locator('#report-view .outcome-matrix tfoot').innerText()).includes('3 / 3'), 'matrix footer counts passes per setup');
    at('click 2: open the failing attempt'); await p.locator('.matrix-cell.fail button').first().click();
    await p.waitForSelector('#output .verdict');
    const tabs = await p.evaluate(() => [...document.querySelectorAll('.inspector-tabs [role=tab]')].map(b => b.textContent + ':' + b.getAttribute('aria-selected')));
    assert(tabs.join('|') === 'What happened:true|Output:false|Checks:false|Trace:false|Timeline:false', 'tabs: ' + tabs.join('|'));
    const story = await p.locator('#output').innerText();
    assert(story.startsWith('Failed:') && story.includes('What went wrong') && story.includes('Denver'), 'the story opens first, names the verdict and the change that failed it: ' + story.slice(0, 200));
    assert(await p.evaluate(() => document.querySelectorAll('#output .story-facts button').length > 0), 'every fact in the story links its evidence');
    at('checks tab'); await p.locator('#inspector-tab-checks').click();
    await p.waitForSelector('#output .check-row.failed');
    const failed = await p.locator('#output .check-row.failed').first().innerText();
    assert(failed.includes('Failed') && failed.includes('No changes outside the permitted scope'), 'failed row names the check and its verdict: ' + failed);
    const checks = await p.locator('#output').innerText();
    assert(checks.includes('Denver') && checks.includes('contact 003004') && checks.includes('mailing city'), 'checks name expected value, record and field');
    assert(await p.evaluate(() => document.querySelector('#output .changes-table') && !document.querySelector('#output').textContent.includes('<object>')), 'changes table without the placeholder');
    at('trace tab'); await p.locator('#inspector-tab-trace').click();
    await p.waitForSelector('#output .trace-event');
    const labels = await p.evaluate(() => [...document.querySelectorAll('#output .trace-event span')].map(s => s.textContent));
    assert(labels.some(l => l.startsWith('Tool call: ')) && labels.some(l => l.startsWith('Check failed: ')), 'events labelled by what they show: ' + labels.join(' | '));
    assert(new Set(labels).size === labels.length, 'no identical labels: ' + labels.join(' | '));
    await p.locator('#output .trace-event').last().click();
    await p.waitForSelector('#trace-detail h3');
    assert((await p.locator('#trace-detail h3').innerText()).startsWith('Check failed'), 'the event opens beside the list, titled by the event');
    assert(await p.evaluate(() => /\/e\d+$/.test(location.hash)), 'the address names the event: ' + await p.evaluate(() => location.hash));
    assert(await p.evaluate(() => !document.querySelector('#attempt-dialog').matches(':modal') && document.querySelector('#report-view .matrix-cell.current') !== null), 'the sheet is not modal and the current cell is marked');
    at('back closes the sheet'); await p.goBack(); await p.waitForFunction(() => !document.querySelector('#attempt-dialog').open);
    assert(await p.evaluate(() => !document.querySelector('.workspace').classList.contains('hidden')), 'Back closes the sheet and keeps the run');
    await p.locator('.matrix-cell.fail button').first().click(); await p.waitForSelector('#attempt-dialog[open]');
    at('next attempt by keyboard'); const before = await p.locator('#attempt-position').innerText(); await p.locator('#inspector-title').focus(); await p.keyboard.press('ArrowDown');
    await p.waitForFunction(b => document.querySelector('#attempt-position').textContent !== b, before);
    assert((await p.locator('#attempt-position').innerText()) !== before, 'j moves to the next attempt');
    await p.keyboard.press('k');
    at('timeline tab'); await p.locator('#inspector-tab-timeline').click();
    await p.waitForSelector('#output figure.chart.timeline svg rect.span');
    at('keyboard'); await p.locator('#inspector-tab-timeline').focus(); await p.keyboard.press('ArrowLeft');
    assert(await p.evaluate(() => document.activeElement.id === 'inspector-tab-trace' && document.activeElement.getAttribute('aria-selected') === 'true'), 'arrow keys move between tabs');
    const styled = await p.evaluate(() => [...document.querySelectorAll('[style]')].map(e => e.outerHTML.slice(0, 120)));
    assert(styled.length === 0, 'no inline styles: ' + styled.join(' | '));
    await snapshot(p, 'run-checks-light');
    await noOverflowNoErrors(p, errors, 'run page');
  } finally { await context.close(); }
});

check('studio: the Live Monarch Graph tab offers the live graph first and shows products with their stored actions, or the reason it cannot', async browser => {
  const { p, context, errors } = await page(browser, 'light', '/#studio');
  try {
    at('open graphs'); await p.waitForSelector('#studio-library-rows');
    await p.locator('.studio-tabs [data-mode=live]').click();
    await p.waitForSelector('#pg-graph-source');
    assert(await p.evaluate(() => document.querySelector('.pg-workspace').dataset.pgView === 'graph'), 'graph view open');
    const options = await p.evaluate(() => [...document.querySelectorAll('#pg-graph-source option')].map(o => o.textContent));
    assert(options[0] === 'Monarch Enterprise, live (read only)', 'live source first: ' + options.join('|'));
    at('products'); await p.waitForFunction(() => document.querySelector('.pg-graph-product') || document.querySelector('#pg-graph .empty-state'), null, { timeout: 45000 });
    const outcome = await p.evaluate(() => ({ products: document.querySelectorAll('.pg-graph-product').length, reason: document.querySelector('#pg-graph .empty-state')?.innerText || '' }));
    if (outcome.products) {
      at('actions'); await p.waitForSelector('#pg-graph-detail .pg-cluster, #pg-graph-detail .empty-state', { timeout: 45000 });
      assert(await p.evaluate(() => document.querySelector('#pg-graph-stamp').textContent.startsWith('Read only')), 'stamp says read only');
      await snapshot(p, 'product-graph-live-light');
      await noOverflowNoErrors(p, errors, 'product graph');
    } else {
      assert(/discovery service|not set/.test(outcome.reason), 'a plain reason when the live graph is out of reach: ' + outcome.reason);
    }
  } finally { await context.close(); }
});

check('studio: New architecture opens the template menu and a choice opens the editor', async browser => {
  const { p, context, errors } = await page(browser, 'light', '/#studio');
  try {
    await p.waitForSelector('#studio-library-rows');
    at('empty state teaches and offers the one action'); assert((await p.locator('#studio-library-rows').innerText()).includes('An architecture is'), 'empty state says what an architecture is');
    await p.locator('[data-studio-empty-create]').click();
    await p.waitForSelector('.context-menu:not(.hidden) [role=menuitem]');
    await p.locator('.context-menu [role=menuitem]').first().click();
    await p.waitForFunction(() => document.querySelector('#setup-panel').dataset.screen === 'editor', null, { timeout: 10000 });
    assert(await p.evaluate(() => document.querySelector('#studio-item-title').textContent.trim() === 'Untitled architecture'), 'editor shows the new draft');
    assert(await p.evaluate(() => document.querySelectorAll('#lanes .node, #arch-panel .node, .graph-node').length > 0 || !!document.querySelector('#arch-panel canvas, #arch-panel svg')), 'canvas rendered');
    await noOverflowNoErrors(p, errors, 'studio new architecture');
  } finally { await context.close(); }
});

check('runs: days as group rows, text filters, a Report link at the edge, the pager only when needed', async browser => {
  const { p, context, errors } = await page(browser, 'light', '/#runs');
  try {
    await p.waitForSelector('#history-rows [data-open-run]');
    assert((await p.locator('#history-rows .history-day').count()) >= 1, 'a day row groups the runs');
    assert((await p.locator('#history-pager').isHidden()), 'no pager for one page');
    assert((await p.locator('#history-rows .run-setups').first().innerText()).includes('task'), 'the row names its setups and task count');
    at('filter'); await p.locator('[data-history-status=failed]').click();
    assert((await p.locator('#history-rows').innerText()).includes('No runs match'), 'the failed filter empties the fixture list');
    await p.locator('[data-history-clear]').click();
    await p.waitForSelector('#history-rows [data-open-run]');
    at('report link'); await p.locator('#history-rows [data-open-report]').first().click();
    await p.waitForSelector('#report-panel:not(.hidden)');
    assert(await p.evaluate(() => location.hash.startsWith('#report/')), 'route is #report/<id>');
    await noOverflowNoErrors(p, errors, 'runs list');
  } finally { await context.close(); }
});

check('budget: the ledger comes first and an empty week is one line, not three', async browser => {
  const { p, context, errors } = await page(browser, 'light', '/#budget');
  try {
    await p.waitForSelector('#budget-content .budget-section');
    const text = await p.locator('#budget-content').innerText();
    assert(text.indexOf('Ledger') < text.indexOf('Usage by model'), 'ledger before usage');
    assert((await p.locator('#budget-content .ledger-table, #budget-content .budget-section .empty-line').count()) >= 1, 'a ledger table or one plain line');
    assert((await p.locator('#budget-content .empty-line').count()) <= 2, 'at most one empty line per section');
    assert((await p.locator('[data-usage-period][aria-pressed=true]').innerText()) === 'This week', 'the usage period matches the ledger week');
    await noOverflowNoErrors(p, errors, 'budget');
  } finally { await context.close(); }
});

check('settings: budget, capacity, providers with key presence, Monarch pin, all in a label column', async browser => {
  const { p, context, errors } = await page(browser, 'light', '/#runtime');
  try {
    await p.waitForSelector('#settings-providers');
    const heads = await p.evaluate(() => [...document.querySelectorAll('#runtime-panel h2')].map(h => h.textContent));
    assert(heads.join('|').startsWith('Budget|Capacity|Providers|Genesis|Monarch Enterprise'), 'sections in order: ' + heads.join('|'));
    const providers = await p.locator('#settings-providers').innerText();
    assert(/Key present|No key/.test(providers), 'each provider says whether a key is present: ' + providers);
    assert(!/sk-|AIza/.test(providers), 'no key value on the page');
    at('genesis configuration'); await p.waitForSelector('#settings-genesis-config .step-table');
    assert((await p.locator('#settings-genesis-config .step-table tbody tr').count()) >= 13, 'one row per step of Genesis\'s work');
    const genesisText = await p.locator('#settings-genesis-config').innerText();
    assert(/envelope/i.test(genesisText) && /People/.test(genesisText) && /Slack/.test(genesisText), 'budget, people and channels on the configuration page');
    await p.waitForSelector('#config-jobs .schedule-table'); assert((await p.locator('[data-run-job]').count()) >= 2, 'daily jobs listed with a run action');
    at('digest'); await p.goto(BASE + '/#genesis/digest'); await p.waitForSelector('#genesis-digest .report-section');
    assert(/^Genesis, week \d{1,2} of \d{4}$/.test(await p.locator('#genesis-digest h1').innerText()), 'the digest reads as a report');
    await noOverflowNoErrors(p, errors, 'settings');
  } finally { await context.close(); }
});

check('genesis: chat first with the rail and the tracking pane; a dropped sentence becomes a queued card; the board has six columns; the Memory view shows the core files and the daily jobs', async browser => {
  const { p, context, errors } = await page(browser, 'light', '/#genesis');
  try {
    await p.waitForSelector('#genesis-panel:not(.hidden) #genesis-form');
    at('chat first'); assert((await p.locator('#genesis-new').count()) === 1 && (await p.locator('.tracking-tabs [role=tab]').count()) === 3, 'the rail offers a new conversation and the tracking pane has three tabs');
    assert((await p.locator('#genesis-messages').innerText()).includes('Ask Genesis'), 'an empty conversation says what to do');
    at('board route'); await p.locator('#genesis-tab-board').click(); await p.waitForSelector('#genesis-board-view:not(.hidden)');
    assert(await p.evaluate(() => location.hash === '#genesis/board'), 'the board has its own address: ' + await p.evaluate(() => location.hash));
    await p.locator('#genesis-drop textarea').fill('Monarch fails more often on tasks that touch two applications.');
    await p.locator('#drop-submit').click();
    await p.waitForSelector('.research-column[data-stage=research] .research-card');
    const card = await p.evaluate(() => { const c = document.querySelector('.research-column[data-stage=research] .research-card'); return { title: c.querySelector('strong').textContent, chip: c.querySelector('.work-chip')?.textContent || '', draggable: c.draggable }; });
    assert(card.title.startsWith('Monarch fails more often') && card.draggable, 'the dropped sentence is a draggable card: ' + JSON.stringify(card));
    assert(/Queued|Waiting/.test(card.chip), 'the card shows its work state: ' + card.chip);
    assert((await p.locator('.research-column').count()) === 6 && (await p.locator('[data-add-stage]').count()) === 4, 'six columns, four with an add action');
    await p.waitForFunction(() => /idle|waiting|paused|working|next card/i.test(document.querySelector('#genesis-watcher').innerText), null, { timeout: 15000 });
    at('open card'); await p.locator('.research-column[data-stage=research] .research-card').first().click();
    await p.waitForSelector('#research-detail:not(.hidden) .research-question');
    assert((await p.locator('#research-detail #research-work-now').count()) === 1, 'a queued card offers Work now');
    assert((await p.locator('#research-detail .stage-track li.now').innerText()) === 'Research', 'the stage track uses the one vocabulary');
    await p.locator('#research-close').click(); await p.waitForSelector('#tracking-list:not(.hidden)');
    assert((await p.locator('.research-column.folded').count()) >= 1, 'empty columns fold to their name');
    assert(await p.evaluate(() => document.querySelector('.research-board').scrollWidth <= document.querySelector('.research-board').clientWidth + 1), 'the board fits the page');
    at('memory tab'); await p.locator('#genesis-tab-memory').click();
    await p.waitForSelector('#memory-core .memory-block');
    assert((await p.locator('#memory-core .memory-block').count()) === 3, 'SOUL.md, LAB.md and MONARCH.md blocks');
    assert(/^# Genesis/.test(await p.locator('#soul-text').inputValue()) && await p.locator('#soul-save').isDisabled(), 'the identity file is shown in an editor with Save off until it changes');
    await p.locator('#soul-text').fill('# Genesis\n\nA test voice.');
    assert(!(await p.locator('#soul-save').isDisabled()), 'Save turns on after an edit');
    await p.locator('#soul-reset').click();
    assert(await p.locator('#soul-save').isDisabled(), 'Discard restores the saved text');
    assert((await p.locator('#memory-changes').innerText()).includes('Track record'), 'the Memory view shows last night and the track record');
    at('library topics'); await p.locator('#genesis-tab-library').click();
    await p.waitForSelector('#library-filters [name=topic] option', { state: 'attached' });
    const topics = await p.evaluate(() => [...document.querySelectorAll('#library-filters [name=topic] option')].map(o => o.textContent));
    assert(topics.includes('Agentic memory') && topics[topics.length - 1] === 'Other', 'fixed topic list with Other last');
    await p.locator('#genesis-tab-board').click(); await p.waitForSelector('#genesis-board-view:not(.hidden)');
    await snapshot(p, 'genesis-board-light');
    await noOverflowNoErrors(p, errors, 'genesis board');
  } finally { await context.close(); }
});

(async () => {
  const { chromium } = loadPlaywright();
  if (!(await portIsFree())) throw new Error('Port ' + PORT + ' already answers: a stale fixture server is running. Kill Python listeners on 8766-8799 (they answer with old code), or set BROWSER_PORT.');
  const server = await startServer();
  const browser = await chromium.launch({ headless: true, channel: process.env.BROWSER_CHANNEL || 'chrome' });
  let failed = 0;
  try {
    for (const { name, fn } of checks) {
      if (only && !name.includes(only)) continue;
      step = '';
      try { await fn(browser); console.log('PASS', name); }
      catch (e) { failed++; console.log('FAIL', name, step ? '[at ' + step + ']' : '', '\n     ', e.message.split('\n')[0]); }
    }
  } finally {
    await browser.close();
    // `uv run` wraps the fixture server in a child process; on Windows killing the
    // wrapper alone leaves the Python listener behind (the stale-server error above).
    if (process.platform === 'win32') require('child_process').spawnSync('taskkill', ['/pid', String(server.pid), '/T', '/F'], { stdio: 'ignore' });
    else server.kill();
  }
  console.log(failed ? `${failed} check(s) failed` : 'all checks passed');
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
