"""Compact native indexes preserve metadata, signal previews and retain exact records."""
import hashlib
import json

import pytest

from wb_studio.report_trace import project, line_page


def test_catalogue_preview_is_explicit_and_every_metadata_field_survives():
    raw = {'kind': 'tool', 'sequence': 0, 'tool': 'api_search', 'status': 'completed',
           'arguments': {'query': 'invoice fields'}, 'result': {'catalogue': 'A' * 100000, 'tail': 'retained-end'}}
    native = {'source': 'events.jsonl', 'sha256': 'original-file-hash', 'events': [{'line': 4, 'record': raw}]}
    index = project(native)
    event = index['events'][0]
    assert event['line'] == 4 and event['record'] == {k: v for k, v in raw.items() if k != 'result'}
    assert not event['result_preview']['complete'] and len(event['result_preview']['text']) == 96
    assert event['result_preview']['characters'] > 100000
    assert not event['full_read_required']
    assert index['sha256'] == native['sha256']
    fragments, offset = [], 0
    while offset is not None:
        page = line_page(native, 4, offset)
        fragments.append(page['fragment']); offset = page['next_after']
    serialized = ''.join(fragments)
    assert json.loads(serialized) == raw
    assert hashlib.sha256(serialized.encode()).hexdigest() == page['record_sha256']
    assert 'retained-end' in serialized


@pytest.mark.parametrize('tool,status', [('api_fetch', 'completed'), ('api_search', 'error'), ('base64_encode', 'completed')])
def test_large_non_catalogue_responses_and_errors_require_full_line_reads(tool, status):
    native = {'events': [{'line': 1, 'record': {'tool': tool, 'status': status, 'result': {'body': 'x' * 5000}}}]}
    event = project(native)['events'][0]
    assert event['full_read_required'] and not event['result_preview']['complete']


def test_small_responses_are_complete_and_foreign_lines_are_rejected():
    native = {'events': [{'line': 2, 'record': {'tool': 'api_fetch', 'result': {'id': 'record-3'}}}]}
    event = project(native)['events'][0]
    assert event['result_preview']['complete']
    assert json.loads(event['result_preview']['text']) == {'id': 'record-3'}
    assert not event['full_read_required']
    with pytest.raises(ValueError, match='exact attempt'):
        line_page(native, 1)
