"""Offline public streaming and provider-continuation regression checks."""
from contextlib import nullcontext
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import openai
import pytest
from openai.types.chat import ChatCompletionChunk

from wb_arms import providers
from wb_arms.api_loop import InfraError, _OpenAIAdapter


def chunk(delta=None, finish=None, usage=None):
    return ChatCompletionChunk.model_validate({
        'id': 'offline-chunk', 'object': 'chat.completion.chunk', 'created': 1,
        'model': 'offline', 'choices': [] if delta is None else [
            {'index': 0, 'delta': delta, 'finish_reason': finish}], 'usage': usage})


def receipt(cached=31):
    value = {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120}
    if cached is not None:
        value['prompt_tokens_details'] = {'cached_tokens': cached}
    return value


@pytest.fixture
def adapter(monkeypatch):
    provider = replace(providers.get('kimi-k3'), header_fallbacks=('x-offline-cached',))
    monkeypatch.setenv(provider.key_env, 'offline-test-key')
    create = Mock()
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        with_raw_response=SimpleNamespace(create=create))))
    monkeypatch.setattr(openai, 'OpenAI', Mock(return_value=client))
    value = _OpenAIAdapter(provider, [{'type': 'function', 'function': {'name': 'catalog'}}])
    value.on_text = Mock()
    value.test_create = create
    return value


def feed(adapter, chunks, headers=None):
    adapter.test_create.return_value = SimpleNamespace(
        headers=headers or {}, parse=lambda: nullcontext(iter(chunks)))


def test_public_deltas_and_fragmented_tools_preserve_private_continuation(adapter):
    feed(adapter, [
        chunk({'role': 'assistant', 'content': 'Reading ', 'reasoning_content': 'private ',
               'tool_calls': [{'index': 0, 'id': 'call_7', 'type': 'function',
                               'function': {'name': 'cat', 'arguments': '{"query":'}}]}),
        chunk({'content': 'catalog.', 'reasoning_content': 'continuation',
               'tool_calls': [{'index': 0, 'function': {'name': 'alog', 'arguments': '"active"}'}}]}, 'tool_calls'),
        chunk(usage=receipt()),
    ])
    messages = adapter.start('system', 'request')
    result = adapter.turn(messages, timeout=17)
    assert [call.args[0] for call in adapter.on_text.call_args_list] == ['Reading ', 'catalog.']
    assert result == {'tool_calls': [{'id': 'call_7', 'name': 'catalog', 'args': {'query': 'active'}}],
                      'text': 'Reading catalog.', 'reasoning': ['private continuation'], 'stop_reason': 'tool_calls',
                      'prompt_tokens': 100, 'output_tokens': 20,
                      'cached_tokens': 31, 'cache_source': 'prompt_tokens_details.cached_tokens'}
    assert messages[-1]['reasoning_content'] == 'private continuation'
    assert messages[-1]['tool_calls'][0]['function'] == {'name': 'catalog', 'arguments': '{"query":"active"}'}
    adapter.append_tool_result(messages, result['tool_calls'][0], 'found')
    feed(adapter, [chunk({'content': 'Done'}, 'stop'), chunk(usage=receipt())])
    adapter.turn(messages)
    second_request = adapter.test_create.call_args.kwargs
    assert second_request['messages'][-3]['reasoning_content'] == 'private continuation'
    assert second_request['messages'][-2] == {'role': 'tool', 'tool_call_id': 'call_7', 'content': 'found'}
    first_request = adapter.test_create.call_args_list[0].kwargs
    assert first_request['stream'] is True
    assert first_request['stream_options'] == {'include_usage': True}
    assert first_request['timeout'] == 17


def test_stream_retains_header_cache_fallback(adapter):
    feed(adapter, [chunk({'content': 'Done'}, 'stop'), chunk(usage=receipt(None))],
         {'x-offline-cached': '23'})
    result = adapter.turn(adapter.start('system', 'request'))
    assert result['cached_tokens'] == 23
    assert result['cache_source'] == 'header:x-offline-cached'
    assert (result['prompt_tokens'], result['output_tokens']) == (100, 20)


@pytest.mark.parametrize('finish,with_usage', [('stop', False), (None, True), ('length', True), ('content_filter', True)])
def test_missing_receipt_or_incomplete_stream_is_refused(adapter, finish, with_usage):
    chunks = [chunk({'content': 'Partial'}, finish)]
    if with_usage:
        chunks.append(chunk(usage=receipt()))
    feed(adapter, chunks)
    messages = adapter.start('system', 'request')
    before = list(messages)
    with pytest.raises(InfraError, match='without a complete response and usage receipt'):
        adapter.turn(messages)
    assert messages == before
    adapter.on_text.assert_called_once_with('Partial')


def test_genesis_gemini_preserves_tool_signature_without_streaming_thoughts(monkeypatch):
    from google import genai
    from google.genai import types
    from wb_studio.genesis_provider import complete
    provider = providers.get('gemini-3.7-flash')
    signed_part = types.Part(function_call=types.FunctionCall(id='call_signed', name='catalog', args={}),
                             thought_signature=b'offline-signature')
    usage = types.GenerateContentResponseUsageMetadata(prompt_token_count=50, cached_content_token_count=5,
                                                       candidates_token_count=7, thoughts_token_count=3)
    first = types.GenerateContentResponse(candidates=[types.Candidate(
        content=types.Content(role='model', parts=[types.Part(text='Private', thought=True), signed_part]),
        finish_reason='STOP')], usage_metadata=usage)
    second = types.GenerateContentResponse(candidates=[types.Candidate(
        content=types.Content(role='model', parts=[types.Part(text='Done')]), finish_reason='STOP')], usage_metadata=usage)
    stream = Mock(side_effect=[iter([first]), iter([second])])
    monkeypatch.setattr(genai, 'Client', Mock(return_value=SimpleNamespace(models=SimpleNamespace(generate_content_stream=stream))))
    state = {}
    body = {'instructions': 'system', 'input': [{'role': 'user', 'content': 'request'}], '_provider_state': state}
    public = Mock()
    result = complete(provider, body, public)
    public.assert_not_called()
    assert result['calls'] == [{'id': 'call_signed', 'name': 'catalog', 'arguments': '{}'}]
    assert state['call_signed']['thought_signature'] == b'offline-signature'
    assert result['usage'] == {'prompt_tokens': 50, 'cached_tokens': 5, 'cache_write_tokens': 0, 'output_tokens': 10}
    body['input'] += [{'type': 'function_call', 'call_id': 'call_signed', 'name': 'catalog', 'arguments': '{}'},
                      {'type': 'function_call_output', 'call_id': 'call_signed', 'output': 'found'}]
    complete(provider, body, public)
    public.assert_called_once_with('Done')
    sent = stream.call_args.kwargs['contents']
    assert sent[1].parts[0].thought_signature == b'offline-signature'
    assert sent[1].parts[0].function_call.name == 'catalog'
    assert sent[2].parts[0].function_response.name == 'catalog'
