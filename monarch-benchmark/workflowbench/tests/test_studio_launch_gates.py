"""What the Studio must record and bound before it spends (feature 024, FR-007, FR-008).

Two holes, both on the most expensive button in the product:

- `POST /api/jobs` went straight to `Studio.create`, which accepts up to 800 tasks and
  12 competitors at up to the whole weekly ceiling, and built a settings dict with no
  operator in it. Decision D5 says every paid launch names the person launching it and
  that an agent never approves its own round; neither was in the code.
- `Studio._execute` passed no run config, so `attempt_cap_usd` stayed None and every arm
  was handed the whole run ceiling as its scope limit. One attempt stuck in a tool loop
  on task 1 of 50 could spend the lot before task 2 started.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from wb_studio.app import ROOT, Studio, attempt_cap_for
from wb_world.episode import load_suite


@pytest.fixture
def studio(tmp_path):
    return Studio(tmp_path / 'studio', tasks=load_suite(ROOT / 'tasks')[:2],
                  gateway_factory=lambda *a, **k: pytest.fail('paid dispatch'))


def payload(studio, **changes):
    return {'models': ['oracle', 'sloppy'], 'tasks': list(studio.tasks),
            'maximum_usd': '10.00', 'title': 'A run', **changes}


# --- FR-007: a launch names a person ---------------------------------------------------

def test_a_launch_records_the_operator(studio, monkeypatch):
    monkeypatch.setenv('WB_OPERATOR', 'lucas')
    job = studio.create(payload(studio), start=False)
    assert job['settings']['operator'] == 'lucas'


def test_an_explicit_operator_on_the_payload_wins(studio, monkeypatch):
    monkeypatch.setenv('WB_OPERATOR', 'lucas')
    job = studio.create(payload(studio, operator='carlos'), start=False)
    assert job['settings']['operator'] == 'carlos'


def test_an_agent_may_not_name_itself_as_the_operator(studio, monkeypatch):
    """D5: an agent never approves its own round. A launch Genesis makes is attributed
    to Genesis and stays attributable; it may not present itself as a person."""
    monkeypatch.delenv('WB_OPERATOR', raising=False)
    for name in ('human:genesis', 'human:studio', 'Human:Genesis'):
        with pytest.raises(ValueError, match='person'):
            studio.create(payload(studio, operator=name), start=False)


def test_a_paid_launch_without_any_operator_is_refused(studio, monkeypatch):
    monkeypatch.delenv('WB_OPERATOR', raising=False)
    monkeypatch.setenv('GEMINI_API_KEY', 'k')   # else the keyless refusal comes first, as it should
    with pytest.raises(ValueError, match='names the person'):
        studio.create(payload(studio, models=['gemini-3.7-flash']), start=False)


def test_a_scripted_run_needs_no_operator(studio, monkeypatch):
    """The answer key and the sloppy check cost nothing, so they are not a paid launch."""
    monkeypatch.delenv('WB_OPERATOR', raising=False)
    job = studio.create(payload(studio), start=False)
    assert job['settings'].get('operator') in (None, '')


# --- FR-008: no attempt may spend the whole run ----------------------------------------

def test_a_many_attempt_run_bounds_one_attempt_well_below_the_ceiling():
    assert attempt_cap_for(Decimal('10.00'), attempts=50) < Decimal('10.00')


def test_a_run_of_a_few_attempts_cannot_bound_one_below_what_it_costs():
    """A three-attempt round sized for three expensive requests has nothing to cut.
    Capping under one request's price refuses every attempt instead of limiting it."""
    assert attempt_cap_for(Decimal('3.00'), attempts=3) == Decimal('3.00')
    assert attempt_cap_for(Decimal('10.00'), attempts=1) == Decimal('10.00')


def test_the_cap_never_falls_below_what_one_request_reserves():
    assert attempt_cap_for(Decimal('10.00'), attempts=50, floor=Decimal('2.00')) == Decimal('2.00')


def test_the_cap_scales_with_how_many_attempts_share_the_run():
    many = attempt_cap_for(Decimal('100.00'), attempts=100)
    fewer = attempt_cap_for(Decimal('100.00'), attempts=20)
    assert many < fewer < Decimal('100.00')
    # below about four attempts the share passes the ceiling and the cap is the ceiling
    assert attempt_cap_for(Decimal('100.00'), attempts=2) == Decimal('100.00')


def test_a_tiny_run_still_gets_a_usable_cap():
    """A cap below what one request reserves would refuse every attempt."""
    assert attempt_cap_for(Decimal('0.10'), attempts=50) > 0


def test_an_explicit_cap_is_respected_when_it_fits(studio, monkeypatch):
    monkeypatch.setenv('WB_OPERATOR', 'lucas')
    job = studio.create(payload(studio, attempt_cap_usd='0.25'), start=False)
    assert job['settings']['attempt_cap_usd'] == '0.25'


def test_an_explicit_cap_above_the_run_ceiling_is_refused(studio, monkeypatch):
    monkeypatch.setenv('WB_OPERATOR', 'lucas')
    with pytest.raises(ValueError, match='cap'):
        studio.create(payload(studio, maximum_usd='1.00', attempt_cap_usd='2.00'), start=False)


def test_every_run_carries_a_cap_even_when_nobody_asked(studio, monkeypatch):
    monkeypatch.setenv('WB_OPERATOR', 'lucas')
    job = studio.create(payload(studio), start=False)
    cap = Decimal(job['settings']['attempt_cap_usd'])
    assert 0 < cap <= Decimal(job['settings']['maximum_usd'])


# --- T034: the cap is what actually reaches the arms -----------------------------------

def test_the_arm_is_bounded_by_the_attempt_cap_not_the_run_ceiling(studio, monkeypatch):
    monkeypatch.setenv('WB_OPERATOR', 'lucas')
    job = studio.create(payload(studio, maximum_usd='10.00', attempt_cap_usd='0.25'), start=False)
    arm = studio._arm(job, job['settings']['arms'][0], list(studio.tasks)[0], None)
    assert arm.maximum == Decimal('0.25')


def test_a_run_recorded_before_the_cap_existed_still_runs(studio, monkeypatch):
    """Older jobs carry no attempt_cap_usd; they fall back to what they ran under."""
    monkeypatch.setenv('WB_OPERATOR', 'lucas')
    job = studio.create(payload(studio, maximum_usd='10.00'), start=False)
    del job['settings']['attempt_cap_usd']
    arm = studio._arm(job, job['settings']['arms'][0], list(studio.tasks)[0], None)
    assert arm.maximum == Decimal('10.00')
