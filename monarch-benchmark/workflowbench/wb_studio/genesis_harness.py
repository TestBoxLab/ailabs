"""Codex subprocess with a scoped model broker and scientist-only MCP tools."""
from __future__ import annotations
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from decimal import Decimal
from wb_arms import providers
from wb_orchestrator.budget import BudgetExceeded
from wb_studio.gateways import ceiling_cost, _money, EFFORTS
from wb_studio.genesis_provider import complete, response_events
from wb_studio.library import now_sao_paulo
from wb_studio.memory import CREDENTIAL
from wb_studio import genesis_plugins

OUTPUT_CAP=16000     # output tokens one request may produce at most
OUTPUT_FLOOR=1024    # below this an answer cannot finish; the request is refused instead
THINKING_ALLOWANCE={'gemini':65536}  # Gemini bills thinking as output; the cap does not bound it


class GenesisRefused(ValueError):
    """The lab's own refusal of a request, written to be shown to a person."""


def summary(value,limit=240):
    """A short, credential-free rendering of a tool payload or result for the turn's record."""
    text=json.dumps(value,ensure_ascii=False,default=str) if not isinstance(value,str) else value
    text=CREDENTIAL.sub('[redacted]',text)
    return text if len(text)<=limit else text[:limit]+'...'


def request_bounds(provider,size,remaining):
    """(input tokens, output cap, ceiling) for one request against what is left of the turn's allowance.

    Two bytes a token is a conservative input estimate for JSON prose, plus room for the tool schema Codex
    adds. The output cap is what the remainder can pay for after the input, at most OUTPUT_CAP; the provider
    receives the cap, so the ceiling is honest. A request that cannot afford OUTPUT_FLOOR is refused in words."""
    input_tokens=size//2+2048
    rate_in=Decimal(str(max(provider.price_in,provider.price_cache_write or 0)))
    price_out=Decimal(str(provider.price_out))
    thinking=THINKING_ALLOWANCE.get(provider.adapter,0)
    remaining=Decimal(remaining)
    input_cost=_money(Decimal(input_tokens)*rate_in/1_000_000)
    affordable=OUTPUT_CAP if price_out<=0 else int((remaining-input_cost)*1_000_000/price_out)-thinking
    max_output=min(OUTPUT_CAP,affordable)
    if max_output<OUTPUT_FLOOR:
        floor=ceiling_cost(provider,input_tokens,OUTPUT_FLOOR+thinking)
        raise GenesisRefused(f"The turn's allowance is spent: ${remaining:.2f} left; one more request on {provider.key} needs at least ${floor:.2f}. Raise the per-turn cap or choose a cheaper model.")
    return input_tokens,max_output,ceiling_cost(provider,input_tokens,max_output+thinking)


def freshness(now=None):
    """The clock and the recency rule every Genesis turn receives."""
    now=now or now_sao_paulo()
    return 'Current date and time: '+now.strftime('%Y-%m-%d %H:%M')+' (America/Sao_Paulo). Prefer sources from the last six months; keep foundational and contradicting work.'


def codex_binary():
    explicit=os.environ.get('STUDIO_CODEX_BINARY')
    if explicit: return explicit if Path(explicit).is_file() else None
    npm=Path(os.environ.get('APPDATA',''))/'npm/node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe'
    return str(npm) if npm.is_file() else shutil.which('codex')


def model_routes():
    # `available` is what a turn needs: the key and the Codex CLI. `keyed` and `harness_ready`
    # are the two facts apart, so the configuration page can say which one is missing.
    ready = bool(codex_binary())
    return [{'id':p.key,'name':p.model_id,'provider':p.family or p.adapter,'harness':'Codex','available':bool(ready and providers.api_key(p)),
             'keyed':bool(providers.api_key(p)),'harness_ready':ready,
             'verification':'Live provider route not yet verified', 'efforts':list(EFFORTS[p.adapter]) or ['default']} for p in providers.REGISTRY.values()]


