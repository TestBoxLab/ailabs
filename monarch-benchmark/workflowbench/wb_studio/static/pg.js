'use strict';
/* Product graphs: versioned, reusable, AI-filled knowledge about the corpus products.
   Shares $, $$, esc, api, toast, budget, controls, option, busy, hint, PROVIDER_LABELS, runnerFor,
   controlFor, runnerSummary, productGraphs, renderNodes, renderInspector and setStudioMode with app.js/graph.js.

   Model: a draft holds the schema (typed fields with descriptions), research instructions and the
   runner. Preparing researches the new or changed fields once over every corpus product, carries the
   untouched fields from the parent version, and pins the result as the next immutable version.
   Architectures reference a version through a Product graph step. */

const PG_TYPES = ['string', 'number', 'boolean', 'object', 'array'];
const PG_PROVIDERS = ['gemini', 'anthropic', 'openai', 'fireworks', 'moonshot', 'zai'];
const PG_DEFAULT_FIELDS = () => [{path: 'product.summary', type: 'string', description: 'What this product is for and which kinds of records it holds.'}];
let pgSavePromise=null, pgSavingTarget=null, pgPreparing=false;
let pg = null, pgDirty = false, pgProducts = [], pgOpenRecords = new Set();
const pgTyping = {key: null, at: 0};

function pgUsable(v) { return ['complete', 'incomplete'].includes(v?.status); }
function pgRecord() { return productGraphs.find(g => g.id === pg?.id) || null; }
function pgLatestUsable(record) { return [...(record?.versions || [])].reverse().find(pgUsable) || null; }
async function loadProductGraphs() {
  const response = await api('/api/product-graphs');
  productGraphs = response.items || []; pgProducts = response.products || [];
  renderPgLibrary();
  return productGraphs;
}
function pgFresh() { return {id: null, revision: 0, name: '', notes: '', fields: PG_DEFAULT_FIELDS(), instructions: 'For every product, inspect its actions with api_search and fill the fields from what the catalog actually offers. Say unknown rather than invent.', runner: runnerFor('gemini')}; }
function setProductGraph(record) {
  pg = record ? {id: record.id, revision: record.revision, name: record.name, notes: record.notes || '', fields: structuredClone(record.fields || []), instructions: record.instructions || '', runner: structuredClone(record.runner || runnerFor('gemini'))} : pgFresh();
  pgDirty = false; pgOpenRecords = new Set(); pgTyping.key = null;renderPgLibrary();
  renderPg();
  pgState(record ? 'Draft revision ' + record.revision : 'New product graph');
}
function pgState(text, dirty = false) { const el = $('#pg-state'); el.textContent = text; el.className = 'builder-state' + (dirty ? ' dirty' : ''); }
function pgMarkDirty() { pgDirty = true; pgState('Unsaved edits', true); renderPgPlan(); }
function renderPgLibrary() {
  const select = $('#pg-library'); const value = pg?.id || '';
  select.innerHTML = '<option value="">New product graph…</option>' + productGraphs.map(g => option(g.id, g.name, false)).join('');
  if ([...select.options].some(o => o.value === value)) select.value = value;
}

// ------------------------------------------------------------------ what the next preparation would do
function pgPlan() {
  const parent = pgLatestUsable(pgRecord());
  const before = new Map((parent?.fields || []).map(f => [f.path, f]));
  const fresh = [], changed = [], carried = [];
  for (const f of pg.fields) {
    const old = before.get(f.path);
    if (!old) fresh.push(f); else if (old.type !== f.type || (old.description || '') !== (f.description || '')) changed.push(f); else carried.push(f);
  }
  const present = new Set(pg.fields.map(f => f.path));
  const removed = [...before.keys()].filter(p => !present.has(p));
  const versions = pgRecord()?.versions || [];
  const last = versions.at(-1);
  const number = last && last.status === 'failed' ? last.version : versions.length + 1;
  return {parent, fresh, changed, carried, removed, number, research: fresh.concat(changed)};
}
function renderPgPlan() {
  const box = $('#pg-plan'); if (!pg) return;
  const p = pgPlan();
  const names = list => list.map(f => f.path).join(', ');
  const runner = runnerSummary(pg.runner);
  let text, cls = 'pg-plan';
  if (!pg.fields.length) { text = 'Declare at least one field to research.'; cls += ' warn'; }
  else if (!p.research.length) { text = 'Nothing new to research: every field is already filled in version ' + p.parent.version + '. Add a field or change a description to prepare version ' + p.number + ', or reference v' + p.parent.version + ' from an architecture.'; cls += ' muted'; }
  else text = 'Version ' + p.number + (p.parent ? ' extends v' + p.parent.version : '') + ': ' + runner + ' will research ' + p.research.length + (p.research.length === 1 ? ' field' : ' fields') + ' (' + names(p.research) + ') over ' + pgProducts.length + ' products' + (p.carried.length ? '; ' + p.carried.length + ' carried from v' + p.parent.version + ' unchanged' : '') + (p.removed.length ? '; dropped: ' + p.removed.join(', ') : '') + '.';
  box.className = cls; box.textContent = text;
  const prepare = $('#pg-prepare');
  const blocked = !pg.fields.length || !p.research.length;
  prepare.classList.toggle('is-disabled', blocked); prepare.setAttribute('aria-disabled', String(blocked));
  prepare.textContent = 'Prepare version ' + p.number;
  prepare.title = blocked ? text : 'Research the fields once with ' + runner + ' and pin the result as version ' + p.number;
}

