"""Responses-wire translation for Genesis only; benchmark harnesses are unchanged."""
import json
import time
import uuid
from wb_arms import providers


def response_inputs(body):
    messages=[]
    system=str(body.get('instructions') or '')
    for item in body.get('input',[]):
        kind=item.get('type','message')
        if kind=='message':
            content=item.get('content','')
            text=content if isinstance(content,str) else '\n'.join(c.get('text','') for c in content if c.get('type') in ('input_text','output_text','text'))
            if item.get('role') in ('system','developer'): system+='\n'+text
            else: messages.append({'role':item.get('role','user'),'content':text})
        elif kind=='function_call':
            messages.append({'role':'assistant','content':None,'tool_calls':[{'id':item['call_id'],'type':'function','function':{'name':(item['namespace']+'__' if item.get('namespace') else '')+item['name'],'arguments':item['arguments']}}]})
        elif kind=='function_call_output': messages.append({'role':'tool','tool_call_id':item['call_id'],'content':str(item.get('output',''))})
        elif kind=='reasoning': continue
        else: raise ValueError('Genesis route does not support '+str(kind)+' input')
    tools=[]
    for group in body.get('tools',[]):
        namespace=group.get('name') if group.get('type')=='namespace' else None
        for tool in group.get('tools',[]) if namespace else [group]:
            if tool.get('type')!='function': raise ValueError('Unsupported Codex tool type')
            function={k:tool[k] for k in ('name','description','parameters') if k in tool}
            if namespace: function['name']=namespace+'__'+function['name']
            tools.append({'type':'function','function':function})
    return system,messages,tools


def complete(provider,body,on_text):
    """Yield only public answer text; retain provider usage, never infer a cache hit.

    `_max_output` in the body is the output cap the broker paid for; every adapter sends it."""
    system,messages,tools=response_inputs(body)
    max_output=int(body.get('_max_output') or 16000)
    effort=(body.get('reasoning') or {}).get('effort','medium')
    calls=[];text='';usage={};finish='completed';incomplete=False
    if provider.adapter=='anthropic':
        import anthropic
        client=anthropic.Anthropic(api_key=providers.api_key(provider),max_retries=0,timeout=120)
        converted=[]
        for m in messages:
            if m['role']=='tool': value={'role':'user','content':[{'type':'tool_result','tool_use_id':m['tool_call_id'],'content':m['content']}]}
            elif m.get('tool_calls'): value={'role':'assistant','content':[{'type':'tool_use','id':c['id'],'name':c['function']['name'],'input':json.loads(c['function']['arguments'])} for c in m['tool_calls']]}
            else: value={'role':m['role'],'content':m['content'] or ''}
            if converted and converted[-1]['role']==value['role'] and isinstance(converted[-1]['content'],list) and isinstance(value['content'],list): converted[-1]['content']+=value['content']
            else: converted.append(value)
        atools=[{'name':t['function']['name'],'description':t['function'].get('description',''),'input_schema':t['function'].get('parameters',{'type':'object'})} for t in tools]
        if atools: atools[-1]['cache_control']={'type':'ephemeral'}
        with client.messages.stream(model=provider.model_id,system=[{'type':'text','text':system,'cache_control':{'type':'ephemeral'}}],messages=converted,tools=atools,max_tokens=max_output,cache_control={'type':'ephemeral'},thinking={'type':'adaptive'},output_config={'effort':effort}) as stream:
            for delta in stream.text_stream: text+=delta;on_text(delta)
            result=stream.get_final_message()
        finish=result.stop_reason;incomplete=finish not in ('end_turn','tool_use')
        for block in result.content:
            if block.type=='tool_use': calls.append({'id':block.id,'name':block.name,'arguments':json.dumps(block.input)})
        u=result.usage;cached=u.cache_read_input_tokens or 0;write=u.cache_creation_input_tokens or 0
        usage={'prompt_tokens':u.input_tokens+cached+write,'cached_tokens':cached,'cache_write_tokens':write,'output_tokens':u.output_tokens}
    elif provider.adapter=='openai_responses':
        import openai
        client=openai.OpenAI(api_key=providers.api_key(provider),max_retries=0,timeout=120)
        request={'instructions':system,'input':[], 'tools':[{'type':'function',**t['function']} for t in tools], 'reasoning':body.get('reasoning',{'effort':'medium'})}
        for m in messages:
            if m['role']=='tool': request['input'].append({'type':'function_call_output','call_id':m['tool_call_id'],'output':m['content']})
            elif m.get('tool_calls'):
                request['input'] += [{'type':'function_call','call_id':c['id'],'name':c['function']['name'],'arguments':c['function']['arguments']} for c in m['tool_calls']]
            else: request['input'].append({'role':m['role'],'content':m['content']})
        request.update(model=provider.model_id,stream=True,max_output_tokens=max_output,store=False)
        result=None
        for event in client.responses.create(**request):
            if event.type=='response.output_text.delta': text+=event.delta;on_text(event.delta)
            elif event.type in ('response.completed','response.incomplete'): result=event.response
        if result is None: raise ValueError('No terminal provider receipt')
        finish=result.status;incomplete=finish!='completed'
        for item in result.output:
            if item.type=='function_call': calls.append({'id':item.call_id,'name':item.name,'arguments':item.arguments})
        u=result.usage
        usage={'prompt_tokens':u.input_tokens,'cached_tokens':getattr(u.input_tokens_details,'cached_tokens',0) or 0,'cache_write_tokens':0,'output_tokens':u.output_tokens}
    elif provider.adapter=='gemini':
        from google import genai
        from google.genai import types
        contents=[];names={};provider_state=body.get('_provider_state',{})
        for m in messages:
            if m.get('tool_calls'):
                parts=[]
                for c in m['tool_calls']:
                    names[c['id']]=c['function']['name']
                    saved=provider_state.get(c['id'])
                    parts.append(types.Part.model_validate(saved) if saved else types.Part.from_function_call(name=c['function']['name'],args=json.loads(c['function']['arguments'])))
                contents.append(types.Content(role='model',parts=parts))
            elif m['role']=='tool': contents.append(types.Content(role='user',parts=[types.Part.from_function_response(name=names[m['tool_call_id']],response={'result':m['content']})]))
            else: contents.append(types.Content(role='model' if m['role']=='assistant' else 'user',parts=[types.Part.from_text(text=m['content'] or '')]))
        config=types.GenerateContentConfig(system_instruction=system,max_output_tokens=max_output,thinking_config=types.ThinkingConfig(thinking_level=effort),tools=[types.Tool(function_declarations=[types.FunctionDeclaration(name=t['function']['name'],description=t['function'].get('description',''),parameters_json_schema=t['function'].get('parameters',{'type':'object'})) for t in tools])] if tools else None)
        client=genai.Client(api_key=providers.api_key(provider))
        meta=None;finish=None
        for chunk in client.models.generate_content_stream(model=provider.model_id,contents=contents,config=config):
            if chunk.usage_metadata: meta=chunk.usage_metadata
            for candidate in chunk.candidates or []:
                if candidate.finish_reason: finish=str(candidate.finish_reason).split('.')[-1]
                for part in candidate.content.parts if candidate.content else []:
                    if part.text and not part.thought: text+=part.text;on_text(part.text)
                    if part.function_call:
                        call_id=part.function_call.id or 'call_'+uuid.uuid4().hex
                        provider_state[call_id]=part.model_dump()
                        calls.append({'id':call_id,'name':part.function_call.name,'arguments':json.dumps(part.function_call.args or {})})
        if meta is None: raise ValueError('No provider usage receipt')
        incomplete=finish!='STOP'
        usage={'prompt_tokens':meta.prompt_token_count,'cached_tokens':meta.cached_content_token_count or 0,'cache_write_tokens':0,'output_tokens':(meta.candidates_token_count or 0)+(meta.thoughts_token_count or 0)}
    else:
        import openai
        client=openai.OpenAI(api_key=providers.api_key(provider),base_url=provider.base_url,max_retries=0,timeout=120)
        collected={};meta=None;finish=None
        for chunk in client.chat.completions.create(model=provider.model_id,messages=[{'role':'system','content':system}]+messages,tools=tools or None,max_tokens=max_output,stream=True,stream_options={'include_usage':True}):
            if chunk.usage: meta=chunk.usage.model_dump()
            for choice in chunk.choices:
                if choice.finish_reason: finish=choice.finish_reason
                if choice.delta.content: text+=choice.delta.content;on_text(choice.delta.content)
                for call in choice.delta.tool_calls or []:
                    target=collected.setdefault(call.index,{'id':'','name':'','arguments':''})
                    if call.id: target['id']=call.id
                    if call.function and call.function.name: target['name']+=call.function.name
                    if call.function and call.function.arguments: target['arguments']+=call.function.arguments
        incomplete=finish not in ('stop','tool_calls')
        calls=list(collected.values())
        if meta is None: raise ValueError('No provider usage receipt')
        cached,_=providers.extract_cached_tokens(meta,{},provider)
        usage={'prompt_tokens':meta.get('prompt_tokens'),'cached_tokens':cached,'cache_write_tokens':0,'output_tokens':meta.get('completion_tokens')}
    return {'text':text,'calls':calls,'usage':usage,'finish_reason':finish,'incomplete':incomplete}


