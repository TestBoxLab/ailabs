'use strict';
// Configuration plans use the shared CLI resolver and their own immutable preview.
(() => {
  let catalog, latest, selected, checked=false, preview, busy=false, requestId;
  const draft=new Map(), el=id=>document.getElementById('bc-'+id);
  const changes=()=>[...draft].map(([path,text])=>({path,text}));
  const status=text=>{el('status').textContent=text;};
  const names=kind=>(catalog?.files||[]).filter(f=>f.path.startsWith('config/'+kind+'/')&&f.path.endsWith('.yaml')&&!/\.(knowledge-map|monarch-kb|monarch-recipes)\.yaml$/.test(f.path)).map(f=>f.path.split('/').pop().slice(0,-5));
  function controls(){
    el('save').disabled=busy||!catalog?.writable||!checked||!draft.size||!el('message').value.trim()||!el('operator').value.trim();
    el('validate').disabled=busy||!draft.size;
    el('preview').disabled=busy||!catalog?.configured||!!draft.size||!el('product').value||!el('plan').value;
    el('run').disabled=busy||!!draft.size||!preview?.launchable||!el('operator').value.trim();
    el('refresh').disabled=busy;
    el('discard').disabled=busy||!draft.size;
    el('files').disabled=busy;
    el('text').readOnly=busy||!catalog?.writable||draft.get(selected)===null;
    el('new').disabled=busy||!catalog?.writable||!el('new-path').value.trim();
    el('delete').disabled=busy||!catalog?.writable||!selected;
    el('delete').textContent=draft.get(selected)===null?'Restore file':'Delete file from draft';
    el('product').disabled=busy;el('plan').disabled=busy;
    el('operator').disabled=busy;
    el('dirty').textContent=draft.size?draft.size+' changed file'+(draft.size===1?'':'s')+' in this tab.':'No unsaved changes.';
  }
  function clearPreview(){preview=null;requestId=null;el('preview-result').textContent='Preview the saved revision to see attempts, cost and readiness.';controls();}
  function file(){
    selected=el('files').value;
    el('text').value=draft.has(selected)?draft.get(selected):catalog.files.find(f=>f.path===selected)?.text||'';
    el('filename').textContent=selected||'Configuration file';
    el('remote').classList.toggle('hidden',!latest);
    el('remote-text').textContent=latest?.files.find(f=>f.path===selected)?.text||'This file is absent from the refreshed revision.';
    controls();
  }
  function render(){
    el('repository').textContent=catalog.repository+' · '+catalog.branch+' · '+catalog.commit;
    const link=el('history');
    // Links are supplied by the configured repository service, but remain URL-checked.
    let url;try{url=new URL(catalog.history_url);}catch{}
    link.classList.toggle('hidden',!url||url.protocol!=='https:');if(url?.protocol==='https:')link.href=url.href;
    el('editor').classList.toggle('hidden',!catalog.configured);
    if(!catalog.configured){status('The benchmark configuration repository is not configured on this Studio server.');return;}
    const paths=[...new Set([...catalog.files.map(f=>f.path),...draft.keys()])].sort();
    el('files').innerHTML=paths.map(path=>'<option value="'+esc(path)+'">'+esc(path)+(draft.get(path)===null?' · deleted':draft.has(path)?' · changed':'')+'</option>').join('');
    el('files').value=paths.includes(selected)?selected:paths[0]||'';
    for(const [id,kind] of [['product','products'],['plan','plans']]){const old=el(id).value;el(id).innerHTML=names(kind).map(n=>'<option>'+esc(n)+'</option>').join('');if(names(kind).includes(old))el(id).value=old;}
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
    });
  }
  window.loadBenchmarkConfig=async()=>{
    if(!el('status')){
      document.getElementById('benchmark-config').innerHTML=`
        <h2>Benchmark configuration</h2><p>Shared files for configured benchmark plans. Saving creates a commit on main. Existing runs keep their original configuration.</p>
        <p id="bc-repository" class="config-revision"></p><div class="action-row"><button class="button" id="bc-refresh" type="button">Refresh configuration</button><a id="bc-history" class="hidden" target="_blank" rel="noreferrer">GitHub history</a></div>
        <p id="bc-status" role="status" aria-live="polite"></p>
        <div id="bc-editor" class="hidden"><div class="config-editor"><div><label for="bc-files">Configuration files</label><select id="bc-files" size="12"></select><label for="bc-new-path">New file path</label><input id="bc-new-path" placeholder="config/plans/my-plan.yaml" autocomplete="off"><button class="button" id="bc-new" type="button">New file</button></div><div><label id="bc-filename" for="bc-text">Configuration file</label><textarea id="bc-text" rows="18" spellcheck="false" autocomplete="off" autocapitalize="off" aria-describedby="bc-dirty"></textarea><p id="bc-dirty" class="field-hint"></p><button class="text-button" id="bc-delete" type="button">Delete file from draft</button><details id="bc-remote" class="hidden"><summary>Latest version of this file on main</summary><pre id="bc-remote-text"></pre></details></div></div>
        <div class="action-row"><button class="button" id="bc-validate" type="button">Validate and review diff</button><button class="text-button" id="bc-discard" type="button">Discard draft</button></div>
        <div id="bc-validation" role="status" aria-live="polite"></div><pre id="bc-diff" class="hidden" aria-label="Configuration diff"></pre>
        <div class="config-fields"><label>Commit message<input id="bc-message" maxlength="500" autocomplete="off"></label><label>Operator<input id="bc-operator" maxlength="100" autocomplete="name" placeholder="Your name"></label></div><p class="field-hint">The operator records who requested the change or run. Your Studio session determines permissions.</p><button id="bc-save" class="button" type="button" disabled>Save changes to main</button>
        <div class="config-launch"><h3>Run a configured plan</h3><p>Choose a saved product and plan. This uses the plan’s competitors, tasks and limits.</p><div class="config-fields"><label>Product<select id="bc-product"></select></label><label>Plan<select id="bc-plan"></select></label></div><button class="button" id="bc-preview" type="button">Preview saved plan</button><div id="bc-preview-result" role="status" aria-live="polite">Preview the saved revision to see attempts, cost and readiness.</div><button class="button primary" id="bc-run" type="button" disabled>Run this revision</button></div></div>`;
      el('refresh').onclick=refresh;el('files').onchange=file;
      el('text').oninput=()=>{
        const original=catalog.files.find(f=>f.path===selected)?.text;
        if(el('text').value===original)draft.delete(selected);else draft.set(selected,el('text').value);
        const option=[...el('files').options].find(o=>o.value===selected);if(option)option.textContent=selected+(draft.has(selected)?' · changed':'');
        checked=false;el('validation').textContent='Validate this draft before saving.';el('diff').classList.add('hidden');clearPreview();
      };
      for(const id of ['message','new-path'])el(id).oninput=controls;
      el('operator').oninput=clearPreview;
      function changed(){checked=false;el('validation').textContent='Validate this draft before saving.';el('diff').classList.add('hidden');clearPreview();render();}
      el('new').onclick=()=>{
        const path=el('new-path').value.trim();
        if(!/^config\/(?:[a-zA-Z0-9_-]+\/)*[a-zA-Z0-9_.-]+\.(yaml|yml|md)$/.test(path)||path.split('/').some(p=>p==='.'||p==='..')){status('Use a configuration path such as config/plans/my-plan.yaml.');return;}
        if(catalog.files.some(f=>f.path===path)||draft.has(path)){status('That file already exists. Select it in the file list.');return;}
        draft.set(path,'');selected=path;el('new-path').value='';changed();el('text').focus();
      };
      el('delete').onclick=()=>{
        if(draft.get(selected)===null||!catalog.files.some(f=>f.path===selected))draft.delete(selected);else draft.set(selected,null);
        changed();
      };
      for(const id of ['product','plan'])el(id).onchange=clearPreview;
      el('discard').onclick=()=>{if(!confirm('Discard all unsaved configuration edits in this tab?'))return;draft.clear();checked=false;if(latest)catalog=latest;latest=null;el('validation').textContent='';el('diff').classList.add('hidden');clearPreview();render();status('Draft discarded.');};
      el('validate').onclick=()=>operation(async()=>{
        const result=await api('/api/benchmark-config/validate',{base_commit:catalog.commit,changes:changes()});checked=result.valid===true;
        const describe=e=>typeof e==='string'?e:JSON.stringify(e);
        el('validation').textContent=(checked?'Valid configuration. Review the diff before saving.':(result.errors||[]).map(describe).join('\n'))+((result.warnings||[]).length?'\nWarnings (launch readiness is checked separately):\n'+result.warnings.map(describe).join('\n'):'');
        el('diff').textContent=result.diff||'No changes.';el('diff').classList.remove('hidden');
      });
      el('save').onclick=()=>operation(async()=>{
        if(!checked||!draft.size)return;
        status('Saving changes…');catalog=await api('/api/benchmark-config/save',{base_commit:catalog.commit,changes:changes(),message:el('message').value.trim(),operator:el('operator').value.trim()});
        draft.clear();latest=null;checked=false;clearPreview();el('validation').textContent='';el('diff').classList.add('hidden');el('message').value='';render();status('Saved configuration at '+catalog.commit+'. No run was started.');
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
    if(!catalog)await refresh();
  };
})();
