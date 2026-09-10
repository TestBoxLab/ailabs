"""Small stdio MCP adapter; only scoped Genesis lab actions are exposed."""
import json
import os
import sys
from urllib.request import Request, urlopen

ACTIONS=['search_research','record_analysis','research_state','list_runs','read_run','catalog','save_research','library_list','library_read','library_save','library_analyze','library_use','library_reclassify','save_architecture','publish_architecture','save_product_graph','code_status','code_search','code_explain','code_read','code_changes','memory_read','memory_add','memory_replace','memory_remove','note_write','record_search','propose_experiment','ask_question','activity','skill_list','skill_read','skill_write','skill_remove']
ACTIONS=list(dict.fromkeys(ACTIONS+[a for a in os.environ.get('GENESIS_ACTIONS','').split(',') if a]))  # plugin actions, named by the harness
def respond(value): print(json.dumps(value),flush=True)
for line in sys.stdin:
    try:
        request=json.loads(line);method=request.get('method');identity=request.get('id')
        if identity is None: continue
        if method=='initialize': result={'protocolVersion':request.get('params',{}).get('protocolVersion','2024-11-05'),'capabilities':{'tools':{}},'serverInfo':{'name':'Genesis lab','version':'1.0'}}
        elif method=='tools/list': result={'tools':[{'name':'lab_action','description':'Read research and run evidence, save research cards and versioned architecture/product graph drafts, read and edit core memory (memory_read, memory_add, memory_replace, memory_remove, note_write), search the record (record_search), propose an experiment as a Studio launch payload (propose_experiment: the Studio computes the plan; it launches by itself only at smoke scale within your allowances, otherwise a person approves), ask the lab one question with a suggested default (ask_question), read the activity record (activity), and keep your own procedures as skills (skill_list, skill_read, skill_write, skill_remove: Markdown, first line "Applies: hypothesis, run, source, question, verdict or always"). No approval capability. Use catalog to discover valid IDs and schemas.','inputSchema':{'type':'object','properties':{'action':{'type':'string','enum':ACTIONS},'payload':{'type':'object','additionalProperties':True}},'required':['action','payload']}}]}
        elif method=='tools/call':
            params=request.get('params',{})
            if params.get('name')!='lab_action': raise ValueError('Unknown tool')
            body=params.get('arguments',{})
            if body.get('action') not in ACTIONS: raise ValueError('Unavailable action')
            req=Request(os.environ['GENESIS_BROKER']+'/tool',data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+os.environ['GENESIS_TOKEN'],'Content-Type':'application/json'})
            with urlopen(req,timeout=45) as response: value=json.load(response)
            result={'content':[{'type':'text','text':json.dumps(value)}]}
        elif method=='ping': result={}
        else:
            respond({'jsonrpc':'2.0','id':identity,'error':{'code':-32601,'message':'Method not found'}});continue
        respond({'jsonrpc':'2.0','id':identity,'result':result})
    except Exception:
        result={'content':[{'type':'text','text':'Lab action failed. Check its parameters and the Genesis event log.'}],'isError':True}
        if 'identity' in locals() and identity is not None: respond({'jsonrpc':'2.0','id':identity,'result':result})
