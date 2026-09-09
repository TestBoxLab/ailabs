'use strict';
// Reports: the front door. A report reads verdict first, then the evidence.
// Every number comes from the server (report_data.py); this file only lays it out.
let reportAudience = 'public', currentReport = null, reportsSequence = 0;
const fmtPct = v => v === null || v === undefined ? '—' : Math.round(v * 100) + '%';
const fmtMoney = v => v === null || v === undefined ? 'unknown' : Charts.money(v);
const fmtDate = s => s ? new Date(s).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '';
const trackWords = t => t === 'create-and-run' ? 'Workflow building' : 'Agentic requests';
const gradeClass = g => ({ Improvement: 'improvement', Regression: 'regression', Tradeoff: 'tradeoff', Tie: 'tie' }[g] || 'none');
const meta = parts => '<p class="meta">' + parts.filter(Boolean).map(esc).join('<span class="sep">·</span>') + '</p>';
const gradeBadge = g => '<span class="grade ' + gradeClass(g.grade) + '">' + esc(g.grade) + '</span>';
const setupFamily = name => Charts.familyOf(name);

function reportRoute(hash) {
  if (hash === '#reports' || hash === '#leaderboard' || hash === '' || hash === '#') return openReports();
  if (hash.startsWith('#report/')) return openReport(decodeURIComponent(hash.slice(8)));
  if (hash.startsWith('#round/')) return openRound(decodeURIComponent(hash.slice(7)));
  return null;
}

async function openReports() {
  showWorkspaceSurface('reports');
  const box = $('#reports-content'), sequence = ++reportsSequence;
  box.innerHTML = '<p class="meta">Loading</p>';
  try {
    const data = await api('/api/reports?audience=' + reportAudience);
    if (sequence !== reportsSequence) return;
    renderReportsIndex(data);
  } catch (e) {
    box.innerHTML = '<div class="empty-state"><h3>Reports could not load</h3><p>' + esc(e.message) + '</p><button class="button" id="reports-retry">Try again</button></div>';
    $('#reports-retry').onclick = openReports;
  }
}

function renderReportsIndex(data) {
  const box = $('#reports-content');
  if (!data.rounds.length) {
    box.innerHTML = '<div class="empty-state"><h3>No finished runs yet</h3><button class="button primary" id="reports-start">Start a run</button></div>';
    $('#reports-start').onclick = () => openLaunch();
    return;
  }
  box.innerHTML = '<div class="reports-toolbar">' + audienceToggle() + '</div>' + data.rounds.map(round => {
    const best = round.best ? '<strong>' + esc(round.best.name) + '</strong> passed ' + round.best.passed + ' of ' + round.best.attempts + ' (' + fmtPct(round.best.rate) + ')' : 'No evaluated attempts';
    return '<article class="block round-card"><header><span>' + (round.full_benchmark ? 'Benchmark round' : 'Round') + '</span><strong>' + round.task_count + ' ' + (round.task_count === 1 ? 'task' : 'tasks') + '</strong><span>' + esc(trackWords(round.track)) + '</span><span>' + round.runs.length + ' ' + (round.runs.length === 1 ? 'run' : 'runs') + '</span><span>' + esc(fmtDate(round.latest)) + '</span></header>' +
      '<div class="block-body"><div class="round-lead">' + gradeBadge(round.grade) + '<span>' + best + '</span></div>' +
      '<ul class="round-runs">' + round.runs.map(run => '<li><button class="text-button" data-open-report="' + esc(run.id) + '">' + esc(run.title || run.id) + '</button>' + meta([fmtDate(run.created_at), run.status]) + '</li>').join('') + '</ul>' +
      '<div class="round-actions"><button class="button small" data-open-round="' + esc(round.id) + '">Round report</button></div></div></article>';
  }).join('');
  bindReportLinks(box);
}

function audienceToggle() {
  return '<div class="audience-toggle" role="group" aria-label="Audience"><button class="' + (reportAudience === 'public' ? 'active' : '') + '" data-audience="public">Public</button><button class="' + (reportAudience === 'internal' ? 'active' : '') + '" data-audience="internal">Internal</button></div>';
}

