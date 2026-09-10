"""Genesis tools as typed function schemas, one per lab action (deep dive of 10 Sep 2026, M2).

The model used to see one tool, `lab_action(action, payload)`, with an untyped payload, and
guessed argument shapes; the failed turns of 10 Sep show thirty guesses in one turn. Here every
action has a name, a sentence and a JSON schema. An action without an entry below still reaches
the model, with a permissive schema and its name as the description, so a plugin can land
before its schema does.

`tool_defs(genesis)` returns `[{name, description, parameters}]` for every action Genesis can
perform now; `shaped(defs, adapter)` renders them the way each provider family expects.
"""
from __future__ import annotations

import json

from wb_studio.genesis_plugins import actions as plugin_actions

S = {'type': 'string'}
I = {'type': 'integer'}
N = {'type': 'number'}
B = {'type': 'boolean'}


def obj(properties: dict, required=(), extra: bool = False, **rest) -> dict:
    out = {'type': 'object', 'properties': properties, 'additionalProperties': extra, **rest}
    if required:
        out['required'] = list(required)
    return out


def arr(items: dict) -> dict:
    return {'type': 'array', 'items': items}


SETUP = obj({'kind': {'type': 'string', 'enum': ['architecture', 'bare', 'monarch']},
             'id': {**S, 'description': 'The version, model or Monarch version id from the catalog.'},
             'model': {**S, 'description': 'A model name from the catalog, when the setup takes one.'}}, ['kind', 'id'])
POPULATION = obj({'task_set': {**S, 'description': 'A saved task set id, or leave out.'},
                  'filter': obj({'tier': S, 'domain': S, 'category': S,
                                 'applications': obj({'min': I, 'max': I}),
                                 'task_ids': arr(S)})},
                 description='A task set, a filter over the catalog, or both.')
HYPOTHESIS = obj({'claim': {**S, 'description': 'One directional sentence, up to 300 characters.'},
                  'population': POPULATION,
                  'comparison': obj({'a': SETUP, 'b': SETUP}, ['a', 'b']),
                  'measure': {'type': 'string', 'enum': ['pass_rate', 'pass_k', 'cost_per_pass', 'violations', 'false_completion', 'turns']},
                  'direction': {'type': 'string', 'enum': ['a_higher', 'a_lower']},
                  'minimum_effect': {**N, 'description': 'Above 0: a fraction of pass rate, a count for violations and turns, a ratio above 1 for cost per pass.'},
                  'prior': {**N, 'description': 'Your probability that the claim holds, 0 to 1.'}},
                 ['claim', 'population', 'comparison', 'measure', 'direction', 'minimum_effect'])
LAUNCH = obj({'title': S, 'tasks': {**arr(S), 'description': 'Task ids from the catalog.'},
              'models': {**arr(S), 'description': 'API model ids to run without Monarch.'},
              'architectures': {**arr(S), 'description': 'Published architecture version ids.'},
              'bare_models': {**arr(S), 'description': 'Bare controls to show beside.'},
              'maximum_usd': {**S, 'description': 'The spending ceiling, like "1.00".'},
              'track': {'type': 'string', 'enum': ['agentic-request', 'create-and-run']},
              'concurrency': I, 'configuration': obj({}, extra=True), 'goal': obj({}, extra=True),
              'card': {**S, 'description': 'The card this plan belongs to, when it has one.'},
              'body': S, 'evidence': arr(obj({}, extra=True))}, ['tasks', 'maximum_usd'])

