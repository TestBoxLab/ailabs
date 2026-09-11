// Start the free fixture: uv run python tests/browser/server.py --port 8777
// Control responses are scripted; no paid run can be dispatched by this check.
'use strict';
const {execFileSync}=require('node:child_process');
const bin=process.env.AGENT_BROWSER_BIN||(process.platform==='win32'?require('node:path').join(process.env.APPDATA,'npm/node_modules/agent-browser/bin/agent-browser-win32-x64.exe'):'agent-browser');
const browser=(...args)=>execFileSync(bin,['--session','controls-ui',...args],{encoding:'utf8'});
console.log(browser('open',`http://127.0.0.1:${process.env.BROWSER_PORT||8777}`));
const test=async()=>{
  const assert=(ok,message)=>{if(!ok)throw Error(message);};
  const el=id=>document.getElementById(id);
  for(let i=0;i<100&&el('connection').dataset.status!=='connected';i++)await new Promise(r=>setTimeout(r,100));
  await openJob(state.jobs[0].id);stream.close();
  const original=structuredClone(job),calls=[];
  job={...job,status:'running',config_source:{commit:'a'.repeat(40)},pause_requested:false,active_attempts:2};
  const configured=structuredClone(job);
  const realApi=api;let blocked=false,failResume=false,reopened=0;
  api=async(path,body)=>{
    if(!path.startsWith('/api/jobs/'+job.id+'/'))return realApi(path,body);
    calls.push({path,body});
    if(path.endsWith('/resume-preview'))return {resumable:!blocked,reasons:blocked?['Unresolved provider request']:[],preview_id:'reviewed-preview',required_initial:2,earned_retries:1,required_attempts:3,conditional_retries:2,maximum_attempts:5,known_cost_usd:'12.50',unresolved_usd:'0.25',reserved_usd:'1.00',remaining_ceiling_usd:'46.25',config_commit:'a'.repeat(40)};
    if(path.endsWith('/pause'))return {...job,status:'pausing',pause_requested:true};
    if(path.endsWith('/resume')){if(failResume)throw Error('Preview expired');return {...job,status:'running',pause_requested:false,resumed_at:new Date().toISOString()};}
    throw Error('Unexpected control request '+path);
  };
  const realOpen=openJob;openJob=async id=>{assert(id===job.id,'Resume must preserve run identity');reopened++;};
  syncJob(job);
  assert(!el('pause-run').classList.contains('hidden')&&!el('pause-run').disabled,'Configured running job must expose Pause');
  await el('pause-run').onclick();
  assert(runStatus(job)==='pausing'&&el('run-message').textContent.includes('active attempts'),'Pause must show draining active attempts');
  assert(el('resume-run').classList.contains('hidden')&&!el('cancel-run').classList.contains('hidden'),'Draining work can cancel but cannot resume yet');
  syncJob({...job,status:'paused',active_attempts:0});
  await el('resume-run').onclick();
  assert(el('resume-dialog').open&&el('resume-dialog').getBoundingClientRect().width>0,'Resume must open a visible review dialog');
  const review=el('resume-summary').textContent;
  assert(review.includes('3')&&review.includes('2')&&review.includes('$12.50')&&review.includes('$0.25')&&review.includes('$46.25'),'Preview must show required, conditional, known, unresolved and ceiling amounts');
  assert(!calls.some(c=>c.path.endsWith('/resume')),'Preview alone must never resume');
  el('resume-cancel').click();assert(!el('resume-dialog').open,'Review can be cancelled without dispatch');
  blocked=true;await el('resume-run').onclick();
  assert(el('resume-confirm').disabled&&el('resume-error').textContent.includes('Unresolved provider'),'Blocked preview must explain its refusal and disable confirmation');
  el('resume-cancel').click();blocked=false;
  await el('resume-run').onclick();failResume=true;await el('resume-form').onsubmit({preventDefault(){}});
  assert(el('resume-dialog').open&&el('resume-error').textContent.includes('expired')&&el('resume-confirm').disabled,'Dispatch refusal must invalidate the reviewed preview');
  el('resume-cancel').click();failResume=false;
  await el('resume-run').onclick();await el('resume-form').onsubmit({preventDefault(){}});
  assert(calls.filter(c=>c.path.endsWith('/resume')).at(-1).body.preview_id==='reviewed-preview'&&reopened===1,'Confirmed preview must be sent once and reconnect the run stream');
  for(const status of ['completed','cancelled']){syncJob({...configured,status});assert(el('resume-run').classList.contains('hidden'),'Terminal '+status+' must not offer Resume');}
  syncJob({...configured,status:'interrupted'});assert(!el('resume-run').classList.contains('hidden'),'Interrupted configured run must offer review');
  syncJob({...original,status:'running',pause_requested:true,active_attempts:0});await el('resume-run').onclick();
  assert(Object.keys(calls.at(-1).body).length===0,'Ordinary paused runs retain the existing resume request');
  api=realApi;openJob=realOpen;
  return 'PASS: configured pause/drain, preview-only review, blocked/expired refusals, explicit resume with stream reconnection, terminal controls and ordinary resume';
};
console.log(execFileSync(bin,['--session','controls-ui','eval','--stdin'],{input:`(${test.toString()})()`,encoding:'utf8'}));
