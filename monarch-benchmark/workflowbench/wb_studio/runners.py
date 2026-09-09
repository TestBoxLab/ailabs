"""Read-only runner catalogs; configuration is distinct from execution readiness."""
import json
import os
import re
from urllib.parse import urlencode
from urllib.request import Request,build_opener,HTTPRedirectHandler
from datetime import datetime,timezone
from wb_results.evidence import write_json

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def runner_config(value):
    if not isinstance(value,dict) or value.get('provider') not in ('anthropic','openai','fireworks','gemini','moonshot','zai','claude-code','codex','bedrock'):
        raise ValueError('Choose an API control (Anthropic, OpenAI, Fireworks, Gemini, Moonshot, Z.ai), a native harness (Claude Code, Codex), or a Bedrock model for Monarch Enterprise')
    model=value.get('model','');effort=value.get('effort','default')
    if not isinstance(model,str) or not model.strip() or len(model)>200 or any(ord(c)<32 for c in model):raise ValueError('A model identifier is required')
    if effort not in ('default','none','low','medium','high','xhigh','max'):raise ValueError('Unsupported reasoning level')
    return {'provider':value['provider'],'model':model.strip(),'effort':effort}

def fireworks_catalog(studio,refresh=False,transport=None):
    cache=studio.directory/'fireworks-models.json'
    if not refresh and cache.exists():return json.loads(cache.read_text(encoding='utf-8'))
    key=os.getenv('FIREWORKS_API_KEY','').strip()
    if not key and transport is None:
        return {'models':[],'status':'credentials_required','message':'Add FIREWORKS_API_KEY to .env to load the complete Fireworks catalog.','complete':False}
    def fetch(account,token):
        query={'pageSize':200}
        if token:query['pageToken']=token
        req=Request('https://api.fireworks.ai/v1/accounts/'+account+'/models?'+urlencode(query),headers={'Authorization':'Bearer '+key})
        with build_opener(NoRedirect()).open(req,timeout=20) as response:return json.loads(response.read(16*1024*1024))
    fetch=transport or fetch
    accounts=['fireworks'];own=os.getenv('FIREWORKS_ACCOUNT_ID','').strip()
    if own and own!='fireworks':
        if not re.fullmatch('[a-zA-Z0-9_-]+',own):raise ValueError('Invalid Fireworks account ID')
        accounts.append(own)
    models={}
    try:
        for account in accounts:
            token='';seen=set()
            while True:
                page=fetch(account,token)
                for m in page.get('models',[]):
                    name=m.get('name')
                    if not isinstance(name,str):continue
                    models[name]={'id':name,'name':m.get('displayName') or name.rsplit('/',1)[-1],
                                  'serverless':bool(m.get('supportsServerless',m.get('baseModelDetails',{}).get('supportsServerless',False))),
                                  'kind':m.get('kind',''),'state':m.get('state','')}
                token=page.get('nextPageToken','')
                if not token:break
                if token in seen:raise ValueError('Repeated pagination cursor')
                seen.add(token)
        data={'models':sorted(models.values(),key=lambda m:m['name'].lower()),'status':'loaded','complete':True,'fetched_at':datetime.now(timezone.utc).isoformat(),
              'message':'All returned models are listed. Catalog membership does not guarantee inference or tool support.'}
        write_json(cache,data);return data
    except Exception:
        # Never disclose provider response bodies or authentication headers.
        return {'models':[],'status':'unavailable','complete':False,'message':'Fireworks catalog could not be refreshed. Check credentials and account access; no models were inferred.'}
