"""Offline first-request admission check for every reserved report worker.

This floor catches a cycle that cannot even start one of its stages. It is not
an estimate of completing the analysis: evidence size and subsequent requests
still consume the same immutable stage budget through the native ledger gate.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_CEILING

from wb_studio import genesis_harness as harness


def validate(genesis, turns, maximum):
    """Refuse impossible stage allocations before the caller reserves any money.

``turns`` contains the exact prepared dispatch messages, including role and
batch indexes. The helper builds prompts and local provider message structures;
it never invokes ``adapter.turn``, the ledger, or ``genesis.chat``.
"""
    from wb_studio.genesis_reports import allowed_tools

    maximum = Decimal(str(maximum))
    if not maximum.is_finite() or maximum <= 0 or not turns:
        raise ValueError('Choose a positive report ceiling and at least one report stage.')
    rows, refused = {}, []
    required = Decimal('0')
    for stage, turn in turns.items():
        if not isinstance(turn.get('message'), str) or not turn['message'].strip():
            raise ValueError('Prepare the exact dispatch message before report budget preflight (' + stage + ').')
        allocated = Decimal(str(turn['maximum_usd']))
        if not allocated.is_finite() or allocated <= 0:
            raise ValueError('Every report stage needs a positive budget allocation (' + stage + ').')
        provider = harness.providers.get(turn['model'])
        system, brief = harness.build_prompt(genesis, turn)
        tools = harness.shaped(harness.tool_defs(allowed_tools(turn)), provider.adapter)
        adapter = None
        try:
            adapter = harness.ADAPTERS[provider.adapter](provider, tools, harness.REQUEST_TIMEOUT)
            messages = adapter.start(system, brief, turn.get('images'))
            body = harness.canonical_json(harness._json_messages(messages))
        except Exception as exc:
            raise ValueError('Report budget preflight could not prepare ' + stage +
                             ' (' + type(exc).__name__ + '). No provider request was sent.') from None
        finally:
            close = getattr(getattr(adapter, 'client', None), 'close', None)
            if callable(close):
                close()
        # Keep this identical to the native loop, including its conservative
        # character estimate, image allowance and cache-write price selection.
        tokens = ((len(system) + len(harness.IMAGE_DATA.sub('', body)) + len(harness.canonical_json(tools))) // 2
                  + 1024 + len(turn.get('images') or []) * harness.IMAGE_TOKENS)
        rate_in = Decimal(str(max(provider.price_in, provider.price_cache_write or 0)))
        input_cost = harness._money(Decimal(tokens) * rate_in / 1_000_000)
        floor = harness._money(input_cost + Decimal(harness.OUTPUT_FLOOR) * Decimal(str(provider.price_out)) / 1_000_000)
        # Execute the native admission arithmetic as well, so a provider's
        # thinking policy or changed floor cannot pass only the estimate.
        try:
            harness.request_bounds(provider, tokens, allocated)
        except harness.GenesisRefused:
            refused.append(stage)
        required = max(required, maximum * floor / allocated)
        rows[stage] = {'model': turn['model'], 'input_tokens': tokens,
                       'allocated_usd': str(allocated), 'first_request_minimum_usd': str(floor)}
    required = required.quantize(Decimal('.01'), rounding=ROUND_CEILING)
    if refused:
        raise ValueError('Report budget is too low for ' + ', '.join(refused) + '. With these stage allocations, '
                         'set at least $' + format(required, '.2f') + ' to admit the first request in every stage. '
                         'Full evidence analysis and later requests need additional room; this is a startup floor, '
                         'not a completion estimate. No money was reserved or provider request sent.')
    return {'minimum_ceiling_usd': str(required), 'turns': rows,
            'basis': 'Native first-request admission floor only; subsequent evidence and requests cost extra.'}
