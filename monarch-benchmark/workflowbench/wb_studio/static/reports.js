'use strict';
// Reports: the front door. A report reads verdict first, then the evidence.
// Every number comes from the server (report_data.py); this file only lays it out.
let currentReport = null, reportsSequence = 0;
const fmtPct = v => v === null || v === undefined ? '—' : Math.round(v * 100) + '%';
// Three significant figures below a dollar, cents above: $0.0284, $0.107, $1.26.
const fmtMoney = v => v === null || v === undefined ? 'unknown' : v === 0 ? '$0.00' : v >= 1 ? '$' + v.toFixed(2) : '$' + Number(v.toPrecision(3)).toString();
const fmtDate = s => s ? new Date(s).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '';
// One date per round: the day it ran, or the span when its runs cross days.
function roundDates(runs) {
  const stamps = runs.map(r => r.created_at && Date.parse(r.created_at)).filter(Boolean);
  if (!stamps.length) return '';
  const first = new Date(Math.min(...stamps)), last = new Date(Math.max(...stamps));
  if (fmtDate(first) === fmtDate(last)) return fmtDate(last);
  const sameYear = first.getFullYear() === last.getFullYear();
  return (sameYear ? first.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : fmtDate(first)) + ' – ' + fmtDate(last);
}
const trackWords = t => t === 'create-and-run' ? 'Workflow configuration' : 'Agentic requests';
const gradeClass = g => ({ Improvement: 'improvement', Regression: 'regression', Tradeoff: 'tradeoff', Tie: 'tie', Undecided: 'undecided' }[g] || 'none');
const meta = parts => '<p class="meta">' + parts.filter(Boolean).map(esc).join('<span class="sep">·</span>') + '</p>';
const gradeBadge = g => '<span class="grade ' + gradeClass(g.grade) + '">' + esc(g.grade) + '</span>';
const setupFamily = name => Charts.familyOf(name);