def response_events(result,model):
    output=[]
    if result['text']: output.append({'id':'msg_'+uuid.uuid4().hex,'type':'message','role':'assistant','status':'completed','content':[{'type':'output_text','text':result['text'],'annotations':[]}]})
    for call in result['calls']:
        item={'id':'fc_'+uuid.uuid4().hex,'type':'function_call','call_id':call['id'],'name':call['name'],'arguments':call['arguments'],'status':'completed'}
        if call['name'].startswith('mcp__lab__'):
            item.update(name=call['name'][len('mcp__lab__'):],namespace='mcp__lab')
        output.append(item)
    u=result['usage'];response={'id':'resp_'+uuid.uuid4().hex,'object':'response','created_at':int(time.time()),'model':model,'status':'completed','output':output,'usage':{'input_tokens':u['prompt_tokens'],'output_tokens':u['output_tokens'],'total_tokens':u['prompt_tokens']+u['output_tokens'],'input_tokens_details':{'cached_tokens':u['cached_tokens']}}}
    events=[{'type':'response.created','response':{**response,'status':'in_progress','output':[]}}]
    for i,item in enumerate(output):
        events.append({'type':'response.output_item.added','output_index':i,'item':{**item,'status':'in_progress'}})
        if item['type']=='message':
            part=item['content'][0]
            events += [{'type':'response.content_part.added','item_id':item['id'],'output_index':i,'content_index':0,'part':{**part,'text':''}}, {'type':'response.output_text.delta','item_id':item['id'],'output_index':i,'content_index':0,'delta':part['text']}, {'type':'response.output_text.done','item_id':item['id'],'output_index':i,'content_index':0,'text':part['text']}, {'type':'response.content_part.done','item_id':item['id'],'output_index':i,'content_index':0,'part':part}]
        else: events.append({'type':'response.function_call_arguments.done','item_id':item['id'],'output_index':i,'arguments':item['arguments']})
        events.append({'type':'response.output_item.done','output_index':i,'item':item})
    events.append({'type':'response.completed','response':response})
    return ''.join('data: '+json.dumps(e)+'\n\n' for e in events).encode()
