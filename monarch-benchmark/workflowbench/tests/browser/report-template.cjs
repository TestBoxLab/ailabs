// Start the free fixture: uv run python tests/browser/server.py --port 8774
'use strict';
const {execFileSync} = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const bin = process.env.AGENT_BROWSER_BIN || (process.platform === 'win32' ? path.join(process.env.APPDATA, 'npm/node_modules/agent-browser/bin/agent-browser-win32-x64.exe') : 'agent-browser');
const args = ['--session', 'report-template'];
const browser = (...command) => execFileSync(bin, [...args, ...command], {encoding: 'utf8', timeout: 60000});
const evaluate = fn => execFileSync(bin, [...args, 'eval', '--stdin'], {input: '(' + fn.toString() + ')()', encoding: 'utf8', timeout: 60000});
console.log(browser('open', 'http://127.0.0.1:' + (process.env.BROWSER_PORT || 8774)));
const check = async () => {
  const assert = (ok, message) => { if (!ok) throw Error(message); };
  history.replaceState(null, '', '#runs');
  await window.goRoute('#benchmarks/products');
  assert(location.hash === '#benchmarks/products', 'Explicit router hash must select the requested Benchmarks group');
  assert(!document.querySelector('#benchmarks-panel').classList.contains('hidden'), 'Explicit Benchmarks route must show its own panel');
  const index = await (await fetch('/api/reports')).json();
  const run = index.rounds.flatMap(r => r.runs).find(r => r.title.startsWith('Answer key against sloppy'));
  assert(run, 'Scripted fixture must have a report');
  await openReport(run.id);
  const article = document.querySelector('#report-article');
  assert(article.classList.contains('readable-report'), 'Approved readable template must render in Studio');
  assert(article.querySelector('.report-summary').textContent.trim().split(/\s+/).length <= 100, 'Summary must stay within 100 words');
  assert(article.querySelector('#report-hero'), 'Comparison must precede diagnosis');
  const disclosure = article.querySelector('details.measurement-details');
  assert(disclosure && disclosure.querySelector('summary').textContent === 'Measurement definitions and limitations', 'One measurement disclosure must exist');
  assert(getComputedStyle(article.querySelector('#report-buckets p')).fontSize === getComputedStyle(article.querySelector('#report-why p')).fontSize, 'Bucket explanation must match body prose size');
  assert(article.textContent.includes('Analysis pending'), 'No review must produce an explicit pending state');
  assert(article.textContent.includes('Initially solved') && article.textContent.includes('Including retries'), 'Task metrics need explicit initial/retry labels');
  assert(article.querySelector('[data-open-run-evidence]'), 'Studio must retain access to evidence');
  for (const kind of ['logs', 'prompts']) {
    const link = article.querySelector('[data-report-download="' + kind + '"]');
    assert(link && link.href.includes('/api/reports/run/' + run.id + '/downloads/' + kind), 'Separate download link required: ' + kind);
    assert(!link.href.includes('audience='), 'Shared report downloads must not restore the removed audience selector');
    const response = await fetch(link.href);
    assert(response.ok && response.headers.get('content-disposition')?.includes('attachment;'), 'Download must return an attachment: ' + kind);
    const saved = await response.json();
    assert(saved.run === run.id && saved.kind === kind, 'Attachment must belong to this shared run');
    assert(saved.coverage && Array.isArray(saved[kind === 'logs' ? 'events' : 'prompts']), 'Attachment must describe retained evidence and coverage');
  }
  assert(!article.querySelector('a[href$=".zip"]'), 'Shared report must not require ZIP files');
  const guideLink = article.querySelector('[data-report-download="guide"]');
  assert(guideLink, 'Review guide needs a separate download link');
  const guideResponse = await fetch(guideLink.href);
  assert(guideResponse.ok && (await guideResponse.text()).includes('Expected result checks'), 'Guide attachment must include frozen expectations');
  assert(!article.querySelector('th')?.textContent.includes('Evidence and causal'), 'No causal-evidence column');
  // Capture the real export blob; no alternative export renderer in this test.
  let exported;
  const originalURL = URL.createObjectURL, originalClick = HTMLAnchorElement.prototype.click;
  URL.createObjectURL = blob => { exported = blob; return originalURL(blob); };
  HTMLAnchorElement.prototype.click = function () { if (!this.download) originalClick.call(this); };
  try { await saveReportHtml(article, currentReport); }
  finally { URL.createObjectURL = originalURL; HTMLAnchorElement.prototype.click = originalClick; }
  assert(exported, 'Export must create a standalone HTML file');
  window.reportTemplateExport = await exported.text();
  const html = new DOMParser().parseFromString(window.reportTemplateExport, 'text/html');
  assert(html.querySelector('.report-summary').textContent === article.querySelector('.report-summary').textContent, 'Summary must match UI exactly');
  assert(html.querySelector('.reading-comparison').textContent === article.querySelector('.reading-comparison').textContent, 'Comparison values must match UI exactly');
  assert(!html.querySelector('button, .studio-only, .report-actions, [role="button"]'), 'Offline report must have no dead Studio controls');
  for (const link of html.querySelectorAll('a[href]')) {
    const href = link.getAttribute('href');
    assert(href.startsWith('#') && html.getElementById(href.slice(1)), 'Every exported link must target a real local section: ' + href);
  }
  assert(html.querySelector('style') && !html.querySelector('script[src],link[rel="stylesheet"],img[src^="/"]'), 'Export embeds assets');
  assert(article.querySelectorAll('.reading-comparison tbody tr').length === currentReport.reading.comparison.length, 'All visible competitor metrics must be shown');
  window.measuredReport = structuredClone(currentReport);
  // Presentation edge cases only; all input is labeled as a layout fixture.
  const example = structuredClone(currentReport);
  example.reading.headline = 'Layout fixture: reviewed failure and retry';
  example.reading.comparison = example.reading.comparison.map((s, i) => ({...s, kind: i ? 'api' : 'monarch'}));
  example.reading.cases = [{task: 'layout-fixture', title: 'Create a VIP contact (layout fixture)',
    failed_attempts: 1, cost: null, unknown_costs: 1, diagnosis: '<img src=x onerror=alert(1)> is untrusted example text, not markup.',
    responsibility: 'shared', event_ids: []}];
  example.reading.status = 'completed';
  example.reading.analysis = {basis: 'Model interpretation; citations require human review', model: 'Layout fixture', revision: 'fixture-v1'};
  renderRunReport(example);
  assert(!article.querySelector('.reading-diagnoses img'), 'Untrusted diagnosis must be escaped');
  assert(article.textContent.includes('citations require human review'), 'Model interpretation must not imply human review');
  assert(article.textContent.includes('fixture-v1'), 'Analysis revision must be shown');
  assert(article.querySelectorAll('.reading-charts figure').length === 3, 'Non-scripted layout needs three readable comparison charts');
  assert(article.querySelectorAll('.reading-diagnoses thead th').length === 4, 'Diagnosis table has exactly four approved columns');
  const authored = structuredClone(example);
  authored.authored = {status: 'completed', revision: 'reviewed-fixture', summary: 'Reviewed layout fixture summary.', findings: [{title: 'Retained finding', explanation: '<img src=x> is plain text.', kind: 'fact', event_ids: []}], what_went_right: 'Recorded success.', what_went_wrong: 'Recorded failure.', why: 'A reviewed hypothesis.', next_experiment: 'Test a bounded intervention.', limitations: 'Layout fixture only.', attempts: [{index: 0, task: 'layout-fixture', model: authored.order[0], explanation: 'Reviewed attempt fixture.', event_ids: []}]};
  renderRunReport(authored);
  assert(article.querySelector('.report-summary').textContent === authored.authored.summary, 'Published Genesis summary remains visible in the readable template');
  assert(article.querySelector('#report-analysis') && article.querySelector('#report-authored-attempts'), 'Authored analysis and every-attempt explanations survive the merge');
  assert(!article.querySelector('#report-why img'), 'Authored prose stays escaped');
  assert(new Set([...article.querySelectorAll('[id]')].map(n=>n.id)).size === article.querySelectorAll('[id]').length, 'Authored and recorded attempt sections need distinct IDs');
  if(authored.performance)assert(article.querySelector('#report-performance'), 'Measured performance remains visible');
  if(authored.patterns)assert(article.querySelector('#report-patterns .report-patterns'), 'Server outcome patterns remain visible');
  authored.lab_setups = [{id:'lab-fixture', name:'Lab fixture'}];renderRunReport(authored);
  const click = new MouseEvent('click', {bubbles:true,cancelable:true});article.querySelector('[data-report-download="logs"]').dispatchEvent(click);
  assert(click.defaultPrevented && article.classList.contains('lab-present'), 'Lab report downloads and printing remain gated');
  renderRunReport(example);
  window.layoutReport = example;
  return 'PASS: Studio template, pending analysis, explicit task metrics, evidence access and standalone export parity';
};
console.log(evaluate(check));
browser('set', 'viewport', '390', '844');
console.log(evaluate(async () => {
  await new Promise(resolve => setTimeout(resolve, 250));
  if (document.documentElement.scrollWidth > innerWidth + 1) throw Error('Mobile report overflows page');
  const summary = document.querySelector('.report-summary');
  if (parseFloat(getComputedStyle(summary).fontSize) < 16) throw Error('Mobile prose is too small');
  const diagnosis = document.querySelector('.reading-diagnoses');
  if (diagnosis.scrollWidth > diagnosis.clientWidth + 1) throw Error('Mobile diagnosis must not require sideways scrolling');
  if (diagnosis.querySelector('tbody th').getBoundingClientRect().width < diagnosis.clientWidth - 2) throw Error('Mobile task title must use the whole reading width');
  for (const svg of document.querySelectorAll('.reading-charts svg')) {
    const scale = svg.getBoundingClientRect().width / svg.viewBox.baseVal.width;
    const label = svg.querySelector('.value-label');
    if (label && parseFloat(getComputedStyle(label).fontSize) * scale < 11) throw Error('Mobile chart labels shrink below readable size');
  }
  goToSection('caveats');
  if (!document.querySelector('.measurement-details').open) throw Error('Old caveats link must open the consolidated disclosure');
  return 'PASS: mobile containment, readable charts, stacked diagnosis and legacy navigation';
}));
const output = process.env.REPORT_EXPORT_PATH || path.join(require('node:os').tmpdir(), 'ailabs-readable-report-check.html');
const raw = evaluate(() => window.reportTemplateExport).trim();
fs.writeFileSync(output, JSON.parse(raw), 'utf8');
console.log(evaluate(async () => {
  const index = await (await fetch('/api/reports')).json();
  await openRound(index.rounds[0].id);
  if (!document.querySelector('.readable-report .standings')) throw Error('Round standings must keep rendering');
  goToSection('caveats');
  if (!document.querySelector('.measurement-details').open) throw Error('Round caveats navigation must open definitions');
  renderRunReport(window.layoutReport);
  return 'PASS: round standings and consolidated disclosure';
}));
const offline = (...command) => execFileSync(bin, ['--session', 'report-template-offline', ...command], {encoding: 'utf8', timeout: 60000});
console.log(offline('open', require('node:url').pathToFileURL(output).href));
offline('set', 'offline', 'on');
offline('reload');
console.log(execFileSync(bin, ['--session', 'report-template-offline', 'eval', '--stdin'], {
  input: `(() => {
    if (location.protocol !== 'file:' || !document.querySelector('.report-summary')) throw Error('Offline export did not load');
    if (document.querySelectorAll('button,.studio-only').length) throw Error('Offline export has dead controls');
    if (![...document.querySelectorAll('a[href]')].every(a=>a.hash&&document.getElementById(a.hash.slice(1)))) throw Error('Offline link is broken');
    return 'PASS: standalone file reloads without network, controls or broken section links';
  })()`, encoding: 'utf8', timeout: 60000
}));
console.log('Saved and opened offline: ' + output);