function reportRoute(hash) {
  const [path] = hash.split('?');
  if (path === '#reports' || path === '#leaderboard' || path === '' || path === '#') return openReports();
  if (path.startsWith('#report/')) { const [id, section] = path.slice(8).split('/').map(decodeURIComponent); return openReport(id, section); }
  if (path.startsWith('#round/')) { const [id, section] = path.slice(7).split('/').map(decodeURIComponent); return openRound(id, section); }
  return null;
}
// A report is a document: every section has an address, and the page is titled by the report.
let permalinkBase = '';
function goToSection(section) {
  const target = section && document.getElementById('report-' + section);
  if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
function settle(kind, id, section, title) {
  const base = '#' + kind + '/' + encodeURIComponent(id), want = section ? base + '/' + encodeURIComponent(section) : base;
  if (location.hash !== want && !location.hash.startsWith(base)) history.pushState(null, '', want);
  else if (location.hash !== want) history.replaceState(null, '', want);
  document.title = 'AI Labs — ' + title;
}

async function openReports() {
  showWorkspaceSurface('reports');
  const box = $('#reports-content'), sequence = ++reportsSequence;
  box.innerHTML = '<p class="meta">Loading</p>';
  try {
    const data = await api('/api/reports');
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
    box.innerHTML = '<div class="empty-state"><h3>No finished runs yet</h3><p>A report is written for every finished run and for every task set that has runs.</p><button class="button primary" id="reports-start">Start a run</button></div>';
    $('#reports-start').onclick = () => openLaunch();
    return;
  }
  const row = round => {
    const best = round.best ? '<strong>' + esc(round.best.name) + '</strong> passed ' + round.best.passed + ' of ' + round.best.attempts + ' (' + fmtPct(round.best.rate) + ')' : 'No evaluated attempts';
    const comparable = round.grade && round.grade.grade !== 'Not comparable';
    // A run name is one line here; the full name is on hover and as the report's own heading.
    return '<tr class="round-card">' + '<td class="round-runs-cell"><ul class="round-runs">' + round.runs.map(run => '<li><a href="#report/' + encodeURIComponent(run.id) + '" data-open-report="' + esc(run.id) + '" title="' + esc(run.title || run.id) + '">' + esc(run.title || run.id) + '</a>' + (run.status === 'completed' ? '' : meta([run.status])) + '</li>').join('') + '</ul></td>' +
      '<td class="round-date">' + esc(roundDates(round.runs)) + '</td>' +
      '<td class="round-lead">' + (comparable ? gradeBadge(round.grade) : '') + '<span>' + best + '</span>' + (comparable ? '<span class="meta">' + esc(round.grade.reason) + '</span>' : '') + '</td>' +
      '<td>' + round.task_count + ' ' + (round.task_count === 1 ? 'task' : 'tasks') + '<br><span class="meta">' + esc(trackWords(round.track)) + ' · ' + round.setups + (round.setups === 1 ? ' setup' : ' setups') + '</span></td>' +
      '<td class="action"><a href="#round/' + encodeURIComponent(round.id) + '" data-open-round="' + esc(round.id) + '">Round report</a></td></tr>';
  };
  const table = rows => '<table class="table reports-table"><thead><tr><th>Runs</th><th>Date</th><th>Result</th><th>Task set</th><th class="num">Report</th></tr></thead><tbody>' + rows.map(row).join('') + '</tbody></table>';
  const benchmark = data.rounds.filter(r => r.full_benchmark), other = data.rounds.filter(r => !r.full_benchmark);
  box.innerHTML = (benchmark.length ? '<h2 class="reports-group">Benchmark rounds</h2>' + table(benchmark) : '') +
    (other.length ? (benchmark.length ? '<h2 class="reports-group">Other task sets</h2>' : '') + table(other) : '');
  bindReportLinks(box);
}

function bindReportLinks(root) {
  $$('[data-open-report]', root).forEach(b => b.onclick = e => { e.preventDefault(); history.pushState(null, '', '#report/' + encodeURIComponent(b.dataset.openReport)); openReport(b.dataset.openReport); });
  $$('[data-open-round]', root).forEach(b => b.onclick = e => { e.preventDefault(); history.pushState(null, '', '#round/' + encodeURIComponent(b.dataset.openRound)); openRound(b.dataset.openRound); });
}

async function openReport(id, section) {
  showWorkspaceSurface('report', false);
  if (currentReport?.run === id && $('#report-article .report-head')) { settle('report', id, section, currentReport.title || 'Run report'); goToSection(section); return; }
  settle('report', id, section, 'Report');
  const article = $('#report-article'), sequence = ++reportsSequence;
  article.innerHTML = '<p class="meta">Loading report</p>';
  try {
    const data = await api('/api/reports/run/' + encodeURIComponent(id));
    if (sequence !== reportsSequence) return;
    currentReport = data; permalinkBase = '#report/' + encodeURIComponent(id); renderRunReport(data);
    document.title = 'AI Labs — ' + (data.title || 'Run report'); goToSection(section);
  } catch (e) { article.innerHTML = '<div class="empty-state"><h3>Report could not load</h3><p>' + esc(e.message) + '</p></div>'; }
}

async function openRound(id, section) {
  showWorkspaceSurface('report', false);
  if (currentReport?.cohort === id && $('#report-article .report-head')) { settle('round', id, section, roundTitle(currentReport)); goToSection(section); return; }
  settle('round', id, section, 'Round report');
  const article = $('#report-article'), sequence = ++reportsSequence;
  article.innerHTML = '<p class="meta">Loading report</p>';
  try {
    const data = await api('/api/reports/round/' + encodeURIComponent(id));
    if (sequence !== reportsSequence) return;
    currentReport = data; permalinkBase = '#round/' + encodeURIComponent(id); renderRoundReport(data);
    document.title = 'AI Labs — ' + roundTitle(data); goToSection(section);
  } catch (e) { article.innerHTML = '<div class="empty-state"><h3>Report could not load</h3><p>' + esc(e.message) + '</p></div>'; }
}
const roundTitle = r => (r.full_benchmark ? 'Benchmark standings, ' : 'Standings on ') + r.task_count + ' tasks' + (r.latest ? ', ' + (r.first && fmtDate(r.first) !== fmtDate(r.latest) ? fmtDate(r.first) + ' to ' + fmtDate(r.latest) : fmtDate(r.latest)) : '');

const section = (id, title, body) => '<section class="report-section" id="report-' + id + '"><h2><a class="section-link" href="' + permalinkBase + '/' + id + '">' + esc(title) + '</a></h2>' + body + '</section>';
const contents = ids => '<nav class="report-contents" aria-label="Contents"><ol>' + ids.map(([id, title]) => '<li><a href="' + permalinkBase + '/' + id + '">' + esc(title) + '</a></li>').join('') + '</ol></nav>';
const setupName = (r, id) => r.setups[id]?.short_name || r.setups[id]?.name || id;
const setupFullName = (r, id) => r.setups[id]?.name || id;

function reportActions(r, kind) {
  return '<div class="report-actions">' + (kind === 'run' ? '<a class="button small" href="#run/' + encodeURIComponent(r.run) + '" data-open-run-evidence="' + esc(r.run) + '">Open run</a>' : '') +
    '<button class="button small" id="report-print">Print</button><button class="button small" id="report-save">Save as HTML</button></div>';
}

function findingsList(findings, modelFindings, r) {
  const items = findings.map(f => '<li>' + esc(f.text) + ' ' + evidenceLink(f.evidence, r) + '</li>').join('');
  const model = modelFindings.map(f => '<li class="model-finding"><span class="meta">' + (f.fact ? 'from the record' : 'a reading') + '</span> <strong>' + esc(f.title) + '</strong> ' + esc(f.text) + ' ' + evidenceLink(f.evidence, r) + '</li>').join('');
  return '<ol class="findings">' + items + '</ol>' + (model ? '<h3>From the model, checked against the record</h3><ol class="findings model-findings">' + model + '</ol><p class="report-note">Written by the analysis model from the measures above; the numbers come from the record, never from the model.</p>' : '');
}

function evidenceLink(evidence, r) {
  if (!evidence) return '';
  if (evidence.kind === 'events' && evidence.event_ids?.length) return '<button class="text-button evidence" data-evidence-run="' + esc(r.run) + '" data-evidence-event="' + evidence.event_ids[0] + '">See event ' + evidence.event_ids[0] + (evidence.event_ids.length > 1 ? ' and ' + (evidence.event_ids.length - 1) + ' more' : '') + '</button>';
  const anchor = { hero: 'hero', matrix: 'failures', bucket: 'failures', attempts: 'failures', figure: 'cost', cost: 'cost', table: 'hero' }[evidence.kind] || 'hero';
  const words = { hero: 'See the pass-rate figure', matrix: 'See the task matrix', bucket: 'See the failures table', attempts: 'See the failures table', figure: 'See the cost figure', cost: 'See the cost table', table: 'See the pass-rate figure' };
  return '<a class="evidence" href="' + permalinkBase + '/' + anchor + '" data-evidence-anchor="report-' + anchor + '" data-evidence-setup="' + esc(evidence.setup || '') + '">' + esc(words[evidence.kind] || 'See the evidence') + '</a>';
}

function sourceText(r, what) { return 'Source: ' + (r.run ? 'run ' + String(r.run).slice(0, 12) : 'task set ' + String(r.task_set || '').slice(0, 12)); }
function sourceLine(r, what) { return '<p class="chart-source">' + esc(sourceText(r, what)) + '</p>'; }
function pairedTable(r) {
  if (!r.paired?.length) return '<p class="report-note">No evaluated attempts to compare.</p>';
  const head = '<tr><th>Category</th>' + r.order.map(id => '<th class="num' + (id === r.baseline ? ' baseline' : '') + '">' + esc(setupName(r, id)) + (id === r.baseline ? ' <span class="meta">Bare</span>' : '') + '</th>').join('') + '</tr>';
  const rows = r.paired.map(row => '<tr><th scope="row">' + esc(row.category) + '</th>' + r.order.map(id => {
    const c = row.cells[id];
    if (!c) return '<td class="num muted">—</td>';
    const delta = c.delta === null || c.delta === undefined ? '' : '<span class="delta ' + (c.delta > 0 ? 'up' : c.delta < 0 ? 'down' : 'flat') + '">' + (c.delta > 0 ? '+' : '') + c.delta + '</span>';
    return '<td class="num">' + c.passed + ' / ' + c.attempts + delta + '</td>';
  }).join('') + '</tr>').join('');
  return '<div class="table-scroll"><table class="paired"><thead>' + head + '</thead><tbody>' + rows + '</tbody></table></div>' + sourceLine(r, '');
}

function heroFigure(r, title) {
  const rows = r.hero.map(h => ({ ...h, family: setupFamily(h.label), sub: r.setups[h.id]?.pass?.attempts ? null : undefined, data: { setup: h.id } }));
  return Charts.dotWhisker({ title, rows, labelWidth: 220, source: sourceText(r, '') });
}

// The first sentence of a task's request is the name a person reads it by.
// Named for the report: app.js already owns a global `taskTitle(id)` and these
// scripts share one scope, so the shorter name here silently broke the run page.
function reportTaskTitle(r, id) {
  const t = (r.tasks || []).find(t => t.id === id)?.title || id;
  const first = t.split(/(?<=\.)\s/)[0];
  return first.length < t.length ? first : t;
}

// Failure modes as rows, setups as columns, counts in the cells. One glance
// answers the run's first question: a row heavy in one column is that setup's
// weakness; a row filled across every column points at the task, not the models.
function failureModes(r) {
  const failed = (r.failures?.attempts || []).filter(a => !a.passed && a.story);
  if (!failed.length) return null;
  const modes = new Map();
  for (const a of failed) {
    const m = modes.get(a.story.mode || 'unclassified') || { label: a.story.mode_label, attempts: 0, setups: {}, tasks: new Map() };
    m.attempts++; m.setups[a.model] = (m.setups[a.model] || 0) + 1;
    const t = m.tasks.get(a.task) || { counts: new Map(), example: a };
    t.counts.set(a.model, (t.counts.get(a.model) || 0) + 1);
    if (a.story.turning_point && !t.example.story.turning_point) t.example = a;
    m.tasks.set(a.task, t); modes.set(a.story.mode || 'unclassified', m);
  }
  const rows = [...modes.values()].sort((a, b) => b.attempts - a.attempts || a.label.localeCompare(b.label));
  // Three steps of one hue, cut against the heaviest cell: enough to find the eye, not a rainbow.
  const peak = Math.max(1, ...rows.flatMap(m => r.order.map(id => m.setups[id] || 0)));
  const level = n => !n ? 'n0' : n >= peak * 0.66 ? 'n3' : n >= peak * 0.34 ? 'n2' : 'n1';
  const count = (n, cls) => '<td class="count ' + cls + '">' + (n || '·') + '</td>';
  // The foot carries what the per-setup story table used to say: failures over attempts.
  // Both come from r.failures.attempts, so an infrastructure attempt counts on both sides.
  const recorded = r.failures?.attempts || [];
  const tried = {};
  for (const a of recorded) tried[a.model] = (tried[a.model] || 0) + 1;
  const over = (n, total) => '<td>' + n + ' of ' + total + '</td>';
  const table = document.createElement('table');
  table.className = 'chart-matrix fail-modes';
  table.innerHTML = '<thead><tr><th class="mode-head">How it failed</th>' + r.order.map(id => '<th class="setup">' + esc(setupName(r, id)) + '</th>').join('') +
    '<th class="setup">Failures</th><th class="setup">Tasks</th></tr></thead><tbody>' +
    rows.map(m => '<tr><th class="mode" scope="row">' + esc(m.label) + '</th>' + r.order.map(id => count(m.setups[id] || 0, level(m.setups[id] || 0))).join('') +
      count(m.attempts, 'total') + count(m.tasks.size, 'total') + '</tr>').join('') +
    '</tbody><tfoot><tr><th scope="row">Failed of attempts</th>' +
    r.order.map(id => over(rows.reduce((s, m) => s + (m.setups[id] || 0), 0), tried[id] || 0)).join('') +
    over(failed.length, recorded.length) + over(new Set(failed.map(a => a.task)).size, (r.tasks || []).length) + '</tr></tfoot>';
  return { table, rows };
}

// Under the table, the tasks behind each mode: one line per task, not per attempt.
function modeFolds(r, rows) {
  return '<p class="chart-title">Open a failure mode for the tasks behind it</p>' + rows.map(m => {
    const tasks = [...m.tasks.entries()].sort((a, b) => b[1].counts.size - a[1].counts.size || String(a[0]).localeCompare(String(b[0])));
    return '<details class="mode-fold"><summary><span class="mode-fold-label">' + esc(m.label) + '</span><span class="meta">' +
      m.attempts + (m.attempts === 1 ? ' attempt' : ' attempts') + ' · ' + m.tasks.size + (m.tasks.size === 1 ? ' task' : ' tasks') + '</span></summary>' +
      '<ul class="mode-tasks">' + tasks.map(([task, t]) => {
        const who = [...t.counts.entries()].map(([id, n]) => setupName(r, id) + (n > 1 ? ' ×' + n : '')).join(', ');
        const tp = t.example.story.turning_point;
        return '<li><p><a href="#run/' + encodeURIComponent(r.run) + '/' + encodeURIComponent(task) + '/' + encodeURIComponent(t.example.model) + '">' + esc(reportTaskTitle(r, task)) + '</a></p>' +
          '<p class="meta">' + esc(who) + '</p>' +
          (tp ? '<p>' + esc(tp.text) + ' ' + evidenceLink({ kind: 'events', event_ids: [tp.event_id] }, r) + '</p>' : '') + '</li>';
      }).join('') + '</ul></details>';
  }).join('');
}

function failuresBlock(r) {
  const summary = r.failures?.summary || {};
  const bars = (r.failures?.buckets || []).some(b => b.count)
    ? Charts.failureColumns({ buckets: r.failures.buckets, failed: summary.failed_attempts,
        title: summary.failed_attempts + ' of ' + summary.recorded_attempts + ' attempts failed', source: sourceText(r, '') })
    : null;
  const matrix = Charts.matrix({ tasks: r.tasks, setups: r.order.map(id => ({ id, name: setupName(r, id), baseline: id === r.baseline, family: setupFamily(setupName(r, id)) })), cells: r.matrix });
  const wrap = document.createElement('div'); wrap.className = 'failures-block';
  if (r.patterns) wrap.appendChild(reportPatternBlock(r));
  else if (bars) wrap.appendChild(bars); else { const p = document.createElement('p'); p.className = 'report-note'; p.textContent = 'No failed attempts.'; wrap.appendChild(p); }
  const grouped = r.patterns ? null : failureModes(r);
  if (grouped) {
    const cap = document.createElement('p'); cap.className = 'chart-title';
    cap.textContent = 'How it failed, by setup; a row filled across every column points at the task';
    wrap.appendChild(cap);
    const scroll = document.createElement('div'); scroll.className = 'table-scroll'; scroll.appendChild(grouped.table); wrap.appendChild(scroll);
    const list = document.createElement('div'); list.className = 'failure-modes';
    list.innerHTML = modeFolds(r, grouped.rows);
    wrap.appendChild(list);
  }
  const cap = document.createElement('p'); cap.className = 'chart-title'; cap.textContent = 'Tasks by setup, disagreements first' + (r.repetitions > 1 || r.method.repetitions > 1 ? '; cells show passes over repetitions' : ''); wrap.appendChild(cap);
  const scroll = document.createElement('div'); scroll.className = 'table-scroll'; scroll.appendChild(matrix); wrap.appendChild(scroll);
  const src = document.createElement('p'); src.className = 'chart-source'; src.textContent = sourceText(r, ''); wrap.appendChild(src);
  const claims = r.order.map(id => r.setups[id]).filter(s => s && s.false_completion?.count);
  if (claims.length) { const p = document.createElement('p'); p.className = 'report-note'; p.textContent = claims.map(s => s.name + ' reported the work as done in ' + s.false_completion.count + ' of ' + s.false_completion.failed + ' failed attempts (inferred from wording)').join('; ') + '.'; wrap.appendChild(p); }
  return wrap;
}

function costBlock(r) {
  const setups = r.order.map(id => r.setups[id]).filter(Boolean);
  const points = setups.map(s => ({ label: s.short_name || s.name, x: s.cost.per_attempt, y: s.pass.rate, low: s.pass.low, high: s.pass.high, baseline: s.is_baseline, family: setupFamily(s.name), data: { setup: s.id } }));
  const wrap = document.createElement('div'); wrap.className = 'cost-block';
  const anyCost = points.some(p => p.x > 0);
  if (anyCost) wrap.appendChild(Charts.scatter({ title: 'Cost per attempt against pass rate', points: points.filter(p => p.x > 0), xLog: true, pareto: points.filter(p => p.x > 0).length > 1, source: sourceText(r, '') }));
  const tokens = setups.filter(s => Object.values(s.cost.tokens).some(v => v)).map(s => ({ label: s.short_name || s.name, parts: s.cost.tokens }));
  if (tokens.length) {
    // The chart refits its SVG on resize; the report legend stays in normal text flow.
    const figure = document.createElement('div'); figure.className = 'report-token-chart';
    figure.appendChild(Charts.waterfall({ title: 'Tokens by kind', rows: tokens, labelWidth: 220, source: sourceText(r, '') }));
    const legend = document.createElement('ul'); legend.className = 'report-token-legend'; legend.setAttribute('aria-label', 'Token kinds');
    legend.innerHTML = [['uncached', 'Uncached input'], ['cache_write', 'Cache writes'], ['cached', 'Cache reads'], ['output', 'Output']].map(([id, label]) => '<li><span class="report-token-swatch token-' + id + '" aria-hidden="true"></span>' + label + '</li>').join('');
    figure.appendChild(legend); wrap.appendChild(figure);
  }
  const table = document.createElement('table'); table.className = 'paired cost-table';
  table.innerHTML = '<thead><tr><th>Setup</th><th class="num">Per attempt</th><th class="num">Per passed task</th><th class="num">Total</th><th class="num">Unpriced attempts</th><th class="num">Typical time</th></tr></thead><tbody>' +
    setups.map(s => '<tr data-setup="' + esc(s.id) + '"><th scope="row">' + esc(s.short_name || s.name) + '</th><td class="num">' + esc(fmtMoney(s.cost.per_attempt)) + '</td><td class="num">' + (s.pass.passed === 0 && s.cost.per_pass === null ? 'no passes' : esc(fmtMoney(s.cost.per_pass))) + '</td><td class="num">' + esc(fmtMoney(s.cost.total)) + '</td><td class="num">' + s.cost.unknown_attempts + '</td><td class="num">' + (s.time.median === null ? '—' : s.time.median.toFixed(1) + 's') + '</td></tr>').join('') + '</tbody>';
  const tscroll = document.createElement('div'); tscroll.className = 'table-scroll'; tscroll.appendChild(table); wrap.appendChild(tscroll);
  const csrc = document.createElement('p'); csrc.className = 'chart-source'; csrc.textContent = sourceText(r, ''); wrap.appendChild(csrc);
  return wrap;
}


// Terms a reader meets in a report, said once, in plain words.
const REPORT_TERMS = [
  ['Setup', 'One competitor as configured for the run: a model with its tools and thinking setting, an architecture built in the Studio, or Monarch itself.'],
  ['Bare', 'The same model with the same tools and nothing else around it. Every setup is compared against Bare.'],
  ['Task', 'One request in plain language, its starting data, and an approval rule saying what must change and what must not.'],
  ['Attempt', 'One task tried once by one setup.'],
  ['Pass', 'The expected result is present, nothing else changed, and the attempt finished normally. Anything less is a fail.'],
  ['95% interval', 'The range the pass rate would most likely fall in if the same tasks ran again; the whiskers on the pass-rate figure. Few tasks give a wide range.'],
  ['Paired comparison', 'The setup and Bare on exactly the same tasks, counted task by task as better, worse or the same. In the category table the small number is how many more or fewer tasks the setup passed than Bare; green is more, red is fewer. The chance sentence is a sign test.'],
  ['Failure reason', 'Read from the record by fixed rules, one per failed attempt, never guessed.'],
  ['Cost', 'Settled provider receipts per setup; an attempt without a receipt is counted but not costed, and a setup missing any receipt is left off the cost figure.'],
  ['Grade', 'One word for the paired comparison: Improvement, Regression, Tie, Tradeoff when the tasks and the cost point in opposite directions, or Not comparable when there is no Bare to compare against.'],
  ['Thinking setting', 'How much reasoning effort the model was allowed per request.'],
  ['Violation', 'A change the task did not permit. One violation fails the attempt even when the requested result is present.'],
];

function methodList(r) {
  const m = r.method;
  const rows = [['Task set', m.task_set + (m.benchmark ? ' (' + m.benchmark + ')' : '') + ' · ' + m.task_count + ' tasks'], ['Track', trackWords(m.track || r.track)], ['Repetitions', String(m.repetitions || 1)], ['Interval', 'Wilson score, 95%, on attempts; it does not include task-selection variance'],
    ['Judge', m.judge ? (m.judge.id + ' · ' + String(m.judge.sha256 || '').slice(0, 12)) : 'historical, unpinned'], ['Corpus', 'AutomationBench ' + m.fork],
    ['Runs', (m.runs || []).join(', ')], ['Setups', (r.order || []).map(id => setupFullName(r, id)).join('; ')], ['Attempts', m.recorded_attempts !== undefined ? m.recorded_attempts + ' recorded of ' + m.planned_attempts + ' planned' : ''],
    ['Concurrency', m.concurrency ? String(m.concurrency) : ''], ['Spending limit', m.maximum_usd ? '$' + m.maximum_usd : ''], ['Instructions', m.configuration ? (m.configuration.prompt ? 'custom' : 'original task text') + (m.configuration.max_turns ? ' · ' + m.configuration.max_turns + ' turns max' : '') : '']];
  return '<dl class="method">' + rows.filter(([, v]) => v).map(([k, v]) => '<dt>' + esc(k) + '</dt><dd>' + esc(v) + '</dd>').join('') + '</dl>';
}

// Report prose is data: render paragraphs and evidence links without interpreting HTML.
function reportParagraphs(value) {
  return String(value || '').split(/\n\s*\n/).filter(s => s.trim()).map(s => '<p>' + esc(s.trim()) + '</p>').join('');
}
function reportEventLinks(ids, run) {
  return (ids || []).map(id => '<button class="text-button evidence" data-evidence-run="' + esc(run) + '" data-evidence-event="' + Number(id) + '">Event ' + Number(id) + '</button>').join(' · ');
}
function reportWorkNote(r) {
  const w = r.report_work || {}, phase = w.stage || w.status;
  const labels = { analysis: 'Genesis is reading the attempts', author: 'Genesis is writing the report', review: 'The report is being reviewed', repair: 'Genesis is addressing the review', review_again: 'The revised report is being reviewed', failed: 'Report authoring stopped', interrupted: 'Report authoring was interrupted' };
  if (!labels[phase]) return '';
  return '<div class="report-work" role="status"><p>' + esc(labels[phase]) + (w.reason || w.error ? '. ' + esc(w.reason || w.error) : '.') + '</p><button class="text-button" data-report-refresh="' + esc(r.run) + '">Refresh report status</button></div>';
}
function authoredFindings(r) {
  return '<ol class="findings">' + (r.authored.findings || []).map(f => '<li><strong>' + esc(f.title) + '</strong> ' + esc(f.explanation) + ' <span class="meta">' + (f.kind === 'fact' ? 'Observed' : 'Hypothesis') + '</span> ' + reportEventLinks(f.event_ids, r.run) + '</li>').join('') + '</ol>';
}
function authoredSections(r, part = "analysis") {
  const a = r.authored;
  if (!a || a.status !== 'completed') return '';
  const blocks = [['What went right', a.what_went_right], ['What went wrong', a.what_went_wrong], ['Why this happened', a.why], ['What would test this explanation', a.next_experiment], ['Limits of this analysis', a.limitations]];
  const detail = blocks.filter(([, body]) => body).map(([title, body]) => '<h3>' + title + '</h3>' + reportParagraphs(body)).join('');
  const attempts = (a.attempts || []).map(t => '<details class="report-attempt" id="report-attempt-' + t.index + '"><summary>' + esc(reportTaskTitle(r, t.task)) + '<span class="meta">' + esc(setupName(r, t.model)) + ' · recorded attempt ' + (t.index + 1) + '</span></summary>' + reportParagraphs(t.explanation) + '<dl>' + [['Expected', t.expected], ['Observed', t.observed], ['Possible mechanism', t.mechanism], ['Alternative explanations', t.alternatives], ['Confidence in interpretation', t.confidence], ['Missing evidence', t.missing_evidence]].map(([label, text]) => '<dt>' + label + '</dt><dd>' + esc(text || 'Not recorded') + '</dd>').join('') + '</dl><p>' + reportEventLinks(t.event_ids, r.run) + '</p></details>').join('');
  if (part === 'attempts') return section('attempts', 'Every attempt', attempts);
  return section('analysis', 'Analysis', '<p class="report-note">Genesis report · revision ' + esc(a.revision) + ' · reviewed interpretation; recorded verdicts remain authoritative.</p>' + detail);
}
function roundAnalyses(r) {
  if (!r.run_analyses?.length) return '';
  return section('analysis', 'Run analyses', '<p class="report-note">Each interpretation applies to the named run. The pooled results below do not establish a shared cause.</p>' + r.run_analyses.map(row => '<div class="run-analysis"><h3><a href="#report/' + encodeURIComponent(row.run) + '" data-open-report="' + esc(row.run) + '">' + esc(row.title || row.run) + '</a></h3>' + (row.authored?.status === 'completed' ? reportParagraphs(row.authored.summary) + '<p class="meta">Genesis · revision ' + esc(row.authored.revision) + ' · <a href="#report/' + encodeURIComponent(row.run) + '/analysis">Read the full analysis</a></p>' : '<p class="report-note">' + esc(({analysis: 'Analysis in progress', author: 'Report being written', review: 'Review in progress', repair: 'Revision in progress', review_again: 'Re-review in progress', failed: 'Report authoring stopped'}[(row.report_work || {}).stage] || 'No reviewed analysis published yet')) + '</p>') + '</div>').join(''));
}

// Percentages and exact membership come from report_patterns.py. This renderer never classifies attempts.
function reportPatternBlock(r) {
  const data = r.patterns, wrap = document.createElement('div'); wrap.className = 'report-patterns';
  if (!data?.setups?.length) { wrap.innerHTML = '<p class="report-note">No recorded outcome mix is available.</p>'; return wrap; }
  wrap.innerHTML = '<h3>Outcome mix by setup</h3><p class="report-note">' + esc(data.denominator) + '</p><label class="pattern-control">Show <select aria-label="Outcome classification"><option value="behavior">Recorded behavior</option><option value="checks">Checker outcomes</option></select></label><div class="pattern-view"></div><div class="pattern-detail" aria-live="polite"></div>';
  const panel = wrap.querySelector('.pattern-detail');
  function showAttempts(slice, column) {
    panel.innerHTML = '<h4>' + esc(column.name + ' · ' + slice.label) + '</h4><p class="report-note">' + slice.count + ' of ' + column.total + ' attempts · ' + slice.percent + '%</p><ol class="pattern-attempts">' + slice.attempts.map(a => '<li><p><a href="#run/' + encodeURIComponent(a.run) + '/' + encodeURIComponent(a.task) + '/' + encodeURIComponent(a.model) + '">' + esc(reportTaskTitle(r, a.task)) + '</a> <span class="meta">Attempt ' + (a.index + 1) + (r.cohort ? ' · run ' + esc(String(a.run).slice(0, 12)) : '') + '</span></p>' + reportParagraphs(a.explanation) + '<p class="meta">Termination: ' + esc(a.termination || 'unknown') + (a.liveness && a.liveness !== 'live' ? ' · historical task version; not regradable against the current task' : '') + '</p><p>' + (a.event_ids.length ? reportEventLinks(a.event_ids, a.run) : 'No trace events retained for this attempt.') + '</p></li>').join('') + '</ol>';
    panel.querySelectorAll('[data-evidence-run]').forEach(b => b.onclick = async () => { await openJob(b.dataset.evidenceRun); setTimeout(() => $('[data-evidence="' + b.dataset.evidenceEvent + '"]')?.click(), 400); });
  }
  function draw(field) {
    const view = wrap.querySelector('.pattern-view'); view.replaceChildren(); panel.innerHTML = '';
    const source = document.createElement('p'); source.className = 'report-note'; source.textContent = data[field === 'behavior' ? 'behavior_basis' : 'checks_basis']; view.appendChild(source);
    const columns = data.setups, width = Math.max(340, columns.length * 152 + 44), height = 346, top = 26, chartHeight = 224;
    const ns = 'http://www.w3.org/2000/svg';
    const el = (tag, attrs, parent, text) => { const n = document.createElementNS(ns, tag); Object.entries(attrs || {}).forEach(([k,v]) => n.setAttribute(k,v)); if (text !== undefined) n.textContent = text; parent.appendChild(n); return n; };
    const scroll = document.createElement('div'); scroll.className = 'pattern-chart'; scroll.tabIndex = 0; scroll.setAttribute('role', 'region'); scroll.setAttribute('aria-label', 'Outcome percentages by setup; scroll horizontally for more setups'); view.appendChild(scroll);
    const svg = el('svg', {width, height, viewBox: '0 0 ' + width + ' ' + height, role:'group', 'aria-label': field === 'behavior' ? 'Recorded behavior: percentage of all attempts' : 'Checker outcomes: percentage of all attempts'}, scroll);
    for (const percent of [0,25,50,75,100]) {
      const y = top + chartHeight * (1 - percent / 100);
      el('line', {x1:44, x2:width, y1:y, y2:y, class:'pattern-grid'}, svg);
      el('text', {x:36, y:y+4, 'text-anchor':'end', class:'pattern-axis'}, svg, percent + '%');
    }
    columns.forEach((column, i) => {
      const x = 62 + i * 152; let filled = 0;
      if (!column.total) el('text', {x:x+38, y:top+chartHeight/2, 'text-anchor':'middle', class:'pattern-axis'}, svg, 'No results');
      column[field].forEach(slice => {
        if (!slice.count) return;
        const h = chartHeight * slice.percent / 100, y = top + chartHeight - filled - h; filled += h;
        const label = column.name + ': ' + slice.label + ', ' + slice.count + ' of ' + column.total + ' attempts (' + slice.percent + '%)';
        const rect = el('rect', {x, y, width:76, height:h, class:'pattern-slice slice-' + slice.id, tabindex:0, role:'button', 'aria-label':label}, svg); el('title', {}, rect, label);
        rect.onclick = () => showAttempts(slice, column); rect.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); showAttempts(slice, column); } };
        if (slice.percent >= 12) el('text', {x:x+84, y:y+h/2+4, 'text-anchor':'start', class:'pattern-value slice-label-' + slice.id, 'pointer-events':'none'}, svg, slice.percent + '%');
      });
      el('text', {x:x+38, y:top+chartHeight+21, 'text-anchor':'middle', class:'pattern-total'}, svg, 'n = ' + column.total);
      const words = column.name.split(/\s+/), lines = [''];
      for (const word of words) { if ((lines.at(-1) + ' ' + word).trim().length > 21 && lines.at(-1)) lines.push(''); lines[lines.length-1] += (lines.at(-1) ? ' ' : '') + word; }
      const name = el('text', {x:x+38, y:top+chartHeight+43, 'text-anchor':'middle', class:'pattern-name'}, svg);
      lines.slice(0,3).forEach((line,j) => el('tspan', {x:x+38, dy:j ? 16 : 0}, name, line.length > 23 ? line.slice(0,20) + '…' : line)); el('title', {}, name, column.name);
    });
    const categories = columns[0][field].filter(s => columns.some(c => c[field].some(other => other.id === s.id && other.count)));
    const legend = document.createElement('ul'); legend.className = 'pattern-legend';
    legend.innerHTML = categories.map(s => '<li><span class="pattern-swatch slice-' + s.id + '"></span>' + esc(s.label) + '</li>').join(''); view.appendChild(legend);
    const detail = document.createElement('details'); detail.className = 'pattern-counts';
    detail.innerHTML = '<summary>Exact counts and attempt links</summary><div class="table-scroll"><table class="paired"><caption>Each cell is count / all attempts for that setup, followed by percentage.</caption><thead><tr><th>Outcome</th>' + columns.map(c => '<th scope="col">' + esc(c.name) + '</th>').join('') + '</tr></thead><tbody>' + categories.map(s => '<tr><th scope="row">' + esc(s.label) + '</th>' + columns.map((c,i) => { const v = c[field].find(v => v.id === s.id); return '<td class="num">' + (v.count ? '<button class="text-button" data-pattern-column="' + i + '" data-pattern-slice="' + s.id + '">' : '') + v.count + ' / ' + c.total + ' · ' + (v.percent === null ? 'unknown' : v.percent + '%') + (v.count ? '</button>' : '') + '</td>'; }).join('') + '</tr>').join('') + '</tbody></table></div>';
    view.appendChild(detail);
    detail.querySelectorAll('[data-pattern-column]').forEach(button => button.onclick = () => { const c = columns[Number(button.dataset.patternColumn)]; showAttempts(c[field].find(s => s.id === button.dataset.patternSlice), c); });
    const historical = columns.some(c => c.historical);
    if (historical) { const note = document.createElement('p'); note.className = 'report-note'; note.textContent = 'This outcome mix includes recorded historical task versions. The quality comparison excludes tasks that no longer match; exact attempts identify those records.'; view.appendChild(note); }
    const src = document.createElement('p'); src.className = 'chart-source'; src.textContent = sourceText(r, 'recorded attempts; percentages rounded to 0.01%'); view.appendChild(src);
  }
  wrap.querySelector('select').onchange = e => draw(e.target.value); draw('behavior');
  if (data.domains.length > 1) {
    const domains = document.createElement('details'); domains.className = 'pattern-domains';
    domains.innerHTML = '<summary>By business domain</summary><p class="report-note">Each cell uses that setup’s attempts in the named domain. Select a pattern to inspect its attempts.</p><div class="table-scroll"><table class="paired"><thead><tr><th>Domain</th>' + data.setups.map(c => '<th scope="col">' + esc(c.name) + '</th>').join('') + '</tr></thead><tbody>' + data.domains.map((d,di) => '<tr><th scope="row">' + esc(d.label) + '</th>' + d.setups.map((c,ci) => { const pass = c.behavior.find(s => s.id === 'passed'), failed = c.behavior.filter(s => s.id !== 'passed' && s.count).sort((a,b) => b.count-a.count); return '<td>' + (c.total ? pass.count + ' / ' + c.total + ' passed' + failed.map(s => '<br><button class="text-button" data-domain="' + di + '" data-domain-setup="' + ci + '" data-domain-slice="' + s.id + '">' + esc(s.label) + ': ' + s.count + ' / ' + c.total + ' · ' + s.percent + '%</button>').join('') : 'No results') + '</td>'; }).join('') + '</tr>').join('') + '</tbody></table></div>';
    domains.querySelectorAll('[data-domain]').forEach(b => b.onclick = () => { const c = data.domains[Number(b.dataset.domain)].setups[Number(b.dataset.domainSetup)]; showAttempts(c.behavior.find(s => s.id === b.dataset.domainSlice), c); });
    wrap.appendChild(domains);
  }
  return wrap;
}