function bindReportLinks(root) {
  $$('[data-open-report]', root).forEach(b => b.onclick = () => { history.pushState(null, '', '#report/' + encodeURIComponent(b.dataset.openReport)); openReport(b.dataset.openReport); });
  $$('[data-open-round]', root).forEach(b => b.onclick = () => { history.pushState(null, '', '#round/' + encodeURIComponent(b.dataset.openRound)); openRound(b.dataset.openRound); });
  $$('[data-audience]', root).forEach(b => b.onclick = () => { reportAudience = b.dataset.audience; reportRoute(location.hash); });
}

async function openReport(id) {
  showWorkspaceSurface('report', false);
  if (location.hash !== '#report/' + encodeURIComponent(id)) history.pushState(null, '', '#report/' + encodeURIComponent(id));
  const article = $('#report-article'), sequence = ++reportsSequence;
  article.innerHTML = '<p class="meta">Loading report</p>';
  try {
    const data = await api('/api/reports/run/' + encodeURIComponent(id) + '?audience=' + reportAudience);
    if (sequence !== reportsSequence) return;
    currentReport = data; renderRunReport(data);
  } catch (e) { article.innerHTML = '<div class="empty-state"><h3>Report could not load</h3><p>' + esc(e.message) + '</p></div>'; }
}

async function openRound(id) {
  showWorkspaceSurface('report', false);
  if (location.hash !== '#round/' + encodeURIComponent(id)) history.pushState(null, '', '#round/' + encodeURIComponent(id));
  const article = $('#report-article'), sequence = ++reportsSequence;
  article.innerHTML = '<p class="meta">Loading report</p>';
  try {
    const data = await api('/api/reports/round/' + encodeURIComponent(id) + '?audience=' + reportAudience);
    if (sequence !== reportsSequence) return;
    currentReport = data; renderRoundReport(data);
  } catch (e) { article.innerHTML = '<div class="empty-state"><h3>Report could not load</h3><p>' + esc(e.message) + '</p></div>'; }
}

const section = (id, title, body) => '<section class="report-section" id="report-' + id + '"><h2>' + esc(title) + '</h2>' + body + '</section>';
const setupName = (r, id) => r.setups[id]?.name || id;

function reportActions(r, kind) {
  return '<div class="report-actions">' + audienceToggle() + (kind === 'run' ? '<button class="button small" data-open-run-evidence="' + esc(r.run) + '">Open run</button>' : '') +
    '<button class="button small" id="report-print">Print</button><button class="button small" id="report-save">Save as HTML</button>' +
    (r.hidden_setups ? '<span class="meta">' + r.hidden_setups + ' internal-only ' + (r.hidden_setups === 1 ? 'setup' : 'setups') + ' hidden</span>' : '') + (reportAudience === 'internal' ? '<span class="internal-mark">Internal view</span>' : '') + '</div>';
}

function findingsList(findings, modelFindings, r) {
  const items = findings.map(f => '<li>' + esc(f.text) + ' ' + evidenceLink(f.evidence, r) + '</li>').join('');
  const model = modelFindings.map(f => '<li class="model-finding"><span class="meta">' + (f.fact ? 'Model, fact' : 'Model, hypothesis') + '</span> <strong>' + esc(f.title) + '</strong> ' + esc(f.text) + ' ' + evidenceLink(f.evidence, r) + '</li>').join('');
  return '<ol class="findings">' + items + model + '</ol>';
}

function evidenceLink(evidence, r) {
  if (!evidence) return '';
  if (evidence.kind === 'events' && evidence.event_ids?.length) return '<button class="text-button evidence" data-evidence-run="' + esc(r.run) + '" data-evidence-event="' + evidence.event_ids[0] + '">Event ' + evidence.event_ids[0] + (evidence.event_ids.length > 1 ? ' +' + (evidence.event_ids.length - 1) : '') + '</button>';
  const targets = { hero: 'Figure', matrix: 'Task matrix', bucket: 'Failures', attempts: 'Failures', figure: 'Cost', cost: 'Cost', table: 'Figure' };
  const anchor = { hero: 'hero', matrix: 'failures', bucket: 'failures', attempts: 'failures', figure: 'cost', cost: 'cost', table: 'hero' }[evidence.kind] || 'hero';
  return '<button class="text-button evidence" data-evidence-anchor="report-' + anchor + '">' + esc(targets[evidence.kind] || 'Evidence') + '</button>';
}

