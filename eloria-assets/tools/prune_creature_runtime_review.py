"""Hide reviewed versions and a user-waived tail without editing review events.

The reviewed prefix is measured against the complete ordered catalog supplied
at the time of the request. Decisions are pinned to source/candidate hashes,
so a later replacement version returns to review rather than inheriting a hide.
"""
from pathlib import Path
from collections import Counter
import argparse
import copy
import json
import os
import re
import uuid
from order_creature_runtime_review import ordered
from review_creature_runtime_optimization import journal_path


def identity(entry):
    draft = next((v for v in entry['variants'] if v['id'] == 'zero-bake'), entry['variants'][0])
    return entry['id'], entry['source']['sha256'], draft['id'], draft['sha256']


def policy_for(catalog, events, reviewed_prefix):
    approved = {(e['actor'], e['source_sha256'], e['variant'], e['candidate_sha256'])
                for e in events if e['type'] == 'approve' and not e.get('test_only')}
    comment_acceptance = {(e['actor'], e['source_sha256'], e['variant'], e['candidate_sha256'])
                          for e in events if e['type'] == 'comment' and not e.get('test_only')
                          and re.match(r'^\s*(?:this is\s+)?approved\b', e.get('text', ''), re.I)}
    hidden = []
    for ordinal, entry in enumerate(catalog['entries'], 1):
        key = identity(entry)
        reason = None
        if key in approved:
            reason = 'Explicit exact-version approval in saved journal'
        elif key in comment_acceptance:
            reason = 'Explicit acceptance in saved comment; repair note retained'
        elif entry['variants'] and all(v.get('accepted') for v in entry['variants']):
            reason = 'Previously accepted installed version'
        elif ordinal > reviewed_prefix and any(v['id'].startswith('close-') for v in entry['variants']):
            reason = f'Remaining close-alternative tail waived by user after reviewing first {reviewed_prefix}'
        if reason:
            hidden.append(dict(zip(('actor', 'source_sha256', 'variant', 'candidate_sha256'), key),
                               original_position=ordinal, reason=reason))
    return {'schema': 1, 'reviewed_prefix': reviewed_prefix, 'original_count': len(catalog['entries']),
            'scope': 'Queue visibility only; no generated approvals, model edits or installation.', 'hidden': hidden}


def apply_visibility(catalog, policy):
    result = copy.deepcopy(catalog)
    hidden = {(v['actor'], v['source_sha256'], v['variant'], v['candidate_sha256']): v for v in policy['hidden']}
    removed = [hidden[identity(e)] for e in result['entries'] if identity(e) in hidden]
    result['entries'] = [e for e in result['entries'] if identity(e) not in hidden]
    result = ordered(result)
    result['review_visibility'] = {'original_count': policy['original_count'], 'visible_count': len(result['entries']),
                                   'hidden_count': len(removed), 'reasons': dict(Counter(v['reason'] for v in removed)),
                                   'scope': policy['scope']}
    return result


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8', newline='\n')
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--reviewed-prefix', type=int, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    path = args.catalog.resolve()
    if '.local' not in path.parts or args.reviewed_prefix < 0:
        raise ValueError('Use an ignored local catalog and a nonnegative reviewed prefix')
    before = path.read_bytes()
    catalog = json.loads(before)
    if catalog.get('review_visibility'):
        raise ValueError('Use the preserved full ordered catalog to choose a new reviewed-prefix cutoff')
    events_path = journal_path(path, catalog)
    journal = events_path.read_bytes()
    events = [json.loads(line) for line in journal.splitlines() if line.strip()]
    policy = policy_for(catalog, events, args.reviewed_prefix)
    result = apply_visibility(catalog, policy)
    print(json.dumps(result['review_visibility'], indent=2))
    if args.apply:
        if path.read_bytes() != before or events_path.read_bytes() != journal:
            raise ValueError('Review inputs changed; retry before applying the visibility plan')
        backup = path.with_name(path.stem + '.before-prune-' + uuid.uuid4().hex + '.json')
        backup.write_bytes(before)
        atomic_json(path.parent / '.local/review-visibility.json', policy)
        atomic_json(path, result)
        if not events_path.read_bytes().startswith(journal):
            raise ValueError('Review journal changed unexpectedly; retained catalog backup requires inspection')


if __name__ == '__main__':
    main()
