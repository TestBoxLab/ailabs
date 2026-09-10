'use strict';
/* Architecture studio: a node builder whose published versions actually execute.
   Shares $, $$, esc, api, toast, state, openLaunch, job, events and budget with app.js.

   Interaction rules (from the node-editor references: n8n, React Flow, Blender, Unreal):
   - every drag has a click and a keyboard equivalent (menus, inspector, C+Enter);
   - ports carry a 24px+ hit area; a wire drag snaps to the target port and dims what it cannot reach;
   - releasing a wire on empty canvas offers a connected step; dropping a palette item on a wire inserts it;
   - a plain click on empty canvas clears the selection; a moved pointer never counts as a click;
   - typing is one undo step per field, not one per keystroke;
   - refusals go to the status line beside the canvas; toasts are for server errors only. */

const STEP_TYPES = {
  'input': {name: 'Task input', symbol: 'input', description: 'The benchmark request and its starting context. Every flow starts here.'},
  'product-graph': {name: 'Product graph', symbol: 'fields', description: 'A prepared product graph version: typed fields filled once by an agent for every product in the corpus. Its records are delivered to every step downstream of it.'},
  'agent': {name: 'Agent step', symbol: 'agent', description: 'One agent loop on the task. Act mode calls application tools; Advise mode answers in text for a later step.'},
  'monarch': {name: 'Monarch Enterprise', symbol: 'monarch', description: 'The official product, pinned to a GitHub revision on publication. It runs its own Bedrock Claude brain; no per-run model or effort override exists.'},
  'merge': {name: 'Join branches', symbol: 'merge', description: 'Joins the outputs of the connected steps into one text for the next step.'},
  'output': {name: 'Result output', symbol: 'output', description: 'The final answer handed to the evaluator. Every flow ends here.'}
};
const PALETTE = ['agent', 'product-graph', 'merge', 'monarch'];
const FIXED = ['input', 'output'];
const PROVIDER_LABELS = {anthropic: 'Anthropic API', openai: 'OpenAI API', gemini: 'Gemini API', fireworks: 'Fireworks', moonshot: 'Moonshot', zai: 'Z.ai',
  'claude-code': 'Claude Code (native harness)', codex: 'Codex (native harness)', bedrock: 'Monarch Enterprise brain (Bedrock)'};
const ENTERPRISE_MODELS = ['claude-opus-4-8', 'claude-opus-5', 'claude-sonnet-5', 'claude-sonnet-4-6', 'claude-haiku-4-5'];
const NATIVE_DEFAULTS = {'claude-code': 'sonnet', codex: 'gpt-5.6-sol'};
const ALL_EFFORTS = ['default', 'low', 'medium', 'high', 'xhigh', 'max'];
const NODE_W = 240, PORT_Y = 46, GRID = 20, NODE_H_GUESS = 120;
const TEMPLATES = {
  'single': {name: 'Single agent', hint: 'One acting agent with the application tools', build: () => ({nodes: [mk('input', 'input', 80, 180), mk('worker', 'agent', 400, 180, {mode: 'act', instructions: 'Complete the request using the application tools. Verify the record you change before writing.', runner: runnerFor('gemini')}, 'Worker'), mk('output', 'output', 720, 180)], edges: E(['input', 'worker'], ['worker', 'output'])})},
  'planner': {name: 'Planner then worker', hint: 'An advising planner writes the plan, an acting worker executes it', build: () => ({nodes: [mk('input', 'input', 60, 180), mk('planner', 'agent', 340, 180, {mode: 'advise', instructions: 'Read the request and write a short numbered plan: which records to find, what to change, what to check afterwards. Prefer exact record identity over name matches. Change only what the request asks for.', runner: runnerFor('anthropic')}, 'Planner'), mk('worker', 'agent', 640, 180, {mode: 'act', instructions: 'Execute the plan with the application tools and report what you changed.', runner: runnerFor('gemini')}, 'Worker'), mk('output', 'output', 940, 180)], edges: E(['input', 'planner'], ['planner', 'worker'], ['worker', 'output'])})},
  'informed': {name: 'Product graph, then act', hint: 'Deliver a prepared product graph to an acting worker', build: () => ({nodes: [mk('input', 'input', 60, 180), mk('knowledge', 'product-graph', 340, 40, latestGraphRef(), 'Product graph'), mk('worker', 'agent', 640, 180, {mode: 'act', instructions: 'Complete the request. Use the product graph to choose the right actions and verify before writing.', runner: runnerFor('gemini')}, 'Worker'), mk('output', 'output', 940, 180)], edges: E(['input', 'knowledge'], ['knowledge', 'worker'], ['worker', 'output'])})},
  'monarch': {name: 'Stock Monarch Enterprise', hint: 'The official product as a definition; runs once its adapter exists', build: () => ({nodes: [mk('input', 'input', 80, 180), mk('monarch', 'monarch', 400, 180, {runner: {provider: 'bedrock', model: 'claude-opus-4-8', effort: 'default'}}), mk('output', 'output', 720, 180)], edges: E(['input', 'monarch'], ['monarch', 'output'])})}
};

function mk(id, type, x, y, config = {}, label) { return {id, type, label: label || STEP_TYPES[type].name, x, y, config}; }
function E(...pairs) { return pairs.map(([from, to]) => ({from, to})); }
function runnerFor(provider) {
  const control = controls.find(c => c.provider === provider) || controls.find(c => c.provider === 'gemini');
  return control ? {provider: control.provider, model: control.model, effort: 'default'} : {provider: 'gemini', model: 'gemini-3.7-flash', effort: 'default'};
}
function newId() { return crypto.randomUUID().replaceAll('-', '').slice(0, 10); }

let blueprint = {id: null, revision: 0, name: '', notes: '', graph: {nodes: [], edges: []}};
let blueprints = [], controls = [], fireworksCatalog = null, opened = false, template = 'single';
let selection = new Set(), selectedEdge = null, dirty = false, problems = [], capabilities = [], live = {};
let camera = {x: 40, y: 40, k: 1};
const editHistory = {undo: [], redo: []};
const typing = {key: null, at: 0};
let validateTimer = null, connectPreview = null, gesture = null, pendingPort = null, menuState = null;
let nodeEls = new Map();
let productGraphs = [];   // filled by pg.js
function latestGraphRef() { for (const g of productGraphs) { const v = [...(g.versions || [])].reverse().find(v => ['complete', 'incomplete'].includes(v.status)); if (v) return {graph: g.id, version: v.version}; } return {}; }
function graphRecord(id) { return productGraphs.find(g => g.id === id) || null; }
function graphVersion(ref) { const g = graphRecord(ref?.graph); return g?.versions?.find(v => v.version === ref?.version && ['complete', 'incomplete'].includes(v.status)) || null; }

