'use strict';
// Pure projection of recorded events. Sequence edges describe observation order,
// never inferred dependencies or access to a model's hidden reasoning.
const WorkflowFlow = (() => {
  const timestamp = value => { const n = Date.parse(value); return Number.isFinite(n) ? n : null; };
  const ungraded = row => !!row?.ungraded || (row?.flags||[]).includes('grading=ungraded');
  const states = {succeeded:'completed',failed:'error',blocked:'error'};
  function project(events, {task, model, result = null, live = false}) {
    const nodes = new Map(), seen = new Set(), dependencies = [];
    let start = null, last = null, recipe = false;
    const get = (id, category) => {
      if (!nodes.has(id)) nodes.set(id, {node:id,task,model,category,status:'pending',output:null,start:null,end:null,eventId:null,terminal:false,updatedAt:null});
      return nodes.get(id);
    };
    for (const e of events) {
      if (e.task !== task || e.model !== model || (e.id != null && seen.has(e.id))) continue;
      if (e.id != null) seen.add(e.id);
      const at = timestamp(e.at); if (at !== null) last = Math.max(last ?? at, at);
      if (e.type === 'attempt_started') { start = at; continue; }
      if (e.type === 'attempt_finished') { result = result || e; continue; }
      if (e.type === 'workflow_recipe') {
        recipe = true;
        for (const item of e.nodes || []) {
          const n = get('wf:' + item.id, 'workflow'); Object.assign(n, item, {node:'wf:' + item.id});
        }
        for (const edge of e.edges || []) {
          if (edge.source != null && edge.target != null) dependencies.push({source:'wf:'+edge.source,target:'wf:'+edge.target,kind:'dependency'});
        }
        continue;
      }
      if (e.type === 'knowledge_delivered') {
        Object.assign(get('knowledge:'+(e.step||e.id), 'knowledge'), {label:e.label || 'Product knowledge',status:'completed',output:e.products+' products attached',eventId:e.id});
        continue;
      }
      if (e.type === 'step_started' || e.type === 'step_finished') {
        // Steps are phase labels; individual model/tool nodes carry their outputs.
        const n = get('step:'+e.step, 'step'); n.label = e.label; n.status = e.type==='step_started'?'running':states[e.status]||e.status||'completed';
        if (e.type==='step_started') n.start = at; else { n.end = at; n.output = e.output; }
        n.eventId = e.id; continue;
      }
      if (!e.node || !['model_started','model_delta','model_finished','node_started','node_finished','workflow_step'].includes(e.type)) continue;
      const category = e.category || (e.type.startsWith('model_')?'model':e.type==='workflow_step'?'workflow':'tool');
      const n = get(e.node,category);
      if (e.type==='workflow_step' && ((at!==null && n.updatedAt!==null && at<n.updatedAt) || (n.terminal && !['succeeded','completed','failed','error','blocked','skipped'].includes(e.status)))) continue;
      if (e.type==='model_delta' && n.terminal) continue;
      n.updatedAt = at ?? n.updatedAt; n.eventId = e.id; n.label = e.label || n.label; n.step = e.step || n.step;
      if (e.arguments !== undefined) n.arguments = e.arguments;
      if (e.message !== undefined) n.message = e.message;
      if (e.progress !== undefined) n.progress = e.progress;
      if (e.type.endsWith('_started')) { n.start = n.start ?? at; if (!n.terminal) n.status = 'running'; }
      else if (e.type==='model_delta') {
        if (!n.terminal) { n.output = (typeof n.output==='string'?n.output:'')+(e.text||''); n.status = 'running'; }
      } else if (e.type==='workflow_step') {
        n.status = states[e.status] || e.status || 'pending';
        if (n.status==='running') n.start = n.start ?? at;
        if (['completed','error','skipped'].includes(n.status)) { n.end = at; n.terminal = true; }
        if (e.rendered !== undefined && e.rendered !== null) n.output = e.rendered;
        else if (e.output !== undefined) n.output = e.output;
      } else {
        n.end = at; n.terminal = true; n.status = states[e.status] || e.status || 'completed';
        if (e.output !== undefined) n.output = e.output;
      }
    }
    const list = [...nodes.values()];
    for (const n of list) {
      n.seconds = n.start !== null && n.end !== null && n.end >= n.start ? (n.end-n.start)/1000 : null;
      if (!live || result) {
        if (n.status==='running') n.status='interrupted';
        if (n.status==='pending') n.status='skipped';
      }
    }
    if (result) list.push({node:'result',category:'result',task,model,result,output:result.output,status:ungraded(result)?'ungraded':result.passed&&result.termination==='completed'?'completed':String(result.termination).startsWith('infra:')?'interrupted':'error',seconds:result.seconds ?? null,label:'Verify task outcome'});
    const visible = list.filter(n=>n.category!=='step');
    const edges = dependencies.length ? dependencies.filter(e=>nodes.has(e.source)&&nodes.has(e.target))
      : visible.slice(1).map((n,i)=>({source:visible[i].node,target:n.node,kind:'sequence'}));
    return {nodes:list,edges,start,last,recipe,result,relationship:dependencies.length?'Recorded dependencies':recipe?'Reported step order · dependencies unavailable':'Observed event order',active:list.filter(n=>n.status==='running').map(n=>n.node)};
  }
  function preview(value, limit=700) {
    if (value===null || value===undefined) return {text:'No output recorded.',label:'Output',truncated:false};
    let parsed=value; if(typeof parsed==='string') {try {parsed=JSON.parse(parsed);}catch { /* plain output */ }}
    if (parsed && typeof parsed==='object' && !Array.isArray(parsed) && !Object.keys(parsed).length) return {text:'No response body returned.',label:'Output',truncated:false};
    const records=Array.isArray(parsed)?parsed:parsed&&typeof parsed==='object'?Object.values(parsed).find(Array.isArray):null;
    const text=typeof parsed==='string'?parsed:JSON.stringify(parsed,null,2);
    return {text:text.slice(0,limit),label:records?records.length+' '+(records.length===1?'record':'records'):'Output',truncated:text.length>limit};
  }
  return {project,preview,timestamp,ungraded};
})();
if (typeof module !== 'undefined') module.exports = WorkflowFlow;
