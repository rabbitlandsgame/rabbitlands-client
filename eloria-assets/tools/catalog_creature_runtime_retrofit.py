"""Assemble a private hash-bound review catalog from completed batch evidence."""
from pathlib import Path
import argparse
import json
from video_motion.asset import digest, read_glb

ROOT = Path(__file__).resolve().parents[2]


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def build(manifest, worker_roots, output, *, complete=False, blender_index=None, additions=None):
    manifest, output = Path(manifest), Path(output)
    plan = load(manifest)
    blender = {(v['actor'], v['variant']): v for v in load(blender_index)['variants']} if blender_index else {}
    extra = load(additions).get('actors', {}) if additions else {}
    entries = []
    progress = {'total': len(plan['actors']), 'sampled': 0, 'baked': 0, 'client_sampled': 0}
    for actor in plan['actors']:
        identity = actor['id']
        if actor['status'] == 'accepted_v2_installed':
            reference = ROOT / '.local/creature-sampling/crystalback_tortoise/fps-30/crystalback_tortoise_30.glb'
            candidate = ROOT / actor['runtime_repository_path']
            entries.append({'id': identity, 'display_name': identity.replace('_', ' ').title(),
                            'source': {'path': str(reference), 'sha256': digest(reference), 'bytes': reference.stat().st_size},
                            'clips': actor['clips'], 'was_installed': True, 'selected_local_draft': False,
                            'variants': [{'id': 'accepted-v2', 'label': 'Accepted V2 / zero correctives', 'path': str(candidate),
                                          'sha256': digest(candidate), 'bytes': candidate.stat().st_size, 'accepted': True,
                                          'metrics': {'maximum_position_mm': 33.5054, 'rms_body_position_mm': 1.56138}}]})
            for key in ('sampled', 'baked', 'client_sampled'):
                progress[key] += 1
            continue
        locations = [Path(root) / identity for root in worker_roots if (Path(root) / identity / 'sampling.json').exists()]
        if len(locations) != 1:
            raise ValueError(f'Expected exactly one candidate folder for {identity}: {locations}')
        folder = locations[0]
        source = Path(actor['source'])
        if digest(source) != actor['sha256']:
            raise ValueError('Frozen reference changed: ' + identity)
        entry = {'id': identity, 'display_name': identity.replace('_', ' ').title(),
                 'source': {'path': str(source), 'sha256': actor['sha256'], 'bytes': source.stat().st_size},
                 'clips': actor['clips'], 'was_installed': actor['was_installed'],
                 'selected_local_draft': actor['selected_local_draft'], 'variants': []}
        variants = [('sampled-30', '30 Hz animation sampling', 'sampled.glb', 'sampling.json', 'client-sample/client-validation.json')]
        if (folder / 'baking.json').exists():
            baked_proof = load(folder / 'baking.json')
            bake_client = 'client-sample/client-validation.json' if baked_proof['sha256'] == load(folder / 'sampling.json')['candidate_sha256'] else 'client-final/client-validation.json'
            variants.append(('zero-bake', 'Zero-corrective mesh / skin bake', 'baked.glb', 'baking.json', bake_client))
        state_path = folder / 'close-state.json'
        if state_path.exists():
            for attempt in load(state_path).get('attempts', []):
                rate = attempt['fps']
                if attempt.get('close_match'):
                    variants.append((f'close-{rate}', f'Close-match delivery / {rate} Hz', f'sampled-{rate}.glb', f'sampling-{rate}.json', f'client-{rate}/client-validation.json'))
        for variant, label, payload, proof_path, client_path in variants:
            path = folder / payload
            proof = load(folder / proof_path)
            expected = proof.get('candidate_sha256', proof.get('sha256'))
            if digest(path) != expected:
                raise ValueError(f'Changed candidate {identity}/{variant}')
            metrics = load(folder / client_path)['summary']['all'] if (folder / client_path).exists() else {}
            if metrics:
                metrics = dict(metrics, scope='Full displayed reference to displayed candidate, including animation sampling and mesh/skin changes.')
            document, _ = read_glb(path)
            value = {'id': variant, 'label': label, 'path': str(path), 'sha256': expected, 'bytes': path.stat().st_size,
                     'metrics': metrics, 'corrective_targets': max((len(p.get('targets', [])) for m in document['meshes'] for p in m['primitives']), default=0),
                     'evidence': {'build_report': str(folder / proof_path), 'client_report': str(folder / client_path)}}
            if variant == 'sampled-30':
                value['evidence']['blender_report'] = str(folder / 'blender-sampled/blender-validation.json')
            elif (identity, variant) in blender:
                value['evidence']['blender_report'] = blender[identity, variant]['report']
            entry['variants'].append(value)
        if identity in extra:
            supplement = extra[identity]
            if supplement['source_sha256'] != actor['sha256']:
                raise ValueError('Supplement reference differs: ' + identity)
            for value in supplement['variants']:
                if digest(value['path']) != value['sha256'] or Path(value['path']).stat().st_size != value['bytes']:
                    raise ValueError('Supplement changed: ' + identity)
                entry['variants'] = [v for v in entry['variants'] if v['id'] != value['id']]
                entry['variants'].append(value)
        if complete:
            for value in entry['variants']:
                evidence = value['evidence']
                client = load(evidence['client_report'])
                imported = load(evidence['blender_report'])
                if client['models'][0]['sha256'] != actor['sha256'] or client['models'][1]['sha256'] != value['sha256'] or not all(client['placement'].values()):
                    raise ValueError('Final client pair/placement is not qualified: ' + identity)
                if imported.get('status') != 'passed_fresh_import_finite_only' or not imported.get('all_clips_finite') or imported.get('sha256') != value['sha256']:
                    raise ValueError('Fresh Blender input is not qualified: ' + identity)
                value['metrics'] = dict(client['summary']['all'], scope='Full displayed reference to displayed candidate.')
        # A zero-bake is the principal review target, while the sampled source
        # and closer higher-rate delivery remain selectable controls.
        entry['variants'].sort(key=lambda v: (v['id'] != 'zero-bake', v['id']))
        progress['sampled'] += int((folder / 'sampling.json').exists())
        progress['baked'] += int((folder / 'baking.json').exists())
        progress['client_sampled'] += int((folder / 'client-sample/client-validation.json').exists())
        entries.append(entry)
    if complete and (progress['sampled'] != progress['total'] or progress['baked'] != progress['total']):
        raise ValueError('Cannot enable approval before every sampling and bake candidate exists')
    catalog = {'schema': 1, 'complete': complete, 'progress': progress, 'entries': entries,
               'review_store': '.local/review-events.jsonl', 'manifest_sha256': digest(manifest),
               'scope': 'Reference versus exact candidate. Approval is per creature/version and covers its full clip set. No runtime installation is performed by the viewer.'}
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.tmp')
    temporary.write_text(json.dumps(catalog, indent=2) + '\n', encoding='utf-8', newline='\n')
    temporary.replace(output)
    return catalog


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--worker-root', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--complete', action='store_true')
    parser.add_argument('--blender-index', type=Path)
    parser.add_argument('--additions', type=Path, help='Hash-bound versioned repairs or optional helper variants')
    args = parser.parse_args()
    catalog = build(args.manifest, args.worker_root, args.output, complete=args.complete,
                    blender_index=args.blender_index, additions=args.additions)
    print(json.dumps(catalog['progress']))
