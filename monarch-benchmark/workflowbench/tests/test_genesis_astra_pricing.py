"""Astra standard and long-context receipts must match request reservations."""
from dataclasses import replace
from decimal import Decimal
import pytest
from wb_arms import providers
from wb_studio.gateways import ceiling_cost
from wb_studio.genesis_harness import request_bounds

@pytest.mark.parametrize('tokens,multiplier', [(272000,1), (272001,2)])
def test_astra_receipt_prices_full_input_and_output_tier(tokens,multiplier):
    p=providers.get('gpt-6-astra')
    actual=providers.cost_usd(p,tokens,1000,2000,500)
    expected=((tokens-1500)*10*multiplier + 1000*1*multiplier + 500*12.5*multiplier + 2000*50*(1 if multiplier==1 else 1.5))/1e6
    assert actual == pytest.approx(expected)
    assert ceiling_cost(p,tokens,2000) >= Decimal(str(actual))


def test_astra_long_context_request_bounds_reserve_the_correct_tier():
    p=providers.get('gpt-6-astra')
    cap,thinking,ceiling=request_bounds(p,272001,Decimal('7'))
    assert thinking == 0
    assert ceiling == ceiling_cost(p,272001,cap)
    assert ceiling <= Decimal('7')
    assert cap < 16000


def test_other_models_keep_their_existing_prices():
    p=providers.get('gpt-5.6-sol')
    assert providers.cost_usd(p,300000,1000,2000)==pytest.approx((299000*4+1000*.4+2000*20)/1e6)