function narrativeBlock(r) {
  const n = r.narrative || {};
  if (n.status === 'failed') return '<p class="meta">The model reading did not complete; the recorded verdicts stand on their own.</p>';
  if (n.status === 'completed' || !n.reason || /nothing to interpret|scripted/i.test(n.reason)) return '';
  return '<p class="meta">Analysis due: ' + esc(n.reason) + '</p>';
}
function modelReadingSection(r) {
  const n = r.narrative || {};
  if (n.status !== 'completed') return '';
  return section('reading', 'Model reading', '<div class="model-reading"><p class="meta">' + esc(n.model || '') + (n.effort ? ' · ' + esc(n.effort) + ' thinking' : '') + ' · checked against the record, never a verdict</p><p>' + esc(n.summary || '') + '</p>' + (n.what_went_right ? '<p><strong>What went right.</strong> ' + esc(n.what_went_right) + '</p>' : '') + (n.what_went_wrong ? '<p><strong>What went wrong.</strong> ' + esc(n.what_went_wrong) + '</p>' : '') + (n.next_experiment ? '<p><strong>Next experiment.</strong> ' + esc(n.next_experiment) + '</p>' : '') + '</div>');
}
function storySection(r) {
  const s = r.story;
  if (!s || !s.setups.length) return '';
  // How each setup failed is the matrix in "Where it failed"; this section is the reading of it.
  const suspect = s.suspect_tasks.length ? '<p><strong>Suspect the task first.</strong> ' + s.suspect_tasks.map(t => esc(t.task) + ' (' + esc(t.mode_label.toLowerCase()) + ', every setup)').join('; ') + '.</p>' : '';
  return section('story', 'What went right and wrong', s.paragraphs.map(p => '<p>' + esc(p) + '</p>').join('') + suspect);
}
function termsList(r) {
  const names = new Set(['Setup', 'Task', 'Attempt', 'Pass', '95% interval']);
  if (r?.baseline) ['Bare', 'Paired comparison', 'Grade'].forEach(x => names.add(x));
  if (Object.values(r?.setups || {}).some(s => /thinking|reasoning|effort/i.test(s.name || ''))) names.add('Thinking setting');
  if ((r?.failures?.buckets || []).some(b => b.id === 'unintended_changes' && b.count) || (r?.paired || []).some(row => /outside|violation/i.test(row.category || ''))) names.add('Violation');
  return '<details class="report-terms-fold"><summary>Terms used in this report</summary><dl class="report-terms">' + REPORT_TERMS.filter(([term]) => names.has(term)).map(([term, text]) => '<dt>' + esc(term) + '</dt><dd>' + esc(text) + '</dd>').join('') + '</dl></details>';
}

