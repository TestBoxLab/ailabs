"use strict";
const $ = id => document.getElementById(id);
let key = "", epoch = 0, selected = null, selection = 0, pending = null;
const states = {queued:"Queued · waiting for execution",running:"Running",awaiting_review:"Verified · awaiting review",failed:"Failed",interrupted:"Interrupted · needs attention"};
function notice(message,error=false){$("notice").textContent=message;$("notice").dataset.error=String(error);}
async function api(path,options={}){
  const generation=epoch;
  const response=await fetch(path,{...options,cache:"no-store",headers:{"Authorization":"Bearer "+key,...options.headers}});
  if(generation!==epoch)throw new Error("Connection changed. Try again.");
  if(!response.ok){const body=await response.json();throw new Error(body.error||"Request failed. Try again.");}
  return response;
}
async function run(button,task){button.disabled=true;try{await task();}catch(error){notice(error.message,true);}finally{button.disabled=false;}}
async function refresh(){const data=await(await api("/jobs")).json();$("jobs").replaceChildren();
  if(!data.jobs.length){const p=document.createElement("p");p.textContent="No repairs yet. Your requests will appear here.";$("jobs").append(p);}
  for(const job of data.jobs){const button=document.createElement("button");button.className="job";button.type="button";button.dataset.job=job.id;button.setAttribute("aria-pressed",String(selected===job.id));const title=document.createElement("strong");title.textContent=job.payload.change;const meta=document.createElement("span");meta.textContent=(job.payload.repo==="lab"?"AI Labs":"Monarch Enterprise")+" · "+(states[job.state]||job.state)+" · "+new Date(job.created*1000).toLocaleString();button.append(title,meta);button.addEventListener("click",()=>run(button,()=>show(job.id)));$("jobs").append(button);}
}
async function show(id,reveal=true){const current=++selection;const job=await(await api("/jobs/"+id)).json();if(current!==selection)return;selected=id;$("detail").hidden=false;$("detail-state").textContent=states[job.state]||job.state;$("metadata").replaceChildren();
  for(const [label,value] of [["Request",id],["Commit",job.payload.commit],["Updated",new Date(job.updated*1000).toLocaleString()],["Patch hash",job.result?.diff_sha256||"Not available"]]){const dt=document.createElement("dt"),dd=document.createElement("dd");dt.textContent=label;dd.textContent=value;$("metadata").append(dt,dd);}
  $("detail-note").textContent=job.result?.error||job.result?.agent_error||job.result?.declined||(job.state==="queued"?"Saved. A valid allowance and worker are required before execution.":job.state==="awaiting_review"?"Verification passed. This patch has not been applied or released.":"");
  $("output").textContent=job.result?.verify_output||"No verification output yet.";$("diff").textContent=job.result?.diff||"No patch preview yet.";$("download").hidden=!job.result?.diff_sha256;document.querySelectorAll(".job").forEach(button=>button.setAttribute("aria-pressed",String(button.dataset.job===id)));if(reveal){$("receipt-title").focus();$("receipt-title").scrollIntoView({block:"nearest"});}
}
$("access").addEventListener("submit",event=>{event.preventDefault();run($("connect"),async()=>{epoch++;key=$("key").value.trim();await refresh();$("key").value="";$("workspace").hidden=false;$("disconnect").hidden=false;$("connect").hidden=true;$("key").disabled=true;$("key").hidden=true;$("key-label").hidden=true;$("connected-state").hidden=false;notice("Connected. Your saved requests are loaded.");});});
$("disconnect").addEventListener("click",()=>{epoch++;selection++;key="";selected=null;pending=null;$("key").value="";$("key").disabled=false;$("key").hidden=false;$("key-label").hidden=false;$("connected-state").hidden=true;$("workspace").hidden=true;$("detail").hidden=true;$("jobs").replaceChildren();$("metadata").replaceChildren();$("diff").textContent="";$("output").textContent="";$("repair").reset();$("disconnect").hidden=true;$("connect").hidden=false;notice("Disconnected.");$("key").focus();});
$("repo").addEventListener("change",()=>{$("commit").value="";});
$("resolve").addEventListener("click",()=>run($("resolve"),async()=>{const repo=$("repo").value;const info=await(await api("/repos/"+repo)).json();if(repo!==$("repo").value)return;$("commit").value=info.commit;notice("Source revision loaded from GitHub.");}));
$("refresh").addEventListener("click",()=>run($("refresh"),async()=>{await refresh();if(selected)await show(selected,false);notice("Repair status refreshed.");}));
$("repair").addEventListener("submit",event=>{event.preventDefault();run(event.submitter,async()=>{const spec=Object.fromEntries(["repo","commit","change","verification"].map(name=>[name,$(name).value.trim()]));const serialized=JSON.stringify(spec);if(!pending||pending.spec!==serialized)pending={spec:serialized,id:crypto.randomUUID()};const job=await(await api("/jobs",{method:"POST",headers:{"Content-Type":"application/json","Idempotency-Key":pending.id},body:JSON.stringify({spec})})).json();await refresh();await show(job.id);notice("Repair queued. Execution is pending funding and worker availability.");});});
$("download").addEventListener("click",()=>run($("download"),async()=>{const id=selected;const response=await api("/jobs/"+id+"/patch");const url=URL.createObjectURL(await response.blob());const link=document.createElement("a");link.href=url;link.download=id+".patch";link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);notice("Complete patch downloaded.");}));
fetch("/health",{cache:"no-store"}).then(response=>{if(!response.ok)throw Error();return response.json();}).then(()=>{$("service").textContent="Recovery service online";}).catch(()=>{$("service").textContent="Recovery service unavailable";notice("Could not reach recovery. Reload this page to reconnect.",true);});
