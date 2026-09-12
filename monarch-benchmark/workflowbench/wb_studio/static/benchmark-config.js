'use strict';
// Configuration plans use the shared CLI resolver and their own immutable preview.
(() => {
  let catalog, latest, selected, checked=false, preview, busy=false, requestId, group='plans';
  const groups={harnesses:'Harnesses',models:'Models',plans:'Plans',products:'Products'}, created=new Map();
  const draft=new Map(), el=id=>document.getElementById('bc-'+id);
  const changes=()=>[...draft].map(([path,text])=>({path,text}));
  const status=text=>{el('status').textContent=text;};
  const names=kind=>(catalog?.files||[]).filter(f=>f.artifact?.kind===kind).map(f=>f.path.split('/').pop().slice(0,-5));
  const artifact=path=>created.get(path)||catalog?.files.find(f=>f.path===path)?.artifact;
  const type=id=>catalog?.artifact_types?.find(t=>t.id===id);
  const editable=()=>!!selected&&artifact(selected)?.editable===true;
  const safeUrl=value=>{try{const url=new URL(value);return url.protocol==='https:'?url.href:null;}catch{return null;}};
  function creationHelp(){
    const t=type(el('new-type').value);
    el('new-help').textContent=t?'Required fields: '+t.required_fields.join(', ')+'. Example values and references must be reviewed.':'';
  }
  async function loadHistory(){
    try{
      const data=await api('/api/benchmark-config/history');
      el('history-list').innerHTML=data.error?'<p>'+esc(data.error)+'</p>':data.history?.length?'<ol>'+data.history.map(row=>{
        const url=safeUrl(row.url), revision=url?'<a href="'+esc(url)+'" target="_blank" rel="noreferrer">'+esc(row.commit)+'</a>':esc(row.commit);
        return '<li><p>'+esc(row.message)+'</p><dl><dt>Author</dt><dd>'+esc(row.author)+'</dd><dt>Technical committer</dt><dd>'+esc(row.committer)+'</dd><dt>Time</dt><dd>'+esc(row.time||'Not recorded')+'</dd><dt>Revision</dt><dd>'+revision+'</dd></dl></li>';
      }).join('')+'</ol>':'<p>No configuration commits recorded.</p>';
    }catch(error){el('history-list').textContent='History unavailable. '+error.message;}
  }
  function controls(){
    el('save').disabled=busy||!catalog?.writable||!checked||!draft.size||!el('message').value.trim()||!catalog?.actor?.id;
    el('validate').disabled=busy||!draft.size;
    el('preview').disabled=busy||!catalog?.configured||!!draft.size||!el('product').value||!el('plan').value;
    el('run').disabled=busy||!!draft.size||!preview?.launchable||!el('operator').value.trim();
    el('refresh').disabled=busy;
    el('discard').disabled=busy||!draft.size;
    el('files').disabled=busy;
    el('text').readOnly=busy||!catalog?.writable||!editable()||draft.get(selected)===null;
    el('new').disabled=busy||!catalog?.writable||!el('new-name').value.trim()||!type(el('new-type').value);
    el('delete').disabled=busy||!catalog?.writable||!editable();
    el('new-type').disabled=busy||!catalog?.writable;el('new-name').disabled=busy||!catalog?.writable;
    el('delete').textContent=draft.get(selected)===null?'Restore file':'Delete file from draft';
    el('product').disabled=busy;el('plan').disabled=busy;
    el('operator').disabled=busy;
    el('dirty').textContent=draft.size?draft.size+' changed file'+(draft.size===1?'':'s')+' in this tab.':'No unsaved changes.';
  }
  function clearPreview(){preview=null;requestId=null;el('preview-result').textContent='Preview the saved revision to see attempts, cost and readiness.';controls();}
  function file(){
    selected=el('files').value;
    el('text').value=draft.has(selected)?draft.get(selected):catalog.files.find(f=>f.path===selected)?.text||'';
    el('filename').textContent=selected||'No '+groups[group].toLowerCase()+' yet';
    const description=artifact(selected), manifest=type(description?.kind);
    el('help').textContent=description?.editable===false?description.reason||'Generated evidence is read-only.':manifest?'Required fields: '+manifest.required_fields.join(', ')+'. Validate to check values and references.':selected?'Validate to check this artifact against the server schema.':'Create an artifact using a supported type below.';
    el('remote').classList.toggle('hidden',!latest);
    el('remote-text').textContent=latest?.files.find(f=>f.path===selected)?.text||'This file is absent from the refreshed revision.';
    controls();
  }
  function render(){
    el('repository').textContent=catalog.configured?catalog.repository+' / '+catalog.branch+' / '+catalog.commit:'';
    el('actor').textContent=catalog.actor?'Configuration author: '+catalog.actor.name+' ('+catalog.actor.id+'; '+catalog.actor.source+'). The server records this authenticated account.':'Configuration author is unavailable. Sign in with a verified person key or Basic account before saving.';
    const link=el('history'),url=safeUrl(catalog.history_url);
    link.classList.toggle('hidden',!url);if(url)link.href=url;
    el('editor').classList.toggle('hidden',!catalog.configured);
    el('group-title').textContent=groups[group];
    document.querySelectorAll('[data-benchmark-group]').forEach(a=>a.setAttribute('aria-current',a.dataset.benchmarkGroup===group?'page':'false'));
    el('launch').classList.toggle('hidden',group!=='plans');
    if(!catalog.configured){status('The benchmark configuration repository is not configured on this Studio server.');return;}
    const paths=[...new Set([...catalog.files.map(f=>f.path),...draft.keys()])].filter(path=>artifact(path)?.group===group).sort();
    el('files').innerHTML=paths.map(path=>'<option value="'+esc(path)+'">'+esc(path)+(draft.get(path)===null?' / deleted':draft.has(path)?' / changed':artifact(path)?.editable===false?' / read-only':'')+'</option>').join('');
    el('files').value=paths.includes(selected)?selected:paths[0]||'';
    const oldType=el('new-type').value,types=(catalog.artifact_types||[]).filter(t=>t.group===group);
    el('new-type').innerHTML=types.map(t=>'<option value="'+esc(t.id)+'">'+esc(t.label)+'</option>').join('');
    if(types.some(t=>t.id===oldType))el('new-type').value=oldType;
    creationHelp();
    for(const [id,kind] of [['product','product'],['plan','plan']]){const old=el(id).value;el(id).innerHTML=names(kind).map(n=>'<option>'+esc(n)+'</option>').join('');if(names(kind).includes(old))el(id).value=old;}
    file();controls();
  }
  async function operation(action){
    if(busy)return;busy=true;controls();
    try{await action();}catch(error){status((error.status===409?'Main changed. Your draft is retained. Refresh to inspect the latest files before resolving the conflict. ':error.uncertain?'The outcome could not be confirmed. Your draft is retained; refresh to inspect the repository before retrying. ':'Your draft is retained. ')+error.message);}
    finally{busy=false;controls();}
  }
  async function refresh(){
    await operation(async()=>{
      status('Reading configuration…');const next=await api('/api/benchmark-config');
      if(draft.size){latest=next;file();status('Refreshed main at '+next.commit+'. Your draft still uses '+catalog.commit+'. Compare the latest file below; copy any edits you need before discarding the draft.');}
      else{catalog=next;latest=null;render();status(next.configured?(next.writable?'Configuration loaded.':'Configuration loaded with read-only access.'):'The benchmark configuration repository is not configured on this Studio server.');}
      await loadHistory();
    });
  }
  window.loadBenchmarkConfig=async()=>{
    if(!el('status')){
      document.getElementById('benchmark-config').innerHTML=`
        <p>Saving creates a commit on main. Existing runs keep their original configuration.</p>
        <nav class="config-groups" aria-label="Benchmark artifact groups">${Object.entries(groups).map(([id,label])=>'<a href="#benchmarks/'+id+'" data-benchmark-group="'+id+'">'+label+'</a>').join('')}</nav><h2 id="bc-group-title">Plans</h2>
        <p id="bc-repository" class="config-revision"></p><div class="action-row"><button class="button" id="bc-refresh" type="button">Refresh configuration</button><a id="bc-history" class="hidden" target="_blank" rel="noreferrer">GitHub history</a></div>
        <p id="bc-status" role="status" aria-live="polite"></p>
        <div id="bc-editor" class="hidden"><div class="config-editor"><div><label for="bc-files">Artifacts in this group</label><select id="bc-files" size="12"></select><details class="config-create"><summary>Create artifact</summary><label for="bc-new-type">Artifact type</label><select id="bc-new-type" aria-describedby="bc-new-help"></select><p id="bc-new-help" class="field-hint"></p><label for="bc-new-name">Name</label><input id="bc-new-name" placeholder="my-artifact" autocomplete="off" aria-describedby="bc-name-help"><p id="bc-name-help" class="field-hint">Use letters, numbers, hyphens or underscores. The type determines the YAML file location.</p><button class="button" id="bc-new" type="button">Create draft</button></details></div><div><label id="bc-filename" for="bc-text">Configuration file</label><p id="bc-help" class="field-hint"></p><textarea id="bc-text" rows="18" spellcheck="false" autocomplete="off" autocapitalize="off" aria-describedby="bc-help bc-dirty"></textarea><p id="bc-dirty" class="field-hint"></p><button class="text-button" id="bc-delete" type="button">Delete file from draft</button><details id="bc-remote" class="hidden"><summary>Latest version of this file on main</summary><pre id="bc-remote-text"></pre></details></div></div>
        <div class="action-row"><button class="button" id="bc-validate" type="button">Validate and review diff</button><button class="text-button" id="bc-discard" type="button">Discard draft</button></div>
        <div id="bc-validation" role="status" aria-live="polite"></div><pre id="bc-diff" class="hidden" aria-label="Configuration diff"></pre>
        <div class="config-save"><label for="bc-message">Commit message</label><input id="bc-message" maxlength="500" autocomplete="off"><p id="bc-actor" class="field-hint"></p><button id="bc-save" class="button" type="button" disabled>Save changes to main</button></div>
        <div class="config-launch" id="bc-launch"><h3>Run a configured plan</h3><p>Choose a saved product and plan. This uses the plan's competitors, tasks and limits.</p><div class="config-fields"><label>Product<select id="bc-product"></select></label><label>Plan<select id="bc-plan"></select></label><label>Declared run operator<input id="bc-operator" maxlength="100" autocomplete="name" placeholder="Your name" aria-describedby="bc-operator-help"></label></div><p id="bc-operator-help" class="field-hint">Records who requests the run, separately from configuration authorship. Approval, billing and budget are checked before launch.</p><button class="button" id="bc-preview" type="button">Preview saved plan</button><div id="bc-preview-result" role="status" aria-live="polite">Preview the saved revision to see attempts, cost and readiness.</div><button class="button primary" id="bc-run" type="button" disabled>Run this revision</button></div></div>
        <details class="config-history"><summary>Configuration history</summary><div id="bc-history-list" aria-live="polite">Reading history...</div></details>`;
      document.querySelectorAll('[data-benchmark-group]').forEach(a=>a.onclick=e=>{e.preventDefault();window.openBenchmarks(a.dataset.benchmarkGroup);});
      el('refresh').onclick=refresh;el('files').onchange=file;
      el('text').oninput=()=>{
        if(!editable()||!catalog.writable||busy||draft.get(selected)===null)return;
        const original=catalog.files.find(f=>f.path===selected)?.text;
        if(el('text').value===original)draft.delete(selected);else draft.set(selected,el('text').value);
        const option=[...el('files').options].find(o=>o.value===selected);if(option)option.textContent=selected+(draft.has(selected)?' · changed':'');
        checked=false;el('validation').textContent='Validate this draft before saving.';el('diff').classList.add('hidden');clearPreview();
      };
      for(const id of ['message','new-name'])el(id).oninput=controls;
      el('operator').oninput=clearPreview;
      el('new-type').onchange=()=>{creationHelp();controls();};
      function changed(){checked=false;el('validation').textContent='Validate this draft before saving.';el('diff').classList.add('hidden');clearPreview();render();}
      el('new').onclick=()=>{
        const name=el('new-name').value.trim(),manifest=type(el('new-type').value);
        if(!/^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(name)){status('Use a name of up to 80 letters, numbers, hyphens or underscores, starting with a letter or number.');return;}
        if(!catalog.writable||!manifest)return;
        const path=manifest.path_pattern.replace('{name}',name);
        if(catalog.files.some(f=>f.path===path)||draft.has(path)){status('That artifact already exists. Select it in the file list.');return;}
        created.set(path,{group:manifest.group,kind:manifest.id,editable:true});
        draft.set(path,manifest.template.split('__NAME__').join(name));selected=path;el('new-name').value='';changed();el('text').focus();
      };
      el('delete').onclick=()=>{
        if(!editable()||!catalog.writable)return;
        if(draft.get(selected)===null||!catalog.files.some(f=>f.path===selected))draft.delete(selected);else draft.set(selected,null);
        if(!draft.has(selected))created.delete(selected);
        changed();
      };
      for(const id of ['product','plan'])el(id).onchange=clearPreview;
      el('discard').onclick=()=>{if(!confirm('Discard all unsaved configuration edits in this tab?'))return;draft.clear();created.clear();checked=false;if(latest)catalog=latest;latest=null;el('validation').textContent='';el('diff').classList.add('hidden');clearPreview();render();status('Draft discarded.');};
      el('validate').onclick=()=>operation(async()=>{
        const result=await api('/api/benchmark-config/validate',{base_commit:catalog.commit,changes:changes()});checked=result.valid===true;
        const describe=e=>typeof e==='string'?e:JSON.stringify(e);
        el('validation').textContent=(checked?'Valid configuration. Review the diff before saving.':(result.errors||[]).map(describe).join('\n'))+((result.warnings||[]).length?'\nWarnings (launch readiness is checked separately):\n'+result.warnings.map(describe).join('\n'):'');
        el('diff').textContent=result.diff||'No changes.';el('diff').classList.remove('hidden');
      });
      el('save').onclick=()=>operation(async()=>{
        if(!checked||!draft.size)return;
        status('Saving changes…');catalog=await api('/api/benchmark-config/save',{base_commit:catalog.commit,changes:changes(),message:el('message').value.trim()});
        draft.clear();created.clear();latest=null;checked=false;clearPreview();el('validation').textContent='';el('diff').classList.add('hidden');el('message').value='';render();status('Saved configuration at '+catalog.commit+'. No run was started.');await loadHistory();
      });
      el('preview').onclick=()=>operation(async()=>{
        preview=null;requestId=null;el('preview-result').textContent='Checking the saved plan…';
        preview=await api('/api/benchmark-config/preview',{commit:catalog.commit,product:el('product').value,plan:el('plan').value,operator:el('operator').value.trim()});
        const competitors=preview.competitors.map(c=>typeof c==='string'?c:c.name||c.id).join(', ');
        const facts=[['Revision',preview.commit],['Product / plan',preview.product+' / '+preview.plan],['Tasks',Array.isArray(preview.tasks)?preview.tasks.length:preview.tasks],['Competitors',competitors],['Attempts including retries',preview.attempts_min+'–'+preview.attempts_max],['Cost ceiling',money(preview.cost_ceiling_usd)],['Readiness',preview.launchable?'Ready for an explicit launch':'Blocked'],['Configuration hash',preview.config_hash]];
        el('preview-result').innerHTML='<dl class="facts">'+facts.map(([label,value])=>'<dt>'+esc(label)+'</dt><dd>'+esc(value)+'</dd>').join('')+'</dl>'+(preview.reasons.length?'<ul>'+preview.reasons.map(r=>'<li>'+esc(r)+'</li>').join('')+'</ul>':'')+'<p>Run uses this revision even if main changes. Launch rechecks approval, billing and budget.</p>';
      });
      el('run').onclick=()=>operation(async()=>{
        if(!preview?.launchable||draft.size)return;
        requestId ||= crypto.randomUUID();
        const result=await api('/api/benchmark-config/run',{preview_id:preview.preview_id,commit:preview.commit,product:preview.product,plan:preview.plan,request_id:requestId,operator:el('operator').value.trim()});
        preview=null;el('status').innerHTML='Started configured run <a href="#run/'+encodeURIComponent(result.id)+'">'+esc(result.id)+'</a>.';
      });
      window.addEventListener('beforeunload',event=>{if(draft.size){event.preventDefault();event.returnValue='';}});
    }
    if(!catalog)await refresh();else render();
  };
  window.openBenchmarks=async requested=>{
    const route=location.hash.startsWith('#benchmarks/')?location.hash.split('/')[1]:null;
    group=Object.hasOwn(groups,requested||route)?requested||route:'plans';
    showWorkspaceSurface('benchmarks',false);
    if(location.hash!=='#benchmarks/'+group)history.pushState(null,'','#benchmarks/'+group);
    await window.loadBenchmarkConfig();
  };
})();
