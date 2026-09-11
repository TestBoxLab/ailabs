// Run with the free tests/browser/server.py fixture on BROWSER_PORT (default 8766).
// Uses agent-browser; every configuration API call is mocked inside this page.
'use strict';
const {execFileSync} = require('node:child_process');
const bin = process.env.AGENT_BROWSER_BIN || (process.platform === 'win32' ? require('node:path').join(process.env.APPDATA,'npm/node_modules/agent-browser/bin/agent-browser-win32-x64.exe') : 'agent-browser');
const browser = (...args) => execFileSync(bin, ['--session', 'benchmark-config', ...args], {encoding: 'utf8'});
const base = `http://127.0.0.1:${process.env.BROWSER_PORT || 8766}`;
console.log(browser('open', base));
browser('set','viewport','1440','1000');
const script = async () => {
  const assert = (value, message) => {if (!value) throw Error(message);};
  const wait = async () => {for(let i=0;i<100;i++){if(document.querySelector('#connection')?.dataset.status==='connected') return; await new Promise(r=>setTimeout(r,100));}throw Error('Fixture did not connect');};
  await wait();
  assert(typeof window.loadBenchmarkConfig === 'function', 'Settings configuration editor is missing');
  const original = api, calls = [];
  let conflict = false, blocked = false, offline = false;
  const catalog = {configured:true,writable:true,repository:'TestBoxLab/ailabls-benchmark-config',branch:'main',commit:'a'.repeat(40),history_url:'https://github.com/TestBoxLab/ailabls-benchmark-config/commits/main',files:[{path:'config/models/example.yaml',text:'name: example\nprice: 1\n'},{path:'config/plans/example.yaml',text:'name: example\nrepetitions: 1\n'},{path:'config/products/example.yaml',text:'name: example\n'}]};
  for(const suffix of ['knowledge-map','monarch-kb','monarch-recipes'])catalog.files.push({path:'config/products/example.'+suffix+'.yaml',text:'fixture: supporting file\n'});
  api = async (path, body) => {
    if(!path.startsWith('/api/benchmark-config'))return original(path, body);
    calls.push({path,body});
    if(offline)throw Error('Fixture offline');
    if(path.endsWith('/validate'))return {valid:!body.changes.some(c=>c.text==='invalid'),errors:['config/models/example.yaml: invalid YAML'],warnings:['Historical plan refers to an unavailable task set'],diff:body.changes.map(c=>'--- '+c.path+'\n+++ '+c.path+'\n+'+c.text).join('\n')};
    if(path.endsWith('/save')){if(conflict){const e=Error('Main changed');e.status=409;throw e;}catalog.commit='b'.repeat(40);for(const c of body.changes){const f=catalog.files.find(f=>f.path===c.path);if(f)f.text=c.text;}return structuredClone(catalog);}
    if(path.endsWith('/preview'))return {preview_id:'preview-fixture',commit:catalog.commit,product:body.product,plan:body.plan,config_hash:'frozen-hash',tasks:1,competitors:['answer key'],attempts_min:1,attempts_max:2,cost_ceiling_usd:'6.00',launchable:!blocked,reasons:blocked?['Billing is not verified']:[]};
    if(path.endsWith('/run'))return {id:'fixture-config-job',status:'queued'};
    return structuredClone(catalog);
  };
  const el = id => document.getElementById('bc-'+id);
  const input = (id,value) => {el(id).value=value;el(id).dispatchEvent(new Event('input',{bubbles:true}));};
  const click = async id => {el(id).click();await new Promise(r=>setTimeout(r,80));};
  await document.getElementById('nav-runtime').onclick();await window.loadBenchmarkConfig();
  assert(el('files').value==='config/models/example.yaml' && el('text').value.includes('price: 1'),'Initial file must be selected and loaded');
  assert([...el('product').options].map(o=>o.value).join(',')==='example','Product options must exclude knowledge maps, knowledge bases and recipes');
  assert(['knowledge-map','monarch-kb','monarch-recipes'].every(s=>[...el('files').options].some(o=>o.value==='config/products/example.'+s+'.yaml')),'Supporting files remain editable');
  input('text','invalid');await click('validate');
  assert(el('save').disabled && el('validation').textContent.includes('invalid YAML'),'Invalid YAML must block save');
  input('text','name: example\nprice: 2\n');
  el('files').value='config/plans/example.yaml';el('files').dispatchEvent(new Event('change'));
  input('text','name: example\nrepetitions: 2\n');input('message','Update model and plan');input('operator','Carlos');
  await click('validate');assert(!el('save').disabled,'Valid multi-file draft should be saveable');
  conflict=true;await click('save');
  assert(el('text').value.includes('repetitions: 2') && el('status').textContent.includes('draft'),'Conflict must retain draft');
  offline=true;await click('refresh');assert(el('text').value.includes('repetitions: 2'),'Network failure must retain draft');offline=false;
  conflict=false;await click('save');
  const saved=calls.filter(c=>c.path.endsWith('/save')).at(-1).body;
  assert(saved.changes.length===2 && saved.changes.some(c=>c.path==='config/models/example.yaml') && saved.base_commit==='a'.repeat(40) && saved.operator==='Carlos','Atomic save must retain base and both files');
  assert(!calls.some(c=>c.path.endsWith('/run')),'Saving must never run');
  input('new-path','config/models/new.yaml');await click('new');input('text','name: new\n');
  el('files').value='config/products/example.yaml';el('files').dispatchEvent(new Event('change'));await click('delete');
  await click('validate');const changed=calls.filter(c=>c.path.endsWith('/validate')).at(-1).body.changes;
  assert(changed.some(c=>c.path==='config/models/new.yaml'&&c.text==='name: new\n') && changed.some(c=>c.path==='config/products/example.yaml'&&c.text===null),'Draft must support creating and deleting files atomically');
  assert(el('validation').textContent.includes('Historical plan') && el('validation').textContent.includes('Valid configuration'),'Warnings remain visible without claiming launch readiness');
  await click('delete');el('files').value='config/models/new.yaml';el('files').dispatchEvent(new Event('change'));await click('delete');
  assert(el('dirty').textContent==='No unsaved changes.','Restore deletion and remove unsaved new file');
  assert(el('files').value==='config/models/example.yaml','Removing new file must select a remaining file');
  blocked=true;await click('preview');assert(el('run').disabled && el('preview-result').textContent.includes('Billing is not verified'),'Readiness refusal must block run');
  blocked=false;await click('preview');
  assert(calls.filter(c=>c.path.endsWith('/preview')).at(-1).body.operator==='Carlos','Preview must use the declared operator');
  assert(el('preview-result').textContent.includes('6.00') && el('preview-result').textContent.includes('2'),'Preview must disclose cost and retry attempts');
  assert(!el('run').disabled,'Launchable preview enables explicit Run');
  input('operator','Lucas');assert(el('run').disabled,'Changing operator invalidates readiness');input('operator','Carlos');await click('preview');
  catalog.commit='c'.repeat(40);await click('run');
  const run=calls.find(c=>c.path.endsWith('/run')).body;
  assert(run.commit==='b'.repeat(40) && run.preview_id==='preview-fixture' && run.request_id && run.operator==='Carlos','Run must echo exact preview and idempotency key');
  assert(el('status').textContent.includes('fixture-config-job'),'Show successful job link');
  const sample=structuredClone(state.jobs[0]);sample.status='running';sample.pause_requested=false;
  for(const marker of [{config_source:{commit:catalog.commit}},{settings:{...sample.settings,plan_semantics:true}}]){
    syncJob({...sample,...marker});
    assert(!document.getElementById('pause-run').classList.contains('hidden') && document.getElementById('resume-run').classList.contains('hidden'),'Running configured plans offer Pause without Resume');
    assert(!document.getElementById('cancel-run').classList.contains('hidden'),'Configured runs retain Cancel');
    syncJob({...sample,...marker,status:'failed',error:'Fixture run stopped'});
    assert(document.getElementById('run-again').classList.contains('hidden'),'Run again must not convert configured plans to ad hoc runs');
    assert(!document.querySelector('[data-run-again="'+sample.id+'"]'),'Configured history must also hide ad hoc Run again');
    assert(!document.getElementById('resume-run').classList.contains('hidden') && document.getElementById('run-message').textContent.includes('spending') && document.getElementById('run-message').textContent.includes('Fixture run stopped'),'Explain configured continuation without hiding errors');
    const before=localStorage.getItem('ailabs-run-draft');runAgain({...sample,...marker});assert(localStorage.getItem('ailabs-run-draft')===before,'Shared rerun function must preserve configured semantics');
  }
  syncJob(sample);assert(!document.getElementById('pause-run').classList.contains('hidden'),'Ordinary Studio runs retain Pause');
  assert(!document.documentElement.scrollWidth || document.documentElement.scrollWidth<=innerWidth+1,'Editor must not overflow');
  return 'PASS: Settings navigation, invalid YAML, warnings, create/delete, multi-file save, conflict/network draft retention, operator readiness, pinned explicit launch and configured controls';
};
// stdin avoids shell interpretation of the browser script on Windows.
console.log(execFileSync(bin, ['--session','benchmark-config','eval','--stdin'], {input:`(${script.toString()})()`,encoding:'utf8'}));
browser('set','viewport','390','844');
console.log(execFileSync(bin, ['--session','benchmark-config','eval','--stdin'], {input:"if(document.documentElement.scrollWidth>innerWidth+1)throw Error('Mobile overflow'); 'PASS: 390px layout'",encoding:'utf8'}));