function renderRunReport(r) {
  const article = $('#report-article');
  const authored = r.authored?.status === 'completed';
  const reading = !authored && (r.narrative || {}).status === 'completed';
  article.innerHTML = '<header class="report-head"><h1>' + esc(r.title || 'Run report') + '</h1>' + meta(['Run ' + String(r.run).slice(0, 12), r.method.task_count + (r.method.task_count === 1 ? ' task' : ' tasks'), r.order.length + (r.order.length === 1 ? ' setup' : ' setups'), trackWords(r.track), fmtDate(r.finished_at || r.created_at)]) +
    '<div class="grade-line">' + gradeBadge(r.grade) + '<span class="grade-reason">' + esc(r.grade.reason) + '</span></div>' + reportActions(r, 'run') + '</header>' +
    contents([['verdict', authored ? 'The result' : 'Verdict'], ['findings', 'Findings'], ...(authored ? [['analysis', 'Analysis']] : r.story && r.story.setups.length ? [['story', 'What went right and wrong']] : []), ...(reading ? [['reading', 'Model reading']] : []), ['hero', 'Pass rate'], ['paired', 'By category'], ['failures', 'Where it failed'], ['cost', 'What it cost'], ...(r.performance ? [['performance', 'Time and reliability']] : []), ['caveats', 'What to keep in mind'], ['method', 'How it was measured']]) +
    section('verdict', authored ? 'The result' : 'Verdict', '<p class="verdict">' + esc(authored ? r.authored.summary : r.verdict) + '</p>' + (authored ? '<p class="report-note">Recorded comparison: ' + esc(r.verdict) + '</p>' : narrativeBlock(r)) + reportWorkNote(r)) +
    section('findings', 'Findings', authored ? authoredFindings(r) : findingsList(r.findings, r.model_findings, r)) + (authored ? authoredSections(r) : storySection(r) + modelReadingSection(r)) +
    section('hero', 'Pass rate', '<div data-slot="hero"></div>') +
    section('paired', 'By category', pairedTable(r)) +
    section('failures', 'Where it failed', '<div data-slot="failures"></div>') +
    section('cost', 'What it cost', '<div data-slot="cost"></div>') + (authored ? authoredSections(r, 'attempts') : '') +
    (r.performance ? section('performance', 'Time and reliability', '<div data-slot="performance"></div>') : '') +
    section('caveats', 'What to keep in mind', '<ul class="caveats">' + r.caveats.map(c => '<li>' + esc(c) + '</li>').join('') + '</ul>') +
    section('method', 'How it was measured', methodList(r)) + termsList(r);
  const subject = r.setups[r.subject], base = r.setups[r.baseline];
  const heroTitle = subject ? subject.name + ' passed ' + subject.pass.passed + ' of ' + subject.pass.attempts + (base ? ', ' + base.name + ' ' + base.pass.passed + ' of ' + base.pass.attempts : '') : 'Pass rate per setup';
  $('[data-slot="hero"]', article).replaceWith(heroFigure(r, heroTitle));
  $('[data-slot="failures"]', article).replaceWith(failuresBlock(r));
  $('[data-slot="cost"]', article).replaceWith(costBlock(r));
  if(r.performance)PerformanceView.paint($('[data-slot="performance"]',article),r.performance);
  bindReportActions(article, r);
}

