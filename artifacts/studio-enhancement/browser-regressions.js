async function studioBrowserRegressions() {
  // Run in the rendered Studio page. Every write below is intercepted in memory.
  const results=[];
  const check=(name,value)=>{if(!value)throw Error(name);results.push({name,passed:true});};
  const originalApi=api, originalEventSource=window.EventSource;
  const saved={state,job,report,events,blueprint,blueprints,pg,productGraphs,dirty,pgDirty};
  const cached=localStorage.getItem('ailabs-architecture-draft');
  const wait=()=>new Promise(resolve=>setTimeout(resolve,0));
  try {
    $('#launch-dialog').close();
    await $('#open-setup').onclick();
    if(!pg)setProductGraph(null);
    check('Unknown money stays unavailable; measured zero stays zero',money(null)==='Not available'&&money(0)==='$0.00');
    selected={model:state.models[0].id,category:'tool',node:'test',status:'completed',output:false};setOutputMode('formatted');renderOutput();
    check('False is displayed as an observed response',$('#output').textContent==='false');
    selected.output=0;renderOutput();check('Zero is displayed as an observed response',$('#output').textContent==='0');
    check('Untrusted output is escaped',pretty('<img src=x onerror=alert(1)>').includes('&lt;img')&&!pretty('<img src=x onerror=alert(1)>').includes('<img'));
    $('#close-setup').click();
    $('#tab-report').focus();$('.tabs').dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}));
    check('Arrow keys select and focus the next tab',view==='live'&&document.activeElement===$('#tab-live')&&$('#tab-report').tabIndex===-1);
    $('#run-search').value='no-such-run-qa';renderJobs();check('Run search has a clear empty state',$('#jobs').textContent.includes('No runs match'));
    $('#run-search').value='';renderJobs();

    const deferred=[];
    api=async(path,body)=>{
      if(path==='/api/blueprints/validate')return new Promise(resolve=>deferred.push(resolve));
      throw Error('Unexpected request '+path);
    };
    blueprint=structuredClone(blueprint);
    const first=validateNow();blueprint.graph.nodes[0].label='New input label';const second=validateNow();
    deferred[1]({problems:[{node:null,message:'Current validation'}],capabilities:[]});await second;
    deferred[0]({problems:[],capabilities:[]});await first;
    check('Late graph validation cannot overwrite current findings',problems[0]?.message==='Current validation');

    pg=pgFresh();pg.name='Concurrent graph';pgDirty=true;renderPg();
    let saveReply,saveCalls=0,sentPg;
    api=async(path,body)=>{
      if(path==='/api/product-graphs/draft'){saveCalls++;sentPg=structuredClone(body);return new Promise(resolve=>saveReply=resolve);}
      if(path==='/api/product-graphs')return {items:[],products:['Gmail']};
      throw Error('Unexpected request '+path);
    };
    const save1=savePg(),save2=savePg();
    pg.fields[0].description='Newer unsaved description';pgMarkDirty();
    saveReply({...sentPg,id:'saved-graph',revision:1});await Promise.all([save1,save2]);
    check('Concurrent product-graph saves coalesce to one write',saveCalls===1);
    check('Typing during product-graph save is retained and marked unsaved',pg.fields[0].description==='Newer unsaved description'&&pgDirty&&pg.id==='saved-graph'&&pg.revision===1);

    let archReply,sentArch;
    blueprint=structuredClone(blueprint);blueprint.id=null;blueprint.revision=0;$('#blueprint-name').value='Original architecture';
    api=async(path,body)=>{
      if(path==='/api/blueprints/draft'){sentArch=structuredClone(body);return new Promise(resolve=>archReply=resolve);}
      if(path==='/api/blueprints')return {items:[]};
      if(path==='/api/blueprints/validate')return {problems:[],capabilities:[]};
      throw Error('Unexpected request '+path);
    };
    const saving=saveDraft();blueprint={...structuredClone(blueprint),id:'other-architecture',name:'Other architecture'};
    archReply({...sentArch,id:'saved-architecture',revision:1});await saving;
    check('Late architecture save cannot assign its ID to another draft',blueprint.id==='other-architecture'&&blueprint.name==='Other architecture');

    pg=pgFresh();pg.name='First product graph';pgDirty=true;renderPg();
    api=async(path,body)=>{
      if(path==='/api/product-graphs/draft'){sentPg=structuredClone(body);return new Promise(resolve=>saveReply=resolve);}
      if(path==='/api/product-graphs')return {items:[],products:[]};
      throw Error('Unexpected request '+path);
    };
    const pgSaving=savePg();pg={...pgFresh(),id:'other-graph',name:'Other graph'};
    saveReply({...sentPg,id:'old-graph',revision:1});await pgSaving;
    check('Late product-graph save cannot replace the selected graph',pg.id==='other-graph'&&pg.name==='Other graph');

    clearTimeout(validateTimer);
    if(stream)stream.close();
    class FakeStream {static instances=[];constructor(){FakeStream.instances.push(this);}close(){this.closed=true;}}
    window.EventSource=FakeStream;
    const baseJob=structuredClone(saved.job),baseReport=structuredClone(saved.report);
    const mockJob=id=>({...structuredClone(baseJob),id,title:'Run '+id});
    let oldReportReply;
    api=async path=>{
      if(path==='/api/jobs/a/report'&&oldReportReply===null)return new Promise(resolve=>oldReportReply=resolve);
      if(path.endsWith('/report'))return {...structuredClone(baseReport),run:path.split('/')[3]};
      if(path.startsWith('/api/jobs/'))return mockJob(path.split('/')[3]);
      throw Error('Unexpected request '+path);
    };
    await openJob('a');oldReportReply=null;
    const late=refreshReport('a',openSequence);
    await openJob('b');oldReportReply({...baseReport,run:'a'});await late;
    check('A late report cannot contaminate a newly selected run',job.id==='b'&&report.run==='b');
    FakeStream.instances[0].onerror();
    check('Old stream errors cannot change current connection status',$('#connection').textContent==='Connected');

    api=originalApi;
    await openLaunch();
    selectedTasks=new Set([state.tasks[0].id]);renderTaskOptions();
    $('#task-search').value='a query with no matching requests 7123';renderTaskOptions();
    check('Filtering preserves selected tasks and explains hidden selections',selectedTasks.size===1&&$('#task-match-count').textContent.includes('1 selected outside filters'));
    $('#reset-task-filters').click();
    check('Reset filters restores matching tasks without clearing selection',selectedTasks.size===1&&filteredTasks().length===state.tasks.length);
    state.models=[{id:'qa-model',name:'QA runner',available:true,efforts:[],request_ceiling_usd:'0.25'}];
    state.capabilities={versions:[],controls:[]};selectedModels=new Set(['qa-model']);
    $$('[data-comparison-version]').forEach(e=>e.remove());$('#without-monarch').checked=true;
    state.budget={available:'10',actual:'0',held:'0'};$('#run-budget').value='5';$('#run-title').value='QA retry';$('#run-turns').value='20';
    setLaunchStep(2,false);check('A valid run enables Start',!$('#launch-button').disabled);
    $('#run-budget').value='0.01';launchSize();check('Insufficient single-request budget blocks launch',$('#launch-button').disabled&&$('#budget-floor').textContent.includes('$0.25'));
    $('#run-budget').value='11';launchSize();check('Weekly capacity blocks an oversized run',$('#launch-button').disabled&&$('#budget-floor').textContent.includes('$10.00'));
    $('#run-budget').value='5';$('#run-title').value='   ';launchSize();check('Whitespace-only names are rejected',$('#launch-button').disabled);
    $('#run-title').value='QA retry';launchSize();
    let launchReply;const launchIds=[];
    api=async(path,body)=>{
      if(path==='/api/jobs'){launchIds.push(body.request_id);return new Promise((resolve,reject)=>launchReply={resolve,reject});}
      throw Error('Unexpected request '+path);
    };
    const launchingFirst=$('#launch-form').onsubmit({preventDefault(){}});
    await $('#launch-form').onsubmit({preventDefault(){}});
    check('Repeated submission while pending issues only one POST',launchIds.length===1&&$('#launch-button').disabled);
    const uncertain=new Error('Simulated lost response');uncertain.uncertain=true;launchReply.reject(uncertain);await launchingFirst;
    const retry=$('#launch-form').onsubmit({preventDefault(){}});
    check('Retry after uncertain response reuses the original request ID',launchIds.length===2&&launchIds[0]===launchIds[1]);
    const rejected=new Error('Offline test completed');rejected.uncertain=false;launchReply.reject(rejected);await retry;
    check('Definitive rejection releases the retry identity',launchRequest===null);
  } catch(error) {results.push({name:'Regression failure',passed:false,error:error.message,stack:error.stack});}
  finally {
    api=originalApi;window.EventSource=originalEventSource;clearTimeout(validateTimer);
    if(stream)stream.close();
    state=saved.state;job=saved.job;report=saved.report;events=saved.events;blueprint=saved.blueprint;blueprints=saved.blueprints;pg=saved.pg;productGraphs=saved.productGraphs;dirty=saved.dirty;pgDirty=saved.pgDirty;
    if(cached===null)localStorage.removeItem('ailabs-architecture-draft');else localStorage.setItem('ailabs-architecture-draft',cached);
    launching=false;launchRequest=null;$('#launch-dialog').close();
    $('#close-setup').click();selectedTasks.clear();selectedModels.clear();pendingJobId=saved.job.id;
    await initialize();
  }
  return {passed:results.filter(r=>r.passed).length,failed:results.filter(r=>!r.passed).length,results};
}