const icons = {
  input: 'M4 12h16m-6-6 6 6-6 6', output: 'M4 4h16v16H4zM8 12h8', fields: 'M4 4h16v16H4zM4 10h16M10 4v16', agent: 'M7 7h10v10H7zM12 3v4m0 10v4M3 12h4m10 0h4',
  monarch: 'M4 19 12 4l8 15M8 13h8', merge: 'M4 5h5l6 7h5M4 19h5l6-7',
  copy: 'M8 8h11v11H8zM16 8V5H5v11h3', trash: 'M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v6m4-6v6', more: 'M4 12h2.5M10.75 12h2.5M17.5 12h2.5'
};
function stepIcon(type) { return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="' + (icons[STEP_TYPES[type]?.symbol] || icons.agent) + '"/></svg>'; }
function uiIcon(name) { return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="' + icons[name] + '"/></svg>'; }

// ------------------------------------------------------------------ model helpers
function byId(id) { return blueprint.graph.nodes.find(n => n.id === id); }
function incomingOf(id) { return blueprint.graph.edges.filter(e => e.to === id).map(e => e.from); }
function outgoingOf(id) { return blueprint.graph.edges.filter(e => e.from === id).map(e => e.to); }
function ancestorsOf(id) { const seen = new Set(); const todo = [...incomingOf(id)]; while (todo.length) { const n = todo.pop(); if (seen.has(n)) continue; seen.add(n); todo.push(...incomingOf(n)); } return seen; }
function controlFor(runner) { if (!runner) return null; return controls.find(c => c.provider === runner.provider && (c.id === runner.model || c.model === runner.model)) || null; }
function runnerSummary(r) {
  if (!r) return '';
  const control = controlFor(r);
  const model = control ? control.name : (r.model || 'choose a model');
  return model + (r.effort && r.effort !== 'default' ? ' · ' + r.effort : '');
}
function canConnect(from, to) {
  if (from === to) return 'A step cannot connect to itself';
  const a = byId(from), b = byId(to);
  if (!a || !b) return 'Unknown step';
  if (a.type === 'output') return 'The result output ends the flow';
  if (b.type === 'input') return 'The task input starts the flow';
  if (blueprint.graph.edges.some(e => e.from === from && e.to === to)) return 'These steps are already connected';
  if (ancestorsOf(from).has(to)) return 'That would create a loop; this version supports forward flows only';
  return null;
}
function validTargets(from) { return blueprint.graph.nodes.filter(n => canConnect(from, n.id) === null); }
function validSources(to) { return blueprint.graph.nodes.filter(n => canConnect(n.id, to) === null); }
function nodeProblems(id) { return problems.filter(p => p.node === id).map(p => p.message); }
function nodeCapability(id) { return capabilities.find(c => c.node === id) || null; }
function hint(text) { $('#canvas-hint').textContent = text; }
function labelOf(id) { return byId(id)?.label || id; }

// ------------------------------------------------------------------ history / dirty
function snapshot() { return JSON.stringify({graph: blueprint.graph, name: blueprint.name, notes: blueprint.notes}); }
function commit() { typing.key = null; editHistory.undo.push(snapshot()); if (editHistory.undo.length > 80) editHistory.undo.shift(); editHistory.redo = []; updateHistoryButtons(); }
// One undo entry per field while typing: a new entry only when the field changes or after a pause.
function commitTyping(key) { const now = Date.now(); if (typing.key !== key || now - typing.at > 1500) { commit(); typing.key = key; } typing.at = now; }
function restore(text) { const value = JSON.parse(text); blueprint.graph = value.graph; blueprint.name = value.name; blueprint.notes = value.notes; $('#blueprint-name').value = blueprint.name; $('#blueprint-notes').value = blueprint.notes; selection = new Set([...selection].filter(id => byId(id))); if (selectedEdge !== null && !blueprint.graph.edges[selectedEdge]) selectedEdge = null; markDirty(); render(); renderInspector(); }
function undo() { if (!editHistory.undo.length) return hint('Nothing to undo'); editHistory.redo.push(snapshot()); restore(editHistory.undo.pop()); typing.key = null; updateHistoryButtons(); hint('Undone'); }
function redo() { if (!editHistory.redo.length) return hint('Nothing to redo'); editHistory.undo.push(snapshot()); restore(editHistory.redo.pop()); typing.key = null; updateHistoryButtons(); hint('Redone'); }
function updateHistoryButtons() { $('#builder-undo').disabled = !editHistory.undo.length; $('#builder-redo').disabled = !editHistory.redo.length; }
function markDirty() {
  dirty = true;
  $('#builder-state').textContent = 'Unsaved edits';
  $('#builder-state').className = 'builder-state dirty';
  try { localStorage.setItem('ailabs-architecture-draft', JSON.stringify(blueprint)); } catch {}
  scheduleValidate(); updateRunButton();
}
function markSaved(text) { dirty = false; $('#builder-state').textContent = text; $('#builder-state').className = 'builder-state'; localStorage.removeItem('ailabs-architecture-draft'); updateRunButton(); }

// ------------------------------------------------------------------ validation
function scheduleValidate() { clearTimeout(validateTimer); validateTimer = setTimeout(validateNow, 300); }
async function validateNow() {
  try {
    const result = await api('/api/blueprints/validate', {graph: blueprint.graph});
    problems = result.problems; capabilities = result.capabilities;
  } catch (e) { problems = [{node: null, message: e.message}]; capabilities = []; }
  renderProblems(); renderNodes(); renderInspector(true);
}
function renderProblems() {
  const box = $('#builder-problems');
  const count = problems.length;
  box.className = 'builder-problems' + (count ? ' has-problems' : ' ok');
  box.innerHTML = count
    ? '<strong>' + count + (count === 1 ? ' problem' : ' problems') + ' before publishing</strong>' + problems.slice(0, 6).map((p, i) => p.node ? '<button type="button" class="problem-link" data-problem="' + i + '">' + esc(labelOf(p.node)) + ': ' + esc(p.message) + '</button>' : '<span>' + esc(p.message) + '</span>').join('') + (count > 6 ? '<span>… and ' + (count - 6) + ' more, marked on the canvas</span>' : '')
    : (blueprint.graph.nodes.length ? '<strong>Publishable</strong><span>Every step validates. ' + readinessPreview() + '</span>' : '');
  $$('[data-problem]').forEach(b => b.onclick = () => focusProblem(problems[Number(b.dataset.problem)]));
  const publish = $('#blueprint-publish');
  publish.classList.toggle('is-disabled', count > 0);
  publish.setAttribute('aria-disabled', String(count > 0));
  publish.title = count ? 'Fix ' + count + (count === 1 ? ' problem' : ' problems') + ' first; click to jump to the first one' : 'Freeze this graph as a runnable version';
}
function readinessPreview() {
  const rows = capabilities.filter(c => c);
  const unsupported = rows.filter(r => !r.supported);
  const blocked = rows.filter(r => r.supported && r.launch_block);
  if (unsupported.length) return 'Would publish as unsupported: ' + unsupported.map(r => r.label + ' — ' + r.reason).join('; ');
  if (blueprint.graph.nodes.some(n => n.type === 'monarch')) return 'Contains the stock Monarch step: publishes as a definition, runs once the Enterprise adapter exists.';
  if (blocked.length) return 'Would publish blocked: ' + blocked.map(r => r.label + ' — ' + r.launch_block).join('; ');
  if (blueprint.graph.nodes.some(n => n.type === 'product-graph' && !graphVersion(n.config))) return 'A product graph step has no prepared version yet: prepare one in Product graphs, then it can run.';
  return 'After publishing it can run immediately.';
}
// A problem is a link to the field that fixes it (NN/g: keep the error beside the control).
function fieldFor(message) {
  const m = message.toLowerCase();
  if (m.includes('instructions')) return '#node-instructions';
  if (m.includes('rate-carded') || m.includes('model')) return '#node-model';
  if (m.includes('turn limit')) return '#node-turns';
  if (m.includes('target fields')) return '[data-target-field]';
  if (m.includes('graph field') || m.includes('field needs')) return '[data-field="path"]';
  if (m.includes('name')) return '#node-label';
  return null;
}
function focusProblem(problem) {
  if (!problem?.node || !byId(problem.node)) return;
  select(problem.node); centerOn(problem.node);
  const selector = fieldFor(problem.message);
  const el = selector && $('#node-settings ' + selector);
  (el || $('#node-settings .node-issues') || $('#node-label'))?.focus?.({preventScroll: false});
  hint(labelOf(problem.node) + ': ' + problem.message);
}

// ------------------------------------------------------------------ rendering
function worldTransform() { $('#builder-world').style.transform = 'translate(' + camera.x + 'px,' + camera.y + 'px) scale(' + camera.k + ')'; $('#zoom-label').textContent = Math.round(camera.k * 100) + '%'; }
function render() { renderNodes(); worldTransform(); }
function chip(text, cls = '') { return '<span class="bp-chip ' + cls + '">' + esc(text) + '</span>'; }
function nodeBody(n) {
  const c = n.config || {}, parts = [];
  if (c.runner) parts.push(chip(runnerSummary(c.runner), 'runner'));
  if (n.type === 'agent') parts.push(chip(c.mode === 'advise' ? 'Advise · text only' : 'Act · uses tools', c.mode === 'advise' ? 'advise' : 'act'));
  if (n.type === 'product-graph') { const v = graphVersion(c); const g = graphRecord(c.graph); parts.push(chip(g ? g.name + ' · v' + (c.version || '?') : 'no product graph chosen', v ? (v.status === 'complete' ? 'ok' : 'warn') : 'unsupported')); if (v) { parts.push(chip(v.fields.length + ' field' + (v.fields.length === 1 ? '' : 's'))); parts.push(chip(Object.keys(v.records || {}).length + ' products')); } }
  if (c.max_turns) parts.push(chip(c.max_turns + ' turns'));
  if (n.type === 'monarch') parts.push(chip(c.baseline?.commit ? 'pinned ' + c.baseline.commit.slice(0, 7) : 'pinned on publish'));
  const text = n.type === 'agent' ? (c.instructions || '') : n.type === 'product-graph' && graphVersion(c) ? 'Delivers ' + graphVersion(c).fields.map(f => f.path).join(', ') + ' for every product to each step after it.' : STEP_TYPES[n.type].description;
  return '<div class="bp-chips">' + parts.join('') + '</div>' + (text ? '<p>' + esc(text.length > 110 ? text.slice(0, 107) + '…' : text) + '</p>' : '');
}
function nodeBadge(n) {
  const issues = nodeProblems(n.id);
  const cap = nodeCapability(n.id);
  const state = live[n.id];
  if (state) return '<span class="bp-badge live ' + esc(state) + '" title="Live execution">' + ({running: 'Running', completed: 'Done', error: 'Attention'}[state] || state) + '</span>';
  if (issues.length) return '<button type="button" class="bp-badge warn" data-issues="' + esc(n.id) + '" title="' + esc(issues.join('\n')) + '" aria-label="' + issues.length + (issues.length === 1 ? ' problem' : ' problems') + ' on ' + esc(n.label) + '. Open the first one">' + issues.length + '</button>';
  if (cap && !cap.supported) return '<span class="bp-badge warn" title="' + esc(cap.reason) + '">!</span>';
  if (cap && cap.launch_block) return '<span class="bp-badge hold" title="' + esc(cap.launch_block) + '">hold</span>';
  return '';
}
function nodeTools(n) {
  const fixed = FIXED.includes(n.type);
  return '<div class="bp-tools" role="toolbar" aria-label="' + esc(n.label) + ' actions">'
    + (fixed ? '' : '<button type="button" data-tool="duplicate" data-id="' + esc(n.id) + '" title="Duplicate (Ctrl+D)" aria-label="Duplicate ' + esc(n.label) + '">' + uiIcon('copy') + '</button><button type="button" class="danger" data-tool="remove" data-id="' + esc(n.id) + '" title="Remove (Del) · Ctrl+Z restores" aria-label="Remove ' + esc(n.label) + '">' + uiIcon('trash') + '</button>')
    + '<button type="button" data-tool="menu" data-id="' + esc(n.id) + '" title="More actions (Shift+F10)" aria-label="More actions for ' + esc(n.label) + '" aria-haspopup="menu">' + uiIcon('more') + '</button></div>';
}
function renderNodes() {
  const nodes = blueprint.graph.nodes;
  const focused = document.activeElement?.closest?.('#builder-nodes [data-node]')?.dataset.node;
  $('#builder-nodes').innerHTML = nodes.map(n => '<div class="bp-node type-' + esc(n.type) + (selection.has(n.id) ? ' selected' : '') + (live[n.id] ? ' live-' + esc(live[n.id]) : '') + (nodeProblems(n.id).length ? ' invalid' : '') + '" data-node="' + esc(n.id) + '" tabindex="0" role="button" aria-label="' + esc(n.label) + ', ' + esc(STEP_TYPES[n.type].name) + (nodeProblems(n.id).length ? ', ' + nodeProblems(n.id).length + ' problems' : '') + '">'
    + (n.type !== 'input' ? '<button type="button" class="bp-port in" data-in="' + esc(n.id) + '" aria-label="Connect into ' + esc(n.label) + '" title="Drag to a step that should feed this one" tabindex="-1"></button>' : '')
    + '<div class="bp-head">' + stepIcon(n.type) + '<div class="bp-title"><strong>' + esc(n.label) + '</strong><small>' + esc(STEP_TYPES[n.type].name) + '</small></div>' + nodeBadge(n) + '</div>'
    + nodeBody(n) + nodeTools(n)
    + (n.type !== 'output' ? '<button type="button" class="bp-port out" data-out="' + esc(n.id) + '" aria-label="Connect from ' + esc(n.label) + '" title="Drag to the next step, or to empty space for a new one" tabindex="-1"></button><button type="button" class="bp-add" data-add-from="' + esc(n.id) + '" aria-label="Add a step after ' + esc(n.label) + '" title="Add a connected step" aria-haspopup="menu">+</button>' : '')
    + '</div>').join('');
  // Positions go through the CSSOM: the page's CSP refuses inline style attributes.
  nodeEls = new Map();
  for (const el of $$('#builder-nodes [data-node]')) { const n = byId(el.dataset.node); el.style.left = n.x + 'px'; el.style.top = n.y + 'px'; nodeEls.set(n.id, el); }
  if (focused && nodeEls.has(focused)) nodeEls.get(focused).focus({preventScroll: true});
  renderWires();
}
function nodeHeight(id) { return nodeEls.get(id)?.offsetHeight || NODE_H_GUESS; }
function portPoint(id, side) { const n = byId(id); if (!n) return null; const y = n.y + Math.min(PORT_Y, nodeHeight(id) / 2); return side === 'out' ? {x: n.x + NODE_W, y} : {x: n.x, y}; }
function wirePath(a, b) {
  const dx = b.x - a.x;
  const c = dx >= 0 ? Math.max(60, dx * .5) : Math.min(260, 80 + Math.abs(dx) * .25);
  return 'M ' + a.x + ' ' + a.y + ' C ' + (a.x + c) + ' ' + a.y + ', ' + (b.x - c) + ' ' + b.y + ', ' + b.x + ' ' + b.y;
}
function renderWires() {
  const svg = $('#builder-wires');
  const focusedWire = document.activeElement?.closest?.('[data-wire]')?.dataset.wire;
  const wires = blueprint.graph.edges.map((e, i) => {
    const a = portPoint(e.from, 'out'), b = portPoint(e.to, 'in');
    if (!a || !b) return '';
    const mid = {x: (a.x + b.x) / 2, y: (a.y + b.y) / 2};
    const active = selectedEdge === i;
    return '<g class="bp-wire' + (active ? ' selected' : '') + (live[e.to] || live[e.from] ? ' live' : '') + '" data-wire="' + i + '" tabindex="0" role="button" aria-label="Connection from ' + esc(labelOf(e.from)) + ' to ' + esc(labelOf(e.to)) + '"><path class="hit" d="' + wirePath(a, b) + '"/><path class="line" d="' + wirePath(a, b) + '"/><g class="bp-wire-delete" transform="translate(' + mid.x + ',' + mid.y + ')" role="button" aria-label="Remove this connection"><title>Remove connection</title><circle class="hit-area" r="14"/><circle class="face" r="9"/><path d="M-3 -3 3 3M3 -3-3 3"/></g></g>';
  }).join('');
  const preview = connectPreview ? '<path class="bp-wire-preview' + (connectPreview.snapped ? ' snapped' : '') + (connectPreview.refused ? ' refused' : '') + '" d="' + wirePath(connectPreview.from, connectPreview.to) + '"/>' : '';
  svg.innerHTML = wires + preview;
  if (focusedWire !== undefined) $$('#builder-wires [data-wire]').find(g => g.dataset.wire === focusedWire)?.focus({preventScroll: true});
}

// ------------------------------------------------------------------ camera
const viewport = $('#builder-viewport');
function worldPoint(event) { const r = viewport.getBoundingClientRect(); return {x: (event.clientX - r.left - camera.x) / camera.k, y: (event.clientY - r.top - camera.y) / camera.k}; }
function screenPoint(p) { return {x: p.x * camera.k + camera.x, y: p.y * camera.k + camera.y}; }
function zoomAt(factor, clientX, clientY) {
  const r = viewport.getBoundingClientRect();
  const k = Math.max(.35, Math.min(2, camera.k * factor));
  const px = clientX === undefined ? r.width / 2 : clientX - r.left, py = clientY === undefined ? r.height / 2 : clientY - r.top;
  camera.x = px - (px - camera.x) * (k / camera.k); camera.y = py - (py - camera.y) * (k / camera.k); camera.k = k; worldTransform();
}
function setZoom(k) { zoomAt(k / camera.k); }
function fitView() {
  const nodes = blueprint.graph.nodes; if (!nodes.length) return;
  const r = viewport.getBoundingClientRect();
  const x1 = Math.min(...nodes.map(n => n.x)), y1 = Math.min(...nodes.map(n => n.y)), x2 = Math.max(...nodes.map(n => n.x + NODE_W)), y2 = Math.max(...nodes.map(n => n.y + nodeHeight(n.id)));
  camera.k = Math.max(.35, Math.min(1.25, Math.min((r.width - 100) / (x2 - x1), (r.height - 80) / (y2 - y1))));
  camera.x = (r.width - (x2 - x1) * camera.k) / 2 - x1 * camera.k; camera.y = (r.height - (y2 - y1) * camera.k) / 2 - y1 * camera.k; worldTransform();
}
function centerOn(id) {
  const n = byId(id); if (!n) return;
  const r = viewport.getBoundingClientRect();
  const cx = n.x + NODE_W / 2, cy = n.y + nodeHeight(id) / 2;
  const s = screenPoint({x: cx, y: cy});
  if (s.x > 40 && s.x < r.width - 40 && s.y > 40 && s.y < r.height - 40) return;
  camera.x = r.width / 2 - cx * camera.k; camera.y = r.height / 2 - cy * camera.k; worldTransform();
}

// ------------------------------------------------------------------ selection
function select(id, add = false) {
  if (!add) selection = new Set();
  if (id) { if (add && selection.has(id)) selection.delete(id); else selection.add(id); }
  selectedEdge = null; typing.key = null; renderNodes(); renderInspector();
}
function selectEdge(index) { selectedEdge = index; selection = new Set(); renderNodes(); renderInspector(); }
function selectAll() { selection = new Set(blueprint.graph.nodes.map(n => n.id)); selectedEdge = null; renderNodes(); renderInspector(); hint(selection.size + ' steps selected'); }
function clearSelectionState() { selection = new Set(); selectedEdge = null; pendingPort = null; renderNodes(); renderInspector(); }

// ------------------------------------------------------------------ pointer gestures
const autoPan = {raf: 0, last: null};
function nodeAt(clientX, clientY) { return document.elementFromPoint(clientX, clientY)?.closest?.('#builder-nodes [data-node]') || null; }
function wireAt(clientX, clientY) { return document.elementFromPoint(clientX, clientY)?.closest?.('[data-wire]') || null; }
function startConnect(event, options) {
  const valid = new Set((options.reverse ? validSources(options.to) : validTargets(options.from)).map(n => n.id));
  gesture = {kind: 'connect', ...options, valid};
  const anchor = options.reverse ? portPoint(options.to, 'in') : portPoint(options.from, 'out');
  connectPreview = {from: anchor, to: worldPoint(event), snapped: false, refused: false, reverse: !!options.reverse};
  for (const [id, el] of nodeEls) { const own = id === (options.reverse ? options.to : options.from); el.classList.toggle('dim', !own && !valid.has(id)); if (!own && !valid.has(id)) el.title = options.reverse ? canConnect(id, options.to) : canConnect(options.from, id); else el.removeAttribute('title'); }
  (options.reverse ? nodeEls.get(options.to)?.querySelector('.bp-port.in') : nodeEls.get(options.from)?.querySelector('.bp-port.out'))?.classList.add('active');
  viewport.setPointerCapture(event.pointerId); viewport.classList.add('connecting'); renderWires(); event.preventDefault();
  hint(valid.size ? 'Drop on a highlighted step, or on empty space to add a new one' : 'No step can take this connection; release on empty space to add one');
}
viewport.addEventListener('pointerdown', event => {
  if (menuState) closeMenu(false);
  if (event.target.closest('[data-tool],[data-add-from],[data-issues]')) return; // click handlers own these
  const outPort = event.target.closest('[data-out]');
  const inPort = event.target.closest('[data-in]');
  const nodeEl = event.target.closest('[data-node]');
  const wire = event.target.closest('[data-wire]');
  viewport.focus({preventScroll: true});
  if (event.button === 1 || (event.button === 0 && !nodeEl && !outPort && !inPort && !wire && !event.shiftKey)) {
    gesture = {kind: 'pan', sx: event.clientX, sy: event.clientY, ox: camera.x, oy: camera.y, moved: false};
    viewport.setPointerCapture(event.pointerId); event.preventDefault(); return;
  }
  if (event.button !== 0) return;
  if (outPort) return startConnect(event, {from: outPort.dataset.out});
  if (inPort) return startConnect(event, {to: inPort.dataset.in, reverse: true});
  if (wire) {
    if (event.target.closest('.bp-wire-delete')) { removeEdge(Number(wire.dataset.wire)); return; }
    selectEdge(Number(wire.dataset.wire)); return;
  }
  if (nodeEl) {
    const id = nodeEl.dataset.node;
    if (event.shiftKey) select(id, true); else if (!selection.has(id)) select(id);
    const starts = [...selection].map(s => ({id: s, x: byId(s).x, y: byId(s).y}));
    gesture = {kind: 'drag', sx: event.clientX, sy: event.clientY, start: worldPoint(event), starts, moved: false};
    viewport.setPointerCapture(event.pointerId); event.preventDefault(); return;
  }
  if (event.shiftKey) { gesture = {kind: 'marquee', start: worldPoint(event), additive: false}; viewport.setPointerCapture(event.pointerId); viewport.classList.add('marquee'); $('#builder-marquee').classList.remove('hidden'); }
});
function applyGesture(event) {
  if (!gesture) return;
  const g = gesture;
  if (g.kind === 'pan') {
    if (!g.moved && Math.hypot(event.clientX - g.sx, event.clientY - g.sy) < 4) return;
    if (!g.moved) { g.moved = true; viewport.classList.add('panning'); }
    camera.x = g.ox + event.clientX - g.sx; camera.y = g.oy + event.clientY - g.sy; worldTransform(); return;
  }
  if (g.kind === 'connect') {
    const target = nodeAt(event.clientX, event.clientY);
    const id = target?.dataset.node;
    const ok = !!id && g.valid.has(id);
    const own = id === (g.reverse ? g.to : g.from);
    for (const [nid, el] of nodeEls) { el.classList.toggle('drop-target', ok && nid === id); el.classList.toggle('drop-refused', !!id && !ok && !own && nid === id); }
    connectPreview.to = ok ? portPoint(id, g.reverse ? 'out' : 'in') : worldPoint(event);
    connectPreview.snapped = ok; connectPreview.refused = !!id && !ok && !own;
    if (id && !ok && !own) hint((g.reverse ? canConnect(id, g.to) : canConnect(g.from, id)) || ''); else if (ok) hint('Release to connect ' + (g.reverse ? labelOf(id) + ' → ' + labelOf(g.to) : labelOf(g.from) + ' → ' + labelOf(id)));
    renderWires(); return;
  }
  if (g.kind === 'drag') {
    if (!g.moved && Math.hypot(event.clientX - g.sx, event.clientY - g.sy) < 4) return;
    if (!g.moved) { commit(); g.moved = true; for (const s of g.starts) nodeEls.get(s.id)?.classList.add('dragging'); }
    const p = worldPoint(event); const dx = p.x - g.start.x, dy = p.y - g.start.y;
    for (const s of g.starts) { const n = byId(s.id); n.x = Math.max(0, Math.min(10000, s.x + dx)); n.y = Math.max(0, Math.min(10000, s.y + dy)); const el = nodeEls.get(s.id); if (el) { el.style.left = n.x + 'px'; el.style.top = n.y + 'px'; } }
    renderWires(); return;
  }
  if (g.kind === 'marquee') {
    const a = screenPoint(g.start), b = worldPoint(event), bs = screenPoint(b); const box = $('#builder-marquee');
    box.style.left = Math.min(a.x, bs.x) + 'px'; box.style.top = Math.min(a.y, bs.y) + 'px'; box.style.width = Math.abs(bs.x - a.x) + 'px'; box.style.height = Math.abs(bs.y - a.y) + 'px';
    g.end = b;
  }
}
function autoPanTick() {
  autoPan.raf = 0;
  if (!gesture || gesture.kind === 'pan' || !autoPan.last) return;
  const r = viewport.getBoundingClientRect(), e = autoPan.last, margin = 28, speed = 12;
  let dx = 0, dy = 0;
  if (e.clientX < r.left + margin) dx = speed; else if (e.clientX > r.right - margin) dx = -speed;
  if (e.clientY < r.top + margin) dy = speed; else if (e.clientY > r.bottom - margin) dy = -speed;
  if (!dx && !dy) return;
  camera.x += dx; camera.y += dy; worldTransform(); applyGesture(e);
  autoPan.raf = requestAnimationFrame(autoPanTick);
}
viewport.addEventListener('pointermove', event => {
  if (!gesture) return;
  applyGesture(event);
  if (gesture && gesture.kind !== 'pan') { autoPan.last = {clientX: event.clientX, clientY: event.clientY}; if (!autoPan.raf) autoPan.raf = requestAnimationFrame(autoPanTick); }
});
function endConnectVisuals() {
  connectPreview = null; viewport.classList.remove('connecting');
  for (const el of nodeEls.values()) { el.classList.remove('dim', 'drop-target', 'drop-refused'); el.removeAttribute('title'); }
  $$('.bp-port.active').forEach(p => p.classList.remove('active'));
}
function cancelGesture() {
  if (!gesture) return;
  const g = gesture; gesture = null; autoPan.last = null;
  viewport.classList.remove('panning', 'marquee');
  if (g.kind === 'connect') { endConnectVisuals(); renderWires(); hint('Connection cancelled'); }
  if (g.kind === 'drag' && g.moved) { for (const s of g.starts) { const n = byId(s.id); n.x = s.x; n.y = s.y; nodeEls.get(s.id)?.classList.remove('dragging'); } editHistory.undo.pop(); updateHistoryButtons(); render(); }
  if (g.kind === 'marquee') $('#builder-marquee').classList.add('hidden');
}
function finishGesture(event) {
  if (!gesture) return;
  const g = gesture; gesture = null; autoPan.last = null;
  viewport.classList.remove('panning', 'marquee');
  if (g.kind === 'pan') { if (!g.moved && event.type === 'pointerup') { clearSelectionState(); } return; }
  if (g.kind === 'connect') {
    endConnectVisuals();
    const target = nodeAt(event.clientX, event.clientY);
    const r = viewport.getBoundingClientRect();
    const inside = event.clientX >= r.left && event.clientX <= r.right && event.clientY >= r.top && event.clientY <= r.bottom;
    if (target) { if (g.reverse) addEdge(target.dataset.node, g.to); else addEdge(g.from, target.dataset.node); }
    else if (inside && event.type === 'pointerup') { const p = worldPoint(event); renderWires(); openQuickAdd(event.clientX, event.clientY, g.reverse ? {x: p.x - NODE_W, y: p.y - PORT_Y} : {x: p.x, y: p.y - PORT_Y}, g.reverse ? {to: g.to} : {from: g.from}); }
    else { renderWires(); hint('Connection cancelled'); }
    return;
  }
  if (g.kind === 'drag') {
    for (const s of g.starts) nodeEls.get(s.id)?.classList.remove('dragging');
    if (g.moved) { for (const s of g.starts) { const n = byId(s.id); n.x = Math.round(n.x / GRID) * GRID; n.y = Math.round(n.y / GRID) * GRID; } markDirty(); render(); hint(g.starts.length === 1 ? 'Moved ' + labelOf(g.starts[0].id) : 'Moved ' + g.starts.length + ' steps'); }
    return;
  }
  if (g.kind === 'marquee') {
    $('#builder-marquee').classList.add('hidden');
    const a = g.start, b = g.end || worldPoint(event);
    const x1 = Math.min(a.x, b.x), x2 = Math.max(a.x, b.x), y1 = Math.min(a.y, b.y), y2 = Math.max(a.y, b.y);
    selection = new Set(blueprint.graph.nodes.filter(n => n.x < x2 && n.x + NODE_W > x1 && n.y < y2 && n.y + nodeHeight(n.id) > y1).map(n => n.id));
    selectedEdge = null; renderNodes(); renderInspector();
    hint(selection.size ? selection.size + (selection.size === 1 ? ' step selected' : ' steps selected') : 'Nothing inside the selection');
  }
}
viewport.addEventListener('pointerup', finishGesture);
viewport.addEventListener('pointercancel', cancelGesture);
viewport.addEventListener('lostpointercapture', () => { if (gesture) cancelGesture(); });
viewport.addEventListener('dblclick', event => {
  const nodeEl = event.target.closest('[data-node]');
  if (event.target.closest('button')) return;
  if (nodeEl) { select(nodeEl.dataset.node); $('#node-label')?.focus(); $('#node-label')?.select(); return; }
  if (event.target.closest('[data-wire]')) return;
  const p = worldPoint(event);
  openQuickAdd(event.clientX, event.clientY, {x: p.x - NODE_W / 2, y: p.y - 30});
});
viewport.addEventListener('contextmenu', event => {
  event.preventDefault();
  const nodeEl = event.target.closest('[data-node]');
  const wire = event.target.closest('[data-wire]');
  if (nodeEl) { if (!selection.has(nodeEl.dataset.node)) select(nodeEl.dataset.node); openMenu({x: event.clientX, y: event.clientY, items: nodeMenuItems(nodeEl.dataset.node), heading: labelOf(nodeEl.dataset.node), opener: nodeEls.get(nodeEl.dataset.node)}); return; }
  if (wire) { const i = Number(wire.dataset.wire); selectEdge(i); openMenu({x: event.clientX, y: event.clientY, items: wireMenuItems(i), heading: 'Connection', opener: viewport}); return; }
  const p = worldPoint(event);
  openMenu({x: event.clientX, y: event.clientY, items: canvasMenuItems({x: p.x - NODE_W / 2, y: p.y - 30}), heading: 'Canvas', opener: viewport});
});
viewport.addEventListener('wheel', event => {
  event.preventDefault();
  if (menuState) closeMenu(false);
  if (event.ctrlKey || event.metaKey) { zoomAt(Math.exp(-event.deltaY * 0.0015), event.clientX, event.clientY); }
  else { camera.x -= event.deltaX; camera.y -= event.deltaY; worldTransform(); }
}, {passive: false});
// Toolbar buttons rendered inside nodes: duplicate, remove, menu, add-after, problem badge.
$('#builder-nodes').addEventListener('click', event => {
  const tool = event.target.closest('[data-tool]');
  const add = event.target.closest('[data-add-from]');
  const badge = event.target.closest('[data-issues]');
  if (tool) {
    const id = tool.dataset.id;
    if (tool.dataset.tool === 'duplicate') { select(id); duplicateSelection(); }
    else if (tool.dataset.tool === 'remove') { select(id); removeSelection(); }
    else if (tool.dataset.tool === 'menu') { select(id); const r = tool.getBoundingClientRect(); openMenu({x: r.left, y: r.bottom + 4, items: nodeMenuItems(id), heading: labelOf(id), opener: nodeEls.get(id)}); }
    return;
  }
  if (add) { const n = byId(add.dataset.addFrom); const r = add.getBoundingClientRect(); openQuickAdd(r.right + 6, r.top - 8, {x: n.x + NODE_W + 80, y: n.y}, {from: n.id}); return; }
  if (badge) { const id = badge.dataset.issues; const first = problems.find(p => p.node === id); if (first) focusProblem(first); else select(id); }
});
$('#builder-wires').addEventListener('focusin', event => { const g = event.target.closest('[data-wire]'); if (g && selectedEdge !== Number(g.dataset.wire)) { selectedEdge = Number(g.dataset.wire); selection = new Set(); renderNodes(); renderInspector(); } });

// ------------------------------------------------------------------ keyboard
viewport.addEventListener('keydown', event => {
  if (menuState) return;
  const editing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName);
  if (editing) return;
  const meta = event.ctrlKey || event.metaKey;
  const key = event.key.toLowerCase();
  const focusedNode = document.activeElement?.closest?.('#builder-nodes [data-node]')?.dataset.node;
  if (meta && key === 'z') { event.preventDefault(); event.shiftKey ? redo() : undo(); return; }
  if (meta && key === 'y') { event.preventDefault(); redo(); return; }
  if (meta && key === 'a') { event.preventDefault(); selectAll(); return; }
  if (meta && key === 'd') { event.preventDefault(); duplicateSelection(); return; }
  if (meta && key === '0') { event.preventDefault(); setZoom(1); return; }
  if (event.key === 'Delete' || event.key === 'Backspace') { event.preventDefault(); if (selectedEdge !== null) removeEdge(selectedEdge); else removeSelection(); return; }
  if (event.key === 'Escape') { if (gesture) { cancelGesture(); return; } if (pendingPort) { pendingPort = null; hint('Connection cancelled'); return; } clearSelectionState(); return; }
  if (event.key === 'Enter') { if (focusedNode) { if (pendingPort && pendingPort !== focusedNode) { addEdge(pendingPort, focusedNode); pendingPort = null; } else select(focusedNode); } else if (selectedEdge !== null) { $('#edge-remove')?.focus(); } return; }
  if ((event.key === 'F10' && event.shiftKey) || event.key === 'ContextMenu') { event.preventDefault(); const id = focusedNode || (selection.size === 1 ? [...selection][0] : null); if (id) { const r = nodeEls.get(id).getBoundingClientRect(); openMenu({x: r.left + 20, y: r.top + 20, items: nodeMenuItems(id), heading: labelOf(id), opener: nodeEls.get(id)}); } return; }
  if (!meta && key === 'c') { if (focusedNode) { pendingPort = focusedNode; hint('Connecting from ' + labelOf(pendingPort) + ': focus another step and press Enter, or Esc to cancel'); } return; }
  if (!meta && (key === 'f' || event.key === 'Home')) { event.preventDefault(); fitView(); return; }
  if (!meta && (event.key === '+' || event.key === '=')) { event.preventDefault(); zoomAt(1.2); return; }
  if (!meta && (event.key === '-' || event.key === '_')) { event.preventDefault(); zoomAt(1 / 1.2); return; }
  if (event.key === '?') { event.preventDefault(); $('#shortcuts-dialog').showModal(); return; }
  if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(event.key) && selection.size) {
    event.preventDefault(); commitTyping('nudge');
    const step = event.shiftKey ? GRID * 5 : GRID;
    for (const id of selection) { const n = byId(id); n.x = Math.max(0, n.x + (event.key === 'ArrowRight' ? step : event.key === 'ArrowLeft' ? -step : 0)); n.y = Math.max(0, n.y + (event.key === 'ArrowDown' ? step : event.key === 'ArrowUp' ? -step : 0)); }
    markDirty(); render();
  }
});