function pairedTable(r) {
  if (!r.paired?.length) return '<p class="report-note">No evaluated attempts to compare.</p>';
  const head = '<tr><th>Category</th>' + r.order.map(id => '<th class="num' + (id === r.baseline ? ' baseline' : '') + '">' + esc(setupName(r, id)) + (id === r.baseline ? ' <span class="meta">Bare</span>' : '') + '</th>').join('') + '</tr>';
  const rows = r.paired.map(row => '<tr><th scope="row">' + esc(row.category) + '</th>' + r.order.map(id => {
    const c = row.cells[id];
    if (!c) return '<td class="num muted">—</td>';
    const delta = c.delta === null || c.delta === undefined ? '' : '<span class="delta ' + (c.delta > 0 ? 'up' : c.delta < 0 ? 'down' : 'flat') + '">' + (c.delta > 0 ? '+' : '') + c.delta + '</span>';
    return '<td class="num">' + c.passed + ' / ' + c.attempts + delta + '</td>';
  }).join('') + '</tr>').join('');
  return '<table class="paired"><thead>' + head + '</thead><tbody>' + rows + '</tbody></table>' + (r.baseline ? '<p class="report-note">The small number is how many more or fewer tasks the setup passed than Bare in that category; green is more, red is fewer.</p>' : '');
}

function heroFigure(r, title) {
  const rows = r.hero.map(h => ({ ...h, family: setupFamily(h.label), sub: r.setups[h.id]?.pass?.attempts ? null : undefined, data: { setup: h.id } }));
  return Charts.dotWhisker({ title, rows, labelWidth: 220, source: 'Run ' + (r.run || r.method.runs.join(', ')) + ' · ' + r.method.task_count + ' tasks · task set ' + r.method.task_set + ' · whiskers show the 95% interval' });
}

function failuresBlock(r) {
  const buckets = (r.failures?.buckets || []).filter(b => b.count).map(b => ({ label: b.label, value: b.count, denominator: r.failures.summary.failed_attempts, cls: b.id === 'infrastructure' ? 'neutral' : 'fail', data: { bucket: b.id } }));
  const bars = buckets.length ? Charts.bars({ title: r.failures.summary.failed_attempts + ' of ' + r.failures.summary.recorded_attempts + ' attempts failed', rows: buckets, labelWidth: 260, source: 'Reasons are read from the recorded evidence, not guessed. One reason per failed attempt.' }) : null;
  const matrix = Charts.matrix({ tasks: r.tasks, setups: r.order.map(id => ({ id, name: setupName(r, id), baseline: id === r.baseline, family: setupFamily(setupName(r, id)) })), cells: r.matrix });
  const wrap = document.createElement('div'); wrap.className = 'failures-block';
  if (bars) wrap.appendChild(bars); else { const p = document.createElement('p'); p.className = 'report-note'; p.textContent = 'No failed attempts.'; wrap.appendChild(p); }
  const cap = document.createElement('p'); cap.className = 'chart-title'; cap.textContent = 'Every task, pass or fail per setup; tasks the setups disagree on come first' + (r.repetitions > 1 || r.method.repetitions > 1 ? '; cells show passes over repetitions' : ''); wrap.appendChild(cap);
  const scroll = document.createElement('div'); scroll.className = 'table-scroll'; scroll.appendChild(matrix); wrap.appendChild(scroll);
  const claims = r.order.map(id => r.setups[id]).filter(s => s && s.false_completion?.count);
  if (claims.length) { const p = document.createElement('p'); p.className = 'report-note'; p.textContent = claims.map(s => s.name + ' reported the work as done in ' + s.false_completion.count + ' of ' + s.false_completion.failed + ' failed attempts').join('; ') + ' (wording heuristic over the final output).'; wrap.appendChild(p); }
  return wrap;
}

