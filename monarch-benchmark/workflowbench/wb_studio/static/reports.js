'use strict';
// Reports: the front door. A report reads verdict first, then the evidence.
// Every number comes from the server (report_data.py); this file only lays it out.
let reportAudience = 'public', currentReport = null, reportsSequence = 0;
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
  const [path, query] = hash.split('?');
  const audience = new URLSearchParams(query || '').get('audience');
  if (audience === 'internal' || audience === 'public') reportAudience = audience;
  if (path === '#reports' || path === '#leaderboard' || path === '' || path === '#') return openReports();
  if (path.startsWith('#report/')) { const [id, section] = path.slice(8).split('/').map(decodeURIComponent); return openReport(id, section); }
  if (path.startsWith('#round/')) { const [id, section] = path.slice(7).split('/').map(decodeURIComponent); return openRound(id, section); }
  return null;
}
const audienceQuery = () => reportAudience === 'internal' ? '?audience=internal' : '';
// A report is a document: every section has an address, and the page is titled by the report.
let permalinkBase = '';
function goToSection(section) {
  const target = section && document.getElementById('report-' + section);
  if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
function settle(kind, id, section, title) {
  const base = '#' + kind + '/' + encodeURIComponent(id), want = (section ? base + '/' + encodeURIComponent(section) : base) + audienceQuery();
  if (location.hash !== want && !location.hash.startsWith(base)) history.pushState(null, '', want);
  else if (location.hash !== want) history.replaceState(null, '', want);
  document.title = 'AI Labs — ' + title;
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
    box.innerHTML = '<div class="empty-state"><h3>No finished runs yet</h3><p>A report is written for every finished run and for every task set that has runs.</p><button class="button primary" id="reports-start">Start a run</button></div>';
    $('#reports-start').onclick = () => openLaunch();
    return;
  }
  const row = round => {
    const best = round.best ? '<strong>' + esc(round.best.name) + '</strong> passed ' + round.best.passed + ' of ' + round.best.attempts + ' (' + fmtPct(round.best.rate) + ')' : 'No evaluated attempts';
    const comparable = round.grade && round.grade.grade !== 'Not comparable';
    return '<tr class="round-card">' + '<td class="round-runs-cell"><ul class="round-runs">' + round.runs.map(run => '<li><a href="#report/' + encodeURIComponent(run.id) + audienceQuery() + '" data-open-report="' + esc(run.id) + '">' + esc(run.title || run.id) + '</a>' + (run.status === 'completed' ? '' : meta([run.status])) + '</li>').join('') + '</ul></td>' +
      '<td class="round-date">' + esc(roundDates(round.runs)) + '</td>' +
      '<td class="round-lead">' + (comparable ? gradeBadge(round.grade) : '') + '<span>' + best + '</span>' + (comparable ? '<span class="meta">' + esc(round.grade.reason) + '</span>' : '') + '</td>' +
      '<td>' + round.task_count + ' ' + (round.task_count === 1 ? 'task' : 'tasks') + '<br><span class="meta">' + esc(trackWords(round.track)) + ' · ' + round.setups + (round.setups === 1 ? ' setup' : ' setups') + '</span></td>' +
      '<td class="action"><a href="#round/' + encodeURIComponent(round.id) + audienceQuery() + '" data-open-round="' + esc(round.id) + '">Round report</a></td></tr>';
  };
  const table = rows => '<table class="table reports-table"><thead><tr><th>Runs</th><th>Date</th><th>Result</th><th>Task set</th><th class="num">Report</th></tr></thead><tbody>' + rows.map(row).join('') + '</tbody></table>';
  const benchmark = data.rounds.filter(r => r.full_benchmark), other = data.rounds.filter(r => !r.full_benchmark);
  box.innerHTML = '<div class="reports-toolbar">' + audienceToggle() + '</div>' +
    (benchmark.length ? '<h2 class="reports-group">Benchmark rounds</h2>' + table(benchmark) : '') +
    (other.length ? (benchmark.length ? '<h2 class="reports-group">Other task sets</h2>' : '') + table(other) : '');
  bindReportLinks(box);
}

function audienceToggle() {
  return '<div class="audience-toggle" role="group" aria-label="Audience"><button class="' + (reportAudience === 'public' ? 'active' : '') + '" data-audience="public">Public</button><button class="' + (reportAudience === 'internal' ? 'active' : '') + '" data-audience="internal">Internal</button></div>';
}