// ------------------------------------------------------------------ editor
function renderPg() {
  if (!pg) return;
  $('#pg-name').value = pg.name; $('#pg-notes').value = pg.notes; $('#pg-instructions').value = pg.instructions;
  renderPgFields(); renderPgRunner(); renderPgPlan(); renderPgVersions();
  $('#pg-products').textContent = pgProducts.length ? 'Corpus products researched by every version: ' + pgProducts.join(', ') : 'The task corpus names no products.';
}
function pgFieldState(f) {
  const parent = pgLatestUsable(pgRecord());
  const old = (parent?.fields || []).find(x => x.path === f.path);
  if (!old) return ['new', 'New: researched in the next version'];
  if (old.type !== f.type || (old.description || '') !== (f.description || '')) return ['changed', 'Changed: researched again'];
  return ['carried', 'Carried from v' + (old.since || parent.version) + ' unchanged'];
}
function renderPgFields(keepFocus) {
  const active = keepFocus ? document.activeElement : null;
  const key = active?.dataset?.pgField !== undefined ? active.dataset.pgField + ':' + active.dataset.index : null;
  const pos = active?.selectionStart;
  $('#pg-fields').innerHTML = pg.fields.map((f, i) => {
    const state = pgFieldState(f);
    return '<div class="fields-row pg-row" data-row="' + i + '"><input data-pg-field="path" data-index="' + i + '" value="' + esc(f.path) + '" placeholder="product.summary" maxlength="120" aria-label="Field path" autocomplete="off"' + (f.path ? '' : ' aria-invalid="true"') + '><select data-pg-field="type" data-index="' + i + '" aria-label="Field type">' + PG_TYPES.map(t => option(t, t, t === f.type)).join('') + '</select><input data-pg-field="description" data-index="' + i + '" value="' + esc(f.description || '') + '" placeholder="What the agent should find and write here" maxlength="600" aria-label="Field description" autocomplete="off"><span class="bp-chip ' + state[0] + '" title="' + esc(state[1]) + '">' + state[0] + '</span><button class="icon-button" data-pg-remove="' + i + '" type="button" aria-label="Remove field ' + esc(f.path || i + 1) + '" title="Remove field">×</button></div>';
  }).join('') || '<p class="node-help">No fields yet. Add one below.</p>';
  $$('[data-pg-field]').forEach(el => { const handler = () => { const i = Number(el.dataset.index); pg.fields[i][el.dataset.pgField] = el.value; pgMarkDirty(); if (el.dataset.pgField === 'path') { const ok = /^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$/i.test(el.value.trim()); el.setAttribute('aria-invalid', String(!ok)); el.title = ok ? '' : 'A path looks like product.summary'; } const chip = el.closest('.pg-row')?.querySelector('.bp-chip'); if (chip) { const state = pgFieldState(pg.fields[i]); chip.className = 'bp-chip ' + state[0]; chip.textContent = state[0]; chip.title = state[1]; } }; if (el.tagName === 'SELECT') el.onchange = handler; else el.oninput = handler; });
  $$('[data-pg-remove]').forEach(b => b.onclick = () => { const removed = pg.fields.splice(Number(b.dataset.pgRemove), 1)[0]; pgMarkDirty(); renderPgFields(); $('#pg-add-field').focus(); hint('Removed field ' + (removed?.path || '')); });
  if (key) { const again = $$('[data-pg-field]').find(el => el.dataset.pgField + ':' + el.dataset.index === key); if (again) { again.focus({preventScroll: true}); if (pos !== undefined && again.setSelectionRange) try { again.setSelectionRange(pos, pos); } catch {} } }
}
function renderPgRunner() {
  const r = pg.runner;
  const control = controlFor(r);
  const models = controls.filter(c => c.provider === r.provider).map(c => option(c.model, c.name + ' · $' + c.prices_per_million.input + ' in / $' + c.prices_per_million.output + ' out per M', r.model === c.model || r.model === c.id));
  if (!models.some(m => m.includes(' selected')) && r.model) models.unshift(option(r.model, r.model + ' (no rate card)', true));
  const efforts = control ? ['default', ...control.efforts] : ['default'];
  $('#pg-runner').innerHTML = '<div class="field"><label for="pg-provider">Researcher</label><select id="pg-provider">' + PG_PROVIDERS.map(p => option(p, PROVIDER_LABELS[p], p === r.provider)).join('') + '</select></div>'
    + '<div class="field"><label for="pg-model">Model</label><select id="pg-model"' + (control ? '' : ' aria-invalid="true"') + '>' + models.join('') + '</select>' + (control ? '' : '<small class="node-help">Choose a rate-carded model; only those can spend.</small>') + '</div>'
    + '<div class="field"><label for="pg-effort">Reasoning effort</label><select id="pg-effort">' + efforts.map(e => option(e, e === 'default' ? 'Default' + (control?.default_effort ? ' (' + control.default_effort + ')' : '') : e, e === r.effort)).join('') + '</select>' + (control && !control.efforts.length ? '<small class="node-help">This API has no reasoning-effort control.</small>' : '') + '</div>'
    + (control ? '<div class="capability ok">' + esc(control.name) + ' · reserves up to $' + esc(Number(control.request_ceiling_usd).toFixed(2)) + ' per request before it is admitted; the budget you set caps the whole preparation.</div>' : '');
  $('#pg-provider').onchange = e => { pg.runner = runnerFor(e.target.value); if (pg.runner.provider !== e.target.value) pg.runner = {provider: e.target.value, model: '', effort: 'default'}; pgMarkDirty(); renderPgRunner(); };
  $('#pg-model').onchange = e => { pg.runner.model = e.target.value; pgMarkDirty(); renderPgRunner(); };
  $('#pg-effort').onchange = e => { pg.runner.effort = e.target.value; pgMarkDirty(); renderPgRunner(); };
}

