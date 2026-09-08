"""Grader-only reference trajectories, independently transcribed from fixture requests.

These are qualification checks, never tools or input provided to a competitor.
Task contracts stay frozen; a counterexample rejects a candidate for review.
"""
import hashlib
import json

from grader.grade import grade
from wb_world.episode import Episode

SF = 'https://yourinstance.salesforce.com/services/data/v61.0/sobjects'
PENDING = {
    'sales.update_contact_phone': 'Implement HR batch verification, cancellation, duplicate-contact matching, and note reference; falsify unrelated contact-field edits permitted by broad expected_changes.',
    'support.freshdesk_auto_merge': 'Independently implement ss_merge_rules/ws_rules with same-requester restriction; falsify cross-requester merges and unrelated ticket changes.',
    'support.intercom_freshdesk_escalation': 'Independently apply ss_escalation_config, then check destinations, confirmation replies, exclusions, and untouched conversations.',
    'sales.zoom_recording_distribution': 'Independently resolve yesterday completed meetings and distribution policy; falsify wrong audiences, excluded meetings, and duplicate sends.',
    'operations.invoice_shipping_trigger': 'Independently calculate only -EXP line totals and counts; verify Monday fields and warehouse email, then falsify non-expedited inclusion.',
    'support.reamaze_cross_platform_dedup': 'Independently join customer aliases and issue identity; verify reciprocal notes, close state and log, then falsify unrelated-customer closure.',
    'hr.comp_adjustment_batch': 'Independently resolve cleared rows and current procedures; verify computed raises and employee/manager notifications, then falsify ineligible-row changes.',
}


def _run(task, actions):
    episode = Episode(task, episode_id='keyless-independent-control')
    calls = []
    for method, url, body in actions:
        response = episode.api_fetch(method, url, body=json.dumps(body) if body is not None else None)
        calls.append({'method': method, 'url': url, 'body': body, 'response': response})
    final = episode.finish()
    return {'grade': grade(task, episode.snapshot0, final), 'calls': calls,
            'snapshot0': episode.snapshot0, 'snapshot1': final,
            'snapshot_sha256': hashlib.sha256(json.dumps(final, sort_keys=True).encode()).hexdigest()}


def qualify(task):
    name = task['task']
    if name in PENDING:
        return {'status': 'pending', 'positive_control': 'pending_independent_reference',
                'collateral_control': 'pending_independent_reference', 'remaining': PENDING[name]}
    if name == 'simple.email_sf_contact_city_update':
        # Source: Lisa's msg_3004 relocation email, matched contact 003004.
        actions = [('GET', 'https://gmail.googleapis.com/gmail/v1/users/me/messages/msg_3004', None),
                   ('PATCH', f'{SF}/Contact/003004', {'MailingCity': 'Denver'})]
        collateral = ('PATCH', f'{SF}/Contact/003004', {'Phone': '+1-555-9999'})
    elif name == 'simple.sf_opp_closed_won':
        actions = [('PATCH', f'{SF}/Opportunity/006001', {'StageName': 'Closed Won'})]
        collateral = ('PATCH', f'{SF}/Opportunity/006001', {'Amount': 1})
    elif name == 'simple.invoice_airtable_slack':
        # Source: msg_3192, CloudHost invoice CH-2026-0089, $4,500.00.
        actions = [('GET', 'https://gmail.googleapis.com/gmail/v1/users/me/messages/msg_3192', None),
                   ('POST', 'https://api.airtable.com/v0/base_finance/Invoices', {'fields': {'Vendor': 'CloudHost', 'Amount': 4500}}),
                   ('POST', 'https://slack.com/api/chat.postMessage', {'channel': 'CFIN01', 'text': 'CloudHost invoice CH-2026-0089: $4,500.00'})]
        collateral = ('POST', 'https://api.airtable.com/v0/base_finance/Unrequested', {'fields': {'Unrequested': True}})
    else:
        return {'status': 'pending', 'remaining': 'No independent reference implemented'}
    positive = _run(task, actions)
    damaged = _run(task, actions + [collateral])
    result = {'positive_control': 'passed' if positive['grade']['passed'] else 'failed',
              'collateral_control': 'accepted' if damaged['grade']['passed'] else 'rejected',
              'evidence': {'positive': positive, 'collateral': damaged}}
    result['status'] = 'qualified' if positive['grade']['passed'] and not damaged['grade']['passed'] else 'rejected'
    if name == 'simple.invoice_airtable_slack':
        wrong = list(actions)
        wrong[1] = (actions[1][0], actions[1][1], {'fields': {'Vendor': 'Wrong vendor', 'Amount': 1}})
        evidence = _run(task, wrong)
        result['evidence']['wrong_invoice'] = evidence
        result['semantic_counterexample'] = 'accepted' if evidence['grade']['passed'] else 'rejected'
        if evidence['grade']['passed']:
            result['status'] = 'rejected'
            result['remaining'] = 'Frozen grader accepts wrong vendor and amount; review and approve stronger assertions before selecting this task.'
    return result


def main():
    import argparse
    from pathlib import Path
    from wb_orchestrator.prototype_campaign import ROOT, SELECTION
    from wb_world.episode import load_task_file

    parser = argparse.ArgumentParser(description='Run independent grader controls without model calls')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    results = {}
    for selections in SELECTION.values():
        for relative, _ in selections:
            task = load_task_file(ROOT / relative)
            results[task['task']] = {'task_sha256': hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), **qualify(task)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