function costBlock(r) {
  const setups = r.order.map(id => r.setups[id]).filter(Boolean);
  const points = setups.map(s => ({ label: s.name, x: s.cost.per_attempt, y: s.pass.rate, low: s.pass.low, high: s.pass.high, baseline: s.is_baseline, family: setupFamily(s.name), data: { setup: s.id } }));
  const wrap = document.createElement('div'); wrap.className = 'cost-block';
  const anyCost = points.some(p => p.x !== null && p.x !== undefined);
  if (anyCost) wrap.appendChild(Charts.scatter({ title: 'Cost per attempt against pass rate', points, xLog: true, pareto: points.filter(p => p.x !== null).length > 1, source: 'Only settled costs are drawn; a setup missing a receipt for any attempt is left out.' }));
  const tokens = setups.filter(s => Object.values(s.cost.tokens).some(v => v)).map(s => ({ label: s.name, parts: s.cost.tokens }));
  if (tokens.length) wrap.appendChild(Charts.waterfall({ title: 'Tokens by kind', rows: tokens, labelWidth: 220, source: 'Provider usage receipts.' }));
  const table = document.createElement('table'); table.className = 'paired cost-table';
  table.innerHTML = '<thead><tr><th>Setup</th><th class="num">Per attempt</th><th class="num">Per passed task</th><th class="num">Total</th><th class="num">Unpriced attempts</th><th class="num">Typical time</th></tr></thead><tbody>' +
    setups.map(s => '<tr><th scope="row">' + esc(s.name) + '</th><td class="num">' + esc(fmtMoney(s.cost.per_attempt)) + '</td><td class="num">' + esc(fmtMoney(s.cost.per_pass)) + '</td><td class="num">' + esc(fmtMoney(s.cost.total)) + '</td><td class="num">' + s.cost.unknown_attempts + '</td><td class="num">' + (s.time.median === null ? '—' : s.time.median.toFixed(1) + 's') + '</td></tr>').join('') + '</tbody>';
  wrap.appendChild(table);
  return wrap;
}


// Terms a reader meets in a report, said once, in plain words.
const REPORT_TERMS = [
  ['Setup', 'One competitor as configured for the run: a model with its tools and thinking setting, an architecture built in the Studio, or Monarch itself.'],
  ['Bare', 'The same model with the same tools and nothing else around it. Every setup is compared against Bare.'],
  ['Task', 'One request in plain language, its starting data, and an approval rule saying what must change and what must not.'],
  ['Attempt', 'One task tried once by one setup.'],
  ['Pass', 'The expected result is present, nothing else changed, and the attempt finished normally. Anything less is a fail.'],
  ['95% interval', 'The range the pass rate would most likely fall in if the same tasks ran again. Few tasks give a wide range.'],
  ['Paired comparison', 'The setup and Bare on exactly the same tasks, counted task by task as better, worse or the same. The chance sentence is a sign test.'],
  ['Grade', 'One word for the paired comparison: Improvement, Regression, Tie, Tradeoff when the tasks and the cost point in opposite directions, or Not comparable when there is no Bare to compare against.'],
  ['Thinking setting', 'How much reasoning effort the model was allowed per request.'],
  ['Violation', 'A change the task did not permit. One violation fails the attempt even when the requested result is present.'],
];
function termsList() { return '<dl class="report-terms">' + REPORT_TERMS.map(([term, text]) => '<dt>' + esc(term) + '</dt><dd>' + esc(text) + '</dd>').join('') + '</dl>'; }

function methodList(r) {
  const m = r.method;
  const rows = [['Task set', m.task_set + (m.benchmark ? ' (' + m.benchmark + ')' : '') + ' · ' + m.task_count + ' tasks'], ['Track', trackWords(m.track || r.track)], ['Repetitions', String(m.repetitions || 1)],
    ['Judge', m.judge ? (m.judge.id + ' · ' + String(m.judge.sha256 || '').slice(0, 12)) : 'historical, unpinned'], ['Corpus', 'AutomationBench ' + m.fork],
    ['Runs', (m.runs || []).join(', ')], ['Attempts', m.recorded_attempts !== undefined ? m.recorded_attempts + ' recorded of ' + m.planned_attempts + ' planned' : ''],
    ['Concurrency', m.concurrency ? String(m.concurrency) : ''], ['Spending limit', m.maximum_usd ? '$' + m.maximum_usd : ''], ['Instructions', m.configuration ? (m.configuration.prompt ? 'custom' : 'original task text') + (m.configuration.max_turns ? ' · ' + m.configuration.max_turns + ' turns max' : '') : '']];
  return '<dl class="method">' + rows.filter(([, v]) => v).map(([k, v]) => '<dt>' + esc(k) + '</dt><dd>' + esc(v) + '</dd>').join('') + '</dl>';
}