function standingsTable(r) {
  if (!r.standings.length) return '<p class="report-note">No evaluated attempts on this task set yet.</p>';
  const k = r.repetitions > 1, overTasks = r.standings.some(s => s.interval?.unit === 'tasks');
  const interval = s => { const i = s.interval || s.pass; return i.low == null ? '—' : fmtPct(i.low) + '–' + fmtPct(i.high); };
  const rankText = s => s.rank_high && s.rank_high !== s.rank ? s.rank + ' to ' + s.rank_high : String(s.rank);
  return '<div class="table-scroll"><table class="paired standings"><thead><tr><th>Rank</th><th>Setup</th><th class="num">Passed</th><th class="num">Rate</th><th class="num">95% interval' + (overTasks ? ' over tasks' : '') + '</th>' + (k ? '<th class="num">Passed all ' + r.repetitions + ' times</th>' : '') + '<th class="num">Per attempt</th><th>Against Bare</th></tr></thead><tbody>' +
    r.standings.map(s => '<tr' + (s.is_baseline ? ' class="baseline-row"' : '') + ' data-setup="' + esc(s.id) + '"><td class="num">' + rankText(s) + '</td><th scope="row">' + esc(s.name) + (s.is_baseline ? ' <span class="meta">Bare</span>' : '') + '</th><td class="num">' + s.pass.passed + ' / ' + s.pass.attempts + '</td><td class="num">' + fmtPct(s.pass.rate) + '</td><td class="num">' + interval(s) + '</td>' + (k ? '<td class="num">' + (s.pass_k.k ? fmtPct(s.pass_k.rate) : '—') + '</td>' : '') + '<td class="num">' + esc(fmtMoney(s.cost.per_attempt)) + '</td><td>' + (s.grade ? gradeBadge(s.grade) + (s.paired?.comparable ? ' <span class="meta">' + s.paired.wins + 'W ' + s.paired.losses + 'L ' + s.paired.ties + 'T</span>' : '') : '') + '</td></tr>').join('') + '</tbody></table></div>' + (r.standings.some(s => s.rank_high && s.rank_high !== s.rank) ? '<p class="report-note">A rank is one plus the number of setups whose whole interval sits above; setups whose intervals overlap share the spread.</p>' : '');
}

