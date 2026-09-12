"""Genesis must not be able to fetch the inside of the network it runs in.

Feature 024, FR-009. `fetch_source` validated only `https?://\S{1,2000}` — no host
allowlist, no private-range check, no redirect limit — and is reachable both from
`POST /api/genesis/drop` and from the model's own tools. The Studio runs on Railway
inside a private network with a metadata endpoint and sibling services, and the fetched
body is stored as a library record and rendered back in the interface. Dropping
`http://169.254.169.254/latest/meta-data/` therefore read cloud credentials into a page.

The check is on the resolved address, not the hostname, so a public name that resolves
to a private address is refused too.
"""
from __future__ import annotations

import pytest

from wb_studio.genesis_ingest import fetch_source, is_public_address

PRIVATE = [
    'http://169.254.169.254/latest/meta-data/',           # cloud metadata
    'http://127.0.0.1:9105/openapi/index.json',           # the attempt's own shim
    'http://localhost:8765/api/state',                    # the Studio itself
    'http://10.0.0.1/',                                   # private range
    'http://192.168.1.1/admin',
    'http://172.16.0.5/',
    'http://[::1]/',                                      # loopback, v6
    'http://[fd00::1]/',                                  # unique local, v6
    'http://0.0.0.0/',
]


@pytest.mark.parametrize('url', PRIVATE)
def test_a_private_address_is_refused_and_nothing_is_fetched(url, monkeypatch):
    monkeypatch.setattr('wb_studio.genesis_ingest._read',
                        lambda *a, **k: pytest.fail('a refused address was fetched anyway'))
    with pytest.raises(ValueError, match='not reachable|public'):
        fetch_source(url)


def test_a_name_that_resolves_to_a_private_address_is_refused(monkeypatch):
    """The check is on the address, not the spelling: DNS rebinding names look public."""
    monkeypatch.setattr('wb_studio.genesis_ingest._resolve', lambda host: ['127.0.0.1'])
    monkeypatch.setattr('wb_studio.genesis_ingest._read',
                        lambda *a, **k: pytest.fail('a refused address was fetched anyway'))
    with pytest.raises(ValueError, match='not reachable|public'):
        fetch_source('http://looks-fine.example.com/paper')


def test_a_public_address_is_still_fetched(monkeypatch):
    monkeypatch.setattr('wb_studio.genesis_ingest._resolve', lambda host: ['93.184.216.34'])
    monkeypatch.setattr('wb_studio.genesis_ingest._read',
                        lambda url, timeout=20: '<title>A paper</title><p>Body text.</p>')
    out = fetch_source('http://example.com/paper')
    assert out['title'] == 'A paper' and 'Body text.' in out['text']


def test_a_host_that_does_not_resolve_is_refused_rather_than_attempted(monkeypatch):
    monkeypatch.setattr('wb_studio.genesis_ingest._resolve', lambda host: [])
    monkeypatch.setattr('wb_studio.genesis_ingest._read',
                        lambda *a, **k: pytest.fail('an unresolvable host was fetched anyway'))
    with pytest.raises(ValueError):
        fetch_source('http://nope.invalid/x')


def test_the_scheme_is_still_checked_first():
    for url in ('file:///etc/passwd', 'ftp://example.com/x', 'gopher://example.com'):
        with pytest.raises(ValueError, match='http'):
            fetch_source(url)


@pytest.mark.parametrize('address,public', [
    ('93.184.216.34', True), ('8.8.8.8', True),
    ('127.0.0.1', False), ('169.254.169.254', False), ('10.1.2.3', False),
    ('192.168.0.1', False), ('172.20.0.1', False), ('0.0.0.0', False),
    ('::1', False), ('fd00::1', False), ('2606:2800:220:1:248:1893:25c8:1946', True),
])
def test_is_public_address(address, public):
    assert is_public_address(address) is public
