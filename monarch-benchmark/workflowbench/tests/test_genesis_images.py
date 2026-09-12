"""Images reach the model, and do not wreck the ledger (feature 023 §5.2).

An image is billed by tile, not by the length of its base64. Left in the character estimate, one
screenshot would reserve a turn's whole allowance and refuse itself, so the estimate counts images
separately. No provider is contacted here: only the message each adapter builds is checked."""
import base64
import json
from types import SimpleNamespace

import pytest

from wb_arms import api_loop
from wb_studio import genesis_harness

PNG = base64.b64decode(  # the smallest valid PNG, so the bytes are real
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')


@pytest.fixture
def shot(tmp_path):
    path = tmp_path / 'runs-light.png'
    path.write_bytes(PNG)
    return path


def test_images_of_reads_paths_and_bytes_and_skips_what_it_cannot(shot, tmp_path):
    kind, data = api_loop.images_of([shot])[0]
    assert kind == 'image/png' and base64.b64decode(data) == PNG
    assert api_loop.images_of([PNG])[0][0] == 'image/png'                 # bytes straight through
    assert api_loop.images_of([tmp_path / 'shot.jpg'])== []               # missing: left out, never raised
    (tmp_path / 'shot.jpg').write_bytes(PNG)
    assert api_loop.images_of([tmp_path / 'shot.jpg'])[0][0] == 'image/jpeg'
    assert api_loop.images_of(None) == []


def test_a_turn_without_images_is_the_message_it_always_was(shot):
    for cls in (api_loop._OpenAIAdapter, api_loop._OpenAIResponsesAdapter, api_loop._AnthropicAdapter):
        messages = cls.start(SimpleNamespace(), 'system', 'brief')
        assert messages[-1] == {'role': 'user', 'content': 'brief'}


def test_each_adapter_puts_the_image_in_the_shape_its_provider_reads(shot):
    chat = api_loop._OpenAIAdapter.start(SimpleNamespace(), 'system', 'brief', [shot])
    assert chat[0]['role'] == 'system'
    assert chat[1]['content'][0] == {'type': 'text', 'text': 'brief'}
    assert chat[1]['content'][1]['image_url']['url'].startswith('data:image/png;base64,')

    responses = api_loop._OpenAIResponsesAdapter.start(SimpleNamespace(), 'system', 'brief', [shot])
    assert responses[0]['content'][0]['type'] == 'input_text'
    assert responses[0]['content'][1]['type'] == 'input_image'
    assert responses[0]['content'][1]['image_url'].startswith('data:image/png;base64,')

    anthropic = api_loop._AnthropicAdapter.start(SimpleNamespace(), 'system', 'brief', [shot])
    block = anthropic[0]['content'][1]
    assert block['type'] == 'image' and block['source'] == {
        'type': 'base64', 'media_type': 'image/png', 'data': base64.b64encode(PNG).decode('ascii')}

    made = []
    fake = SimpleNamespace(config=SimpleNamespace(system_instruction=None), types=SimpleNamespace(
        Part=SimpleNamespace(from_bytes=lambda data, mime_type: made.append((mime_type, data)) or 'part'),
        Content=lambda role, parts: {'role': role, 'parts': parts}))
    fake.types.Part = type('P', (), {'__new__': lambda cls, text=None: 'text-part',
                                     'from_bytes': staticmethod(lambda data, mime_type: made.append((mime_type, data)) or 'image-part')})
    contents = api_loop._GeminiAdapter.start(fake, 'system', 'brief', [shot])
    assert contents[0]['parts'] == ['text-part', 'image-part'] and made == [('image/png', PNG)]
    assert fake.config.system_instruction == 'system'


def test_a_screenshot_is_counted_as_tiles_not_as_characters():
    """The regression this guards: 200 KB of base64 in the estimate is ~135,000 'tokens'."""
    big = base64.b64encode(b'\x89PNG' + b'x' * 200_000).decode('ascii')
    body = json.dumps([{'role': 'user', 'content': [{'type': 'text', 'text': 'brief'},
                                                    {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + big}}]}])
    stripped = genesis_harness.IMAGE_DATA.sub('', body)
    assert len(stripped) < 300 and 'brief' in stripped
    without = (len('system') + len(stripped) + len('[]')) // 2 + 1024
    assert without + 1 * genesis_harness.IMAGE_TOKENS < len(body) // 10   # tiles, not characters
    assert genesis_harness.IMAGE_DATA.sub('', 'a short word') == 'a short word'


def test_the_turn_record_carries_the_paths_and_the_harness_hands_them_to_the_adapter(shot, tmp_path, monkeypatch):
    """`Genesis.chat` keeps at most eight paths on the turn, and `start_turn` gives them to `start`."""
    from unittest.mock import Mock
    from wb_orchestrator.budget import BudgetLedger
    from wb_studio.genesis import Genesis
    (tmp_path / 'genesis').mkdir(exist_ok=True)
    monkeypatch.setattr('wb_studio.genesis_harness.model_routes', lambda: [{'id': 'glm-5.3', 'available': True}])
    really_start = genesis_harness.start_turn                 # `chat` looks this up on the module, so keep the real one
    monkeypatch.setattr('wb_studio.genesis_harness.start_turn', lambda *a, **k: None)   # nothing is dispatched
    studio = SimpleNamespace(directory=tmp_path, jobs=Mock(return_value=[]), events=Mock(return_value=[]),
                             job=Mock(), create=Mock(), budget=Mock(return_value={}),
                             ledger=BudgetLedger(tmp_path / 'budget.sqlite3'))
    genesis = Genesis(studio)
    turn = genesis.chat({'message': 'look at this', 'model': 'glm-5.3', 'maximum_usd': '1.00',
                         'purpose': 'Genesis critic', 'images': [shot] * 12})
    assert genesis.read('turns', turn['id'])['images'] == [str(shot)] * 8      # capped, and stored as paths
    assert genesis.chat({'message': 'no pictures', 'model': 'glm-5.3', 'maximum_usd': '1.00',
                         'purpose': 'Genesis critic'})['images'] == []

    # The harness hands whatever the turn carries to the adapter, and nothing else.
    given = {}
    monkeypatch.setattr(genesis_harness, 'ADAPTERS', {'openai': lambda *a, **k: SimpleNamespace(
        start=lambda system, brief, images=None: given.setdefault('images', images) or [])})
    really_start(genesis, genesis.read('turns', turn['id']))   # stops at the first request; never raises out
    assert given.get('images') == [str(shot)] * 8