// Every pairing on the frozen set. Bare sits on the "against" side; colour only
// there, and always with a sign and a word.
function pairingsTable(r) {
  if (!r.pairings?.length) return '';
  const rows = r.pairings.map(p => p.a === r.baseline ? { setup: p.b, against: p.a, tasks: p.tasks, wins: p.losses, losses: p.wins, ties: p.ties, only: p.unique_b, onlyAgainst: p.unique_a } : { setup: p.a, against: p.b, tasks: p.tasks, wins: p.wins, losses: p.losses, ties: p.ties, only: p.unique_a, onlyAgainst: p.unique_b });
  const net = x => { const d = x.wins - x.losses, sign = d > 0 ? '+' : d < 0 ? '−' : '±', bare = x.against === r.baseline; return '<td class="num ' + (bare ? (d > 0 ? 'pass' : d < 0 ? 'fail' : 'neutral') : '') + '">' + sign + Math.abs(d) + (bare ? ' ' + (d > 0 ? 'better' : d < 0 ? 'worse' : 'even') : '') + '</td>'; };
  return '<h3>Pairings</h3><div class="table-scroll"><table class="paired pairings"><thead><tr><th>Setup</th><th>Against</th><th class="num">Tasks</th><th class="num">Wins</th><th class="num">Losses</th><th class="num">Ties</th><th class="num">Only setup</th><th class="num">Only against</th><th class="num">Net</th></tr></thead><tbody>' +
    rows.map(x => '<tr><th scope="row">' + esc(setupName(r, x.setup)) + '</th><td>' + esc(setupName(r, x.against)) + (x.against === r.baseline ? ' <span class="meta">Bare</span>' : '') + '</td><td class="num">' + x.tasks + '</td><td class="num">' + x.wins + '</td><td class="num">' + x.losses + '</td><td class="num">' + x.ties + '</td><td class="num">' + x.only + '</td><td class="num">' + x.onlyAgainst + '</td>' + net(x) + '</tr>').join('') + '</tbody></table></div>';
}