// ------------------------------------------------------------------ context menus
const menu = $('#context-menu');
function openMenu({x, y, items, heading, opener}) {
  closeMenu(false);
  menuState = {items, opener, x, y, heading};
  menu.innerHTML = (heading ? '<div class="menu-heading">' + esc(heading) + '</div>' : '') + items.map((it, i) => it.separator ? '<hr>' : '<button type="button" role="menuitem" data-item="' + i + '" class="' + (it.danger ? 'danger' : '') + '"' + (it.disabled ? ' aria-disabled="true"' : '') + (it.submenu ? ' aria-haspopup="menu"' : '') + ' title="' + esc(it.disabled ? (it.reason || '') : (it.title || '')) + '">' + (it.icon || '') + '<span>' + esc(it.label) + (it.hint || (it.disabled && it.reason) ? '<small>' + esc(it.disabled && it.reason ? it.reason : it.hint) + '</small>' : '') + '</span>' + (it.submenu ? '<i aria-hidden="true">›</i>' : '') + '</button>').join('');
  menu.classList.remove('hidden');
  const w = menu.offsetWidth, h = menu.offsetHeight;
  menu.style.left = Math.max(8, Math.min(x, innerWidth - w - 8)) + 'px';
  menu.style.top = Math.max(8, Math.min(y, innerHeight - h - 8)) + 'px';
  menu.querySelector('button')?.focus();
}
function closeMenu(restoreFocus = true) {
  if (!menuState) return;
  const s = menuState; menuState = null;
  menu.classList.add('hidden'); menu.innerHTML = '';
  if (restoreFocus) s.opener?.focus?.({preventScroll: true});
}
function activateMenuItem(i) {
  const s = menuState; if (!s) return;
  const it = s.items[i]; if (!it || it.separator) return;
  if (it.disabled) { hint(it.reason || 'Not available'); return; }
  if (it.submenu) { const items = it.submenu(); openMenu({x: s.x, y: s.y, items: [...items, {separator: true}, {label: 'Back', hint: 'Esc', action: () => openMenu({x: s.x, y: s.y, items: s.items, heading: s.heading, opener: s.opener})}], heading: it.label, opener: s.opener}); return; }
  closeMenu(); it.action();
}
menu.addEventListener('click', event => { const b = event.target.closest('[data-item]'); if (b) activateMenuItem(Number(b.dataset.item)); });
menu.addEventListener('keydown', event => {
  const buttons = $$('#context-menu [data-item]');
  const index = buttons.indexOf(document.activeElement);
  if (event.key === 'Escape') { event.preventDefault(); closeMenu(); return; }
  if (event.key === 'ArrowDown') { event.preventDefault(); buttons[(index + 1) % buttons.length]?.focus(); return; }
  if (event.key === 'ArrowUp') { event.preventDefault(); buttons[(index - 1 + buttons.length) % buttons.length]?.focus(); return; }
  if (event.key === 'Home') { event.preventDefault(); buttons[0]?.focus(); return; }
  if (event.key === 'End') { event.preventDefault(); buttons.at(-1)?.focus(); return; }
  if (event.key === 'Tab') { closeMenu(false); return; }
  if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); if (index >= 0) activateMenuItem(Number(buttons[index].dataset.item)); return; }
  if (event.key.length === 1 && !event.ctrlKey && !event.metaKey) { const next = buttons.find((b, i) => i > index && b.textContent.trim().toLowerCase().startsWith(event.key.toLowerCase())) || buttons.find(b => b.textContent.trim().toLowerCase().startsWith(event.key.toLowerCase())); next?.focus(); }
});
document.addEventListener('pointerdown', event => { if (menuState && !event.target.closest('#context-menu')) closeMenu(false); }, true);
window.addEventListener('resize', () => closeMenu(false));
window.addEventListener('blur', () => closeMenu(false));