function bindReportLinks(root) {
  $$('[data-open-report]', root).forEach(b => b.onclick = e => { e.preventDefault(); history.pushState(null, '', '#report/' + encodeURIComponent(b.dataset.openReport) + audienceQuery()); openReport(b.dataset.openReport); });
  $$('[data-open-round]', root).forEach(b => b.onclick = e => { e.preventDefault(); history.pushState(null, '', '#round/' + encodeURIComponent(b.dataset.openRound) + audienceQuery()); openRound(b.dataset.openRound); });
  $$('[data-audience]', root).forEach(b => b.onclick = () => { reportAudience = b.dataset.audience; const y = scrollY; const path = location.hash.split('?')[0] || '#reports'; history.replaceState(null, '', path + audienceQuery()); Promise.resolve(reportRoute(location.hash)).then(() => scrollTo(0, y)); });
}

async function openReport(id, section) {
  showWorkspaceSurface('report', false);
  if (currentReport?.run === id && currentReport.audience === reportAudience && $('#report-article .report-head')) { settle('report', id, section, currentReport.title || 'Run report'); goToSection(section); return; }
  settle('report', id, section, 'Report');
  const article = $('#report-article'), sequence = ++reportsSequence;
  article.innerHTML = '<p class="meta">Loading report</p>';
  try {
    const data = await api('/api/reports/run/' + encodeURIComponent(id) + '?audience=' + reportAudience);
    if (sequence !== reportsSequence) return;
    currentReport = data; permalinkBase = '#report/' + encodeURIComponent(id); renderRunReport(data);
    document.title = 'AI Labs — ' + (data.title || 'Run report'); goToSection(section);
  } catch (e) { article.innerHTML = '<div class="empty-state"><h3>Report could not load</h3><p>' + esc(e.message) + '</p></div>'; }
}

async function openRound(id, section) {
  showWorkspaceSurface('report', false);
  if (currentReport?.cohort === id && currentReport.audience === reportAudience && $('#report-article .report-head')) { settle('round', id, section, roundTitle(currentReport)); goToSection(section); return; }
  settle('round', id, section, 'Round report');
  const article = $('#report-article'), sequence = ++reportsSequence;
  article.innerHTML = '<p class="meta">Loading report</p>';
  try {
    const data = await api('/api/reports/round/' + encodeURIComponent(id) + '?audience=' + reportAudience);
    if (sequence !== reportsSequence) return;
    currentReport = data; permalinkBase = '#round/' + encodeURIComponent(id); renderRoundReport(data);
    document.title = 'AI Labs — ' + roundTitle(data); goToSection(section);
  } catch (e) { article.innerHTML = '<div class="empty-state"><h3>Report could not load</h3><p>' + esc(e.message) + '</p></div>'; }
}
const roundTitle = r => (r.full_benchmark ? 'Benchmark standings, ' : 'Standings on ') + r.task_count + ' tasks' + (r.latest ? ', ' + (r.first && fmtDate(r.first) !== fmtDate(r.latest) ? fmtDate(r.first) + ' to ' + fmtDate(r.latest) : fmtDate(r.latest)) : '');

const section = (id, title, body) => '<section class="report-section" id="report-' + id + '"><h2><a class="section-link" href="' + permalinkBase + '/' + id + audienceQuery() + '">' + esc(title) + '</a></h2>' + body + '</section>';
const contents = ids => '<nav class="report-contents" aria-label="Contents"><ol>' + ids.map(([id, title]) => '<li><a href="' + permalinkBase + '/' + id + audienceQuery() + '">' + esc(title) + '</a></li>').join('') + '</ol></nav>';
const setupName = (r, id) => r.setups[id]?.short_name || r.setups[id]?.name || id;
const setupFullName = (r, id) => r.setups[id]?.name || id;