function excludedTable(r) {
  // Every run in the round counts here; this names the ones the frozen benchmark leaderboard would not take, and only on a benchmark round.
  if (!r.excluded?.length || !r.full_benchmark) return '';
  return '<h3>Not eligible for the benchmark leaderboard</h3><div class="table-scroll"><table class="paired excluded"><thead><tr><th>Run</th><th>Reason</th></tr></thead><tbody>' +
    r.excluded.map(e => '<tr><th scope="row"><a href="#report/' + encodeURIComponent(e.id) + '" data-open-report="' + esc(e.id) + '">' + esc(e.title || e.id) + '</a></th><td>' + esc(e.reason) + '</td></tr>').join('') + '</tbody></table></div>';
}

function renderRoundReport(r) {
  const article = $('#report-article');
  const when = r.first && r.latest && fmtDate(r.first) !== fmtDate(r.latest) ? fmtDate(r.first) + ' to ' + fmtDate(r.latest) : fmtDate(r.latest);
  article.innerHTML = '<header class="report-head"><h1>' + esc(roundTitle(r)) + '</h1>' + meta([(r.full_benchmark ? 'Benchmark round' : 'Round'), 'task set ' + r.task_set, r.task_count + (r.task_count === 1 ? ' task' : ' tasks'), trackWords(r.track), r.runs.length + (r.runs.length === 1 ? ' run' : ' runs'), when]) +
    (r.note ? '<p class="report-note">' + esc(r.note) + '</p>' : '') +
    reportActions(r, 'round') + '</header>' +
    contents([['standings', 'Standings'], ...(r.run_analyses?.length ? [['analysis', 'Run analyses']] : []), ['hero', 'Pass rate'], ...(r.trend.length > 1 ? [['trend', 'Over time']] : []), ['curve', 'What it costs to run again'], ['paired', 'By category'], ['failures', 'Outcome patterns'], ['caveats', 'What to keep in mind'], ['method', 'How it was measured']]) +
    section('standings', 'Standings', standingsTable(r) + pairingsTable(r) + '' + excludedTable(r)) + roundAnalyses(r) +
    section('hero', 'Pass rate', '<div data-slot="hero"></div>') +
    (r.trend.length > 1 ? section('trend', 'Over time', '<div data-slot="trend"></div>') : '') +
    section('curve', 'What it costs to run again', '<div data-slot="curve"></div>') +
    section('paired', 'By category', pairedTable(r)) +
    section('failures', 'Outcome patterns', '<div data-slot="patterns"></div><h3>Tasks by setup</h3><div data-slot="matrix"></div>') +
    section('caveats', 'What to keep in mind', '<ul class="caveats">' + r.caveats.map(c => '<li>' + esc(c) + '</li>').join('') + '</ul>') +
    section('method', 'How it was measured', methodList({ ...r, method: { ...r.method, track: r.track } }) + '<h3>Runs in this round</h3><ul class="round-runs">' + r.runs.map(run => '<li><a href="#report/' + encodeURIComponent(run.id) + '" data-open-report="' + esc(run.id) + '">' + esc(run.title || run.id) + '</a>' + meta([fmtDate(run.created_at), run.status === 'completed' ? '' : run.status, run.full_benchmark ? 'full benchmark' : '']) + '</li>').join('') + '</ul>') + termsList(r);
  $('[data-slot="hero"]', article).replaceWith(heroFigure(r, 'Pass rate per setup, pooled over ' + r.runs.length + ' ' + (r.runs.length === 1 ? 'run' : 'runs')));
  if (r.trend.length > 1) {
    const series = {};
    for (const t of r.trend) (series[t.series] = series[t.series] || []).push(t);
    // Title and colour come from the data. Both were constants: every round was titled
    // "Monarch pass rate by run" and every series drawn in the Monarch colour, whatever
    // the cohort held (feature 024, FR-015).
    $('[data-slot="trend"]', article).replaceWith(Charts.trend({ title: r.trend_title || 'Pass rate by run', series: Object.entries(series).map(([label, points]) => ({ label, family: setupFamily(label), points })), source: 'Each point is one run; whiskers show the 95% interval.' }));
  }
  drawCurve(article, r);
  $('[data-slot="patterns"]', article)?.replaceWith(reportPatternBlock(r));
  const matrix = Charts.matrix({ tasks: r.tasks, setups: r.order.map(id => ({ id, name: setupName(r, id), baseline: id === r.baseline, family: setupFamily(setupName(r, id)) })), cells: r.matrix });
  const scroll = document.createElement('div'); scroll.className = 'table-scroll'; scroll.appendChild(matrix);
  const msrc = document.createElement('p'); msrc.className = 'chart-source'; msrc.textContent = sourceText(r, 'one cell per task and setup, pooled over ' + (r.runs || []).length + ' runs'); scroll.appendChild(msrc);
  $('[data-slot="matrix"]', article).replaceWith(scroll);
  bindReportActions(article, r);
}

