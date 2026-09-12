"""Bounded editorial index; complete attempt analyses remain the publication source."""
from wb_studio.report_batches import digest

LIMITS = {'explanation': 120, 'mechanism': 100, 'alternatives': 80, 'missing_evidence': 80}
IDENTITY = ('index', 'task', 'model', 'passed', 'confidence', 'event_ids')


def patterns(source):
    def setups(columns):
        return [{k: column[k] for k in ('id', 'name', 'total', 'historical') if k in column} |
            {kind: [{k: s[k] for k in ('id', 'label', 'count', 'percent')} for s in column[kind] if s['count']]
             for kind in ('behavior', 'checks')} for column in columns]
    return {k: source[k] for k in ('denominator', 'behavior_basis', 'checks_basis') if k in source} | {
        'setups': setups(source.get('setups', [])),
        'domains': [{k: domain[k] for k in ('id', 'label', 'total') if k in domain} |
                    {'setups': setups(domain['setups'])} for domain in source.get('domains', [])]}


def packet(rows, capture):
    columns = [*IDENTITY, *LIMITS, 'clipped_fields']
    records = []
    for key in sorted(rows, key=int):
        row = rows[key]
        clipped = [name for name, limit in LIMITS.items() if len(row[name]) > limit]
        records.append([*[row[k] for k in IDENTITY],
                        *[row[k][:limit] for k, limit in LIMITS.items()], clipped])
    return {'columns': columns, 'rows': records, 'attempt_count': len(rows),
        'full_analysis_sha256': digest(rows), 'patterns': patterns(capture.get('patterns', {})),
        'note': 'Every attempt appears once. clipped_fields explicitly names incomplete excerpts; they are an index, not complete support for a claim. '
            'Read full rows with read_report_draft(indexes=[...],include_draft=false) before citing them. '
            'Full expected, observed and all explanation fields remain in the published detailed analysis.'}


def cited_indexes(draft, capture):
    ids = {event for finding in (draft or {}).get('findings', []) for event in finding.get('event_ids', [])}
    return [i for i, row in enumerate(capture['checked']['attempts']) if ids.intersection(row['event_ids'])]
