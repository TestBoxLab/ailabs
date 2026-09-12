// Use retained attachments only: node tests/browser/evidence-guide.cjs GUIDE LOGS_GZ PROMPTS_GZ
'use strict';
const {execFileSync}=require('node:child_process'),path=require('node:path');
const [guide,logs,prompts]=process.argv.slice(2);
if(!guide||!logs||!prompts)throw Error('Supply guide, logs and prompts files');
const bin=path.join(process.env.APPDATA,'npm/node_modules/agent-browser/bin/agent-browser-win32-x64.exe');
const args=['--session','evidence-guide'];
const run=(...cmd)=>execFileSync(bin,[...args,...cmd],{encoding:'utf8',timeout:60000});
const evaluate=fn=>execFileSync(bin,[...args,'eval','--stdin'],{input:'('+fn.toString()+')()',encoding:'utf8',timeout:60000});
console.log(run('open',require('node:url').pathToFileURL(path.resolve(guide)).href));
console.log(run('upload','#files',path.resolve(logs),path.resolve(prompts)));
console.log(evaluate(async()=>{
  const until=Date.now()+45000;
  while(document.querySelector('#load-status').textContent.startsWith('Reading')&&Date.now()<until)await new Promise(r=>setTimeout(r,200));
  if(!document.querySelector('#load-status').textContent.startsWith('Loaded:'))throw Error(document.querySelector('#load-status').textContent);
  const task=document.querySelector('#task');task.value='simple.airtable_find_update';task.dispatchEvent(new Event('change'));
  if(!document.querySelector('#brief').textContent.includes('VIP'))throw Error('Missing actual task brief');
  if(!document.querySelector('#expected').textContent.includes('VIP'))throw Error('Missing expected VIP criterion');
  const attempt=document.querySelector('#attempt'),retry=[...attempt.options].find(o=>o.textContent.startsWith('monarch@')&&o.textContent.endsWith('Retry 1'));
  if(!retry)throw Error('Missing Monarch retry');attempt.value=retry.value;attempt.dispatchEvent(new Event('change'));
  if(!document.querySelector('#result').textContent.startsWith('Passed'))throw Error('Saved retry result must be a pass');
  const prompt=document.querySelector('#prompts details');if(!prompt)throw Error('Missing Monarch goal');prompt.open=true;
  const button=prompt.querySelector('button');if(!button)throw Error('Missing prompt to log link');button.click();
  if(!document.querySelector('#logs details'))throw Error('Prompt has no matching log observations');
  const observation=document.querySelector('#logs details');observation.open=true;await new Promise(r=>setTimeout(r,100));
  const record=JSON.parse(observation.querySelector('pre').textContent);
  if(record.attempt_id!==attempt.value||!record.log_id)throw Error('Wrong linked attempt or missing log ID');
  return 'PASS: real compressed files, frozen request/expected result, saved retry verdict and exact prompt→log linkage';
}));
run('set','viewport','390','844');
console.log(evaluate(()=>{if(document.documentElement.scrollWidth>innerWidth+1)throw Error('Mobile overflow');return 'PASS: mobile guide fits the page';}));
console.log(evaluate(()=>{
  guide.tasks.push({...guide.tasks[0],id:'empty-layout-fixture'});
  option(document.querySelector('#task'),'empty-layout-fixture','Empty layout fixture');
  document.querySelector('#task').value='empty-layout-fixture';renderTask();
  if(document.querySelector('#attempt-id').textContent||document.querySelector('#logs').children.length||!document.querySelector('#result').textContent.includes('No recorded attempt'))throw Error('Empty task retains another task result');
  return 'PASS: task without outcomes clears prior evidence';
}));