def build_prompt(genesis,turn):
    """Protocol, freshness, core memory (LAB.md, MONARCH.md, the card's notes), the previous exchange and the request."""
    protocol=(Path(__file__).with_name('GENESIS.md')).read_text(encoding='utf8')+genesis_plugins.protocol()
    history=[];parent_id=turn.get('parent');seen=set();history_size=0
    while parent_id and parent_id not in seen and len(history)<8:
        seen.add(parent_id)
        try:
            parent=genesis.read('turns',parent_id)
            exchange={'user':parent['message'],'genesis':parent['answer']}
            history_size+=len(json.dumps(exchange))
            if history_size>64000: break
            history.insert(0,exchange);parent_id=parent.get('parent')
        except (ValueError,FileNotFoundError): break
    memory=getattr(genesis,'memory',None)
    core=memory.prompt_block(turn.get('card')) if memory else ''
    skills=getattr(genesis,'skills',None)
    if skills:
        kind=None
        if turn.get('card'):
            try: kind=genesis.read('cards',turn['card']).get('kind')
            except (ValueError,FileNotFoundError,OSError): kind=None
        core+=skills.prompt_block(kind or turn.get('kind'))
    core+=genesis_plugins.prompt(genesis,turn)
    return protocol+'\n\n'+freshness()+core+'\n\nPrevious exchange:\n'+json.dumps(history)+'\n\nUser request:\n'+turn['message']