# name -> (sentence, parameters)
SCHEMAS = {
    # --- evidence -------------------------------------------------------------------------
    'list_runs': ('Every run with its status and per-attempt results. Large; prefer measures or read_run for one run.', obj({})),
    'read_run': ('One run: its record, a page of its events (task filter, after, limit), the Studio analysis and earlier Genesis analyses.',
                 obj({'id': {**S, 'description': 'The run id.'}, 'task': {**S, 'description': 'Only events of this task.'},
                      'after': {**I, 'description': 'Only events with an id above this; use next_after from the last page.'},
                      'limit': {**I, 'description': '1 to 500 events, default 100.'}}, ['id'])),
    'measures': ("Every measure of one run with Wilson intervals, computed by the Studio; group_by adds a tally per setup, task or category.",
                 obj({'run': S, 'group_by': {'type': 'string', 'enum': ['setup', 'task', 'category']}}, ['run'])),
    'compare': ('Paired delta, interval, sign test and solved-task overlap between a run and its Bare baseline, or between two runs.',
                obj({'run': S, 'against': {**S, 'description': 'Another run id, or "baseline" (default).'}}, ['run'])),
    'failure_buckets': ('The outcome buckets of a run with counts, denominators and one event id to read per bucket.', obj({'run': S}, ['run'])),
    'report': ('The internal run report as data, without the written narrative.', obj({'run': S}, ['run'])),
    'task_catalog': ('Tasks with tier, domain, category, hash and the applications they change; filter by task set or catalog fields.',
                     obj({'task_set': S, 'filter': POPULATION['properties']['filter']})),
    'catalog': ('Architectures, product graphs, task sets, models and the creation contracts for save_architecture and save_product_graph.', obj({})),
    'research_state': ('The whole Genesis state: cards, recent turns, threads, routes, analyses. Large; use it once, if at all.', obj({})),
    'record_analysis': ('File a cited analysis of a run so unchanged evidence is not analysed twice; each finding names event ids and is a fact or a hypothesis.',
                        obj({'run': S, 'summary': S,
                             'findings': arr(obj({'kind': {'type': 'string', 'enum': ['fact', 'hypothesis']}, 'text': S, 'event_ids': arr(I)}, ['kind', 'text', 'event_ids']))},
                            ['run', 'findings'])),
    'activity': ('The activity record: what Genesis and the lab did, newest first; optionally one card.', obj({'limit': I, 'card': S})),
    # --- cards ----------------------------------------------------------------------------
    'save_research': ('Create or update a research card. To update, give id and the current revision. Stage: research, hypothesis, approval, review or complete.',
                      obj({'id': S, 'revision': I, 'title': {**S, 'description': 'Up to 140 characters.'}, 'body': S,
                           'stage': {'type': 'string', 'enum': ['research', 'hypothesis', 'approval', 'review', 'complete']},
                           'kind': S, 'evidence': arr(obj({'kind': S, 'id': S}, extra=True)), 'parent': S,
                           'hypothesis': HYPOTHESIS, 'proposal': obj({}, extra=True), 'analysis': S}, ['title'])),
    'propose_experiment': ('Propose a run as a Studio launch payload; the Studio computes the plan. Smoke scale inside your allowances launches after the Reviewer accepts; anything else waits for a person.', LAUNCH),
    'ask_question': ('Ask the lab one question with a suggested default; the card you name waits until a person answers. Finish the turn after asking.',
                     obj({'question': {**S, 'description': 'Up to 600 characters.'}, 'default': S, 'card': {**S, 'description': 'The card that waits for the answer.'}}, ['question'])),
    'hypothesis_check': ('Turn a claim into a hypothesis record, or learn exactly which field is wrong.', obj({'record': HYPOTHESIS}, ['record'])),
    'hypothesis_settle': ('Whether recorded runs already answer a hypothesis: supported, not supported, inconclusive, untested or invalid, with intervals and run tags.',
                          obj({'card': {**S, 'description': 'A card carrying a hypothesis record.'}, 'record': HYPOTHESIS})),
    'hypothesis_plan': ('The smallest run that would settle a hypothesis, ready for propose_experiment.', obj({'card': S, 'record': HYPOTHESIS})),
    'request_review': ('Ask the Reviewer to judge one artifact on a card: hypothesis, plan, verdict, skill or patch. Read it back with read_review.',
                       obj({'card': S, 'subject': {'type': 'string', 'enum': ['hypothesis', 'plan', 'verdict', 'skill', 'patch']}}, ['card'])),
    'read_review': ("The Reviewer's verdict on a card and whether it accepts the plan as it stands.", obj({'card': S}, ['card'])),
    # --- library --------------------------------------------------------------------------
    'search_research': ('Paper metadata from Crossref for a query. Metadata only, never evidence that you read the paper.', obj({'query': S}, ['query'])),
    'library_list': ('Library sources, filtered by publication or discovery dates, topic or status (saved, analyzed).',
                     obj({'published_from': S, 'published_to': S, 'discovered_from': S, 'discovered_to': S, 'topic': S, 'status': S})),
    'library_read': ('One library source with its abstract, original text when fetched, analysis and columns.', obj({'id': S}, ['id'])),
    'library_save': ('Save a source to the library.', obj({'title': S, 'url': S, 'source_type': S, 'authors': arr(S), 'published_at': S, 'abstract': S, 'topic': S}, ['title'])),
    'library_analyze': ('Write the analysis of a source, optionally naming the sources it contradicts and its extraction columns.',
                        obj({'id': S, 'analysis': S, 'contradicts': arr(S), 'columns': obj({}, extra=True)}, ['id', 'analysis'])),
    'library_use': ('Record where a source was used: an architecture version, a blueprint, a place, a reason, experiment ids.',
                    obj({'id': S, 'version_id': S, 'blueprint': S, 'where': S, 'why': S, 'experiment_ids': arr(S)}, ['id'])),
    'library_reclassify': ('Move a source to another topic from the fixed list.', obj({'id': S, 'topic': S}, ['id', 'topic'])),
    'ingest_source': ('Fetch a source in full and start one extraction turn that fills its columns with quotes. Paid.', obj({'library': S, 'card': S}, ['library'])),
    'read_columns': ('The extraction columns of a source, each with the quote it rests on.', obj({'library': S}, ['library'])),
    # --- memory ---------------------------------------------------------------------------
    'memory_read': ('SOUL.md, LAB.md, MONARCH.md and, when a card is named, its notes.', obj({'card': S})),
    'memory_add': ('Add one line to LAB.md (Recent by default), tagged with the record it comes from, like run:abc or card:def.',
                   obj({'text': S, 'record': {**S, 'description': 'kind:id of the record, for example run:ccc6564c.'}, 'section': {'type': 'string', 'enum': ['Known', 'Recent']}}, ['text', 'record'])),
    'memory_replace': ('Rewrite one LAB.md entry: a piece of the old line and its replacement.', obj({'old': S, 'new': S, 'record': S}, ['old', 'new'])),
    'memory_remove': ('Drop one LAB.md entry by a piece of its text.', obj({'old': S}, ['old'])),
    'memory_recent': ('The newest indexed records: turns, cards, analyses, sources, code changes, with their tags.', obj({'limit': I})),
    'note_write': ('Write the whole notes block of a card (4,000 characters).', obj({'card': S, 'text': S}, ['card', 'text'])),
    'record_search': ('Search the record by words (and meaning, when an embedding route exists): turns, analyses, cards, sources, code changes. Every hit carries the tag to cite.',
                      obj({'query': S, 'limit': I}, ['query'])),
    'memory_changes': ('What memory promoted, dropped, marked stale or removed, with reasons.', obj({'limit': I})),
    'memory_eval_status': ('The last weekly memory evaluation and its trend.', obj({})),
    'person_read': ('What you know about a person (their file).', obj({'person': S})),
    'person_write': ("Rewrite a person's file (1,000 characters).", obj({'person': S, 'text': S}, ['person', 'text'])),
    # --- skills ---------------------------------------------------------------------------
    'skill_list': ('Your skills by name with what each applies to.', obj({})),
    'skill_read': ('The full text of one skill.', obj({'name': S}, ['name'])),
    'skill_write': ('Write or rewrite a skill: Markdown whose first line is "Applies: hypothesis, run, source, question, verdict or always". Reviewed before it enters a prompt.',
                    obj({'name': {**S, 'description': 'A slug like read-a-run.'}, 'text': S}, ['name', 'text'])),
    'skill_remove': ('Remove one skill.', obj({'name': S}, ['name'])),
    # --- code -----------------------------------------------------------------------------
    'code_status': ('The Monarch code index: commit, when it was built, counts.', obj({})),
    'code_search': ('Search the Monarch index for a symbol, path or phrase.', obj({'query': S, 'limit': I}, ['query'])),
    'code_explain': ('One symbol with its neighbours in the Monarch index.', obj({'symbol': S}, ['symbol'])),
    'code_read': ('A range of one Monarch file (at most 200 lines).', obj({'path': S, 'start': I, 'end': I}, ['path'])),
    'code_changes': ('What moved in Monarch since a commit, or since the previous index.', obj({'since': S})),
    'propose_patch': ('Draft a Monarch patch for a failed attempt as a card with a diff, path:line citations and a review. Paid. Internal only.', obj({'run': S, 'task': S}, ['run'])),
    'code_diff_check': ('Whether a unified diff applies cleanly to the indexed Monarch commit.', obj({'diff': S}, ['diff'])),
    'read_patch': ('A patch card: its diff, citations, check result and review.', obj({'card': S}, ['card'])),
    # --- architectures ----------------------------------------------------------------------
    'save_architecture': ('Save an architecture draft (see catalog.creation_contracts.save_architecture for the graph shape).',
                          obj({'name': S, 'track': S, 'revision': I, 'graph': obj({}, extra=True), 'notes': S, 'id': S}, ['name', 'graph'])),
    'publish_architecture': ('Publish a saved architecture draft as a version.', obj({'id': S, 'revision': I}, ['id', 'revision'])),
    'save_product_graph': ('Save a product graph draft (see catalog.creation_contracts.save_product_graph).',
                           obj({'name': S, 'revision': I, 'fields': arr(obj({}, extra=True)), 'instructions': S, 'runner': obj({}, extra=True), 'id': S}, ['name'])),
}

