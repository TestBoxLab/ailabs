// Offline browser regression against tests/browser/server.py; no provider calls.
'use strict';
const {execFileSync}=require('node:child_process');
const bin=process.env.AGENT_BROWSER_BIN || (process.platform==='win32'?require('node:path').join(process.env.APPDATA,'npm/node_modules/agent-browser/bin/agent-browser-win32-x64.exe'):'agent-browser');
const check=()=>{
  const assert=(value,message)=>{if(!value)throw Error(message);};
  assert(typeof renderMonarchProvenance==='function','Runs need a Monarch version display');
  renderMonarchProvenance({status:'not_recorded',segments:[{status:'not_recorded',build_label:'monarch@local-label',note:'Exact deployed commit was not recorded. A label is not deployment proof.'}]});
  const panel=document.getElementById('monarch-version');
  assert(!panel.classList.contains('hidden') && panel.textContent.includes('Exact deployed commit was not recorded'),'Historical unknown must be explicit');
  assert(panel.textContent.split('Exact deployed commit was not recorded.').length===2,'Missing-version explanation should appear once');
  const commit='a'.repeat(40),kb='b'.repeat(64);
  renderMonarchProvenance({status:'recorded',segments:[{status:'checkout',competitor_id:'Monarch A',harness:'monarch-primary',commit,knowledge_base_sha256:kb,segment_id:'first',dirty:true},{status:'declared',competitor_id:'Monarch B',commit:'c'.repeat(40),segment_id:'resume',build_label:'<img src=x onerror=alert(1)>'}]});
  assert(panel.textContent.includes(commit) && panel.textContent.includes(kb),'Full source and knowledge-base hashes must be readable');
  assert(panel.textContent.includes('Local checkout') && panel.textContent.includes('Operator declaration'),'Source labels must not imply deployed proof');
  assert(panel.textContent.includes('first') && panel.textContent.includes('resume') && panel.textContent.includes('Modified'),'Continuation segments and dirty state must remain separate');
  assert(panel.textContent.includes('Monarch A') && panel.textContent.includes('Monarch B') && panel.textContent.includes('monarch-primary'),'Multiple Monarch setups retain their own identity');
  assert(!panel.querySelector('img'),'Retained labels must be escaped');
  renderMonarchProvenance({status:'not_applicable',segments:[]});
  assert(panel.classList.contains('hidden'),'Non-Monarch runs should not show empty provenance');
  return 'PASS Monarch version, historical absence, resumed segments and escaping';
};
console.log(execFileSync(bin,['--session','monarch-version','eval','--stdin'],{input:`(${check.toString()})()`,encoding:'utf8',timeout:30000}));