function quickAddItems(at, link) {
  return PALETTE.map(type => ({label: STEP_TYPES[type].name, title: STEP_TYPES[type].description, icon: stepIcon(type), action: () => addNode(type, at, link)}));
}
function openQuickAdd(x, y, at, link) {
  const heading = link?.from ? 'Add a step after ' + labelOf(link.from) : link?.to ? 'Add a step before ' + labelOf(link.to) : link?.insert !== undefined ? 'Insert a step here' : 'Add a step here';
  openMenu({x, y, items: quickAddItems(at, link), heading, opener: viewport});
}
function nodeMenuItems(id) {
  const n = byId(id); if (!n) return [];
  const fixed = FIXED.includes(n.type);
  const targets = validTargets(id), sources = validSources(id);
  const touching = blueprint.graph.edges.filter(e => e.from === id || e.to === id).length;
  return [
    {label: 'Rename', hint: 'Double-click', action: () => { select(id); $('#node-label')?.focus(); $('#node-label')?.select(); }},
    {label: 'Add a step after this…', disabled: n.type === 'output', reason: 'The result output ends the flow', submenu: () => quickAddItems({x: n.x + NODE_W + 80, y: n.y}, {from: id})},
    {label: 'Connect to…', disabled: !targets.length, reason: n.type === 'output' ? 'The result output ends the flow' : 'Every reachable step is already connected', submenu: () => targets.map(t => ({label: t.label, hint: STEP_TYPES[t.type].name, icon: stepIcon(t.type), action: () => addEdge(id, t.id)}))},
    {label: 'Receive from…', disabled: !sources.length, reason: n.type === 'input' ? 'The task input starts the flow' : 'Every possible source is already connected', submenu: () => sources.map(t => ({label: t.label, hint: STEP_TYPES[t.type].name, icon: stepIcon(t.type), action: () => addEdge(t.id, id)}))},
    {label: 'Disconnect all', hint: touching ? touching + (touching === 1 ? ' connection' : ' connections') : '', disabled: !touching, reason: 'No connections on this step', action: () => disconnectNode(id)},
    {separator: true},
    {label: 'Duplicate', hint: 'Ctrl+D', icon: uiIcon('copy'), disabled: fixed, reason: 'The task input and result output are fixed', action: () => { select(id); duplicateSelection(); }},
    {label: 'Remove', hint: 'Del · Ctrl+Z restores', icon: uiIcon('trash'), danger: true, disabled: fixed, reason: 'The task input and result output are fixed', action: () => { select(id); removeSelection(); }}
  ];
}
function wireMenuItems(i) {
  const e = blueprint.graph.edges[i]; if (!e) return [];
  const a = portPoint(e.from, 'out'), b = portPoint(e.to, 'in');
  const mid = {x: (a.x + b.x) / 2 - NODE_W / 2, y: (a.y + b.y) / 2 - PORT_Y};
  return [
    {label: 'Insert a step here…', hint: labelOf(e.from) + ' → new step → ' + labelOf(e.to), submenu: () => quickAddItems(mid, {insert: i})},
    {separator: true},
    {label: 'Remove connection', hint: 'Del', icon: uiIcon('trash'), danger: true, action: () => removeEdge(i)}
  ];
}
function canvasMenuItems(at) {
  return [
    {label: 'Add a step here…', submenu: () => quickAddItems(at)},
    {separator: true},
    {label: 'Fit to view', hint: 'F', action: fitView},
    {label: 'Reset zoom to 100%', hint: 'Ctrl+0', action: () => setZoom(1)},
    {label: 'Arrange steps left to right', action: arrange},
    {label: 'Select all', hint: 'Ctrl+A', action: selectAll}
  ];
}

