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
  pgDirty = false; pgOpenRecords = new Set(); pgTyping.key = null;
  renderPg();
  pgState(record ? 'Draft revision ' + record.revision : 'New product graph');
}
function pgState(text, dirty = false) { const el = $('#pg-state'); el.textContent = text; el.className = 'builder-state' + (dirty ? ' dirty' : ''); }
function pgMarkDirty() { pgDirty = true; pgState('Unsaved edits', true); renderPgPlan(); }
function renderPgLibrary() {
  const select = $('#pg-library'); const value = pg?.id || '';
  select.innerHTML = '<option value="">New product graph…</option>' + productGraphs.map(g => option(g.id, g.name + ' · ' + (g.versions?.length ? 'v' + g.versions.length : 'no version yet'), false)).join('');
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
  $$('[data-pg-field]').forEach(el => { const handler = () => { const i = Number(el.dataset.index); pg.fields[i][el.dataset.pgField] = el.value; pgMarkDirty(); if (el.dataset.pgField === 'path') el.setAttribute('aria-invalid', String(!el.value)); const chip = el.closest('.pg-row')?.querySelector('.bp-chip'); if (chip) { const state = pgFieldState(pg.fields[i]); chip.className = 'bp-chip ' + state[0]; chip.textContent = state[0]; chip.title = state[1]; } }; if (el.tagName === 'SELECT') el.onchange = handler; else el.oninput = handler; });
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
function renderPgVersions() {
  const record = pgRecord();
  const versions = record?.versions?.slice().reverse() || [];
  const box = $('#pg-versions');
  if (!versions.length) { box.innerHTML = '<p class="node-help">' + (pg.id ? 'No prepared version yet. Prepare one to research the fields and pin the result.' : 'Save the draft and prepare a version to research the fields. Every version is immutable; extend it by adding fields and preparing the next one.') + '</p>'; return; }
  box.innerHTML = versions.map(v => {
    const products = Object.keys(v.records || {});
    const researched = new Set(v.researched || []);
    return '<article class="pg-version" data-pg-version="' + v.version + '"><div class="version-main"><strong>Version ' + v.version + '</strong><span class="bp-chip ' + (v.status === 'complete' ? 'ok' : v.status === 'incomplete' ? 'warn' : 'unsupported') + '">' + esc(pgStatusLabel(v)) + '</span><span class="bp-chip">$' + esc(v.cost_usd) + '</span><span class="bp-chip">' + products.length + ' products</span>' + (v.parent_version ? '<span class="bp-chip">extends v' + v.parent_version + '</span>' : '')
      + '<p>' + esc(v.notes || '') + '</p><ul class="graph-field-list">' + v.fields.map(f => '<li><code>' + esc(f.path) + '</code> <small>' + esc(f.type) + ' · ' + (researched.has(f.path) ? 'researched in v' + v.version : 'carried from v' + (f.since || v.parent_version)) + '</small>' + (f.description ? '<br><span>' + esc(f.description) + '</span>' : '') + '</li>').join('') + '</ul>'
      + (v.removed?.length ? '<small>Dropped: ' + esc(v.removed.join(', ')) + '</small>' : '')
      + (v.error ? '<small class="version-reason">' + esc(v.error) + '</small>' : '') + (v.problems?.length ? '<details class="pg-problems"><summary>' + v.problems.length + (v.problems.length === 1 ? ' note' : ' notes') + '</summary><ul>' + v.problems.map(p => '<li>' + esc(p) + '</li>').join('') + '</ul></details>' : '')
      + '<small>' + esc(runnerSummary(v.runner ? {provider: v.runner.provider, model: v.runner.model || v.runner.key, effort: v.runner.effort} : null) || v.runner?.provider || '') + ' · ' + v.turns + ' turns · ' + v.tool_calls + ' catalog searches · ' + esc(new Date(v.prepared_at).toLocaleString()) + ' · ' + esc((v.sha256 || '').slice(0, 12)) + '</small></div>'
      + '<div class="version-actions">' + (products.length ? '<button class="text-button" data-pg-records="' + v.version + '" aria-expanded="' + pgOpenRecords.has(v.version) + '">Records</button>' : '') + '<button class="text-button" data-pg-load="' + v.version + '" title="Copy this version\'s fields, instructions and runner into the draft">Load into draft</button>' + (pgUsable(v) ? '<button class="text-button" data-pg-use="' + v.version + '">Use in an architecture</button>' : '') + '<button class="text-button" data-pg-export="' + v.version + '">Export JSON</button></div>'
      + '<div class="version-detail' + (pgOpenRecords.has(v.version) ? '' : ' hidden') + '">' + (pgOpenRecords.has(v.version) ? renderPgRecords(v) : '') + '</div></article>';
  }).join('');
  $$('[data-pg-records]').forEach(b => b.onclick = () => { const n = Number(b.dataset.pgRecords); pgOpenRecords.has(n) ? pgOpenRecords.delete(n) : pgOpenRecords.add(n); renderPgVersions(); });
  $$('[data-pg-load]').forEach(b => b.onclick = () => { const v = record.versions.find(x => x.version === Number(b.dataset.pgLoad)); pg.fields = v.fields.map(f => ({path: f.path, type: f.type, description: f.description || ''})); pg.instructions = v.instructions || pg.instructions; if (v.runner?.provider && v.runner?.model) pg.runner = {provider: v.runner.provider, model: v.runner.model, effort: v.runner.effort || 'default'}; pgMarkDirty(); renderPg(); hint('Draft now holds the fields of version ' + v.version + '; add or change fields to prepare the next one'); $('#pg-add-field').focus(); });
  $$('[data-pg-use]').forEach(b => b.onclick = () => { setStudioMode('architectures'); hint('Add a Product graph step and pick ' + record.name + ' v' + b.dataset.pgUse + ' in its settings'); });
  $$('[data-pg-export]').forEach(b => b.onclick = () => { const v = record.versions.find(x => x.version === Number(b.dataset.pgExport)); const url = URL.createObjectURL(new Blob([JSON.stringify(v, null, 2)], {type: 'application/json'})); const a = document.createElement('a'); a.href = url; a.download = (record.name || 'product-graph') + '-v' + v.version + '.json'; a.click(); URL.revokeObjectURL(url); });
}
function renderPgRecords(v) {
  const products = Object.keys(v.records || {});
  return '<div class="table-scroll"><table class="pg-records"><thead><tr><th>Product</th>' + v.fields.map(f => '<th>' + esc(f.path) + '</th>').join('') + '</tr></thead><tbody>' + products.map(p => '<tr><td>' + esc(p) + '</td>' + v.fields.map(f => { const value = v.records[p]?.[f.path]; return '<td>' + (value === undefined ? '<span class="neutral">—</span>' : esc(typeof value === 'string' ? value : JSON.stringify(value))) + '</td>'; }).join('') + '</tr>').join('') + '</tbody></table></div>';
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
$('#pg-prepare').onclick = () => {
  if(!pg||pgPreparing)return;
  const p = pgPlan();
  if (!pg.fields.length || !p.research.length) { hint($('#pg-plan').textContent); $('#pg-add-field').focus(); return; }
  if (!pg.name.trim()) { hint('Name the product graph first'); $('#pg-name').focus(); return; }
  const control = controlFor(pg.runner);
  const floor = Number(control?.request_ceiling_usd || 0);
  $('#prepare-title').textContent = 'Prepare version ' + p.number + (pg.name ? ' of ' + pg.name : '');
  $('#prepare-summary').textContent = $('#pg-plan').textContent + ' The draft is saved first. The result is pinned as version ' + p.number + ' and never rewritten; extend it by preparing the next version.' + (floor ? ' ' + (control.name) + ' reserves up to $' + floor.toFixed(2) + ' for one request before it is admitted, so the budget must cover at least that.' : '');
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
    hint('Version ' + version.version + ' ' + version.status + ' · $' + version.cost_usd + ' · ' + Object.keys(version.records || {}).length + ' products');
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