function narrativeBlock(r) {
  const n = r.narrative || {};
  if (n.status === 'completed') return '<div class="model-reading"><p class="meta">Model reading · ' + esc(n.model || '') + (n.effort ? ' · ' + esc(n.effort) + ' thinking' : '') + '</p><p>' + esc(n.summary || '') + '</p>' + (n.next_experiment ? '<p><strong>Next experiment.</strong> ' + esc(n.next_experiment) + '</p>' : '') + '</div>';
  if (n.status === 'failed') return '<p class="report-note">The model reading did not complete; the recorded verdicts stand on their own.</p>';
  return '<p class="report-note pending"><span class="meta">Analysis pending</span> ' + esc(n.reason || '') + '</p>';
}

function renderRunReport(r) {
  const article = $('#report-article');
  article.innerHTML = '<header class="report-head">' + meta(['Run ' + String(r.run).slice(0, 12), r.method.task_count + (r.method.task_count === 1 ? ' task' : ' tasks'), r.order.length + (r.order.length === 1 ? ' setup' : ' setups'), trackWords(r.track), fmtDate(r.finished_at || r.created_at)]) +
    '<h1>' + esc(r.title || 'Run report') + '</h1><div class="grade-line">' + gradeBadge(r.grade) + '<span class="grade-reason">' + esc(r.grade.reason) + '</span></div>' + reportActions(r, 'run') + '</header>' +
    section('verdict', 'Verdict', '<p class="verdict">' + esc(r.verdict) + '</p>' + narrativeBlock(r)) +
    section('findings', 'Findings', findingsList(r.findings, r.model_findings, r)) +
    section('hero', 'Pass rate', '<div data-slot="hero"></div>') +
    section('paired', 'By category', pairedTable(r)) +
    section('failures', 'Where it failed', '<div data-slot="failures"></div>') +
    section('cost', 'What it cost', '<div data-slot="cost"></div>') +
    section('caveats', 'What to keep in mind', '<ul class="caveats">' + r.caveats.map(c => '<li>' + esc(c) + '</li>').join('') + '</ul>') +
    section('method', 'How it was measured', methodList(r)) +
    section('terms', 'Terms', termsList());
  const subject = r.setups[r.subject], base = r.setups[r.baseline];
  const heroTitle = subject ? subject.name + ' passed ' + subject.pass.passed + ' of ' + subject.pass.attempts + (base ? ', ' + base.name + ' ' + base.pass.passed + ' of ' + base.pass.attempts : '') : 'Pass rate per setup';
  $('[data-slot="hero"]', article).replaceWith(heroFigure(r, heroTitle));
  $('[data-slot="failures"]', article).replaceWith(failuresBlock(r));
  $('[data-slot="cost"]', article).replaceWith(costBlock(r));
  bindReportActions(article, r);
}

