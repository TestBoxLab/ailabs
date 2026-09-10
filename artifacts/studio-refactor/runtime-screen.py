from pathlib import Path
p=Path('monarch-benchmark/workflowbench/wb_studio/static/workspace.js');s=p.read_text(encoding='utf8')
s=s.replace("<dt>Active agents</dt><dd>'+runtime.active_agents", "<dt>'+(runtime.agent_metric==='allocated'?'Assigned agent slots':'Active agents')+'</dt><dd>'+runtime.active_agents")
s=s.replace("<dt>Execution</dt><dd>Single host</dd>", "<dt>Execution</dt><dd>'+(runtime.mode==='coordinator-workers'?'Worker pool':'Local worker')+'</dd>")
s=s.replace("<th>Requests / minute</th><th>Active</th>", "<th>Requests / minute</th><th>Tokens / minute</th><th>Active</th>")
s=s.replace("runtime.default_provider_limits.requests_per_minute+'</td><td>—", "runtime.default_provider_limits.requests_per_minute+'</td><td>Not configured</td><td>—")
s=s.replace("p.requests_per_minute+'</td><td>'+p.active", "p.requests_per_minute+'</td><td>'+esc(p.tokens_per_minute??'Not configured')+'</td><td>'+p.active")
s=s.replace('This workspace uses shared team access; separate tenants and distributed workers are not configured.', "This is a shared team workspace. Workers use authenticated connections and the same central budget. Unknown work is held for investigation rather than automatically replayed.")
s=s.replace("  const selected=Object.fromEntries", "  const selected=Object.fromEntries")
# Add worker inventory as operational detail, outside the launch journey.
needle="}\n$('#nav-runtime').onclick="
s=s.replace(needle,"  if(runtime.worker_nodes)$('#runtime-content').insertAdjacentHTML('beforeend','<details class=\"runtime-details\"><summary>Connected workers</summary>'+runtime.worker_nodes.map(w=>'<p><strong>'+esc(w.worker)+'</strong> · '+(w.connected?'Connected':'Offline')+' · '+w.active_jobs.length+' assigned runs</p>').join('')+'</details>');\n}\n$('#nav-runtime').onclick=")
p.write_text(s,encoding='utf8')
