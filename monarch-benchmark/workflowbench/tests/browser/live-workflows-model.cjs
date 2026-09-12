'use strict';
const assert = require('node:assert/strict');
const Flow = require('../../wb_studio/static/flow-model.js');
const base = {task: 't', model: 'm'};
const e = (id, type, data = {}) => ({...base, id, type, at: new Date(id * 1000).toISOString(), ...data});
const rows = [e(1, 'attempt_started'), e(2, 'model_started', {node:'m1'}),
  e(3, 'model_delta', {node:'m1',text:'Read '}), e(4, 'model_delta', {node:'m1',text:'the contact'}),
  e(5, 'node_started', {node:'t1',label:'api_fetch',arguments:{url:'https://salesforce.mock/contacts',method:'GET'}}),
  e(6, 'node_finished', {node:'t1',status:'completed',output:{records:[{city:'Denver'}]}})];
let p = Flow.project([...rows, rows[3]], {...base, live:true});
assert.equal(p.nodes.find(n=>n.node==='m1').output,'Read the contact');
assert.equal(p.nodes.find(n=>n.node==='t1').seconds,1);
assert.deepEqual(p.nodes.find(n=>n.node==='t1').output,{records:[{city:'Denver'}]});
assert.equal(p.nodes.some(n=>n.category==='result'),false);
assert.equal(p.edges.every(x=>x.kind==='sequence'),true);
assert.equal(p.nodes[0].status,'running');
p = Flow.project([...rows,e(7,'model_finished',{node:'m1',status:'completed',output:'Final text'})], {...base,live:true});
assert.equal(p.nodes[0].output,'Final text');
assert.equal(p.nodes[0].seconds,5);
p = Flow.project(rows,{...base,live:false});
assert.equal(p.nodes[0].status,'interrupted');
assert.equal(p.nodes[0].seconds,null, 'an interrupted node has no recorded finish time');
p = Flow.project(rows,{...base,live:false,result:{...base,passed:false,termination:'timeout',seconds:8,output:'Incomplete'}});
assert.equal(p.nodes.at(-1).status,'error');
assert.equal(p.nodes[0].status,'interrupted');
p = Flow.project([e(1,'workflow_recipe',{nodes:[{id:'a',label:'Read'},{id:'b',label:'Write'},{id:'c',label:'Notify'}],edges:[{source:'a',target:'c'}]}),
  e(2,'workflow_step',{node:'wf:a',status:'running'}),e(3,'workflow_step',{node:'wf:a',status:'succeeded',rendered:{value:42}})],{...base,live:true});
assert.equal(p.nodes[0].seconds,1);
assert.deepEqual(p.edges,[{source:'wf:a',target:'wf:c',kind:'dependency'}]);
assert.deepEqual(p.nodes[0].output,{value:42});
assert.equal(p.nodes[1].status,'pending');
assert.equal(Flow.project([e(1,'model_finished',{node:'orphan',output:'Hello',status:'completed',at:'bad'})],{...base,live:false}).nodes[0].seconds,null);
assert.equal(Flow.preview({records:[{a:1},{a:2}]}).label,'2 records');
assert.equal(Flow.preview({}).text,'No response body returned.');
assert.equal(Flow.preview(null).text,'No output recorded.');
assert.equal(Flow.preview('x'.repeat(5000)).truncated,true);
const late = Flow.project([e(2,'workflow_step',{node:'wf:late',status:'succeeded',rendered:'complete'}),e(1,'workflow_step',{node:'wf:late',status:'running'})],{...base,live:true});
assert.equal(late.nodes[0].status,'completed','late running event cannot undo a terminal result');
const invalidFinish = Flow.project([e(1,'model_finished',{node:'invalid',at:'bad',status:'completed',output:'Complete'}),e(2,'model_delta',{node:'invalid',text:' duplicate'}),e(3,'model_started',{node:'invalid'})],{...base,live:true});
assert.equal(invalidFinish.nodes[0].status,'completed');
assert.equal(invalidFinish.nodes[0].output,'Complete');
assert.equal(Flow.project([],{...base,result:{passed:true,termination:'completed',flags:['grading=ungraded']}}).nodes.at(-1).status,'ungraded');
console.log('Live workflow projection checks passed.');