// ------------------------------------------------------------------ versions
function pgStatusLabel(v) { return {complete: 'Complete', incomplete: 'Incomplete', failed: 'Failed'}[v.status] || v.status; }
function pgWhen(iso) { return new Date(iso).toLocaleString(undefined, {dateStyle: 'medium', timeStyle: 'short'}); }
function pgMeta(parts, tag = 'p') { return '<' + tag + ' class="meta">' + parts.filter(Boolean).join('<span class="sep">·</span>') + '</' + tag + '>'; }
function renderPgVersions() {
  const record = pgRecord();
  const versions = record?.versions?.slice().reverse() || [];
  const box = $('#pg-versions');
  if (!versions.length) { box.innerHTML = '<div class="empty-state"><p>No version yet.</p><button class="button" type="button" data-pg-prepare-first>' + esc($('#pg-prepare').textContent) + '</button></div>'; $('[data-pg-prepare-first]').onclick = () => $('#pg-prepare').click(); return; }
  box.innerHTML = versions.map(v => {
    const products = Object.keys(v.records || {});
    const researched = new Set(v.researched || []);
    const open = pgOpenRecords.has(v.version);
    const runner = runnerSummary(v.runner ? {provider: v.runner.provider, model: v.runner.model || v.runner.key, effort: v.runner.effort} : null) || v.runner?.provider || '';
    return '<article class="block pg-version' + (v.status === 'failed' ? ' failed' : '') + '" data-pg-version="' + v.version + '">'
      + '<header><strong>Version ' + v.version + '</strong><span>' + esc(pgWhen(v.prepared_at)) + '</span><span class="status ' + (v.status === 'complete' ? 'completed' : esc(v.status)) + '">' + esc(pgStatusLabel(v)) + '</span><span class="pg-version-summary">' + esc(v.summary || '') + '</span></header>'
      + '<div class="block-body">'
      + pgMeta([v.parent_version ? 'Extends <b>version ' + v.parent_version + '</b>' : 'First version', 'Researched <b>' + esc((v.researched || []).join(', ') || 'nothing') + '</b>', v.carried?.length ? 'Carried <b>' + v.carried.length + '</b>' : '', v.removed?.length ? 'Dropped <b>' + esc(v.removed.join(', ')) + '</b>' : ''])
      + pgMeta([esc(runner), v.turns + ' turns', v.tool_calls + ' catalog searches', '$' + esc(Number(v.cost_usd || 0).toFixed(4)), esc((v.sha256 || '').slice(0, 12))])
      + (v.notes ? '<p class="pg-version-notes">' + esc(v.notes) + '</p>' : '')
      + (v.error ? '<p class="version-reason">' + esc(v.error) + '</p>' : '')
      + (v.problems?.length ? '<details class="pg-problems"><summary>' + v.problems.length + (v.problems.length === 1 ? ' note' : ' notes') + '</summary><ul>' + v.problems.map(p => '<li>' + esc(p) + '</li>').join('') + '</ul></details>' : '')
      + '<ul class="graph-field-list">' + v.fields.map(f => '<li><code>' + esc(f.path) + '</code> <small>' + esc(f.type) + ' · ' + (researched.has(f.path) ? 'researched in version ' + v.version : 'carried from version ' + (f.since || v.parent_version)) + '</small>' + (f.description ? '<br><span>' + esc(f.description) + '</span>' : '') + '</li>').join('') + '</ul>'
      + '<div class="version-actions">' + (products.length ? '<button class="text-button" data-pg-records="' + v.version + '" aria-expanded="' + open + '">' + (open ? 'Close review' : 'Review changes') + '</button>' : '') + '<button class="text-button" data-pg-load="' + v.version + '" title="Copy this version\'s fields, instructions and runner into the draft">Load into draft</button>' + (pgUsable(v) ? '<button class="text-button" data-pg-use="' + v.version + '">Use in an architecture</button>' : '') + '<button class="text-button" data-pg-export="' + v.version + '">Export JSON</button></div>'
      + '<div class="version-detail' + (open ? '' : ' hidden') + '">' + (open ? renderPgRecords(v) + renderPgDrilldownShell(v) + renderPgLogShell(v) : '') + '</div></div></article>';
  }).join('');
  // workspace.js appends its raw-JSON research log to the review; the block log rendered here replaces it.
  $$('.pg-log-section').forEach(section => section.remove());
  $$('[data-pg-records]').forEach(b => b.onclick = () => { const n = Number(b.dataset.pgRecords); pgOpenRecords.has(n) ? pgOpenRecords.delete(n) : pgOpenRecords.add(n); renderPgVersions(); });
  $$('[data-pg-load]').forEach(b => b.onclick = () => { const v = record.versions.find(x => x.version === Number(b.dataset.pgLoad)); pg.fields = v.fields.map(f => ({path: f.path, type: f.type, description: f.description || ''})); pg.instructions = v.instructions || pg.instructions; if (v.runner?.provider && v.runner?.model) pg.runner = {provider: v.runner.provider, model: v.runner.model, effort: v.runner.effort || 'default'}; pgMarkDirty(); renderPg(); hint('Draft now holds the fields of version ' + v.version + '; add or change fields to prepare the next one'); $('#pg-add-field').focus(); });
  $$('[data-pg-use]').forEach(b => b.onclick = () => { setStudioMode('architectures'); hint('Add a Product graph step and pick ' + record.name + ' v' + b.dataset.pgUse + ' in its settings'); });
  $$('[data-pg-export]').forEach(b => b.onclick = () => { const v = record.versions.find(x => x.version === Number(b.dataset.pgExport)); const url = URL.createObjectURL(new Blob([JSON.stringify(v, null, 2)], {type: 'application/json'})); const a = document.createElement('a'); a.href = url; a.download = (record.name || 'product-graph') + '-v' + v.version + '.json'; a.click(); URL.revokeObjectURL(url); });
}
function renderPgRecords(v) {
  const products = Object.keys(v.records || {});
  return '<div class="table-scroll"><table class="pg-records"><thead><tr><th>Product</th>' + v.fields.map(f => '<th>' + esc(f.path) + '</th>').join('') + '</tr></thead><tbody>' + products.map(p => '<tr><td>' + esc(p) + '</td>' + v.fields.map(f => { const value = v.records[p]?.[f.path]; return '<td>' + (value === undefined ? '<span class="neutral">—</span>' : esc(typeof value === 'string' ? value : JSON.stringify(value))) + '</td>'; }).join('') + '</tr>').join('') + '</tbody></table></div>';
}

