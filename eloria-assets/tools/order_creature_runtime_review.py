"""Put differing 30 fps drafts with close 120/240 fps alternatives first.

Within each group sort worst-first by full-reference-to-30-fps-bake maximum
position error, RMS position error, then maximum and RMS normal error.
Candidate identities, variants and append-only review decisions stay unchanged.
"""
from pathlib import Path
import argparse
import copy
import json
import os
import uuid


def ordered(catalog):
    result = copy.deepcopy(catalog)
    groups = {'30_fps_with_close_alternative': 0, 'other_drafts': 0, 'previously_accepted': 0}
    def rank(entry):
        variants = entry['variants']
        draft = next((v for v in variants if v['id'] == 'zero-bake'),
                     next((v for v in variants if v['id'] == 'sampled-30'), None))
        metrics = draft.get('metrics', {}) if draft else {}
        close = [v for v in variants if v['id'].startswith('close-')]
        differs = (metrics.get('maximum_position_mm', 0.) > 1.
                   or metrics.get('maximum_normal_degrees', 0.) > .5)
        accepted = bool(variants) and all(v.get('accepted', False) for v in variants)
        group = 2 if accepted else (0 if close and differs else 1)
        name = ['30_fps_with_close_alternative', 'other_drafts', 'previously_accepted'][group]
        groups[name] += 1
        return (group, -metrics.get('maximum_position_mm', 0.), -metrics.get('rms_position_mm', 0.),
                -metrics.get('maximum_normal_degrees', 0.), -metrics.get('rms_normal_degrees', 0.), entry['id'])
    result['entries'] = sorted(result['entries'], key=rank)
    result['review_order'] = {'groups': groups, 'within_group': 'Descending full-reference-to-30-fps-bake maximum position mm, RMS position mm, maximum normal degrees, RMS normal degrees; creature ID breaks ties.',
                              'close_alternative_scope': 'A close 120/240 fps sampling variant does not qualify the more aggressive 30 fps fixed bake.',
                              'scope': 'Candidate identities, available variants and saved review decisions are preserved.'}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    path = args.catalog.resolve()
    if '.local' not in path.parts:
        raise ValueError('Review catalogs must remain in ignored .local storage')
    current = path.read_bytes()
    result = ordered(json.loads(current))
    print(json.dumps(result['review_order'], indent=2))
    print(json.dumps({'first_creatures': [e['id'] for e in result['entries'][:12]]}))
    if args.apply:
        backup = path.with_name(path.stem + '.before-order-' + uuid.uuid4().hex + '.json')
        backup.write_bytes(current)
        temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
        try:
            temporary.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8', newline='\n')
            if path.read_bytes() != current:
                raise ValueError('Catalog changed while sorting; retry against the current version')
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