function standingsTable(r) {
  if (!r.standings.length) return '<p class="report-note">No evaluated attempts on this task set yet.</p>';
  const k = r.repetitions > 1, overTasks = r.standings.some(s => s.interval?.unit === 'tasks');
  const interval = s => { const i = s.interval || s.pass; return i.low == null ? '—' : fmtPct(i.low) + '–' + fmtPct(i.high); };
  return '<table class="paired standings"><thead><tr><th>#</th><th>Setup</th><th class="num">Passed</th><th class="num">Rate</th><th class="num">95% interval' + (overTasks ? ' over tasks' : '') + '</th>' + (k ? '<th class="num">Passed all ' + r.repetitions + ' times</th>' : '') + '<th class="num">Per attempt</th><th>Against Bare</th></tr></thead><tbody>' +
    r.standings.map(s => '<tr' + (s.is_baseline ? ' class="baseline-row"' : '') + '><td class="num">' + s.rank + '</td><th scope="row">' + esc(s.name) + (s.is_baseline ? ' <span class="meta">Bare</span>' : '') + '</th><td class="num">' + s.pass.passed + ' / ' + s.pass.attempts + '</td><td class="num">' + fmtPct(s.pass.rate) + '</td><td class="num">' + interval(s) + '</td>' + (k ? '<td class="num">' + (s.pass_k.k ? fmtPct(s.pass_k.rate) : '—') + '</td>' : '') + '<td class="num">' + esc(fmtMoney(s.cost.per_attempt)) + '</td><td>' + (s.grade ? gradeBadge(s.grade) + (s.paired?.comparable ? ' <span class="meta">' + s.paired.wins + 'W ' + s.paired.losses + 'L ' + s.paired.ties + 'T</span>' : '') : '') + '</td></tr>').join('') + '</tbody></table>';
}

// Every pairing on the frozen set. Bare sits on the "against" side; colour only
// there, and always with a sign and a word.
function pairingsTable(r) {
  if (!r.pairings?.length) return '';
  const rows = r.pairings.map(p => p.a === r.baseline ? { setup: p.b, against: p.a, tasks: p.tasks, wins: p.losses, losses: p.wins, ties: p.ties, only: p.unique_b, onlyAgainst: p.unique_a } : { setup: p.a, against: p.b, tasks: p.tasks, wins: p.wins, losses: p.losses, ties: p.ties, only: p.unique_a, onlyAgainst: p.unique_b });
  const net = x => { const d = x.wins - x.losses, sign = d > 0 ? '+' : d < 0 ? '−' : '±', bare = x.against === r.baseline; return '<td class="num ' + (bare ? (d > 0 ? 'pass' : d < 0 ? 'fail' : 'neutral') : '') + '">' + sign + Math.abs(d) + (bare ? ' ' + (d > 0 ? 'better' : d < 0 ? 'worse' : 'even') : '') + '</td>'; };
  return '<h3>Pairings</h3><table class="paired pairings"><thead><tr><th>Setup</th><th>Against</th><th class="num">Tasks</th><th class="num">Wins</th><th class="num">Losses</th><th class="num">Ties</th><th class="num">Only setup</th><th class="num">Only against</th><th class="num">Net</th></tr></thead><tbody>' +
    rows.map(x => '<tr><th scope="row">' + esc(setupName(r, x.setup)) + '</th><td>' + esc(setupName(r, x.against)) + (x.against === r.baseline ? ' <span class="meta">Bare</span>' : '') + '</td><td class="num">' + x.tasks + '</td><td class="num">' + x.wins + '</td><td class="num">' + x.losses + '</td><td class="num">' + x.ties + '</td><td class="num">' + x.only + '</td><td class="num">' + x.onlyAgainst + '</td>' + net(x) + '</tr>').join('') + '</tbody></table>';
}

function excludedTable(r) {
  if (!r.excluded?.length) return '';
  return '<h3>Excluded from the leaderboard</h3><table class="paired excluded"><thead><tr><th>Run</th><th>Reason</th></tr></thead><tbody>' +
    r.excluded.map(e => '<tr><th scope="row"><button class="text-button" data-open-report="' + esc(e.id) + '">' + esc(e.title || e.id) + '</button></th><td>' + esc(e.reason) + '</td></tr>').join('') + '</tbody></table>';
}