// ------------------------------------------------------------------ mutations
function addEdge(from, to) {
  const refusal = canConnect(from, to);
  if (refusal) { hint(refusal); renderWires(); return false; }
  commit(); blueprint.graph.edges.push({from, to}); markDirty(); render(); renderInspector();
  hint('Connected ' + labelOf(from) + ' → ' + labelOf(to));
  return true;
}
function removeEdge(index) {
  const e = blueprint.graph.edges[index]; if (!e) return;
  commit(); blueprint.graph.edges.splice(index, 1); selectedEdge = null; markDirty(); render(); renderInspector();
  hint('Removed the connection ' + labelOf(e.from) + ' → ' + labelOf(e.to) + ' · Ctrl+Z restores it');
}
function disconnectNode(id) {
  const count = blueprint.graph.edges.filter(e => e.from === id || e.to === id).length; if (!count) return;
  commit(); blueprint.graph.edges = blueprint.graph.edges.filter(e => e.from !== id && e.to !== id); selectedEdge = null; markDirty(); render(); renderInspector();
  hint('Removed ' + count + (count === 1 ? ' connection' : ' connections') + ' from ' + labelOf(id) + ' · Ctrl+Z restores them');
}
function freeSpot(at) {
  const p = {x: Math.round(at.x / GRID) * GRID, y: Math.round(at.y / GRID) * GRID};
  for (let i = 0; i < 12; i++) {
    const overlaps = blueprint.graph.nodes.some(n => Math.abs(n.x - p.x) < NODE_W - 20 && Math.abs(n.y - p.y) < nodeHeight(n.id) - 10);
    if (!overlaps) break;
    p.y += 160;
  }
  return p;
}
function addNode(type, at, link) {
  commit();
  const id = newId();
  const config = {};
  if (type === 'agent') { config.mode = 'act'; config.instructions = ''; config.runner = runnerFor('gemini'); }
  if (type === 'product-graph') Object.assign(config, latestGraphRef());
  if (type === 'monarch') config.runner = {provider: 'bedrock', model: 'claude-opus-4-8', effort: 'default'};
  const count = blueprint.graph.nodes.length;
  const position = freeSpot(at || {x: 120 + (count % 4) * 280, y: 360 + Math.floor(count / 4) * 180});
  blueprint.graph.nodes.push({id, type, label: STEP_TYPES[type].name, x: Math.max(0, position.x), y: Math.max(0, position.y), config});
  let note = 'Added ' + STEP_TYPES[type].name;
  if (link?.from && canConnect(link.from, id) === null) { blueprint.graph.edges.push({from: link.from, to: id}); note += ' after ' + labelOf(link.from); }
  else if (link?.to && canConnect(id, link.to) === null) { blueprint.graph.edges.push({from: id, to: link.to}); note += ' before ' + labelOf(link.to); }
  else if (link?.insert !== undefined) {
    const e = blueprint.graph.edges[link.insert];
    if (e && canConnect(e.from, id) === null && canConnect(id, e.to) === null) { blueprint.graph.edges.splice(link.insert, 1); blueprint.graph.edges.push({from: e.from, to: id}, {from: id, to: e.to}); note += ' between ' + labelOf(e.from) + ' and ' + labelOf(e.to); }
  }
  selection = new Set([id]); selectedEdge = null; markDirty(); render(); renderInspector(); centerOn(id);
  hint(note + ' · configure it in the panel on the right');
  if (type === 'agent') $('#node-instructions')?.focus({preventScroll: true});
}
function removeSelection() {
  const ids = [...selection].filter(id => !FIXED.includes(byId(id)?.type));
  const kept = selection.size - ids.length;
  if (!ids.length) { if (kept) hint('The task input and result output are fixed'); return; }
  commit();
  const names = ids.map(labelOf);
  blueprint.graph.nodes = blueprint.graph.nodes.filter(n => !ids.includes(n.id));
  blueprint.graph.edges = blueprint.graph.edges.filter(e => !ids.includes(e.from) && !ids.includes(e.to));
  selection = new Set(); selectedEdge = null; markDirty(); render(); renderInspector();
  hint('Removed ' + (names.length === 1 ? names[0] : names.length + ' steps') + ' · Ctrl+Z restores ' + (names.length === 1 ? 'it' : 'them'));
  viewport.focus({preventScroll: true});
}
function duplicateSelection() {
  const ids = [...selection].filter(id => !FIXED.includes(byId(id)?.type));
  if (!ids.length) { if (selection.size) hint('The task input and result output are fixed'); return; }
  commit();
  const map = {};
  for (const id of ids) { const n = byId(id); const copy = structuredClone(n); copy.id = newId(); copy.x += 40; copy.y += 60; copy.label = n.label + ' copy'; delete copy.config.baseline; map[id] = copy.id; blueprint.graph.nodes.push(copy); }
  for (const e of [...blueprint.graph.edges]) if (map[e.from] && map[e.to]) blueprint.graph.edges.push({from: map[e.from], to: map[e.to]});
  selection = new Set(Object.values(map)); selectedEdge = null; markDirty(); render(); renderInspector();
  hint('Duplicated ' + (ids.length === 1 ? labelOf(ids[0]) : ids.length + ' steps') + ' · the copies are selected, drag them into place');
}
function arrange() {
  commit();
  const nodes = blueprint.graph.nodes, edges = blueprint.graph.edges;
  const depth = new Map(nodes.map(n => [n.id, 0]));
  for (let i = 0; i < nodes.length; i++) for (const e of edges) depth.set(e.to, Math.min(nodes.length, Math.max(depth.get(e.to), depth.get(e.from) + 1)));
  const columns = new Map();
  for (const n of nodes) { const d = depth.get(n.id); if (!columns.has(d)) columns.set(d, []); columns.get(d).push(n); }
  for (const [d, column] of columns) { column.sort((a, b) => a.y - b.y); column.forEach((n, i) => { n.x = 60 + d * 300; n.y = 60 + i * 190; }); }
  markDirty(); render(); fitView(); hint('Arranged left to right · Ctrl+Z restores the previous layout');
}