// The break-even curve (FR-029). A workflow is configured once and run many times; a
// harness pays for every request. Where the two lines cross is what the product is for.
// The server decides whether a crossing exists, whether it is merely outside the
// observed range, or whether the lines can never meet — this only draws what it is told,
// and never extrapolates past the executions actually recorded.
function drawCurve(article, r) {
  const slot = $('[data-slot="curve"]', article);
  if (!slot) return;
  const curve = r.curve || {};
  if (!curve.available) {
    const p = document.createElement('p');
    p.className = 'meta';
    p.textContent = curve.reason || 'Nothing in this round builds a workflow it can run again.';
    slot.replaceWith(p);
    return;
  }
  const wrap = document.createElement('div');
  for (const c of curve.curves || []) {
    wrap.appendChild(Charts.breakEven({
      title: c.title,
      product: c.product, comparator: c.comparator, crossing: c.crossing,
      productLabel: c.name, comparatorLabel: c.comparator_name,
      source: c.source + '; costs are per successful task.',
      note: c.note,
    }));
  }
  slot.replaceWith(wrap);
}

function bindReportActions(article, r) {
  // Historical report tables retain every column inside a keyboard-scrollable region.
  article.querySelectorAll('.report-section > table').forEach(table => {
    const scroll = document.createElement('div'); scroll.className = 'table-scroll'; scroll.tabIndex = 0;
    scroll.setAttribute('role', 'region'); scroll.setAttribute('aria-label', 'Report table');
    table.replaceWith(scroll); scroll.appendChild(table);
  });
  bindReportLinks(article);
  $$('[data-report-refresh]', article).forEach(b => b.onclick = () => { currentReport = null; openReport(b.dataset.reportRefresh); });
  $$('a.section-link, .report-contents a', article).forEach(a => a.onclick = e => { e.preventDefault(); history.replaceState(null, '', a.getAttribute('href')); goToSection(a.getAttribute('href').split('/').pop()); });
  $$('[data-open-run-evidence]', article).forEach(b => b.onclick = e => { e.preventDefault(); openJob(b.dataset.openRunEvidence); });
  $$('[data-evidence-anchor]', article).forEach(b => b.onclick = e => { e.preventDefault(); history.replaceState(null, '', b.getAttribute('href')); const target = document.getElementById(b.dataset.evidenceAnchor); target?.scrollIntoView({ behavior: 'smooth', block: 'start' }); const setup = b.dataset.evidenceSetup; const row = setup && target ? [...target.querySelectorAll('[data-setup]')].find(n => n.dataset.setup === setup) : null; (row || target)?.classList.add('lit'); setTimeout(() => (row || target)?.classList.remove('lit'), 2400); });
  $$('[data-evidence-run]', article).forEach(b => b.onclick = async () => { await openJob(b.dataset.evidenceRun); setTimeout(() => $('[data-evidence="' + b.dataset.evidenceEvent + '"]')?.click(), 400); });
  // The class carries the gate into the print stylesheet, so Ctrl+P cannot walk around the button.
  article.classList.toggle('lab-present', !!(r.lab_setups || []).length);
  const print = $('#report-print', article); if (print) print.onclick = () => { if (!labGate(r, 'print')) window.print(); };
  const save = $('#report-save', article); if (save) save.onclick = () => { if (!labGate(r, 'save')) saveReportHtml(article, r); };
}

// Display yes, export no (Lucas, 11 September). The report shows every setup that ran, including a
// lab build; what a lab build may not do is leave the machine, because `wb_report/audiences.yaml`
// says it "can never reach an exportable artifact". Print is gated with Save: printing to PDF makes
// the same artifact, and a gate one menu item can walk around is decoration.
//
// It refuses rather than stripping the lab rows out, which is the CLI's own behaviour — the gate
// "raises GateError, never warns". A silently thinner export is a document whose reader cannot tell
// what is missing. Returns true when it stopped something.
function labGate(r, what) {
  const lab = (r && r.lab_setups) || [];
  if (!lab.length) return false;
  const names = lab.map(s => s.name || s.id).join(', ');
  toast('Not ' + (what === 'print' ? 'printed' : 'saved') + ': this report includes ' + lab.length +
        ' lab build' + (lab.length === 1 ? '' : 's') + ' (' + names + '), which may not leave the machine. ' +
        'Re-run without ' + (lab.length === 1 ? 'it' : 'them') + ' to share this report.');
  return true;
}

// The export is one file, so its stylesheet travels inline; the served page never does.
const styleTag = css => { const s = document.createElement('style'); s.textContent = css; return s.outerHTML; };

async function inlineFonts(css) {
  // The single file carries its fonts as data URLs so it reads the same on any machine.
  const urls = [...new Set([...css.matchAll(/url\((\/vendor\/[^)]+\.woff2)\)/g)].map(m => m[1]))];
  for (const href of urls) {
    try {
      const blob = await (await fetch(href)).blob();
      const data = await new Promise(resolve => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.readAsDataURL(blob); });
      css = css.split('url(' + href + ')').join('url(' + data + ')');
    } catch { /* the export falls back to the system fonts for that face */ }
  }
  return css;
}
async function saveReportHtml(article, r) {
  const sheets = ['/vendor/radix-colors/radix-colors.css', '/tokens.css', '/ui.css', '/charts.css', '/report.css'];
  let css = '';
  for (const href of sheets) { try { css += (await (await fetch(href)).text()) + '\n'; } catch { /* the export still reads with system fonts */ } }
  css = await inlineFonts(css);
  const clone = article.cloneNode(true);
  clone.querySelectorAll('.report-actions').forEach(n => n.remove());
  clone.querySelectorAll('button').forEach(b => b.replaceWith(document.createTextNode(b.textContent)));
  clone.querySelectorAll('a.section-link, .report-contents a').forEach(a => a.setAttribute('href', '#report-' + a.getAttribute('href').split('/').pop()));
  clone.querySelectorAll('[tabindex], [role=button]').forEach(n => { n.removeAttribute('tabindex'); if (n.getAttribute('role') === 'button') n.removeAttribute('role'); });
  const title = (r.title || roundTitle(r)) + ' — AI Labs';
  const html = '<!doctype html><html lang="en"' + (document.documentElement.classList.contains('dark') ? ' class="dark"' : '') + '><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + esc(title) + '</title>' + styleTag(css) + '</head><body class="export"><main><article class="report">' + clone.innerHTML + '</article></main></body></html>';
  const url = URL.createObjectURL(new Blob([html], { type: 'text/html' })), a = document.createElement('a');
  a.href = url; a.download = ('report-' + (r.run || r.cohort) + '.html'); a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}

$('#nav-reports').onclick = () => { history.pushState(null, '', '#reports'); openReports(); };
window.openReports = openReports; window.openReport = openReport; window.openRound = openRound; window.reportRoute = reportRoute;