// ------------------------------------------------------------------ products and research log of a version, loaded when opened
const PG_EVENT_LABELS = {step_started: 'Research started', model_started: 'Model request', model_finished: 'Model answer', node_started: 'Catalog search', node_finished: 'Search result', billing: 'Charge', step_finished: 'Research finished', attempt_error: 'Error'};
const pgLoaded = new Map();
function renderPgDrilldownShell(v) { return '<details class="pg-drilldown" data-pg-drilldown="' + v.version + '"><summary>Products</summary><div><p class="node-help">Loading…</p></div></details>'; }
function renderPgLogShell(v) { return '<details class="pg-log-detail" data-pg-log="' + v.version + '"><summary>Research log</summary><div><p class="node-help">Loading…</p></div></details>'; }
function pgLoad(kind, version) {
  const key = kind + ':' + pg.id + '/' + version;
  if (!pgLoaded.has(key)) pgLoaded.set(key, api('/api/product-graphs/' + pg.id + '/versions/' + version + '/' + kind).catch(e => { pgLoaded.delete(key); throw e; }));
  return pgLoaded.get(key);
}
async function pgFill(detail) {
  if (detail.dataset.loaded) return;
  const kind = detail.dataset.pgDrilldown ? 'products' : 'events', version = Number(detail.dataset.pgDrilldown || detail.dataset.pgLog), body = detail.lastElementChild;
  try { const data = await pgLoad(kind, version); if (!body.isConnected || detail.dataset.loaded) return; body.innerHTML = kind === 'products' ? renderPgDrilldown(data) : renderPgLog(data.events, version); detail.dataset.loaded = '1'; }
  catch (e) { body.innerHTML = '<p class="version-reason">' + esc(e.message) + '</p>'; }
}
document.addEventListener('toggle', e => { const detail = e.target; if (detail.open && (detail.dataset.pgDrilldown || detail.dataset.pgLog)) pgFill(detail); }, true);
document.addEventListener('click', async e => {
  const link = e.target.closest('[data-pg-event]'); if (!link) return;
  const [version, id] = link.dataset.pgEvent.split(':').map(Number);
  if (!pgOpenRecords.has(version)) { pgOpenRecords.add(version); renderPgVersions(); }
  const log = $('[data-pg-log="' + version + '"]'); if (!log) return;
  log.open = true; await pgFill(log);
  const block = log.querySelector('[data-pg-event-id="' + id + '"]'); if (!block) return;
  $$('.pg-log-entry.is-target').forEach(b => b.classList.remove('is-target')); block.classList.add('is-target'); block.scrollIntoView({behavior: 'smooth', block: 'center'});
});
function pgValue(value) { return typeof value === 'string' ? esc(value) : '<code>' + esc(JSON.stringify(value)) + '</code>'; }
function renderPgDrilldown(data) {
  if (!data.products.length) return '<p class="node-help">No products in this version.</p>';
  return data.products.map(p => {
    const filled = p.fields.filter(f => f.present && !f.unknown).length, unknown = p.fields.filter(f => f.unknown).length, missing = p.fields.filter(f => !f.present).length;
    return '<details class="pg-product"><summary><strong>' + esc(p.product) + '</strong>' + pgMeta([filled + ' of ' + p.fields.length + ' filled', unknown ? unknown + ' unknown' : '', missing ? missing + ' missing' : ''], 'span') + '</summary>'
      + '<div class="table-scroll"><table class="table pg-product-fields"><thead><tr><th>Field</th><th>Value</th><th>Events</th></tr></thead><tbody>' + p.fields.map(f => '<tr><th scope="row"><code>' + esc(f.path) + '</code></th><td>' + (!f.present ? '<span class="neutral">missing</span>' : f.unknown ? '<span class="neutral">unknown</span>' : pgValue(f.value)) + '</td><td>' + (f.events.ids.length ? f.events.ids.map(id => '<button type="button" class="text-button" data-pg-event="' + f.events.version + ':' + id + '">' + (f.events.version === data.version ? '' : 'v' + f.events.version + ' ') + 'event ' + id + '</button>').join('') : '<span class="neutral">none</span>') + '</td></tr>').join('') + '</tbody></table></div></details>';
  }).join('');
}
function pgText(text) { if (!/^[\[{]/.test(text.trim())) return '<p>' + esc(text) + '</p>'; let pretty = text; try { pretty = JSON.stringify(JSON.parse(text), null, 2); } catch {} return '<pre>' + esc(pretty) + '</pre>'; }
function pgEventBody(e, args) {
  switch (e.type) {
    case 'step_started': return '<p>Researching ' + esc((e.fields || []).join(', ')) + ' for version ' + esc(e.version) + '.</p>';
    case 'model_started': return '<p>Turn ' + (Number(e.turn) + 1) + ' sent to the model.</p>';
    case 'model_finished': return e.output ? pgText(e.output) : '<p class="neutral">No text in this turn.</p>';
    case 'node_started': return '<dl class="pg-args">' + Object.entries(args || {}).map(([k, v]) => '<dt>' + esc(k) + '</dt><dd>' + esc(typeof v === 'string' ? v : JSON.stringify(v)) + '</dd>').join('') + '</dl>';
    case 'node_finished': return pgText(e.output || '');
    case 'billing': return pgMeta([e.billing?.actual_usd != null ? 'Charged <b>$' + esc(Number(e.billing.actual_usd).toFixed(4)) + '</b>' : 'Charge not settled yet', e.budget?.available !== undefined ? '<b>$' + esc(e.budget.available) + '</b> left this week' : '']);
    case 'step_finished': return e.status === 'completed' ? '<p>Completed.</p>' : '<p class="version-reason">' + esc(e.output || 'Ended with an error.') + '</p>';
    case 'attempt_error': return '<p class="version-reason">' + esc(e.message || '') + '</p>';
    default: return '';
  }
}
function renderPgLog(events, version) {
  const shown = events.filter(e => e.type !== 'model_delta');
  if (!shown.length) return '<p class="node-help">No research events were recorded for version ' + version + '.</p>';
  const searches = new Map(shown.filter(e => e.type === 'node_started').map(e => [e.node, e.arguments || {}]));
  return '<div class="pg-log">' + shown.map(e => {
    const args = e.type === 'node_finished' ? searches.get(e.node) : e.arguments;
    const named = args ? pgProducts.filter(p => JSON.stringify(args).toLowerCase().includes(p.toLowerCase())) : [];
    const failed = e.status === 'error' || e.type === 'attempt_error';
    return '<article class="block pg-log-entry' + (failed ? ' failed' : '') + '" data-pg-event-id="' + e.id + '"><header><span>' + e.id + '</span><span>' + esc(new Date(e.at).toLocaleTimeString()) + '</span>' + (named.length ? '<span>' + esc(named.join(', ')) + '</span>' : '') + '<strong>' + esc(PG_EVENT_LABELS[e.type] || String(e.type).replaceAll('_', ' ')) + '</strong></header>'
      + '<div class="block-body">' + pgEventBody(e, args) + '<details class="pg-raw"><summary>Raw</summary><pre>' + esc(JSON.stringify(e, null, 2)) + '</pre></details></div></article>';
  }).join('') + '</div>';
}

// ------------------------------------------------------------------ save and prepare
function pgPayload() { return {id: pg.id, revision: pg.revision, name: pg.name, notes: pg.notes, fields: pg.fields, instructions: pg.instructions, runner: pg.runner}; }
async function savePg() {
  if(pgSavePromise){if(pgSavingTarget!==pg)throw Error('Wait for the previous draft to finish saving.');return pgSavePromise;}
  const target=pg,sent=structuredClone(pgPayload());
  pgSavingTarget=target;
  pgSavePromise=(async()=>{
    const saved=await api('/api/product-graphs/draft',sent);
    if(target===pg) {
      const unchanged=JSON.stringify(pgPayload())===JSON.stringify(sent);
      pg.id=saved.id;pg.revision=saved.revision;
      if(unchanged){pg.fields=structuredClone(saved.fields);pgDirty=false;}else pgMarkDirty();
    }
    await loadProductGraphs();
    if(target===pg){renderPg();if(!pgDirty)pgState('Draft saved · revision '+saved.revision);}
    return saved;
  })();
  try{return await pgSavePromise;}finally{pgSavePromise=null, pgSavingTarget=null;}
}

$('#pg-save').onclick = async () => { const release = busy($('#pg-save'), 'Saving…'); try { await savePg(); hint('Product graph draft saved'); } catch (e) { toast(e.message); } finally { release(); } };
$('#pg-prepare').onclick = async () => {
  if(!pg||pgPreparing)return;
  const p = pgPlan();
  if (!pg.fields.length || !p.research.length) { hint($('#pg-plan').textContent); $('#pg-add-field').focus(); return; }
  if (!pg.name.trim()&&!await ensureStudioName('graphs'))return;
  const control = controlFor(pg.runner);
  const floor = Number(control?.request_ceiling_usd || 0);
  $('#prepare-title').textContent = 'Prepare version ' + p.number + (pg.name ? ' of ' + pg.name : '');
  $('#prepare-plan').innerHTML = '<header><strong>Version ' + p.number + '</strong><span>' + (p.parent ? 'extends version ' + p.parent.version : 'first version') + '</span><span>' + esc(runnerSummary(pg.runner)) + '</span></header><div class="block-body">'
    + pgMeta([p.research.length + ' to research', p.carried.length + ' carried', p.removed.length + ' dropped', pgProducts.length + ' products'])
    + '<ul class="pg-prepare-fields">' + p.fresh.map(f => '<li><code>' + esc(f.path) + '</code> new</li>').concat(p.changed.map(f => '<li><code>' + esc(f.path) + '</code> changed</li>'), p.removed.map(path => '<li><code>' + esc(path) + '</code> dropped</li>')).join('') + '</ul></div>';
  $('#prepare-floor').textContent = floor ? 'Reserved up front; ' + control.name + ' needs at least $' + floor.toFixed(2) + '.' : 'Reserved up front.';
  const input = $('#prepare-budget');
  input.min = floor ? Math.ceil(floor * 100) / 100 : 0.01;
  if (Number(input.value) < floor) input.value = Math.max(1, Math.ceil(floor * 2)).toFixed(2);
  input.oninput = () => { $('#prepare-error').textContent = floor && Number(input.value) < floor ? 'Set at least $' + floor.toFixed(2) + ': the researcher reserves that much for its first request.' : ''; };
  $('#prepare-error').textContent = '';
  $('#prepare-dialog').showModal();
};
$('#prepare-cancel').onclick = () => $('#prepare-dialog').close();
$('#prepare-form').onsubmit = async e => {
  e.preventDefault(); if (!pg||pgPreparing) return;
  if(!$('#prepare-form').reportValidity())return;
  const target=pg;pgPreparing=true;
  const release = busy($('#prepare-start'), 'Preparing…'); $('#prepare-error').textContent = '';
  try {
    if (pgDirty || !pg.id) await savePg();
    if(target!==pg||pgDirty)throw Error('The draft changed while saving. Review it before preparing a paid version.');
    const version = await api('/api/product-graphs/prepare', {id: pg.id, revision: pg.revision, maximum_usd: $('#prepare-budget').value});
    $('#prepare-dialog').close();
    await loadProductGraphs();
    if(target!==pg){toast('Product graph version '+version.version+' prepared. Open its graph to inspect it.');return;}
    pgOpenRecords.add(version.version); renderPg(); pgState('Version ' + version.version + ' ' + version.status);
    hint('Version ' + version.version + ' ' + version.status + '. ' + (version.summary || ''));
    try { budget((await api('/api/state')).budget); } catch {}
    if (typeof renderNodes === 'function') { renderNodes(); renderInspector(true); }
    $$('[data-pg-version]').find(a => a.dataset.pgVersion === String(version.version))?.scrollIntoView({behavior: 'smooth', block: 'nearest'});
  } catch (error) { $('#prepare-error').textContent = error.message;if(!$('#prepare-dialog').open)toast(error.message); }
  finally { pgPreparing=false;release(); }
};

// ------------------------------------------------------------------ chrome
function pgTypingCommit(key) { pgTyping.key = key; pgTyping.at = Date.now(); }
$('#pg-name').oninput = e => { pg.name = e.target.value; pgMarkDirty(); };
$('#pg-notes').oninput = e => { pg.notes = e.target.value; pgMarkDirty(); };
$('#pg-instructions').oninput = e => { pg.instructions = e.target.value; pgMarkDirty(); };
$('#pg-add-field').onclick = () => { if(pg.fields.length>=60)return toast('A product graph supports up to 60 fields.'); pg.fields.push({path: '', type: 'string', description: ''}); pgMarkDirty(); renderPgFields(); $$('[data-pg-field="path"]').at(-1)?.focus(); };
$('#pg-new').onclick = () => { if (pgDirty && !confirm('Start a new product graph and discard the unsaved edits?')) return; setProductGraph(null); $('#pg-library').value = ''; $('#pg-name').focus(); };
$('#pg-library').onchange = e => { if (pgDirty && !confirm('Discard the unsaved edits and open this product graph?')) { e.target.value = pg?.id || ''; return; } setProductGraph(productGraphs.find(g => g.id === e.target.value) || null); };
window.addEventListener('beforeunload', e => { if (pgDirty) { e.preventDefault(); e.returnValue = ''; } });
$('#close-setup-graphs').onclick = () => $('#close-setup').click();

// ------------------------------------------------------------------ graph view: products and the actions stored for each, live or from a version
// The live source is the graph Monarch Enterprise uses, read through the Studio's GET routes only.
const pgGraph = {source: 'live', product: null, query: ''};
const pgGraphLoads = new Map();
let pgGraphProducts = [];
function pgGraphFetch(url) {
  if (!pgGraphLoads.has(url)) pgGraphLoads.set(url, api(url).catch(e => { pgGraphLoads.delete(url); throw e; }));
  return pgGraphLoads.get(url);
}
function pgGraphSources() {
  const record = pgRecord();
  const versions = (record?.versions || []).filter(pgUsable).slice().reverse();
  return [{id: 'live', label: 'Monarch Enterprise, live (read only)'}].concat(versions.map(v => ({id: 'v' + v.version, label: (record.name || 'This graph') + ', version ' + v.version, version: v})));
}
function pgGraphVersion() { return pgGraphSources().find(s => s.id === pgGraph.source)?.version || null; }
function renderPgGraph() {
  const box = $('#pg-graph'); if (!box) return;
  const sources = pgGraphSources();
  if (!sources.some(s => s.id === pgGraph.source)) { pgGraph.source = 'live'; pgGraph.product = null; }
  box.innerHTML = '<div class="pg-graph-bar"><label for="pg-graph-source">Source</label><select id="pg-graph-source">' + sources.map(s => option(s.id, s.label, s.id === pgGraph.source)).join('') + '</select>'
    + '<input id="pg-graph-search" type="search" placeholder="Find a product" aria-label="Find a product" value="' + esc(pgGraph.query) + '"><span class="meta" id="pg-graph-stamp"></span></div>'
    + '<div class="pg-graph-body"><div class="pg-graph-products" id="pg-graph-products"></div><div class="pg-graph-detail" id="pg-graph-detail"></div></div>';
  $('#pg-graph-source').onchange = e => { pgGraph.source = e.target.value; pgGraph.product = null; renderPgGraph(); };
  $('#pg-graph-search').oninput = e => { pgGraph.query = e.target.value; renderPgGraphProducts(); };
  loadPgGraphProducts();
}
async function loadPgGraphProducts() {
  const list = $('#pg-graph-products'), stamp = $('#pg-graph-stamp'), source = pgGraph.source, version = pgGraphVersion();
  list.innerHTML = '<p class="node-help">Loading</p>'; $('#pg-graph-detail').innerHTML = '';
  try {
    if (version) {
      const data = await pgLoad('products', version.version);
      if (pgGraph.source !== source) return;
      pgGraphProducts = data.products.map(p => ({slug: p.product, name: p.product, actions: p.fields.filter(f => f.present && !f.unknown).length, fields: p.fields}));
      stamp.textContent = 'Version ' + version.version + ' · prepared ' + pgWhen(version.prepared_at);
    } else {
      const data = await pgGraphFetch('/api/live-graph/products');
      if (pgGraph.source !== source) return;
      pgGraphProducts = data.products;
      stamp.textContent = 'Read only · ' + data.source + ' · read ' + new Date(data.fetched_at).toLocaleTimeString();
    }
  } catch (e) {
    pgGraphProducts = [];
    const unset = /not set|MONARCH_FD_URL/i.test(e.message);
    list.innerHTML = '<div class="empty-state"><p>' + (unset ? 'The live graph is not configured: MONARCH_FD_URL is not set on the server. Add it to workflowbench/.env and restart the Studio; Settings lists what is present.' : esc(e.message)) + '</p>' + (unset ? '<button class="text-button" type="button" id="pg-graph-settings">Open Settings</button>' : '<button class="button" type="button" id="pg-graph-retry">Try again</button>') + '</div>';
    if ($('#pg-graph-retry')) $('#pg-graph-retry').onclick = () => { pgGraphLoads.clear(); renderPgGraph(); };
    if ($('#pg-graph-settings')) $('#pg-graph-settings').onclick = () => $('#nav-runtime').click();
    return;
  }
  if (!pgGraph.product || !pgGraphProducts.some(p => p.slug === pgGraph.product)) pgGraph.product = pgGraphProducts[0]?.slug || null;
  renderPgGraphProducts();
  loadPgGraphDetail();
}
function renderPgGraphProducts() {
  const list = $('#pg-graph-products'); if (!list) return;
  const query = pgGraph.query.trim().toLowerCase();
  const shown = pgGraphProducts.filter(p => !query || p.name.toLowerCase().includes(query) || p.slug.toLowerCase().includes(query));
  if (!pgGraphProducts.length) { list.innerHTML = '<div class="empty-state"><p>No products in this source.</p></div>'; return; }
  if (!shown.length) { list.innerHTML = '<div class="empty-state"><p>No product matches.</p><button class="text-button" type="button" id="pg-graph-clear">Clear search</button></div>'; $('#pg-graph-clear').onclick = () => { pgGraph.query = ''; renderPgGraph(); }; return; }
  list.innerHTML = shown.map(p => '<button type="button" class="pg-graph-product" data-pg-graph-product="' + esc(p.slug) + '" aria-current="' + (p.slug === pgGraph.product) + '"><span>' + esc(p.name) + '</span><span class="count">' + p.actions + '</span></button>').join('');
  $$('[data-pg-graph-product]').forEach(b => b.onclick = () => { pgGraph.product = b.dataset.pgGraphProduct; renderPgGraphProducts(); loadPgGraphDetail(); });
}
function pgCluster(title, count, cards) { return '<section class="pg-cluster"><header><span>' + esc(title) + '</span><span>' + count + '</span></header>' + cards + '</section>'; }
function pgFieldCard(f) {
  const body = !f.present ? '<span class="neutral">missing</span>' : f.unknown ? '<span class="neutral">unknown</span>' : pgValue(f.value);
  const events = f.events?.ids?.length ? '<p class="meta">' + f.events.ids.length + (f.events.ids.length === 1 ? ' research event' : ' research events') + '</p>' : '';
  return '<article class="pg-action" data-state="' + (f.present && !f.unknown ? 'active' : 'retired') + '"><header><span class="verb">' + esc(f.type) + '</span><strong><code>' + esc(f.path) + '</code></strong></header><p class="value">' + body + '</p>' + events + '</article>';
}
function pgActionCard(a) {
  const facts = [a.state !== 'active' ? esc(a.state) : '', a.implemented ? 'implemented' + (a.sources.length ? ' (' + esc(a.sources.join(', ')) + ')' : '') : 'no implementation', a.verified === true ? 'replay verified' : a.verified === false ? 'replay failed' : '', a.contract_version ? 'contract v' + a.contract_version : ''];
  return '<article class="pg-action" data-verb="' + esc(a.verb) + '" data-state="' + esc(a.state) + '" title="' + esc(a.key) + '"><header><span class="verb">' + esc(a.verb) + '</span><strong>' + esc(a.label) + '</strong></header>' + pgMeta(facts) + '</article>';
}
async function loadPgGraphDetail() {
  const box = $('#pg-graph-detail'), product = pgGraphProducts.find(p => p.slug === pgGraph.product), version = pgGraphVersion(), chosen = pgGraph.product;
  if (!box) return;
  if (!product) { box.innerHTML = ''; return; }
  if (version) {
    const present = product.fields.filter(f => f.present && !f.unknown), unknown = product.fields.filter(f => f.unknown), missing = product.fields.filter(f => !f.present);
    box.innerHTML = '<header><h3>' + esc(product.name) + '</h3>' + pgMeta([present.length + ' of ' + product.fields.length + ' filled', unknown.length ? unknown.length + ' unknown' : '', missing.length ? missing.length + ' missing' : ''], 'span') + '</header>'
      + '<div class="pg-clusters">' + pgCluster('Stored values', product.fields.length, product.fields.map(pgFieldCard).join('')) + '</div>';
    return;
  }
  box.innerHTML = '<header><h3>' + esc(product.name) + '</h3>' + pgMeta([esc(product.slug), product.domain ? esc(product.domain) : '', product.actions + (product.actions === 1 ? ' action' : ' actions')], 'span') + '</header><p class="node-help">Loading</p>';
  try {
    const data = await pgGraphFetch('/api/live-graph/products/' + encodeURIComponent(product.slug) + '/actions');
    if (pgGraph.product !== chosen || pgGraphVersion()) return;
    const areas = new Map();
    for (const a of data.actions) { const key = a.area || 'other'; if (!areas.has(key)) areas.set(key, []); areas.get(key).push(a); }
    box.querySelector('.node-help').outerHTML = data.actions.length ? '<div class="pg-clusters">' + [...areas.entries()].map(([area, rows]) => pgCluster(area, rows.length, rows.map(pgActionCard).join(''))).join('') + '</div>' : '<div class="empty-state"><p>No business actions stored for this product.</p></div>';
  } catch (e) {
    if (pgGraph.product !== chosen) return;
    box.querySelector('.node-help').outerHTML = '<div class="empty-state"><p>' + esc(e.message) + '</p><button class="button" type="button" id="pg-graph-retry-detail">Try again</button></div>';
    $('#pg-graph-retry-detail').onclick = () => { pgGraphLoads.clear(); loadPgGraphDetail(); };
  }
}
$('[data-pg-view="graph"]')?.addEventListener('click', renderPgGraph);
const pgRenderBeforeGraph = renderPg;
renderPg = function () { pgRenderBeforeGraph(); if ($('.pg-workspace')?.dataset.pgView === 'graph') renderPgGraph(); };
