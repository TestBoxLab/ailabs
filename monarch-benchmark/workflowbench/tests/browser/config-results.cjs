// Start the free fixture: uv run python tests/browser/server.py --port 8766 --configured-results
// This check consumes real SSE and job/report endpoints; no API or EventSource mocks.
'use strict';
const {execFileSync}=require('node:child_process');
const bin=process.env.AGENT_BROWSER_BIN||(process.platform==='win32'?require('node:path').join(process.env.APPDATA,'npm/node_modules/agent-browser/bin/agent-browser-win32-x64.exe'):'agent-browser');
const args=['--session','config-results'];
console.log(execFileSync(bin,[...args,'open',`http://127.0.0.1:${process.env.BROWSER_PORT||8766}`],{encoding:'utf8'}));
const test=async()=>{
  const assert=(ok,message)=>{if(!ok)throw Error(message);};
  for(let i=0;i<100&&document.getElementById('connection').dataset.status!=='connected';i++)await new Promise(r=>setTimeout(r,100));
  const fixture=state.jobs.find(j=>j.title==='Configured result stream fixture');
  assert(fixture,'Configured SSE fixture must be enabled');
  const requests=[];const original=window.fetch;
  window.fetch=(url,options)=>{requests.push(String(url));return original(url,options);};
  await openJob(fixture.id);
  assert(job.completed===1&&runCost(job)===0.25,'Initial authoritative state is one attempt at $0.25');
  for(let i=0;i<60&&job.completed!==3;i++)await new Promise(r=>setTimeout(r,100));
  assert(events.filter(e=>e.type==='result').length===2,'Two actual result SSE messages must arrive');
  assert(job.completed===3&&job.results.length===3,'Result events must refresh all attempts including retries of the same task/model');
  assert(new Set(job.results.map(r=>r.episode_id)).size===3&&new Set(job.results.map(r=>r.task+':'+r.model)).size===1,'Repeated task/model pairs retain distinct episode identities');
  assert(runCost(job)===1.5&&document.getElementById('comparison-meta').textContent.includes('$1.50'),'Authoritative cost must update from $0.25 to $1.50');
  assert(document.getElementById('result-count').textContent==='3','Visible result count must refresh');
  assert(requests.filter(p=>p==='/api/jobs/'+fixture.id).length===2,'Burst of result events should debounce to one authoritative job refresh');
  assert(requests.filter(p=>p==='/api/jobs/'+fixture.id+'/report').length===2,'Burst should reuse the debounced report refresh');
  stream.close();
  return 'PASS: real result SSE refreshes authoritative retries, completed count and $1.50 cost; two events share one job/report refresh';
};
console.log(execFileSync(bin,[...args,'eval','--stdin'],{input:`(${test.toString()})()`,encoding:'utf8'}));