def start_turn(genesis,turn):
    identity=turn['id'];scope='genesis-'+identity;maximum=Decimal(turn['maximum_usd']);studio=genesis.studio
    token=secrets.token_urlsafe(32);provider=providers.get(turn['model']);counter=0;request_lock=threading.Lock();provider_state={};spent=Decimal('0');last_reason=None
    class Broker(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def reply(self,status,value,content='application/json'):
            raw=value if isinstance(value,bytes) else json.dumps(value).encode()
            self.send_response(status);self.send_header('Content-Type',content);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def do_POST(self):
            nonlocal counter,spent,last_reason
            request_id = None
            dispatched = settled = False
            if not secrets.compare_digest(self.headers.get('Authorization',''),'Bearer '+token): return self.reply(403,{'error':'Scoped authorization required'})
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=2_000_000: raise ValueError('Genesis request is too large')
                body=json.loads(self.rfile.read(size))
                if self.path=='/tool':
                    genesis.event(identity,'tool_started',action=body['action'],payload=summary(body.get('payload',{})))
                    result=genesis.tool(body['action'],body.get('payload',{}))
                    genesis.event(identity,'tool_completed',action=body['action'],result=summary(result))
                    return self.reply(200,result)
                if self.path!='/v1/responses': return self.reply(404,{'error':'Unknown route'})
                with request_lock:
                    counter+=1
                    if counter>24: raise GenesisRefused('Genesis reached its limit of 24 requests in one turn')
                    request_id=scope+'-'+str(counter)
                    # A realistic input estimate and an output cap paid for by what is left of the allowance; the provider receives the cap.
                    upper,max_output,ceiling=request_bounds(provider,size,maximum-spent)
                    studio.ledger.reserve(request_id,ceiling,scope_id=scope,scope_limit_usd=maximum,metadata={'purpose':'Genesis','provider':provider.key,'model':provider.model_id,'harness':'codex-cross-provider'})
                    with studio.runtime.provider(provider.family or provider.adapter,timeout=180,tokens=upper+max_output):
                        studio.ledger.claim(request_id)
                        dispatched = True
                        genesis.event(identity,'model_started',request=counter,model=provider.model_id,max_output=max_output,ceiling_usd=str(ceiling))
                        body['_provider_state']=provider_state;body['_max_output']=max_output
                        body['reasoning']={'effort':turn.get('effort','medium' if provider.adapter!='openai' else 'default')}
                        result=complete(provider,body,lambda text:genesis.event(identity,'text_delta',text=text))
                    u=result['usage']
                    if any(type(v) is not int or v<0 for v in u.values()): raise ValueError('Provider usage could not be verified')
                    genesis.event(identity,'provider_receipt',request=counter,usage=u,finish_reason=result.get('finish_reason'))
                    actual=_money(str(providers.cost_usd(provider,u['prompt_tokens'],u['cached_tokens'],u['output_tokens'],u['cache_write_tokens'])))
                    from wb_arms.reservations import usage_details
                    studio.ledger.settle(request_id,actual,usage=usage_details(u),
                                         outcome='error' if result.get('incomplete') else 'completed');spent+=actual
                    settled = True
                    genesis.event(identity,'usage',usage=u,cost_usd=str(actual),finish_reason=result.get('finish_reason'))
                    if result.get('incomplete'): raise ValueError('Provider stopped without completing its response')
                    return self.reply(200,response_events(result,body.get('model',provider.model_id)),'text/event-stream')
            except Exception as exc:
                if dispatched and not settled:
                    studio.ledger.settle(request_id,None,outcome='error')
                # Do not expose SDK errors, request bodies, credentials or arbitrary provider text; the lab's own refusals are shown in full.
                frames=traceback.extract_tb(exc.__traceback__)
                location=Path(frames[-1].filename).name+':'+str(frames[-1].lineno) if frames else None
                if isinstance(exc,BudgetExceeded): last_reason=f"The ledger refused the request ({exc}): ${maximum-spent:.2f} left of the turn's ${maximum:.2f}."
                elif isinstance(exc,GenesisRefused) or str(exc) in ('Provider stopped without completing its response','No provider usage receipt','Provider usage could not be verified','No terminal provider receipt'): last_reason=str(exc)
                else: last_reason='Inspect the provider receipt and routing configuration'
                genesis.event(identity,'request_error',message='Request stopped. Any uncertain charge remains reserved.',error_type=type(exc).__name__,location=location,reason=last_reason)
                return self.reply(400,{'error':{'message':'Genesis request stopped; inspect the recorded event.','type':'request_failed'}})
    server=ThreadingHTTPServer(('127.0.0.1',0),Broker)
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    folder=genesis.root/'sessions'/identity;folder.mkdir(parents=True,exist_ok=True)
    (folder/'codex').mkdir(exist_ok=True)
    prompt=build_prompt(genesis,turn)
    (folder/'prompt.txt').write_text(prompt,encoding='utf8')
    env={k:v for k,v in os.environ.items() if k.upper() in ('SYSTEMROOT','WINDIR','PATH','PATHEXT','TEMP','TMP','COMSPEC','APPDATA','LOCALAPPDATA','USERPROFILE')}
    env.update(CODEX_HOME=str(folder/'codex'),GENESIS_BROKER='http://127.0.0.1:'+str(server.server_port),GENESIS_TOKEN=token,GENESIS_ACTIONS=','.join(genesis_plugins.actions()))
    cmd=[codex_binary(),'exec','--json','--ephemeral','--skip-git-repo-check','--ignore-user-config','--ignore-rules','--sandbox','read-only','-C',str(folder),'-m','genesis-scientist']
    config={'model_provider':'genesis','model_providers.genesis.name':'Genesis model broker','model_providers.genesis.base_url':env['GENESIS_BROKER']+'/v1','model_providers.genesis.env_key':'GENESIS_TOKEN','model_providers.genesis.wire_api':'responses','model_providers.genesis.request_max_retries':0,'model_providers.genesis.stream_max_retries':0,'model_reasoning_effort':('high' if turn.get('effort')=='max' else turn.get('effort')) if turn.get('effort') not in (None,'default') else 'medium','features.shell_tool':False,'features.code_mode_host':False,'features.code_mode':False,'features.skip_host_skill_discovery':True,'features.plugins':False,'features.content_item_kinds':False,'features.multi_agent':False,'features.view_image':False,'skills.include_instructions':False,'project_doc_max_bytes':0,'mcp_servers.lab.tools.lab_action.approval_mode':'approve','web_search':'disabled','mcp_servers.lab.command':sys.executable,'mcp_servers.lab.args':[str(Path(__file__).with_name('genesis_mcp.py'))],'mcp_servers.lab.env_vars':['GENESIS_BROKER','GENESIS_TOKEN','GENESIS_ACTIONS']}
    for key,value in config.items(): cmd+=['-c',key+'='+json.dumps(value)]
    cmd+=['-']
    process=None
    try:
        genesis.event(identity,'harness_started',harness='Codex',model=provider.model_id)
        process=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf8',env=env,cwd=folder,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        genesis.active[identity]=process
        # communicate drains both pipes and bounds the scientist turn; public deltas arrive through the broker.
        stdout,stderr=process.communicate(prompt,timeout=600)
        if process.returncode: raise RuntimeError('Codex stopped before completing its turn')
        genesis.event(identity,'completed',message='Genesis finished this turn.')
        memory=getattr(genesis,'memory',None)
        if memory:
            from wb_studio.memory import tags
            try: memory.touch(tags(genesis.read('turns',identity)['answer']))
            except Exception: pass  # citation bookkeeping never fails a finished turn
    except Exception as exc:
        if process and process.poll() is None: process.kill();process.communicate()
        genesis.event(identity,'failed',message='Genesis could not complete this turn. No experiment was launched.',error_type=type(exc).__name__,**({'reason':last_reason} if last_reason else {}))
    finally:
        genesis.active.pop(identity,None);server.shutdown();server.server_close();studio.ledger.finish_run(scope)
