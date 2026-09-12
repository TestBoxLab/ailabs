'use strict';
// Both live Activity and the permanent report render this server projection.
// No aggregation of benchmark results happens in this presentation layer.
const PerformanceView = (() => {
  const svgNS = 'http://www.w3.org/2000/svg';
  const seconds = v => v == null ? 'Unavailable' : v < 60 ? Number(v.toFixed(2))+'s' : Math.floor(v/60)+'m '+Number((v%60).toFixed(1))+'s';
  const money = v => v == null ? 'Unavailable' : '$'+(v===0?'0.00':Number(v.toPrecision(4)));
  const percent = v => v == null ? 'Unavailable' : Number((v*100).toFixed(1))+'%';
  function text(parent, selector, value) {const el=parent.querySelector(selector);if(el&&el.textContent!==String(value))el.textContent=String(value);}
  function sEl(type,attrs,parent) {const n=document.createElementNS(svgNS,type);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);parent.append(n);return n;}
  function paint(root, data, {live=false, inspect=null}={}) {
    if (!data) { root.textContent='Performance metrics are loading…'; return; }
    root._performance = data; root._inspect = inspect;
    if (!root.querySelector('.performance-figures')) {
      root.classList.add('performance-view');
      root.innerHTML='<div class="performance-heading"><h3>Performance as tasks finish</h3><span class="performance-progress" role="status"></span></div>'+
        '<div class="performance-figures"><figure><figcaption>Task outcomes <span>All recorded attempts</span></figcaption><div class="performance-outcomes"></div><p class="performance-key"><span class="passed">Passed</span><span class="failed">Failed</span><span class="infra">Execution issue</span><span class="ungraded">Ungraded</span><span>Remaining</span></p></figure>'+
        '<figure><figcaption>Time to successful completion <span>Median and 90th percentile · seconds</span></figcaption><div class="performance-times"></div><p class="performance-scale"></p></figure></div>'+
        '<p class="performance-note"></p><details class="performance-detail"><summary>Compare time, cost and reliability</summary><div class="table-scroll" tabindex="0" role="region" aria-label="Performance metrics by model"><table class="table performance-table"><caption class="sr-only">Recorded performance by model</caption><thead><tr><th scope="col">Model</th><th scope="col">Passed / recorded</th><th scope="col">Successful median / p90</th><th scope="col">Failed median</th><th scope="col">All-attempt median</th><th scope="col">Cost / success</th><th scope="col">Recorded cost</th><th scope="col">Tool calls / errors</th><th scope="col">Model turns</th><th scope="col">Unintended changes</th></tr></thead><tbody></tbody></table></div><div class="performance-samples"></div><p class="performance-provenance performance-definitions"></p><p class="performance-definitions">Completion time is recorded attempt run time; queueing and grading are not included. Successful timing includes only passed attempts that finished normally. Cost per success includes failed attempts and execution issues. P90 is descriptive with small samples. Tool errors and turns depend on available event coverage; a successful tool response is not proof that the task passed.</p></details><p class="chart-source performance-source"></p>';
    }
    const rows=data.order.map(id=>data.setups[id]).filter(Boolean), maxTime=Math.max(1,...rows.map(r=>r.timing.successful.p90||0));
    text(root,'.performance-progress',data.recorded_attempts+' / '+data.planned_attempts+' recorded');
    text(root,'.performance-note',live?'Partial results · metrics change when graded attempts arrive. Pending work is excluded from rates.':'Recorded results · timing samples can differ by model. Inspect the same task before comparing speed.');
    text(root,'.performance-heading h3',live?'Results so far':'Recorded performance');
    text(root,'.performance-source','Source: run '+data.run+' · original records');
    text(root,'.performance-provenance',data.source||'Original recorded run evidence.');
    text(root,'.performance-scale','Shared scale: 0–'+seconds(maxTime)+'. Circle = median; end marker = p90.');
    for (const [selector,type] of [['.performance-outcomes','outcomes'],['.performance-times','times']]) {
      const parent=root.querySelector(selector);
      for(const child of [...parent.children])if(!rows.some(r=>r.id===child.dataset.setup))child.remove();
      rows.forEach(row=>{
        let item=[...parent.children].find(n=>n.dataset.setup===row.id);
        if(!item){
          item=document.createElement('div');item.className='performance-row';item.dataset.setup=row.id;
          item.innerHTML='<div><strong class="performance-name"></strong><span class="performance-value"></span></div><svg viewBox="0 0 360 26" role="img"></svg>';
          const svg=item.querySelector('svg');
          sEl('title',{},svg);sEl('rect',{x:0,y:6,width:360,height:14,class:'performance-track'},svg);
          if(type==='outcomes') ['passed','failed','infra','ungraded'].forEach(cls=>sEl('rect',{y:6,height:14,class:'performance-bar '+cls},svg));
          else {sEl('line',{y1:13,y2:13,class:'performance-range'},svg);sEl('circle',{cy:13,r:5,class:'performance-median'},svg);sEl('line',{y1:7,y2:19,class:'performance-p90'},svg);}
          parent.append(item);
        }
        text(item,'.performance-name',row.name);
        const svg=item.querySelector('svg'),width=Math.max(150,item.clientWidth);
        svg.setAttribute('viewBox','0 0 '+width+' 26');svg.querySelector('.performance-track').setAttribute('width',width);
        if(type==='outcomes') {
          const scale=width/Math.max(1,row.planned,row.recorded), counts=[row.passed,row.failed,row.infrastructure,row.ungraded||0];let x=0;
          item.querySelectorAll('.performance-bar').forEach((rect,i)=>{rect.setAttribute('x',x);rect.setAttribute('width',counts[i]*scale);x+=counts[i]*scale;});
          const value=row.passed+' passed / '+row.recorded+' recorded';text(item,'.performance-value',value);
          text(svg,'title',row.name+': '+value+', '+row.failed+' failed, '+row.infrastructure+' execution issues, '+(row.ungraded||0)+' ungraded, '+Math.max(0,row.planned-row.recorded)+' remaining');
        } else {
          const d=row.timing.successful, median=d.median==null?0:d.median/maxTime*(width-10)+5, end=d.p90==null?0:d.p90/maxTime*(width-10)+5;
          const line=item.querySelector('.performance-range');line.setAttribute('x1',median);line.setAttribute('x2',end);
          item.querySelector('.performance-median').setAttribute('cx',median);
          const tail=item.querySelector('.performance-p90');tail.setAttribute('x1',end);tail.setAttribute('x2',end);
          svg.classList.toggle('performance-unavailable',d.count===0);
          text(item,'.performance-value',d.count?seconds(d.median)+' / '+seconds(d.p90)+' · n='+d.count:'No successful timing samples');
          text(svg,'title',row.name+': median '+seconds(d.median)+', p90 '+seconds(d.p90)+', '+d.count+' successful timing samples, '+d.missing+' missing');
        }
      });
    }
    const body=root.querySelector('tbody');
    for(const tr of [...body.children])if(!rows.some(r=>r.id===tr.dataset.setup))tr.remove();
    for(const row of rows) {
      let tr=[...body.children].find(n=>n.dataset.setup===row.id);
      if(!tr){tr=document.createElement('tr');tr.dataset.setup=row.id;tr.innerHTML='<th scope="row"></th>'+Array.from({length:9},()=>'<td></td>').join('');body.append(tr);}
      const d=row.timing.successful;
      const vals=[row.name,row.passed+' / '+row.recorded+' ('+percent(row.operational_success_rate)+')',seconds(d.median)+' / '+seconds(d.p90)+' · n='+d.count+(d.missing?' · '+d.missing+' missing':''),seconds(row.timing.failed.median)+' · n='+row.timing.failed.count+(row.timing.failed.missing?' · '+row.timing.failed.missing+' missing':''),seconds(row.timing.all.median)+' · n='+row.timing.all.count+(row.timing.all.missing?' · '+row.timing.all.missing+' missing':''),row.passed?money(row.cost.per_success):'No passes',row.cost.total==null?money(row.cost.known_subtotal)+' known · '+row.cost.unknown_attempts+' unpriced':money(row.cost.total),(row.tools.calls??'Unavailable')+' / '+(row.tools.observed_calls?(row.tools.errors??'Unavailable'):'Unavailable')+(row.tools.observed_calls?' ('+row.tools.observed_calls+' observed)':' (no error telemetry)'),row.turns.observed_attempts?(row.turns.total??'Unavailable')+' · '+row.turns.observed_attempts+' attempts observed':'Unavailable · no turn coverage',row.collateral.changes+' known across '+row.collateral.attempts+' attempts'+(row.collateral.missing_attempts?' · '+row.collateral.missing_attempts+' incomplete':'')];
      [...tr.children].forEach((td,i)=>{if(td.textContent!==String(vals[i]))td.textContent=vals[i];});
    }
    const samples=root.querySelector('.performance-samples');
    for(const child of [...samples.children])if(!rows.some(r=>r.id===child.dataset.setup))child.remove();
    for(const row of rows){
      let group=[...samples.children].find(n=>n.dataset.setup===row.id);
      if(!group){group=document.createElement('details');group.dataset.setup=row.id;group.innerHTML='<summary></summary><p class="performance-phases"></p><ol></ol>';samples.append(group);}
      text(group,'summary',row.name+' · '+row.recorded+' attempt samples');
      text(group,'.performance-phases','Recorded phase medians: '+(Object.entries(row.phases||{}).map(([key,d])=>key+' '+seconds(d.median)+' (n='+d.count+')').join('; ')||'Unavailable'));
      const list=group.querySelector('ol');
      row.attempts.forEach((a,index)=>{
        let li=list.children[index];if(!li){li=document.createElement('li');li.append(document.createElement('a'));list.append(li);}
        const link=li.firstChild;link.href='#run/'+encodeURIComponent(data.run)+'/'+encodeURIComponent(a.task)+'/'+encodeURIComponent(a.model);
        const label=a.task+' · '+seconds(a.seconds)+' · '+(a.infrastructure?'Execution issue':a.ungraded?'Ungraded':a.passed?'Passed':'Failed');if(link.textContent!==label)link.textContent=label;
        link.onclick=inspect?event=>{event.preventDefault();root._inspect(a);}:null;
      });
      while(list.children.length>row.attempts.length)list.lastChild.remove();
    }
  }
  return {paint,seconds,money};
})();