// ------------------------------------------------------------------ inspector
function option(value, label, selected) { return '<option value="' + esc(value) + '"' + (selected ? ' selected' : '') + '>' + esc(label) + '</option>'; }
function invalidAttr(n, ...needles) { const issues = nodeProblems(n.id).map(m => m.toLowerCase()); return issues.some(m => needles.some(k => m.includes(k))) ? ' aria-invalid="true"' : ''; }
function runnerFields(n) {
  const r = n.config.runner;
  const providers = n.type === 'monarch' ? ['bedrock'] : ['anthropic', 'openai', 'gemini', 'fireworks', 'moonshot', 'zai', 'claude-code', 'codex'];
  const control = controlFor(r);
  let models;
  if (r.provider === 'bedrock') models = ENTERPRISE_MODELS.map(m => option(m, m, r.model === m));
  else if (['claude-code', 'codex'].includes(r.provider)) models = null;
  else models = controls.filter(c => c.provider === r.provider).map(c => option(c.model, c.name + ' · $' + c.prices_per_million.input + ' in / $' + c.prices_per_million.output + ' out per M', r.model === c.model || r.model === c.id));
  if (models && !models.some(m => m.includes(' selected')) && r.model) models.unshift(option(r.model, r.model + ' (no rate card)', true));
  const efforts = r.provider === 'bedrock' ? ['default'] : control ? ['default', ...control.efforts] : ALL_EFFORTS;
  const cap = nodeCapability(n.id);
  return '<div class="field"><label for="node-provider">Runner</label><select id="node-provider">' + providers.map(p => option(p, PROVIDER_LABELS[p], p === r.provider)).join('') + '</select></div>'
    + '<div class="field"><label for="node-model">Model</label>' + (models ? '<select id="node-model"' + invalidAttr(n, 'rate-carded', 'model') + '>' + models.join('') + (r.provider === 'fireworks' ? option('__custom__', 'Other Fireworks model…', false) : '') + '</select>' : '<input id="node-model" value="' + esc(r.model || '') + '" placeholder="Model alias for the native harness" autocomplete="off">')
    + (r.provider === 'fireworks' ? '<div class="field-tools"><input id="node-model-custom" list="fireworks-model-list" class="' + (models.some(m => m.includes(' selected')) ? 'hidden' : '') + '" value="' + esc(r.model || '') + '" placeholder="accounts/fireworks/models/…" autocomplete="off"><button class="text-button" id="node-load-models" type="button">Load Fireworks catalog</button><small id="node-model-status"></small></div>' : '') + '</div>'
    + '<div class="field"><label for="node-effort">Reasoning effort</label><select id="node-effort">' + efforts.map(e => option(e, e === 'default' ? 'Default' + (control?.default_effort ? ' (' + control.default_effort + ')' : '') : e, e === r.effort)).join('') + '</select>' + (control && !control.efforts.length ? '<small class="node-help">This API has no reasoning-effort control.</small>' : '') + '</div>'
    + (cap ? '<div class="capability ' + (cap.supported ? (cap.launch_block ? 'hold' : 'ok') : 'bad') + '">' + esc(cap.supported ? (cap.launch_block ? 'Valid runner, on hold: ' + cap.launch_block : cap.reason) : cap.reason) + '</div>' : '');
}
function graphFields(n) {
  const c = n.config;
  const graphs = productGraphs.filter(g => (g.versions || []).some(v => ['complete', 'incomplete'].includes(v.status)));
  if (!graphs.length) return '<div class="capability hold">No prepared product graph exists yet. <button class="text-button" type="button" data-open-graphs="1">Open Product graphs</button> to declare fields and prepare a version.</div>';
  const g = graphRecord(c.graph);
  const usable = (g?.versions || []).filter(v => ['complete', 'incomplete'].includes(v.status));
  const v = graphVersion(c);
  return '<div class="field"><label for="node-graph">Product graph</label><select id="node-graph"' + (g ? '' : ' aria-invalid="true"') + '><option value="">Choose a product graph…</option>' + graphs.map(x => option(x.id, x.name + ' · ' + x.versions.length + (x.versions.length === 1 ? ' version' : ' versions'), x.id === c.graph)).join('') + '</select></div>'
    + (g ? '<div class="field"><label for="node-graph-version">Version</label><select id="node-graph-version"' + (v ? '' : ' aria-invalid="true"') + '>' + (v ? '' : '<option value="">Choose a version…</option>') + usable.slice().reverse().map(x => option(x.version, 'v' + x.version + ' · ' + x.status + ' · ' + x.fields.length + ' fields · ' + Object.keys(x.records || {}).length + ' products · $' + x.cost_usd, x.version === c.version)).join('') + '</select></div>' : '')
    + (v ? '<div class="capability ' + (v.status === 'complete' ? 'ok' : 'hold') + '"><strong>Delivered to every step downstream</strong><ul class="graph-field-list">' + v.fields.map(f => '<li><code>' + esc(f.path) + '</code> <small>' + esc(f.type) + (f.since ? ' · since v' + f.since : '') + '</small>' + (f.description ? '<br><span>' + esc(f.description) + '</span>' : '') + '</li>').join('') + '</ul><small>' + Object.keys(v.records || {}).length + ' products · prepared ' + esc(new Date(v.prepared_at).toLocaleString()) + ' · ' + esc(v.sha256.slice(0, 12)) + (v.problems?.length ? ' · ' + v.problems.length + ' notes' : '') + '</small> <button class="text-button" type="button" data-open-graphs="' + esc(c.graph) + '">Open in Product graphs</button></div>' : '');
}
function connectionsEditor(n) {
  const incoming = blueprint.graph.edges.map((e, i) => ({e, i})).filter(x => x.e.to === n.id);
  const outgoing = blueprint.graph.edges.map((e, i) => ({e, i})).filter(x => x.e.from === n.id);
  const targets = validTargets(n.id), sources = validSources(n.id);
  const rows = [...incoming.map(x => '<li><i aria-hidden="true">←</i><span>' + esc(labelOf(x.e.from)) + '</span><button class="text-button" data-unlink="' + x.i + '" type="button" aria-label="Remove the connection from ' + esc(labelOf(x.e.from)) + '">Remove</button></li>'), ...outgoing.map(x => '<li><i aria-hidden="true">→</i><span>' + esc(labelOf(x.e.to)) + '</span><button class="text-button" data-unlink="' + x.i + '" type="button" aria-label="Remove the connection to ' + esc(labelOf(x.e.to)) + '">Remove</button></li>')];
  const options = (targets.length ? '<optgroup label="Send output to">' + targets.map(t => option('to:' + t.id, t.label, false)).join('') + '</optgroup>' : '') + (sources.length ? '<optgroup label="Receive from">' + sources.map(t => option('from:' + t.id, t.label, false)).join('') + '</optgroup>' : '');
  return '<div class="field"><label for="node-connect">Connections</label>' + (rows.length ? '<ul class="connections">' + rows.join('') + '</ul>' : '<small class="node-help">Not connected yet.</small>')
    + (options ? '<div class="field-tools"><select id="node-connect" aria-label="Add a connection"><option value="">Add a connection…</option>' + options + '</select></div>' : '<small class="node-help">Every reachable step is already connected.</small>') + '</div>';
}
function renderInspector(keepFocus = false) {
  const active = keepFocus ? document.activeElement : null;
  const activeId = active?.closest?.('#node-settings') ? active.id : null, activeValue = activeId && ['INPUT', 'TEXTAREA'].includes(active.tagName) ? active.value : null, activePos = active?.selectionStart;
  const box = $('#node-settings');
  const deleteButton = $('#node-delete'), duplicateButton = $('#node-duplicate');
  if (selectedEdge !== null) {
    const e = blueprint.graph.edges[selectedEdge];
    $('#node-heading').textContent = 'Connection';
    box.innerHTML = '<p class="node-help"><strong>' + esc(labelOf(e.from)) + ' → ' + esc(labelOf(e.to)) + '</strong>. A step receives the outputs of the steps directly before it, plus any knowledge prepared upstream.</p><div class="field-tools"><button class="button" id="edge-insert" type="button" aria-haspopup="menu">Insert a step here…</button><button class="button danger" id="edge-remove" type="button" title="Delete">Remove connection</button></div>';
    $('#edge-remove').onclick = () => removeEdge(selectedEdge);
    $('#edge-insert').onclick = event => { const r = event.currentTarget.getBoundingClientRect(); openMenu({x: r.left, y: r.bottom + 4, items: wireMenuItems(selectedEdge)[0].submenu(), heading: 'Insert a step here', opener: event.currentTarget}); };
    deleteButton.disabled = true; duplicateButton.disabled = true; return;
  }
  if (selection.size !== 1) {
    $('#node-heading').textContent = selection.size > 1 ? selection.size + ' steps selected' : 'Step settings';
    box.innerHTML = '<p class="node-help">' + (selection.size > 1 ? 'Drag to move them together. Delete removes them (Ctrl+Z restores), Ctrl+D duplicates them.' : 'Select a step on the canvas to edit its name, runner, mode and instructions. Drag from a port to another step to connect them, or right-click for actions.') + '</p>';
    const movable = [...selection].some(id => !FIXED.includes(byId(id)?.type));
    deleteButton.disabled = !movable; duplicateButton.disabled = !movable; return;
  }
  const n = byId([...selection][0]); if (!n) return;
  const c = n.config = n.config || {};
  $('#node-heading').textContent = STEP_TYPES[n.type].name;
  deleteButton.disabled = FIXED.includes(n.type); duplicateButton.disabled = FIXED.includes(n.type);
  deleteButton.title = FIXED.includes(n.type) ? 'The task input and result output are fixed' : 'Remove (Del) · Ctrl+Z restores';
  const issues = nodeProblems(n.id);
  let html = '<p class="node-help">' + esc(STEP_TYPES[n.type].description) + '</p>' + (issues.length ? '<ul class="node-issues" tabindex="-1" aria-label="Problems on this step">' + issues.map(m => '<li>' + esc(m) + '</li>').join('') + '</ul>' : '')
    + '<div class="field"><label for="node-label">Step name</label><input id="node-label" value="' + esc(n.label) + '" maxlength="100" autocomplete="off"' + invalidAttr(n, 'short name') + '></div>';
  if (n.type === 'agent') html += '<div class="field"><label id="node-mode-label">Mode</label><div class="segmented" role="radiogroup" aria-labelledby="node-mode-label"><label><input type="radio" name="node-mode" value="act" ' + ((c.mode || 'act') === 'act' ? 'checked' : '') + '>Act<small>uses application tools</small></label><label><input type="radio" name="node-mode" value="advise" ' + (c.mode === 'advise' ? 'checked' : '') + '>Advise<small>text only, for a later step</small></label></div></div>';
  if (c.runner) html += runnerFields(n);
  if (n.type === 'product-graph') html += graphFields(n);
  if (n.type === 'agent') html += '<div class="field"><label for="node-instructions">Instructions</label><textarea id="node-instructions" rows="8"' + invalidAttr(n, 'instructions') + ' placeholder="' + esc('What this step must do and how to decide it is done') + '">' + esc(c.instructions || '') + '</textarea><small class="node-help counter">' + (c.instructions || '').length + ' characters</small></div>';
  if (n.type === 'agent') html += '<div class="field"><label for="node-turns">Turn limit</label><input id="node-turns" type="number" min="1" max="50" value="' + esc(c.max_turns || '') + '" placeholder="run setting"' + invalidAttr(n, 'turn limit') + '></div>';
  if (n.type === 'monarch') html += '<div class="capability hold">' + esc(c.baseline ? 'Pinned to ' + c.baseline.commit : 'Pinned to the latest TestBoxLab/monarch main when you publish.') + ' Runs once the Enterprise adapter exists; until then this version publishes as a definition.</div>';
  html += connectionsEditor(n);
  box.innerHTML = html;
  const edit = (selector, fn, rerender = true) => { const el = $(selector); if (!el) return; el.oninput = () => { commitTyping(selector + n.id); fn(el.value); markDirty(); renderNodes(); if (rerender) renderInspector(true); }; };
  edit('#node-label', v => n.label = v, false);
  edit('#node-instructions', v => { c.instructions = v; $('.counter') && ($('.counter').textContent = v.length + ' characters'); }, false);
  edit('#node-turns', v => { if (v === '') delete c.max_turns; else c.max_turns = Number(v); }, false);
  $$('[name=node-mode]').forEach(r => r.onchange = () => { commit(); c.mode = r.value; markDirty(); renderNodes(); renderInspector(true); hint(n.label + ' now ' + (r.value === 'advise' ? 'advises in text for a later step' : 'acts with the application tools')); });
  if ($('#node-provider')) $('#node-provider').onchange = e => { commit(); const p = e.target.value; c.runner = p === 'bedrock' ? {provider: 'bedrock', model: 'claude-opus-4-8', effort: 'default'} : NATIVE_DEFAULTS[p] ? {provider: p, model: NATIVE_DEFAULTS[p], effort: 'default'} : runnerFor(p); markDirty(); renderNodes(); renderInspector(true); if (p === 'fireworks') loadFireworks(false); };
  if ($('#node-model')) { const el = $('#node-model'); const handler = () => { if (el.value === '__custom__') { $('#node-model-custom')?.classList.remove('hidden'); $('#node-model-custom')?.focus(); return; } commitTyping('#node-model' + n.id); c.runner.model = el.value; markDirty(); renderNodes(); renderInspector(true); }; if (el.tagName === 'SELECT') el.onchange = handler; else el.oninput = handler; }
  if ($('#node-model-custom')) $('#node-model-custom').oninput = e => { commitTyping('#node-model-custom' + n.id); c.runner.model = e.target.value; markDirty(); renderNodes(); };
  if ($('#node-effort')) $('#node-effort').onchange = e => { commit(); c.runner.effort = e.target.value; markDirty(); renderNodes(); renderInspector(true); };
  if ($('#node-load-models')) $('#node-load-models').onclick = () => loadFireworks(true);
  if ($('#node-graph')) $('#node-graph').onchange = e => { commit(); const g = graphRecord(e.target.value); const latest = [...(g?.versions || [])].reverse().find(v => ['complete', 'incomplete'].includes(v.status)); if (g) { c.graph = g.id; if (latest) c.version = latest.version; else delete c.version; } else { delete c.graph; delete c.version; } markDirty(); renderNodes(); renderInspector(true); };
  if ($('#node-graph-version')) $('#node-graph-version').onchange = e => { commit(); if (Number(e.target.value)) c.version = Number(e.target.value); else delete c.version; markDirty(); renderNodes(); renderInspector(true); };
  $$('#node-settings [data-open-graphs]').forEach(b => b.onclick = () => setStudioMode('graphs', b.dataset.openGraphs));
  $$('[data-unlink]').forEach(b => b.onclick = () => { removeEdge(Number(b.dataset.unlink)); select(n.id); $('#node-connect')?.focus(); });
  if ($('#node-connect')) $('#node-connect').onchange = e => { const [dir, other] = e.target.value.split(':'); if (!other) return; if (dir === 'to') addEdge(n.id, other); else addEdge(other, n.id); select(n.id); $('#node-connect')?.focus(); };
  if (keepFocus && activeId) { const again = $('#' + CSS.escape(activeId)); if (again) { again.focus({preventScroll: true}); if (activeValue !== null && again.value === activeValue && activePos !== undefined && again.setSelectionRange) try { again.setSelectionRange(activePos, activePos); } catch {} } }
}

