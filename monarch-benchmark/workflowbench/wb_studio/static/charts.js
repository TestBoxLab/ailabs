'use strict';
// Chart kit: every figure the Studio draws, built as SVG through DOM APIs and
// styled only by classes in charts.css (the CSP allows no inline styles).
// Every chart takes the same frame options: title as a claim, a source line,
// series coloured by model family. Numbers are labelled on the mark.
window.Charts = (() => {
  const NS = 'http://www.w3.org/2000/svg';
  const el = (name, attrs = {}, parent = null, text = null) => {
    const node = document.createElementNS(NS, name);
    for (const [key, value] of Object.entries(attrs)) if (value !== undefined && value !== null) node.setAttribute(key, value);
    if (text !== null) node.textContent = text;
    if (parent) parent.appendChild(node);
    return node;
  };
  const html = (name, cls, parent, text) => { const n = document.createElement(name); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; if (parent) parent.appendChild(n); return n; };
  const pct = v => v === null || v === undefined || Number.isNaN(v) ? '—' : Math.round(v * 100) + '%';
  const money = v => v === null || v === undefined ? 'unknown' : (v < 0.01 && v > 0 ? '$' + v.toFixed(4) : '$' + v.toFixed(2));
  const trim = s => s.replace(/\.0$/, '');
  const compact = v => v === null || v === undefined ? '—' : v >= 1e6 ? trim((v / 1e6).toFixed(1)) + 'M' : v >= 1e3 ? trim((v / 1e3).toFixed(1)) + 'K' : String(Math.round(v));
  const familyOf = name => {
    const s = String(name || '').toLowerCase();
    if (/claude|opus|sonnet|haiku|anthropic/.test(s)) return 'claude';
    if (/gpt|openai|codex|o[0-9]\b|sol\b/.test(s)) return 'gpt';
    if (/gemini|google/.test(s)) return 'gemini';
    if (/kimi|moonshot/.test(s)) return 'kimi';
    if (/glm|zhipu|z\.ai/.test(s)) return 'glm';
    if (/monarch|enterprise/.test(s)) return 'monarch';
    return 'other';
  };
  const seriesClass = row => row.baseline ? 'baseline' : 'family-' + (row.family || familyOf(row.label || row.name || row.id));
  const interactive = (node, item) => {
    if (!item || !item.data) return node;
    for (const [key, value] of Object.entries(item.data)) node.setAttribute('data-' + key.replace(/[A-Z]/g, m => '-' + m.toLowerCase()), value);
    node.setAttribute('tabindex', '0'); node.setAttribute('role', 'button'); node.classList.add('interactive');
    if (item.aria) node.setAttribute('aria-label', item.aria);
    return node;
  };

  // Ticks the way d3 picks them: a 1, 2 or 5 step that gives about `count` ticks.
  function ticks(lo, hi, count = 5) {
    if (!(hi > lo)) return [lo];
    const span = hi - lo, raw = span / count, power = Math.pow(10, Math.floor(Math.log10(raw))), err = raw / power;
    const step = power * (err >= Math.sqrt(50) ? 10 : err >= Math.sqrt(10) ? 5 : err >= Math.sqrt(2) ? 2 : 1);
    const out = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + step / 1e6; v += step) out.push(Number(v.toFixed(10)));
    return out;
  }
  function linear(domain, range) {
    const [d0, d1] = domain, [r0, r1] = range;
    const f = v => d1 === d0 ? r0 : r0 + (v - d0) / (d1 - d0) * (r1 - r0);
    f.ticks = n => ticks(d0, d1, n); f.domain = domain; f.range = range; return f;
  }
  function log10(domain, range) {
    const floor = Math.max(1e-6, domain[0]), ceil = Math.max(floor * 10, domain[1]);
    const inner = linear([Math.log10(floor), Math.log10(ceil)], range);
    const f = v => inner(Math.log10(Math.max(v, floor)));
    f.ticks = () => { const out = []; for (let p = Math.floor(Math.log10(floor)); p <= Math.ceil(Math.log10(ceil)); p++) for (const m of [1, 2, 5]) { const v = m * Math.pow(10, p); if (v >= floor && v <= ceil) out.push(v); } return out; };
    f.domain = [floor, ceil]; f.range = range; return f;
  }

  // The frame every chart shares: title, plot, source.
  function frame(options) {
    const { width = 720, height = 320, margin = { top: 12, right: 24, bottom: 36, left: 160 } } = options;
    const figure = html('figure', 'chart ' + (options.kind || ''));
    if (options.title) html('figcaption', 'chart-title', figure, options.title);
    const svg = el('svg', { viewBox: `0 0 ${width} ${height}`, role: 'img', 'aria-label': options.title || options.kind || 'chart' }, figure);
    const plot = el('g', { transform: `translate(${margin.left},${margin.top})`, class: 'plot' }, svg);
    if (options.source) html('p', 'chart-source', figure, options.source);
    if (options.note) html('p', 'chart-note', figure, options.note);
    return { figure, svg, plot, width: width - margin.left - margin.right, height: height - margin.top - margin.bottom, margin };
  }
  function axisBottom(plot, scale, height, format, label, integers = false) {
    const g = el('g', { class: 'axis axis-x', transform: `translate(0,${height})` }, plot);
    el('line', { x1: 0, x2: scale.range[1], y1: 0, y2: 0, class: 'axis-line' }, g);
    for (const t of scale.ticks(5).filter(v => !integers || Number.isInteger(v))) {
      el('line', { x1: scale(t), x2: scale(t), y1: -height, y2: 0, class: 'grid' }, g);
      el('text', { x: scale(t), y: 18, 'text-anchor': 'middle', class: 'tick' }, g, format(t));
    }
    if (label) el('text', { x: scale.range[1], y: 32, 'text-anchor': 'end', class: 'axis-label' }, g, label);
  }
  function axisLeft(plot, scale, width, format, label) {
    const g = el('g', { class: 'axis axis-y' }, plot);
    for (const t of scale.ticks(5)) {
      el('line', { x1: 0, x2: width, y1: scale(t), y2: scale(t), class: 'grid' }, g);
      el('text', { x: -8, y: scale(t) + 4, 'text-anchor': 'end', class: 'tick' }, g, format(t));
    }
    if (label) el('text', { x: 0, y: -10, 'text-anchor': 'start', class: 'axis-label' }, g, label);
  }
  const rowLabel = (g, y, text, sub) => {
    el('text', { x: -12, y, 'text-anchor': 'end', class: 'row-label' }, g, text);
    if (sub) el('text', { x: -12, y: y + 14, 'text-anchor': 'end', class: 'row-sub' }, g, sub);
  };

  // 1. Dot and whisker: one row per setup, value with interval, baseline in grey.
  function dotWhisker(options) {
    const rows = options.rows || [];
    const rowHeight = 34, f = frame({ ...options, kind: 'dot-whisker', height: rows.length * rowHeight + 48, margin: { top: 8, right: 96, bottom: 36, left: options.labelWidth || 190 } });
    const x = linear([0, 1], [0, f.width]);
    axisBottom(f.plot, x, rows.length * rowHeight, pct, options.xLabel || 'pass rate');
    if (options.ceiling !== undefined) { el('line', { x1: x(options.ceiling), x2: x(options.ceiling), y1: 0, y2: rows.length * rowHeight, class: 'reference' }, f.plot); el('text', { x: x(options.ceiling), y: -1, 'text-anchor': 'middle', class: 'reference-label' }, f.plot, options.ceilingLabel || 'answer key'); }
    rows.forEach((row, i) => {
      const y = i * rowHeight + rowHeight / 2, g = interactive(el('g', { class: 'row ' + seriesClass(row) }, f.plot), row);
      rowLabel(g, y + 4, row.label, row.sub);
      if (row.value === null || row.value === undefined) { el('text', { x: 0, y: y + 4, class: 'empty-mark' }, g, 'not evaluated'); return; }
      if (row.low !== undefined && row.low !== null) {
        el('line', { x1: x(row.low), x2: x(row.high), y1: y, y2: y, class: 'whisker' }, g);
        el('line', { x1: x(row.low), x2: x(row.low), y1: y - 5, y2: y + 5, class: 'whisker' }, g);
        el('line', { x1: x(row.high), x2: x(row.high), y1: y - 5, y2: y + 5, class: 'whisker' }, g);
      }
      el('rect', { x: x(row.value) - 5, y: y - 5, width: 10, height: 10, class: 'mark' }, g);
      el('text', { x: f.width + 10, y: y + 4, class: 'value-label' }, g, (row.detail || pct(row.value)));
    });
    return f.figure;
  }

  // 3. Scatter with an optional log x axis and the Pareto line (best pass rate at each cost).
  function scatter(options) {
    const points = (options.points || []).filter(p => p.x !== null && p.x !== undefined && p.y !== null && p.y !== undefined);
    const f = frame({ ...options, kind: 'scatter', height: options.height || 340, margin: { top: 28, right: 40, bottom: 44, left: 56 } });
    const xs = points.map(p => p.x), lo = Math.min(...xs, options.xMin ?? Infinity), hi = Math.max(...xs, options.xMax ?? 0);
    const x = options.xLog ? log10([lo > 0 ? lo / 1.5 : 0.001, hi * 1.5 || 1], [0, f.width]) : linear([0, (hi || 1) * 1.1], [0, f.width]);
    const y = linear([0, 1], [f.height, 0]);
    axisBottom(f.plot, x, f.height, options.xFormat || money, options.xLabel || 'cost per attempt' + (options.xLog ? ' (log scale)' : ''));
    axisLeft(f.plot, y, f.width, pct, options.yLabel || 'pass rate');
    if (options.pareto && points.length > 1) {
      const front = []; let best = -1;
      for (const p of [...points].sort((a, b) => a.x - b.x || b.y - a.y)) if (p.y > best) { front.push(p); best = p.y; }
      el('path', { d: front.map((p, i) => (i ? 'L' : 'M') + x(p.x) + ',' + y(p.y)).join(' '), class: 'pareto' }, f.plot);
    }
    for (const group of Object.values(points.reduce((acc, p) => { if (p.link) (acc[p.link] = acc[p.link] || []).push(p); return acc; }, {}))) {
      if (group.length > 1) el('path', { d: group.sort((a, b) => a.x - b.x).map((p, i) => (i ? 'L' : 'M') + x(p.x) + ',' + y(p.y)).join(' '), class: 'link' }, f.plot);
    }
    for (const p of points) {
      const g = interactive(el('g', { class: 'point ' + seriesClass(p) }, f.plot), p);
      if (p.low !== undefined && p.low !== null) el('line', { x1: x(p.x), x2: x(p.x), y1: y(p.low), y2: y(p.high), class: 'whisker' }, g);
      el('rect', { x: x(p.x) - 5, y: y(p.y) - 5, width: 10, height: 10, class: 'mark' }, g);
      const flip = x(p.x) > f.width * .7;
      el('text', { x: x(p.x) + (flip ? -9 : 9), y: y(p.y) - 8, 'text-anchor': flip ? 'end' : 'start', class: 'point-label' }, g, p.label);
    }
    if (!points.length) el('text', { x: f.width / 2, y: f.height / 2, 'text-anchor': 'middle', class: 'empty-mark' }, f.plot, options.empty || 'No costed attempts');
    return f.figure;
  }

  // 5. Horizontal bars with counts and denominators (failure categories, checks).
  function bars(options) {
    const rows = options.rows || [], rowHeight = 30;
    const f = frame({ ...options, kind: 'bars', height: rows.length * rowHeight + 40, margin: { top: 6, right: 120, bottom: 30, left: options.labelWidth || 220 } });
    const max = Math.max(1, ...rows.map(r => r.value || 0), options.max || 0);
    const x = linear([0, max], [0, f.width]);
    axisBottom(f.plot, x, rows.length * rowHeight, options.format || (v => String(v)), options.xLabel || '', rows.every(r => Number.isInteger(r.value || 0)));
    rows.forEach((row, i) => {
      const y = i * rowHeight, g = interactive(el('g', { class: 'row ' + (row.cls || seriesClass(row)) }, f.plot), row);
      rowLabel(g, y + rowHeight / 2 + 4, row.label);
      el('rect', { x: 0, y: y + 7, width: Math.max(0, x(row.value || 0)), height: rowHeight - 14, class: 'bar' }, g);
      el('text', { x: x(row.value || 0) + 8, y: y + rowHeight / 2 + 4, class: 'value-label' }, g, row.detail || (row.denominator ? `${row.value} of ${row.denominator}` : String(row.value)));
    });
    return f.figure;
  }

  // Vertical columns grouped by category; used by Budget for tokens and cost per model.
  function columns(options) {
    const groups = options.groups || [];
    const f = frame({ ...options, kind: 'columns', height: options.height || 260, margin: { top: 28, right: 16, bottom: 56, left: 56 } });
    const max = Math.max(1e-9, ...groups.flatMap(g => g.values.map(v => v.value || 0)));
    if (!groups.length || max <= 1e-9) { el('text', { x: f.width / 2, y: f.height / 2, 'text-anchor': 'middle', class: 'empty-mark' }, f.plot, options.empty || 'Nothing recorded yet'); return f.figure; }
    const y = linear([0, max * 1.15], [f.height, 0]);
    axisLeft(f.plot, y, f.width, options.format || compact, options.yLabel || '');
    const groupWidth = f.width / Math.max(1, groups.length);
    groups.forEach((group, gi) => {
      const n = group.values.length, barWidth = Math.min(40, (groupWidth - 16) / Math.max(1, n));
      group.values.forEach((v, vi) => {
        const x0 = gi * groupWidth + (groupWidth - n * barWidth) / 2 + vi * barWidth;
        const g = interactive(el('g', { class: 'column ' + seriesClass(v) }, f.plot), v);
        el('rect', { x: x0 + 1, y: y(v.value || 0), width: barWidth - 2, height: f.height - y(v.value || 0), class: 'bar' }, g);
        el('text', { x: x0 + barWidth / 2, y: y(v.value || 0) - 5, 'text-anchor': 'middle', class: 'value-label' }, g, (options.format || compact)(v.value || 0));
      });
      el('text', { x: gi * groupWidth + groupWidth / 2, y: f.height + 18, 'text-anchor': 'middle', class: 'tick' }, f.plot, group.label);
      if (group.sub) el('text', { x: gi * groupWidth + groupWidth / 2, y: f.height + 32, 'text-anchor': 'middle', class: 'row-sub' }, f.plot, group.sub);
    });
    return f.figure;
  }

  // 6. Time strips: every attempt as a tick, the median as a mark.
  function strips(options) {
    const rows = options.rows || [], rowHeight = 28;
    const f = frame({ ...options, kind: 'strips', height: rows.length * rowHeight + 44, margin: { top: 6, right: 90, bottom: 34, left: options.labelWidth || 190 } });
    const max = Math.max(1, ...rows.flatMap(r => r.values || []));
    const x = linear([0, max], [0, f.width]);
    axisBottom(f.plot, x, rows.length * rowHeight, v => v + 's', options.xLabel || 'seconds to finish');
    rows.forEach((row, i) => {
      const y = i * rowHeight + rowHeight / 2, g = el('g', { class: 'row ' + seriesClass(row) }, f.plot);
      rowLabel(g, y + 4, row.label);
      for (const v of row.values || []) el('line', { x1: x(v), x2: x(v), y1: y - 7, y2: y + 7, class: 'strip' }, g);
      if (row.median !== undefined && row.median !== null) el('rect', { x: x(row.median) - 4, y: y - 4, width: 8, height: 8, class: 'mark' }, g);
      el('text', { x: f.width + 10, y: y + 4, class: 'value-label' }, g, row.detail || (row.median === null || row.median === undefined ? '—' : 'median ' + row.median.toFixed(1) + 's'));
    });
    return f.figure;
  }

  // 7. Token waterfall per setup: uncached input, cache writes, cache reads, output.
  function waterfall(options) {
    const rows = options.rows || [], rowHeight = 34, parts = ['uncached', 'cache_write', 'cached', 'output'];
    const names = { uncached: 'uncached input', cache_write: 'cache writes', cached: 'cache reads', output: 'output' };
    const f = frame({ ...options, kind: 'waterfall', height: rows.length * rowHeight + 64, margin: { top: 6, right: 100, bottom: 54, left: options.labelWidth || 190 } });
    const max = Math.max(1, ...rows.map(r => parts.reduce((n, p) => n + (r.parts[p] || 0), 0)));
    const x = linear([0, max], [0, f.width]);
    axisBottom(f.plot, x, rows.length * rowHeight, compact, options.xLabel || 'tokens');
    rows.forEach((row, i) => {
      const y = i * rowHeight, g = el('g', { class: 'row' }, f.plot);
      rowLabel(g, y + rowHeight / 2 + 4, row.label);
      let offset = 0;
      for (const part of parts) {
        const value = row.parts[part] || 0;
        if (value > 0) el('rect', { x: x(offset), y: y + 8, width: Math.max(0, x(offset + value) - x(offset)), height: rowHeight - 16, class: 'segment ' + part }, g);
        offset += value;
      }
      el('text', { x: x(offset) + 8, y: y + rowHeight / 2 + 4, class: 'value-label' }, g, compact(offset));
    });
    const legend = el('g', { class: 'legend', transform: `translate(0,${rows.length * rowHeight + 40})` }, f.plot);
    parts.forEach((part, i) => { el('rect', { x: i * 150, y: -8, width: 10, height: 10, class: 'segment ' + part }, legend); el('text', { x: i * 150 + 16, y: 1, class: 'tick' }, legend, names[part]); });
    return f.figure;
  }

  // 8. Trend over rounds: one line per series with intervals.
  function trend(options) {
    const series = options.series || [], f = frame({ ...options, kind: 'trend', height: options.height || 300, margin: { top: 28, right: 120, bottom: 44, left: 56 } });
    const labels = [...new Set(series.flatMap(s => s.points.map(p => p.x)))];
    const x = linear([0, Math.max(1, labels.length - 1)], [0, f.width]), y = linear([0, 1], [f.height, 0]);
    axisLeft(f.plot, y, f.width, pct, options.yLabel || 'pass rate');
    labels.forEach((label, i) => el('text', { x: x(i), y: f.height + 18, 'text-anchor': 'middle', class: 'tick' }, f.plot, label));
    for (const s of series) {
      const g = el('g', { class: 'series ' + seriesClass(s) }, f.plot);
      const pts = s.points.map(p => ({ ...p, px: x(labels.indexOf(p.x)), py: y(p.y) }));
      el('path', { d: pts.map((p, i) => (i ? 'L' : 'M') + p.px + ',' + p.py).join(' '), class: 'line' }, g);
      for (const p of pts) {
        if (p.low !== undefined && p.low !== null) el('line', { x1: p.px, x2: p.px, y1: y(p.low), y2: y(p.high), class: 'whisker' }, g);
        el('rect', { x: p.px - 4, y: p.py - 4, width: 8, height: 8, class: 'mark' }, g);
      }
      const last = pts[pts.length - 1];
      if (last) el('text', { x: last.px + 10, y: last.py + 4, class: 'point-label' }, g, s.label);
    }
    return f.figure;
  }

  // 9. Timeline of tool calls by node over the attempt.
  function timeline(options) {
    const lanes = options.lanes || [], rowHeight = 26;
    const f = frame({ ...options, kind: 'timeline', height: lanes.length * rowHeight + 44, margin: { top: 6, right: 24, bottom: 34, left: options.labelWidth || 150 } });
    const end = Math.max(1, options.end || Math.max(...lanes.flatMap(l => l.spans.map(s => s.end))));
    const x = linear([0, end], [0, f.width]);
    axisBottom(f.plot, x, lanes.length * rowHeight, v => v.toFixed(1) + 's', 'seconds since the attempt started');
    lanes.forEach((lane, i) => {
      const y = i * rowHeight, g = el('g', { class: 'lane' }, f.plot);
      rowLabel(g, y + rowHeight / 2 + 4, lane.label);
      for (const span of lane.spans) {
        const s = el('rect', { x: x(span.start), y: y + 6, width: Math.max(2, x(span.end) - x(span.start)), height: rowHeight - 12, class: 'span ' + (span.status || 'observed') }, g);
        el('title', {}, s, (span.label || '') + ' ' + span.start.toFixed(2) + 's – ' + span.end.toFixed(2) + 's');
      }
    });
    return f.figure;
  }

  // 3b. Task matrix and consistency grid: an HTML table, tasks by setups.
  function matrix(options) {
    const table = html('table', 'chart-matrix');
    const head = html('tr', null, html('thead', null, table));
    html('th', null, head, options.taskLabel || 'Task');
    for (const setup of options.setups) html('th', 'setup ' + seriesClass(setup), head, setup.name || setup.id);
    const body = html('tbody', null, table);
    const rows = options.tasks.map(task => {
      const cells = options.setups.map(setup => (options.cells[task.id + ' ' + setup.id]) || null);
      const passes = cells.map(c => c ? c.rate : null).filter(v => v !== null);
      const disagreement = passes.length ? Math.max(...passes) - Math.min(...passes) : 0;
      return { task, cells, disagreement };
    }).sort((a, b) => b.disagreement - a.disagreement || String(a.task.title).localeCompare(String(b.task.title)));
    for (const row of rows) {
      const tr = html('tr', null, body);
      const th = html('th', 'task', tr); th.textContent = row.task.title || row.task.id; th.title = row.task.id;
      row.cells.forEach(cell => {
        const td = html('td', 'cell ' + (cell === null ? 'missing' : cell.rate === 1 ? 'pass' : cell.rate === 0 ? 'fail' : 'mixed'), tr);
        td.textContent = cell === null ? '—' : cell.reps.length > 1 ? cell.reps.filter(Boolean).length + '/' + cell.reps.length : cell.rate === 1 ? 'pass' : 'fail';
        if (cell && cell.infra) td.classList.add('infra');
      });
    }
    return table;
  }

  function architecture(options) {
    // Chart 10: the published architecture read-only, per-node cost and time badges, the executing node lit.
    const graph = options.graph || {}, nodes = graph.nodes || [], edges = graph.edges || [], steps = options.steps || {};
    const w = 168, h = 48, xs = nodes.map(n => n.x || 0), ys = nodes.map(n => n.y || 0);
    const minX = Math.min(0, ...xs), minY = Math.min(0, ...ys), maxX = Math.max(w, ...xs.map(x => x + w)), maxY = Math.max(h, ...ys.map(y => y + h));
    const figure = html('figure', 'chart architecture');
    if (options.title) html('figcaption', 'chart-title', figure, options.title);
    const svg = el('svg', { viewBox: `${minX - 8} ${minY - 8} ${maxX - minX + 16} ${maxY - minY + 16}`, role: 'img', 'aria-label': options.title || 'architecture' }, figure);
    const byId = Object.fromEntries(nodes.map(n => [n.id, n]));
    for (const e of edges) {
      const a = byId[e.from], b = byId[e.to];
      if (!a || !b) continue;
      const x1 = (a.x || 0) + w, y1 = (a.y || 0) + h / 2, x2 = b.x || 0, y2 = (b.y || 0) + h / 2;
      el('path', { class: 'edge', d: `M${x1},${y1} C${x1 + 40},${y1} ${x2 - 40},${y2} ${x2},${y2}` }, svg);
    }
    const seconds = v => v === null || v === undefined ? 'unknown' : v.toFixed(1) + 's';
    for (const n of nodes) {
      const m = steps[n.id] || {};
      const g = el('g', { class: 'node ' + (m.status || '') + (options.active === n.id ? ' active' : ''), transform: `translate(${n.x || 0},${n.y || 0})` }, svg);
      el('rect', { width: w, height: h }, g);
      el('text', { x: 10, y: 19 }, g, String(n.label || n.id).slice(0, 24));
      el('text', { x: 10, y: 37, class: 'badge' }, g, money(m.cost === undefined ? null : m.cost) + ' · ' + seconds(m.seconds));
      el('title', {}, g, (n.label || n.id) + ' · cost ' + money(m.cost === undefined ? null : m.cost) + ' · time ' + seconds(m.seconds));
    }
    if (options.source) html('p', 'chart-source', figure, options.source);
    return figure;
  }

  return { dotWhisker, scatter, bars, columns, strips, waterfall, trend, timeline, matrix, architecture, familyOf, pct, money, compact, ticks, linear, log10 };
})();