function reportActions(r, kind) {
  return '<div class="report-actions">' + audienceToggle() + (kind === 'run' ? '<a class="button small" href="#run/' + encodeURIComponent(r.run) + '" data-open-run-evidence="' + esc(r.run) + '">Open run</a>' : '') +
    '<button class="button small" id="report-print">Print</button><button class="button small" id="report-save">Save as HTML</button>' +
    (reportAudience === 'internal' ? '<span class="internal-mark">Internal view' + (r.hidden_setups ? ' · ' + r.hidden_setups + ' lab ' + (r.hidden_setups === 1 ? 'setup' : 'setups') + ' shown only here' : '') + '</span>' : '') + '</div>';
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
  return '<a class="evidence" href="' + permalinkBase + '/' + anchor + audienceQuery() + '" data-evidence-anchor="report-' + anchor + '" data-evidence-setup="' + esc(evidence.setup || '') + '">' + esc(words[evidence.kind] || 'See the evidence') + '</a>';
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

function failuresBlock(r) {
  const summary = r.failures?.summary || {};
  const bars = (r.failures?.buckets || []).some(b => b.count)
    ? Charts.failureColumns({ buckets: r.failures.buckets, failed: summary.failed_attempts,
        title: summary.failed_attempts + ' of ' + summary.recorded_attempts + ' attempts failed', source: sourceText(r, '') })
    : null;
  const matrix = Charts.matrix({ tasks: r.tasks, setups: r.order.map(id => ({ id, name: setupName(r, id), baseline: id === r.baseline, family: setupFamily(setupName(r, id)) })), cells: r.matrix });
  const wrap = document.createElement('div'); wrap.className = 'failures-block';
  if (bars) wrap.appendChild(bars); else { const p = document.createElement('p'); p.className = 'report-note'; p.textContent = 'No failed attempts.'; wrap.appendChild(p); }
  const failed = (r.failures?.attempts || []).filter(a => !a.passed && a.story);
  if (failed.length) {
    const list = document.createElement('div'); list.className = 'failed-attempts';
    const taskTitle = id => { const t = (r.tasks || []).find(t => t.id === id)?.title || id; const first = t.split(/(?<=\.)\s/)[0]; return first.length < t.length ? first : t; };
    list.innerHTML = '<p class="chart-title">Each failed attempt, in one line; open one for what went wrong</p>' + failed.map(a => {
      const s = a.story, facts = (s.went_wrong || []).slice(0, 4);
      return '<details class="attempt-fold"><summary><span class="attempt-fold-task">' + esc(taskTitle(a.task)) + '</span><span class="meta">' + esc(setupName(r, a.model)) + ' · ' + esc(s.mode_label) + '</span></summary>' +
        '<p>' + esc(s.verdict) + '</p>' + (s.turning_point ? '<p><strong>Where it turned.</strong> ' + esc(s.turning_point.text) + ' ' + evidenceLink({ kind: 'events', event_ids: [s.turning_point.event_id] }, r) + '</p>' : '') +
        (facts.length ? '<ul class="story-facts">' + facts.map(f => '<li>' + esc(f.text) + ' ' + evidenceLink({ kind: 'events', event_ids: f.event_ids || [] }, r) + '</li>').join('') + '</ul>' : '') +
        '<p><a class="text-button" href="#run/' + encodeURIComponent(r.run) + '/' + encodeURIComponent(a.task) + '/' + encodeURIComponent(a.model) + '">Open the attempt</a></p></details>';
    }).join('');
    wrap.appendChild(list);
  }
  const cap = document.createElement('p'); cap.className = 'chart-title'; cap.textContent = 'Tasks by setup, disagreements first' + (r.repetitions > 1 || r.method.repetitions > 1 ? '; cells show passes over repetitions' : ''); wrap.appendChild(cap);
  const scroll = document.createElement('div'); scroll.className = 'table-scroll'; scroll.appendChild(matrix); wrap.appendChild(scroll);
  const src = document.createElement('p'); src.className = 'chart-source'; src.textContent = sourceText(r, ''); wrap.appendChild(src);
  const claims = r.order.map(id => r.setups[id]).filter(s => s && s.false_completion?.count);
  if (claims.length) { const p = document.createElement('p'); p.className = 'report-note'; p.textContent = claims.map(s => s.name + ' reported the work as done in ' + s.false_completion.count + ' of ' + s.false_completion.failed + ' failed attempts').join('; ') + ' (wording heuristic over the final output).'; wrap.appendChild(p); }
  return wrap;
}

function costBlock(r) {
  const setups = r.order.map(id => r.setups[id]).filter(Boolean);
  const points = setups.map(s => ({ label: s.short_name || s.name, x: s.cost.per_attempt, y: s.pass.rate, low: s.pass.low, high: s.pass.high, baseline: s.is_baseline, family: setupFamily(s.name), data: { setup: s.id } }));
  const wrap = document.createElement('div'); wrap.className = 'cost-block';
  const anyCost = points.some(p => p.x > 0);
  if (anyCost) wrap.appendChild(Charts.scatter({ title: 'Cost per attempt against pass rate', points: points.filter(p => p.x > 0), xLog: true, pareto: points.filter(p => p.x > 0).length > 1, source: sourceText(r, '') }));
  const tokens = setups.filter(s => Object.values(s.cost.tokens).some(v => v)).map(s => ({ label: s.short_name || s.name, parts: s.cost.tokens }));
  if (tokens.length) wrap.appendChild(Charts.waterfall({ title: 'Tokens by kind', rows: tokens, labelWidth: 220, source: sourceText(r, '') }));
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
  const modes = s.setups.filter(x => x.failed).map(x => '<tr><th scope="row">' + esc(x.name) + '</th><td>' + x.failed + ' of ' + x.attempts + '</td><td>' + x.modes.map(m => esc(m.label) + ' (' + m.count + ')').join('; ') + '</td></tr>').join('');
  const table = modes ? '<table class="table story-modes"><thead><tr><th scope="col">Setup</th><th scope="col">Failed</th><th scope="col">How it failed, most common first</th></tr></thead><tbody>' + modes + '</tbody></table>' : '';
  const suspect = s.suspect_tasks.length ? '<p><strong>Suspect the task first.</strong> ' + s.suspect_tasks.map(t => esc(t.task) + ' (' + esc(t.mode_label.toLowerCase()) + ', every setup)').join('; ') + '.</p>' : '';
  return section('story', 'What went right and wrong', s.paragraphs.map(p => '<p>' + esc(p) + '</p>').join('') + table + suspect);
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
  const reading = (r.narrative || {}).status === 'completed';
  article.innerHTML = '<header class="report-head"><h1>' + esc(r.title || 'Run report') + '</h1>' + meta(['Run ' + String(r.run).slice(0, 12), r.method.task_count + (r.method.task_count === 1 ? ' task' : ' tasks'), r.order.length + (r.order.length === 1 ? ' setup' : ' setups'), trackWords(r.track), fmtDate(r.finished_at || r.created_at)]) +
    '<div class="grade-line">' + gradeBadge(r.grade) + '<span class="grade-reason">' + esc(r.grade.reason) + '</span></div>' + reportActions(r, 'run') + '</header>' +
    contents([['verdict', 'Verdict'], ['findings', 'Findings'], ...(r.story && r.story.setups.length ? [['story', 'What went right and wrong']] : []), ...(reading ? [['reading', 'Model reading']] : []), ['hero', 'Pass rate'], ['paired', 'By category'], ['failures', 'Where it failed'], ['cost', 'What it cost'], ['caveats', 'What to keep in mind'], ['method', 'How it was measured']]) +
    section('verdict', 'Verdict', '<p class="verdict">' + esc(r.verdict) + '</p>' + narrativeBlock(r)) +
    section('findings', 'Findings', findingsList(r.findings, r.model_findings, r)) + storySection(r) + modelReadingSection(r) +
    section('hero', 'Pass rate', '<div data-slot="hero"></div>') +
    section('paired', 'By category', pairedTable(r)) +
    section('failures', 'Where it failed', '<div data-slot="failures"></div>') +
    section('cost', 'What it cost', '<div data-slot="cost"></div>') +
    section('caveats', 'What to keep in mind', '<ul class="caveats">' + r.caveats.map(c => '<li>' + esc(c) + '</li>').join('') + '</ul>') +
    section('method', 'How it was measured', methodList(r)) + termsList(r);
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
    r.excluded.map(e => '<tr><th scope="row"><a href="#report/' + encodeURIComponent(e.id) + audienceQuery() + '" data-open-report="' + esc(e.id) + '">' + esc(e.title || e.id) + '</a></th><td>' + esc(e.reason) + '</td></tr>').join('') + '</tbody></table></div>';
}

function renderRoundReport(r) {
  const article = $('#report-article');
  const when = r.first && r.latest && fmtDate(r.first) !== fmtDate(r.latest) ? fmtDate(r.first) + ' to ' + fmtDate(r.latest) : fmtDate(r.latest);
  article.innerHTML = '<header class="report-head"><h1>' + esc(roundTitle(r)) + '</h1>' + meta([(r.full_benchmark ? 'Benchmark round' : 'Round'), 'task set ' + r.task_set, r.task_count + (r.task_count === 1 ? ' task' : ' tasks'), trackWords(r.track), r.runs.length + (r.runs.length === 1 ? ' run' : ' runs'), when]) +
    reportActions(r, 'round') + '</header>' +
    contents([['standings', 'Standings'], ['hero', 'Pass rate'], ...(r.trend.length > 1 ? [['trend', 'Over time']] : []), ['paired', 'By category'], ['failures', 'Task matrix'], ['caveats', 'What to keep in mind'], ['method', 'How it was measured']]) +
    section('standings', 'Standings', standingsTable(r) + pairingsTable(r) + '' + excludedTable(r)) +
    section('hero', 'Pass rate', '<div data-slot="hero"></div>') +
    (r.trend.length > 1 ? section('trend', 'Over time', '<div data-slot="trend"></div>') : '') +
    section('paired', 'By category', pairedTable(r)) +
    section('failures', 'Task matrix', '<div data-slot="matrix"></div>') +
    section('caveats', 'What to keep in mind', '<ul class="caveats">' + r.caveats.map(c => '<li>' + esc(c) + '</li>').join('') + '</ul>') +
    section('method', 'How it was measured', methodList({ ...r, method: { ...r.method, track: r.track } }) + '<h3>Runs in this round</h3><ul class="round-runs">' + r.runs.map(run => '<li><a href="#report/' + encodeURIComponent(run.id) + audienceQuery() + '" data-open-report="' + esc(run.id) + '">' + esc(run.title || run.id) + '</a>' + meta([fmtDate(run.created_at), run.status === 'completed' ? '' : run.status, run.full_benchmark ? 'full benchmark' : '']) + '</li>').join('') + '</ul>') + termsList(r);
  $('[data-slot="hero"]', article).replaceWith(heroFigure(r, 'Pass rate per setup, pooled over ' + r.runs.length + ' ' + (r.runs.length === 1 ? 'run' : 'runs')));
  if (r.trend.length > 1) {
    const series = {};
    for (const t of r.trend) (series[t.series] = series[t.series] || []).push(t);
    $('[data-slot="trend"]', article).replaceWith(Charts.trend({ title: 'Monarch pass rate by run', series: Object.entries(series).map(([label, points]) => ({ label, family: 'monarch', points })), source: 'Each point is one run; whiskers show the 95% interval.' }));
  }
  const matrix = Charts.matrix({ tasks: r.tasks, setups: r.order.map(id => ({ id, name: setupName(r, id), baseline: id === r.baseline, family: setupFamily(setupName(r, id)) })), cells: r.matrix });
  const scroll = document.createElement('div'); scroll.className = 'table-scroll'; scroll.appendChild(matrix);
  const msrc = document.createElement('p'); msrc.className = 'chart-source'; msrc.textContent = sourceText(r, 'one cell per task and setup, pooled over ' + (r.runs || []).length + ' runs'); scroll.appendChild(msrc);
  $('[data-slot="matrix"]', article).replaceWith(scroll);
  bindReportActions(article, r);
}

function bindReportActions(article, r) {
  bindReportLinks(article);
  $$('a.section-link, .report-contents a', article).forEach(a => a.onclick = e => { e.preventDefault(); history.replaceState(null, '', a.getAttribute('href')); goToSection(a.getAttribute('href').split('/').pop()); });
  $$('[data-open-run-evidence]', article).forEach(b => b.onclick = e => { e.preventDefault(); openJob(b.dataset.openRunEvidence); });
  $$('[data-evidence-anchor]', article).forEach(b => b.onclick = e => { e.preventDefault(); history.replaceState(null, '', b.getAttribute('href')); const target = document.getElementById(b.dataset.evidenceAnchor); target?.scrollIntoView({ behavior: 'smooth', block: 'start' }); const setup = b.dataset.evidenceSetup; const row = setup && target ? [...target.querySelectorAll('[data-setup]')].find(n => n.dataset.setup === setup) : null; (row || target)?.classList.add('lit'); setTimeout(() => (row || target)?.classList.remove('lit'), 2400); });
  $$('[data-evidence-run]', article).forEach(b => b.onclick = async () => { await openJob(b.dataset.evidenceRun); setTimeout(() => $('[data-evidence="' + b.dataset.evidenceEvent + '"]')?.click(), 400); });
  const print = $('#report-print', article); if (print) print.onclick = () => window.print();
  const save = $('#report-save', article); if (save) save.onclick = () => saveReportHtml(article, r);
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