// ------------------------------------------------------------------ library, save, publish, prepare, run
function busy(button, label) {
  const text = button.textContent;
  button.disabled = true; button.setAttribute('aria-busy', 'true'); button.textContent = label;
  return () => { button.disabled = false; button.removeAttribute('aria-busy'); button.textContent = text; };
}
function setBlueprint(value, note) {
  localStorage.removeItem('ailabs-architecture-draft');
  blueprint = structuredClone(value); selection = new Set(); selectedEdge = null; editHistory.undo = []; editHistory.redo = []; live = {}; typing.key = null;
  $('#blueprint-name').value = blueprint.name || ''; $('#blueprint-notes').value = blueprint.notes || '';
  markSaved(note || (blueprint.id ? 'Draft revision ' + blueprint.revision : 'New from template'));
  updateHistoryButtons(); render(); renderInspector(); renderVersions(); fitView(); validateNow();
}
function renderLibrary() {
  const value = $('#blueprint-library').value;
  $('#blueprint-library').innerHTML = '<option value="">New architecture…</option>' + blueprints.map(b => option(b.id, b.name + ' · ' + (b.versions?.length ? 'v' + b.versions.length : 'draft'), false)).join('');
  if ([...$('#blueprint-library').options].some(o => o.value === value)) $('#blueprint-library').value = value;
}
async function loadBlueprints() { const response = await api('/api/blueprints'); blueprints = response.items; renderLibrary(); }
async function loadControls() { try { const matrix = await api('/api/capabilities'); controls = matrix.controls || []; state.capabilities = matrix; } catch (e) { toast(e.message); } }
async function saveDraft() {
  blueprint.name = $('#blueprint-name').value; blueprint.notes = $('#blueprint-notes').value;
  const sent = structuredClone({id: blueprint.id, revision: blueprint.revision, name: blueprint.name, notes: blueprint.notes, graph: blueprint.graph});
  const saved = await api('/api/blueprints/draft', sent);
  const unchanged = JSON.stringify([blueprint.graph, blueprint.name, blueprint.notes]) === JSON.stringify([sent.graph, sent.name, sent.notes]);
  blueprint.id = saved.id; blueprint.revision = saved.revision;
  if (unchanged) markSaved('Draft saved · revision ' + saved.revision); else markDirty();
  await loadBlueprints(); $('#blueprint-library').value = saved.id; renderVersions();
  return saved;
}
function readinessLabel(r) { return {ready: 'Ready to run', adapter_required: 'Needs the Enterprise adapter', blocked: 'On hold', unsupported: 'Unsupported configuration', preparation_required: 'Prepare knowledge first', source_required: 'Historical source missing'}[r?.runtime] || (r?.runtime || ''); }
function latestVersion() { return blueprints.find(x => x.id === blueprint.id)?.versions?.at(-1) || null; }
function runRefusal() {
  const latest = latestVersion();
  if (!latest) return 'Publish a version first. Runs bind to a published version, never to the draft.';
  if (!latest.readiness?.launchable) return 'Version ' + latest.version + ' cannot run: ' + readinessLabel(latest.readiness) + (latest.readiness?.reasons?.[0] ? '. ' + latest.readiness.reasons[0] : '') + (latest.readiness?.runtime === 'preparation_required' ? ' Use Prepare knowledge in the versions list.' : '');
  return null;
}
function updateRunButton() {
  const button = $('#builder-run');
  const refusal = runRefusal();
  const latest = latestVersion();
  button.classList.toggle('is-disabled', !!refusal);
  button.setAttribute('aria-disabled', String(!!refusal));
  button.textContent = latest ? 'Run version ' + latest.version : 'Run latest version';
  button.title = refusal || ('Open the launcher with version ' + latest.version + ' selected' + (dirty ? '. The draft has unsaved edits; the published version runs' : ''));
}
function renderVersions() {
  const record = blueprints.find(x => x.id === blueprint.id);
  const versions = record?.versions?.slice().reverse() || [];
  const latest = versions[0]?.version;
  $('#blueprint-versions').innerHTML = versions.length ? versions.map(v => {
    const r = v.readiness || {}; const gs = Object.values(v.graphs || {});
    return '<article class="version-row' + (v.version === latest ? ' latest' : '') + '"><div class="version-main"><strong>Version ' + v.version + '</strong><span class="bp-chip ' + esc(r.runtime || '') + '">' + esc(readinessLabel(r)) + '</span>' + gs.map(g => '<span class="bp-chip ' + (g.status === 'complete' ? 'ok' : 'warn') + '" title="' + esc(g.fields.join(', ')) + '">' + esc(g.name + ' v' + g.version + ' · ' + g.products + ' products · ' + g.sha256.slice(0, 8)) + '</span>').join('')
      + '<p>' + esc(v.notes || 'Published architecture') + '</p>' + (r.reasons?.length ? '<small class="version-reason">' + esc(r.reasons.join(' ')) + '</small>' : '') + '<small>' + esc(new Date(v.published_at).toLocaleString()) + ' · graph ' + esc((v.sha256 || '').slice(0, 12)) + '</small></div>'
      + '<div class="version-actions">' + (r.launchable ? '<button class="button primary" data-run-version="' + v.version + '" title="Open the launcher with this version selected">Run</button>' : '') + (r.runtime === 'preparation_required' ? '<button class="button" data-open-graphs="1">Open Product graphs</button>' : '') + (v.version > 1 ? '<button class="text-button" data-diff-version="' + v.version + '" aria-expanded="false">What changed</button>' : '') + '<button class="text-button" data-use-version="' + v.version + '" title="Load this version into the draft (Ctrl+Z restores the current draft)">Use as draft</button><button class="text-button" data-export-version="' + v.version + '">Export JSON</button></div><div class="version-detail hidden" data-detail="' + v.version + '"></div></article>';
  }).join('') : '<p class="node-help">No published versions yet. Publish to freeze this graph as a version you can run and compare.</p>';
  $$('[data-use-version]').forEach(b => b.onclick = () => { if (dirty && !confirm('Replace the unsaved edits with version ' + b.dataset.useVersion + '? Ctrl+Z restores them afterwards.')) return; const v = record.versions.find(x => x.version === Number(b.dataset.useVersion)); commit(); blueprint.graph = structuredClone(v.graph); for (const n of blueprint.graph.nodes) delete n.config?.baseline; selection = new Set(); selectedEdge = null; markDirty(); render(); renderInspector(); fitView(); hint('Draft now matches version ' + v.version + ' · Ctrl+Z restores the previous draft'); });
  $$('[data-export-version]').forEach(b => b.onclick = () => { const v = record.versions.find(x => x.version === Number(b.dataset.exportVersion)); const url = URL.createObjectURL(new Blob([JSON.stringify(v, null, 2)], {type: 'application/json'})); const a = document.createElement('a'); a.href = url; a.download = (record.name || 'architecture') + '-v' + v.version + '.json'; a.click(); URL.revokeObjectURL(url); });
  $$('[data-run-version]').forEach(b => b.onclick = () => openLaunch({version: 'blueprint.' + record.id + '.v' + b.dataset.runVersion}));
  $$('#blueprint-versions [data-open-graphs]').forEach(b => b.onclick = () => setStudioMode('graphs'));
  const toggleDetail = (b, mode, load) => async () => { const n = Number(b.dataset.diffVersion || b.dataset.knowledgeVersion); const box = $$('[data-detail]').find(d => d.dataset.detail === String(n)); const row = b.closest('.version-row'); if (!box.classList.contains('hidden') && box.dataset.mode === mode) { box.classList.add('hidden'); b.setAttribute('aria-expanded', 'false'); return; } const release = busy(b, b.textContent + '…'); try { box.innerHTML = await load(n); box.dataset.mode = mode; box.classList.remove('hidden'); row.querySelectorAll('[aria-expanded]').forEach(x => x.setAttribute('aria-expanded', 'false')); b.setAttribute('aria-expanded', 'true'); } catch (e) { toast(e.message); } finally { release(); } };
  $$('[data-diff-version]').forEach(b => b.onclick = toggleDetail(b, 'diff', async n => renderDiff(await api('/api/blueprints/' + record.id + '/versions/' + n + '/diff'))));
  updateRunButton();
}
function renderDiff(d) {
  if (d.identical) return '<p class="node-help">Version ' + d.to + ' is byte-identical to version ' + d.from + '.</p>';
  const rows = [];
  d.added.forEach(n => rows.push('<li class="added">Added <strong>' + esc(n.label) + '</strong> (' + esc(STEP_TYPES[n.type]?.name || n.type) + ')</li>'));
  d.removed.forEach(n => rows.push('<li class="removed">Removed <strong>' + esc(n.label) + '</strong></li>'));
  d.changed.forEach(n => rows.push('<li class="changed"><strong>' + esc(n.label) + '</strong>' + n.fields.map(f => '<div class="diff-field"><span>' + esc(f.field) + '</span><del>' + esc(f.before ?? '—') + '</del><ins>' + esc(f.after ?? '—') + '</ins></div>').join('') + '</li>'));
  d.edges_added.forEach(e => rows.push('<li class="added">Connected ' + esc(e.from) + ' → ' + esc(e.to) + '</li>'));
  d.edges_removed.forEach(e => rows.push('<li class="removed">Disconnected ' + esc(e.from) + ' → ' + esc(e.to) + '</li>'));
  if (d.moved_only.length) rows.push('<li>Only moved: ' + esc(d.moved_only.join(', ')) + '</li>');
  return '<h4>Version ' + d.from + ' → ' + d.to + '</h4><ul class="diff-list">' + rows.join('') + '</ul>';
}
async function loadFireworks(refresh) {
  const labels = [$('#node-model-status'), $('#runner-catalog-status')].filter(Boolean);
  labels.forEach(el => el.textContent = 'Loading Fireworks catalog…');
  try { fireworksCatalog = await api(refresh ? '/api/runners/fireworks/refresh' : '/api/runners/fireworks', refresh ? {} : undefined); $('#fireworks-model-list').innerHTML = fireworksCatalog.models.map(m => '<option value="' + esc(m.id) + '">' + esc(m.name) + (m.serverless ? ' · serverless' : ' · deployment may be required') + '</option>').join(''); labels.forEach(el => el.textContent = (fireworksCatalog.complete ? fireworksCatalog.models.length + ' models listed. ' : '') + fireworksCatalog.message + ' Only models with a rate card in config/models can spend.'); }
  catch (e) { labels.forEach(el => el.textContent = e.message); }
}

