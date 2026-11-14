"""Reuse imported kit art for the additional isle resources; never generate models.

Run before publish_harvest_diversity.py. --check replays the same processing into
an ignored temporary folder and compares both bytes and the registry records.
The shared packager preserves the original binary geometry and UVs, embeds
existing textures and adds only an outer floor/size transform.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import tempfile

import prepare_underground_scenery as U

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'eloria-assets/source/world_objects/isle-harvest-reuse.json'
# Each is a complete imported clump/pile; none is a retired procedural model.
PLANTS = {
    'Sunleaf': ('flower-shrub-2', 'height', .65, 'flora'),
    'Seed': ('feather-grass-2', 'height', .85, 'crop'),
    'Riverflax': ('alpine-flower-cushion-1', 'length', 1.2, 'fibre'),
    'Lotus': ('lotus-flower-pads-1', 'length', 1.6, 'aquatic'),
    'Orchid': ('flower-shrub-1', 'height', .65, 'flora'),
    'Silverleaf': ('frost-grass-1', 'height', .65, 'herb'),
    'Thistle': ('flower-meadow-3', 'height', .7, 'herb'),
    'Peat': ('peat-stack-1', 'length', 1.25, 'fuel'),
    'Berries': ('blackthorn-shrub-1', 'height', 1.05, 'crop'),
    'Blue Berries': ('juniper-shrub-1', 'height', .85, 'crop'),
    'Mushroom': ('toadstool-ring-1', 'length', 1.25, 'fungus'),
}
MINERALS = {
    'Bog Iron': ('#756451', '#a2693f'),
    'Silver Ore': ('#56525c', '#d4d8e0'),
    'Gold Ore': ('#665345', '#e3b54d'),
    'Titanium Ore': ('#443e52', '#a697bd'),
}


def model_id(label):
    return 'rl_isle_' + label.lower().replace(' ', '_')


def generate(output):
    catalog = json.loads((ROOT / 'godot-client/data/world/objects.json').read_bytes())
    harvest = catalog['harvestables']
    for key in list(harvest['models']):
        if key.startswith('rl_isle_') and '_wall_' in key:
            del harvest['models'][key]
    records = []
    files = {}
    # The complete kit peat stack exceeds the 2,600-triangle harvest budget.
    # Reuse its upper turf heap, grounded at the cut, rather than its tall
    # storage base. Existing triangles/UVs/textures are selected, never rebuilt.
    def peat_heap(positions, faces):
        heights = positions[faces][:,:,1].mean(axis=1)
        return heights > U.np.quantile(heights, .4)
    U.FACE_SELECTIONS[model_id('Peat')] = ('Upper turf heap; storage base omitted', peat_heap)
    for label, (slug, axis, size, kind) in PLANTS.items():
        identity = model_id(label)
        record = U.package(identity, ('lf-biomes', slug, axis, size), output)
        relative = f'godot-client/assets/world/harvestables/{identity}.glb'
        record['output'] = relative
        record['resource'] = label
        files[ROOT / relative] = (output / f'{identity}.glb').read_bytes()
        records.append(record)
        harvest['models'][identity] = dict(label=label, kind=kind, tier='common', imported=True,
            standsAlone=True, scene='res://' + relative.removeprefix('godot-client/'),
            **U.measure_glb(output / f'{identity}.glb'), source=SOURCE)
        harvest['resources'][label] = identity
        harvest['variants'][label] = [identity]
    for label, (stone, mineral) in MINERALS.items():
        identity = model_id(label)
        base = copy.deepcopy(harvest['models']['rl_iron_ore_v1'])
        base.pop('replaces', None)
        base.update(label=label, tier='uncommon', resourcePalette=dict(stone=stone, mineral=mineral),
                    source=SOURCE, standsAlone=True)
        harvest['models'][identity] = base
        harvest['resources'][label] = identity
        harvest['variants'][label] = [identity]
        if label == 'Bog Iron':
            continue
        variants = []
        for index, original in enumerate(harvest['wallVariants']['Iron Ore']):
            key = 'rl_' + label.lower().replace(' ', '_') + f'_wall_{index+1}'
            wall = copy.deepcopy(harvest['models'][original])
            wall.update(label=label, tier='uncommon', resourcePalette=dict(stone=stone, mineral=mineral))
            harvest['models'][key] = wall
            variants.append(key)
        harvest['wallVariants'][label] = variants
    # Preserve the rest of the registry, including every retired entry.
    files[ROOT / 'godot-client/data/world/objects.json'] = (json.dumps(catalog, indent=2) + '\n').encode()
    files[ROOT / SOURCE] = (json.dumps(dict(schema='rabbitlands-imported-harvest-reuse-v1',
        about='Existing imported kit art sized for resource patches. Plant silhouettes are reused art, not botanical reconstructions. Mineral seams reuse the current wall meshes with distinct resource palettes.',
        models=records, mineralPalettes={k:dict(stone=v[0],mineral=v[1]) for k,v in MINERALS.items()}), indent=2)+'\n').encode()
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    work = ROOT / '.local/isle-harvestables'
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as temporary:
        updates = generate(Path(temporary))
    different = [str(p.relative_to(ROOT)) for p,b in updates.items() if not p.exists()
                 or (p.read_bytes().replace(b'\r\n',b'\n') if p.suffix == '.json' else p.read_bytes()) != b]
    if not args.check:
        for p,b in updates.items():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b)
    print(json.dumps(dict(mode='check' if args.check else 'apply', differences=different), indent=2))
    return int(args.check and bool(different))


if __name__ == '__main__':
    raise SystemExit(main())