function renderRoundReport(r) {
  const article = $('#report-article');
  article.innerHTML = '<header class="report-head">' + meta([(r.full_benchmark ? 'Benchmark round' : 'Round'), 'task set ' + r.task_set, r.task_count + (r.task_count === 1 ? ' task' : ' tasks'), trackWords(r.track), r.runs.length + (r.runs.length === 1 ? ' run' : ' runs')]) +
    '<h1>' + esc((r.full_benchmark ? 'Standings on the ' : 'Standings on ') + r.task_count + '-task set') + '</h1>' + reportActions(r, 'round') + '</header>' +
    section('standings', 'Standings', standingsTable(r) + pairingsTable(r) + '' + excludedTable(r)) +
    section('hero', 'Pass rate', '<div data-slot="hero"></div>') +
    (r.trend.length > 1 ? section('trend', 'Over time', '<div data-slot="trend"></div>') : '') +
    section('paired', 'By category', pairedTable(r)) +
    section('failures', 'Task matrix', '<div data-slot="matrix"></div>') +
    section('runs', 'Runs', '<ul class="round-runs">' + r.runs.map(run => '<li><button class="text-button" data-open-report="' + esc(run.id) + '">' + esc(run.title || run.id) + '</button>' + meta([fmtDate(run.created_at), run.status, run.full_benchmark ? 'full benchmark' : '']) + '</li>').join('') + '</ul>') +
    section('caveats', 'What to keep in mind', '<ul class="caveats">' + r.caveats.map(c => '<li>' + esc(c) + '</li>').join('') + '</ul>') +
    section('method', 'How it was measured', methodList({ ...r, method: { ...r.method, track: r.track } })) +
    section('terms', 'Terms', termsList());
  $('[data-slot="hero"]', article).replaceWith(heroFigure(r, 'Pass rate per setup, pooled over ' + r.runs.length + ' ' + (r.runs.length === 1 ? 'run' : 'runs')));
  if (r.trend.length > 1) {
    const series = {};
    for (const t of r.trend) (series[t.series] = series[t.series] || []).push(t);
    $('[data-slot="trend"]', article).replaceWith(Charts.trend({ title: 'Monarch pass rate by run', series: Object.entries(series).map(([label, points]) => ({ label, family: 'monarch', points })), source: 'Each point is one run; whiskers show the 95% interval.' }));
  }
  const matrix = Charts.matrix({ tasks: r.tasks, setups: r.order.map(id => ({ id, name: setupName(r, id), baseline: id === r.baseline, family: setupFamily(setupName(r, id)) })), cells: r.matrix });
  const scroll = document.createElement('div'); scroll.className = 'table-scroll'; scroll.appendChild(matrix);
  $('[data-slot="matrix"]', article).replaceWith(scroll);
  bindReportActions(article, r);
}

function bindReportActions(article, r) {
  bindReportLinks(article);
  $$('[data-open-run-evidence]', article).forEach(b => b.onclick = () => openJob(b.dataset.openRunEvidence));
  $$('[data-evidence-anchor]', article).forEach(b => b.onclick = () => document.getElementById(b.dataset.evidenceAnchor)?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
  $$('[data-evidence-run]', article).forEach(b => b.onclick = async () => { await openJob(b.dataset.evidenceRun); setTimeout(() => $('[data-evidence="' + b.dataset.evidenceEvent + '"]')?.click(), 400); });
  const print = $('#report-print', article); if (print) print.onclick = () => window.print();
  const save = $('#report-save', article); if (save) save.onclick = () => saveReportHtml(article, r);
}

// The export is one file, so its stylesheet travels inline; the served page never does.
const styleTag = css => { const s = document.createElement('style'); s.textContent = css; return s.outerHTML; };

async function saveReportHtml(article, r) {
  const sheets = ['/vendor/radix-colors/radix-colors.css', '/tokens.css', '/ui.css', '/charts.css', '/report.css'];
  let css = '';
  for (const href of sheets) { try { css += (await (await fetch(href)).text()) + '\n'; } catch { /* the export still reads with system fonts */ } }
  const title = (r.title || 'Report') + ' — AI Labs';
  const html = '<!doctype html><html lang="en"' + (document.documentElement.classList.contains('dark') ? ' class="dark"' : '') + '><head><meta charset="utf-8"><title>' + esc(title) + '</title>' + styleTag(css) + '</head><body class="export"><main><article class="report">' + article.innerHTML.replace(/<div class="report-actions">[\s\S]*?<\/div>/, '') + '</article></main></body></html>';
  const url = URL.createObjectURL(new Blob([html], { type: 'text/html' })), a = document.createElement('a');
  a.href = url; a.download = ('report-' + (r.run || r.cohort) + '.html'); a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}

$('#nav-reports').onclick = () => { history.pushState(null, '', '#reports'); openReports(); };
window.openReports = openReports; window.openReport = openReport; window.openRound = openRound; window.reportRoute = reportRoute;
