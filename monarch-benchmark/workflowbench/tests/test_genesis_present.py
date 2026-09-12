"""Presentation receipts stay typed, bounded and replayable in the existing stream."""
import json

import pytest

from wb_studio import genesis_plugins
from tests.test_genesis_loop import genesis, turn_record, FakeAdapter, harness


def payload(**changes):
    return {'card_id': 'history-audit', 'template': 'research',
            'title': 'Read previous architectures', **changes}


def present(**changes):
    found, receipt = genesis_plugins.dispatch(None, 'present', payload(**changes))
    assert found, 'The presentation tool must be callable through Genesis plugins.'
    return receipt


def test_receipt_keeps_sources_and_routes_and_replaces_by_stable_id():
    first = present(detail='Checking stored failures.',
                    sources=[{'label': 'Earlier diagnostic', 'ref': 'run-20260910-155059:event:4'}],
                    items=[{'label': 'Scope', 'value': 'Frozen tier tasks'}], route='#runs')
    second = present(status='complete', detail='Audit notes saved.')
    assert first == {'presentation': True, **payload(), 'status': 'active',
                     'detail': 'Checking stored failures.',
                     'sources': [{'label': 'Earlier diagnostic', 'ref': 'run-20260910-155059:event:4'}],
                     'items': [{'label': 'Scope', 'value': 'Frozen tier tasks'}],
                     'route': '#runs', 'label': 'Open runs'}
    assert second['card_id'] == first['card_id']
    assert second['status'] == 'complete'
    assert second['items'] == [] and second['sources'] == [] and 'route' not in second


@pytest.mark.parametrize('changes', [
    {'route': 'javascript:alert(1)'}, {'route': '#run/../secrets'},
    {'template': 'raw_html'}, {'status': 'won'}, {'card_id': '../../x'},
    {'html': '<script>alert(1)</script>'}, {'items': [{'label': 'x', 'value': {}}]},
    {'sources': [{'label': 'x', 'ref': 'file:1', 'html': 'x'}]},
    {'title': ''}, {'detail': 'x' * 1201}, {'sources': 'not a list'},
    {'items': [{'label': 'x', 'value': 'y'}] * 7},
])
def test_invalid_presentations_are_refused_without_receipts(changes):
    result = present(**changes)
    assert 'error' in result and 'presentation' not in result


def test_serialized_receipt_survives_event_detail_with_unicode_and_escaping():
    from wb_studio.genesis_harness import DETAIL_CHARS, summary
    receipt = present(detail='Looking at 東京 source paths and quoted "facts".',
                      sources=[{'label': 'Source', 'ref': 'docs/history.md:12'}])
    encoded = json.dumps(receipt, ensure_ascii=False)
    assert json.loads(summary(encoded, DETAIL_CHARS)) == receipt
    # Backslash-heavy text expands when encoded; per-field limits alone are insufficient.
    too_large = present(detail='\\' * 1200,
                        items=[{'label': 'a' * 80, 'value': '\\' * 240}] * 6,
                        sources=[{'label': 's' * 100, 'ref': '\\' * 240}] * 6)
    assert 'error' in too_large and 'presentation' not in too_large


def test_tool_schema_advertises_only_supported_templates():
    from wb_studio.genesis_schemas import tool_defs
    definition, = tool_defs(['present'])
    schema = definition['parameters']
    assert schema['required'] == ['card_id', 'template', 'title']
    assert schema['properties']['template']['enum'] == [
        'research', 'thinking', 'architecture', 'configuration', 'execution', 'result', 'warning']
    assert schema['additionalProperties'] is False


def test_harness_persists_card_updates_and_redacts_credentials(genesis):
    FakeAdapter.script = [
        {'tool_calls': [{'id': 'p1', 'name': 'present', 'args': payload(
            detail='Reading stored evidence.', sources=[{'label': 'History', 'ref': 'docs/history.md:12'}])}]},
        {'tool_calls': [{'id': 'p2', 'name': 'present', 'args': payload(
            template='warning', status='blocked', detail='Missing credential sk-example1234; work is blocked.')}]},
        {'text': 'Waiting for the missing prerequisite.'}]
    harness.start_turn(genesis, turn_record(genesis))
    saved = genesis.read('turns', 't1')
    events = [event for event in saved['events']
              if event['type'] == 'tool_completed' and event['action'] == 'present']
    cards = [json.loads(event['detail']) for event in events]
    assert [card['card_id'] for card in cards] == ['history-audit', 'history-audit']
    assert [card['status'] for card in cards] == ['active', 'blocked']
    assert cards[0]['sources'] == [{'label': 'History', 'ref': 'docs/history.md:12'}]
    assert cards[1]['detail'] == 'Missing credential [redacted]; work is blocked.'
    assert saved['status'] == 'completed'
    assert 'sk-example1234' not in json.dumps(saved)
    genesis.studio.create.assert_not_called()


def test_redaction_expansion_is_counted_before_the_receipt_is_accepted():
    receipt = present(detail='Credential sk-abcd is missing.')
    assert receipt['detail'] == 'Credential [redacted] is missing.'
    assert 'error' in present(detail='sk-abcd ' * 150)