BUILTIN = ('research_state', 'list_runs', 'read_run', 'catalog', 'search_research', 'record_analysis', 'save_research',
           'library_list', 'library_read', 'library_save', 'library_analyze', 'library_use', 'library_reclassify',
           'propose_experiment', 'skill_list', 'skill_read', 'skill_write', 'skill_remove', 'ask_question', 'activity',
           'record_search', 'memory_read', 'memory_add', 'memory_replace', 'memory_remove', 'memory_recent', 'note_write',
           'save_architecture', 'publish_architecture', 'save_product_graph',
           'code_status', 'code_search', 'code_explain', 'code_read', 'code_changes')


def action_names() -> list[str]:
    """Every action Genesis performs now: the built-ins, then the plugins', without duplicates."""
    return list(dict.fromkeys(list(BUILTIN) + plugin_actions()))


def tool_defs(names=None) -> list[dict]:
    out = []
    for name in (names if names is not None else action_names()):
        sentence, parameters = SCHEMAS.get(name, (name.replace('_', ' ') + '.', obj({}, extra=True)))
        out.append({'name': name, 'description': sentence, 'parameters': parameters})
    return out


def canonical(value) -> list:
    return json.loads(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True))


def shaped(defs: list[dict], adapter: str) -> list:
    """The tool list in the shape each provider family reads (the same four shapes `wb_arms.api_loop` uses)."""
    if not defs:
        return []
    if adapter == 'anthropic':
        tools = canonical([{'name': d['name'], 'description': d['description'], 'input_schema': d['parameters']} for d in defs])
        tools[-1]['cache_control'] = {'type': 'ephemeral'}
        return tools
    if adapter == 'openai_responses':
        return canonical([{'type': 'function', 'name': d['name'], 'description': d['description'], 'parameters': d['parameters']} for d in defs])
    if adapter == 'gemini':
        return canonical(defs)
    return canonical([{'type': 'function', 'function': d} for d in defs])