// ------------------------------------------------------------------ studio modes: architectures | product graphs
function setStudioMode(mode, graphId) {
  const panel = $('#setup-panel');
  panel.dataset.mode = mode;
  $$('.studio-tabs [data-mode]').forEach(b => { b.setAttribute('aria-selected', String(b.dataset.mode === mode)); b.tabIndex = b.dataset.mode === mode ? 0 : -1; });
  $('#arch-panel').classList.toggle('hidden', mode !== 'architectures');
  $('#pg-panel').classList.toggle('hidden', mode !== 'graphs');
  closeMenu(false);
  if (mode === 'graphs') { if (graphId && graphRecord(graphId)) { if (!pgDirty || confirm('Discard the unsaved product graph edits?')) { setProductGraph(graphRecord(graphId)); $('#pg-library').value = graphId; } } else if (!pg) setProductGraph(productGraphs[0] || null); else renderPg(); }
  else { renderNodes(); renderInspector(true); renderVersions(); fitView(); }
}
$$('.studio-tabs [data-mode]').forEach(b => b.onclick = () => setStudioMode(b.dataset.mode));
$('.studio-tabs').addEventListener('keydown', e => { if (!['ArrowLeft', 'ArrowRight'].includes(e.key)) return; const tabs = $$('.studio-tabs [data-mode]'); const i = tabs.indexOf(document.activeElement); const next = tabs[(i + (e.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length]; next.focus(); setStudioMode(next.dataset.mode); });

// ------------------------------------------------------------------ live overlay from the open run
window.builderLive = function (currentJob, currentEvents) {
  if (!opened || !currentJob || !blueprint.id) return;
  const arm = (currentJob.settings.arms || []).find(a => a.kind === 'version' && a.blueprint === blueprint.id);
  if (!arm) { if (Object.keys(live).length) { live = {}; renderNodes(); } $('#builder-live-note').textContent = ''; return; }
  const next = {};
  for (const e of currentEvents) {
    if (e.model !== arm.id) continue;
    if (e.type === 'step_started') next[e.step] = 'running';
    if (e.type === 'step_finished') next[e.step] = e.status === 'completed' ? 'completed' : 'error';
  }
  const changed = JSON.stringify(next) !== JSON.stringify(live);
  live = next;
  $('#builder-live-note').textContent = 'Showing live execution of ' + arm.name + ' in run "' + currentJob.title + '"';
  if (changed) renderNodes();
};

// ------------------------------------------------------------------ wiring the chrome
$('#node-palette').innerHTML = PALETTE.map(type => '<button type="button" data-add-node="' + type + '" draggable="true" title="' + esc(STEP_TYPES[type].description) + '" aria-label="Add ' + esc(STEP_TYPES[type].name) + '">' + stepIcon(type) + '<span>' + esc(STEP_TYPES[type].name) + '</span></button>').join('');
$$('[data-add-node]').forEach(b => {
  b.onclick = () => { const r = viewport.getBoundingClientRect(); const centre = worldPoint({clientX: r.left + r.width / 2, clientY: r.top + r.height / 2}); addNode(b.dataset.addNode, {x: centre.x - NODE_W / 2, y: centre.y - 40}); };
  b.ondragstart = e => { e.dataTransfer.setData('text/x-step', b.dataset.addNode); e.dataTransfer.effectAllowed = 'copy'; };
});
let insertWire = null;
viewport.addEventListener('dragover', e => {
  if (!e.dataTransfer.types.includes('text/x-step')) return;
  e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; viewport.classList.add('drop-ready');
  const wire = wireAt(e.clientX, e.clientY);
  const index = wire ? Number(wire.dataset.wire) : null;
  if (index !== insertWire) { insertWire = index; $$('#builder-wires [data-wire]').forEach(g => g.classList.toggle('insert-target', Number(g.dataset.wire) === index)); hint(index === null ? 'Drop to add the step here' : 'Drop to insert it between ' + labelOf(blueprint.graph.edges[index].from) + ' and ' + labelOf(blueprint.graph.edges[index].to)); }
});
viewport.addEventListener('dragleave', e => { if (e.target === viewport) { viewport.classList.remove('drop-ready'); insertWire = null; $$('#builder-wires .insert-target').forEach(g => g.classList.remove('insert-target')); } });
viewport.addEventListener('drop', e => {
  const type = e.dataTransfer.getData('text/x-step'); viewport.classList.remove('drop-ready');
  $$('#builder-wires .insert-target').forEach(g => g.classList.remove('insert-target'));
  if (!type) return; e.preventDefault();
  const p = worldPoint(e); const index = insertWire; insertWire = null;
  addNode(type, {x: p.x - NODE_W / 2, y: p.y - 30}, index === null ? undefined : {insert: index});
});
$('#builder-undo').onclick = undo; $('#builder-redo').onclick = redo; $('#builder-arrange').onclick = arrange;
$('#zoom-in').onclick = () => zoomAt(1.2); $('#zoom-out').onclick = () => zoomAt(1 / 1.2); $('#zoom-label').onclick = () => setZoom(1); $('#zoom-fit').onclick = fitView;
$('#node-delete').onclick = removeSelection; $('#node-duplicate').onclick = duplicateSelection;
$('#blueprint-name').oninput = e => { commitTyping('name'); blueprint.name = e.target.value; markDirty(); };
$('#blueprint-notes').oninput = e => { commitTyping('notes'); blueprint.notes = e.target.value; markDirty(); };
$('#blueprint-save').onclick = async () => { const release = busy($('#blueprint-save'), 'Saving…'); try { await saveDraft(); hint('Draft saved'); } catch (e) { toast(e.message); } finally { release(); } };
$('#shortcuts-open').onclick = () => $('#shortcuts-dialog').showModal();
$('#shortcuts-close').onclick = () => $('#shortcuts-dialog').close();
document.addEventListener('keydown', e => {
  if (!opened || $('#setup-panel').classList.contains('hidden')) return;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); ($('#setup-panel').dataset.mode === 'graphs' ? $('#pg-save') : $('#blueprint-save')).click(); }
});
$('#blueprint-publish').onclick = async () => {
  const button = $('#blueprint-publish');
  if (problems.length) { const first = problems.find(p => p.node) || problems[0]; hint('Fix ' + problems.length + (problems.length === 1 ? ' problem' : ' problems') + ' before publishing'); if (first.node) focusProblem(first); return; }
  const release = busy(button, 'Publishing…');
  try {
    if (dirty || !blueprint.id) await saveDraft();
    if (dirty) throw Error('New edits arrived while saving. Review and publish again.');
    const version = await api('/api/blueprints/publish', {id: blueprint.id, revision: blueprint.revision});
    markSaved('Version ' + version.version + ' published · ' + readinessLabel(version.readiness));
    await loadBlueprints(); renderVersions();
    hint('Version ' + version.version + ' published: ' + readinessLabel(version.readiness) + (version.readiness?.launchable ? ' · Run version ' + version.version + ' is ready' : ''));
    $('.builder-versions')?.scrollIntoView({behavior: 'smooth', block: 'nearest'});
  } catch (e) { toast(e.message); } finally { release(); renderProblems(); }
};
$('#builder-run').onclick = () => {
  const refusal = runRefusal();
  if (refusal) { hint(refusal); $('.builder-versions')?.scrollIntoView({behavior: 'smooth', block: 'nearest'}); return; }
  const record = blueprints.find(x => x.id === blueprint.id);
  const latest = latestVersion();
  if (dirty) hint('The draft has unsaved edits; version ' + latest.version + ' runs as published');
  openLaunch({version: 'blueprint.' + record.id + '.v' + latest.version});
};
$('#blueprint-new').onclick = event => {
  const button = event.currentTarget; const r = button.getBoundingClientRect();
  button.setAttribute('aria-expanded', 'true');
  openMenu({x: r.left, y: r.bottom + 6, heading: 'Start from a template', opener: button, items: Object.entries(TEMPLATES).map(([key, t]) => ({label: t.name, hint: t.hint, action: () => {
    if (dirty && !confirm('Start a new architecture and discard the unsaved edits?')) return;
    template = key; setBlueprint({id: null, revision: 0, name: '', notes: '', graph: TEMPLATES[template].build()}, 'New from template: ' + TEMPLATES[template].name); $('#blueprint-library').value = ''; $('#blueprint-name').focus();
  }}))});
  const observer = new MutationObserver(() => { if (menu.classList.contains('hidden')) { button.setAttribute('aria-expanded', 'false'); observer.disconnect(); } });
  observer.observe(menu, {attributes: true, attributeFilter: ['class']});
};
$('#blueprint-library').onchange = e => {
  if (dirty && !confirm('Discard the unsaved edits and open this architecture?')) { e.target.value = blueprint.id || ''; return; }
  const record = blueprints.find(b => b.id === e.target.value);
  setBlueprint(record ? {id: record.id, revision: record.revision, name: record.name, notes: record.notes, graph: record.graph} : {id: null, revision: 0, name: '', notes: '', graph: TEMPLATES[template].build()});
};
$('#open-setup').onclick = async () => {
  $('#setup-panel').classList.remove('hidden'); $('.workspace').classList.add('hidden'); $('.page-heading').classList.add('hidden');
  try {
    await loadControls(); await loadProductGraphs(); await loadBlueprints();
    if (!opened) {
      let cached; try { cached = JSON.parse(localStorage.getItem('ailabs-architecture-draft')); } catch {}
      setBlueprint(cached || {id: null, revision: 0, name: '', notes: '', graph: TEMPLATES[template].build()});
      if (cached) { markDirty(); hint('Restored the unsaved draft from this browser'); }
      opened = true;
    } else { renderVersions(); renderNodes(); fitView(); }
    if (typeof job !== 'undefined' && job) builderLive(job, events);
  } catch (e) { toast(e.message); }
};
$('#close-setup').onclick = () => { closeMenu(false); $('#setup-panel').classList.add('hidden'); $('.workspace').classList.remove('hidden'); $('.page-heading').classList.remove('hidden'); };
window.addEventListener('beforeunload', e => { if (dirty) { e.preventDefault(); e.returnValue = ''; } });
window.addEventListener('resize', () => { if (opened && !$('#setup-panel').classList.contains('hidden')) renderWires(); });
$('#configure-runner').onclick = () => { const editor = $('#runner-editor'); editor.classList.toggle('hidden'); $('#configure-runner').setAttribute('aria-expanded', String(!editor.classList.contains('hidden'))); if (!editor.classList.contains('hidden')) $('#runner-provider').focus(); };
$('#runner-provider').onchange = () => { if ($('#runner-provider').value === 'fireworks') loadFireworks(false); };
$('#runner-refresh').onclick = () => loadFireworks(true);
$('#runner-save').onclick = async () => { const release = busy($('#runner-save'), 'Saving…'); try { await api('/api/runners/config', {provider: $('#runner-provider').value, model: $('#runner-model').value, effort: $('#runner-effort').value}); await openLaunch(); $('#runner-editor').classList.add('hidden'); toast('Runner configuration saved'); } catch (e) { $('#runner-catalog-status').textContent = e.message; } finally { release(); } };
updateHistoryButtons();
