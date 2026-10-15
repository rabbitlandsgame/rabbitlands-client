"""Rebuild retained regional content from its authored recipes, for world assembly.

The old survey is a frozen source dependency for reusable settlement composition.
Its terrain is sampled for existing foundation heights and is never the new
continent's terrain. Each subprocess isolates the legacy modules named 'layout'
and 'region'; no neighbouring exported GLB is an input.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict
import hashlib
import importlib.util
import json
import os
import pickle
from pathlib import Path
import sys
import time
import numpy as np
import authoring as AUTHORING

HERE = Path(__file__).resolve().parent
REGIONS = HERE.parent
MAPS = REGIONS.parent
CLIENT = MAPS.parents[1]
TOOLKIT = REGIONS / '_toolkit'
BUILDERS = {
    'whitehorn_range': 'build_whitehorn.py', 'amberwood': 'build_amberwood.py',
    'mirrorhold': 'build_mirrorhold.py', 'amethyst_barrens': 'build_amethyst.py',
    'grey_moors': 'build_grey_moors.py', 'westhaven': 'build_westhaven.py',
    'crownwater': 'build_crownwater.py', 'four_gates': 'build_four_gates.py',
    'sunmane_steppe': 'build_landscape.py', 'manymouth_delta': 'build_manymouth_delta.py',
    'verdant_stair': 'build_verdant_stair.py', 'ssarathi_ruins': 'build_ssarathi.py',
}


def package(region):
    return MAPS / 'four-gates' if region == 'four_gates' else REGIONS / region


def authored_snapshot(region):
    return next((snapshot for snapshot in AUTHORING.load_snapshots()
                 if snapshot.document['regionId'] == region), None)


def clean(value):
    if isinstance(value, dict): return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)): return [clean(v) for v in value]
    if isinstance(value, np.ndarray): return value.tolist()
    if isinstance(value, np.generic): return value.item()
    return value


def inputs(region):
    snapshot = authored_snapshot(region)
    if snapshot is not None:
        sources = set(TOOLKIT.rglob('*.py'))
        sources.update((Path(__file__).resolve(), HERE/'authoring.py', HERE/'scene_io.py',
                        HERE/'legacy-geography.json', HERE/'legacy-contracts.json'))
        sources.update(CLIENT/relative for relative in snapshot.bound_sources())
        return {p.relative_to(CLIENT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(sources)}
    sources = set(TOOLKIT.rglob('*.py')) | set((package(region)/'source').rglob('*.py'))
    sources.update((package(region)/'source').rglob('*.json'))
    for name in ('_northern', '_finishing', '_outer', '_color'):
        sources.update((REGIONS/name).rglob('*.py'))
    sources.update([Path(__file__).resolve(), HERE/'legacy-geography.json', HERE/'legacy-contracts.json'])
    # Native adapters share their authored equipment-free scenery kits.
    for name in ('four-gates',):
        sources.update((MAPS/name/'source').glob('*.py'))
        sources.update((MAPS/name/'source').glob('*.json'))
    for name in ('four_gates', 'sunmane_steppe'):
        sources.update((CLIENT/'eloria-assets'/'tools'/name).rglob('*.py'))
    return {p.relative_to(CLIENT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(sources)}


def composition_inputs(certificate):
    # Export-bridge repairs need not repeat a costly, unchanged authored build.
    return {path: digest for path, digest in certificate.items()
            if path != Path(__file__).resolve().relative_to(CLIENT).as_posix()}


def cached_composition(root, certificate):
    """Only load this bridge's local generated cache, after identity/hash checks.

    Pickle is an internal trusted build artifact, never an import file format.
    The cache is created here, not accepted from a user-selected source path.
    """
    cache, sidecar = root/'composed-build.pickle', root/'composed-build.json'
    if not cache.exists() or not sidecar.exists():
        return None
    info = json.loads(sidecar.read_text(encoding='utf-8'))
    if info.get('schema') != 1 or info.get('inputs') != composition_inputs(certificate):
        return None
    if hashlib.sha256(cache.read_bytes()).hexdigest() != info.get('sha256'):
        raise RuntimeError(f'Composition cache hash mismatch: {cache}')
    with cache.open('rb') as stream:
        return pickle.load(stream)


def save_composition(root, built, certificate):
    cache = root/'composed-build.pickle'
    temporary = root/'composed-build.pending'
    with temporary.open('wb') as stream:
        pickle.dump(built, stream, protocol=pickle.HIGHEST_PROTOCOL)
    temporary.replace(cache)
    info = {'schema':1, 'inputs':composition_inputs(certificate),
            'sha256':hashlib.sha256(cache.read_bytes()).hexdigest()}
    (root/'composed-build.json').write_text(json.dumps(info,indent=2)+'\n',encoding='utf-8')


def material_sets(module):
    import preview
    sets = preview.texture_sets()
    if hasattr(module, 'register_materials'):
        result = module.register_materials(sets)
        if result is not None: sets = result
    elif hasattr(module, 'CK'):
        sets = module.CK.register(sets)
    # Verdant extends the global recipes; its normal CLI handles this explicitly.
    if hasattr(module, 'MAT') and hasattr(module, 'MATERIALS'):
        needed = {module.MAT.BY_NAME[name].texture for name in module.MATERIALS
                  if name in module.MAT.BY_NAME}
        if needed - sets.keys():
            sets.update({k:v for k,v in module.MAT.build_texture_sets().items() if k not in sets})
    return sets


def build(region, output, force=False):
    certificate = inputs(region)
    root = output/region
    root.mkdir(parents=True, exist_ok=True)
    proof = root/'source-certificate.json'
    if not force and proof.exists():
        previous = json.loads(proof.read_text())
        if previous.get('inputs') == certificate and all((root/p).exists() and hashlib.sha256((root/p).read_bytes()).hexdigest() == digest for p,digest in previous.get('outputs',{}).items()):
            print(f'{region}: retained content is current', flush=True)
            return
    snapshot = authored_snapshot(region)
    if snapshot is not None:
        started = time.monotonic()
        print(f'{region}: exporting Godot-authored retained-content GLB', flush=True)
        products = AUTHORING.build_retained_library(snapshot, root)
        if certificate != inputs(region):
            raise RuntimeError('Godot authoring sources changed during retained-content export')
        proof.write_text(json.dumps({'schema':2, 'region':region, 'authority':'godot-continent-authoring',
            'snapshotSha256':snapshot.digest, 'inputs':certificate, 'outputs':products,
            'elapsedSeconds':round(time.monotonic()-started,2)}, indent=2)+'\n', encoding='utf-8')
        print(f'{region}: Godot-authored reusable content complete in {time.monotonic()-started:.1f}s', flush=True)
        return
    sys.path.insert(0, str(TOOLKIT))
    import continent_geography
    legacy = json.loads((HERE/'legacy-geography.json').read_text(encoding='utf-8'))
    continent_geography.plan = lambda: legacy
    source = package(region)/'source'/BUILDERS[region]
    os.chdir(source.parent)
    sys.path.insert(0, str(source.parent))
    spec = importlib.util.spec_from_file_location('continent_regional_content', source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    started = time.monotonic()
    built = None if force else cached_composition(root, certificate)
    if built is None:
        print(f'{region}: composing retained authored content', flush=True)
        built = module.build_region()
        save_composition(root, built, certificate)
        print(f'{region}: composed and cached {len(built.placements)} reusable placements in {time.monotonic()-started:.1f}s', flush=True)
    else:
        print(f'{region}: restored {len(built.placements)} placements from verified composition cache in {time.monotonic()-started:.1f}s', flush=True)
    print(f'{region}: exporting retained-content GLB', flush=True)
    if region == 'four_gates':
        module.A.export(built, root/'library.glb', root/'material-cache')
    elif region == 'sunmane_steppe':
        module.A.export(built, root/'library.glb')
    else:
        module.export_glb(built, material_sets(module), root/'library.glb')
    metadata = {key: clean(getattr(built,key,[])) for key in (
        'landmarks','interactives','npc_markers','harvestables','portals','spawns','notes','empty_nodes','authored_roads','crossings')}
    metadata['placements'] = [clean(asdict(p)) for p in built.placements]
    metadata['region'] = region
    (root/'library.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
    np.savez_compressed(root/'foundation-samples.npz', x=built.terrain.gx[0], z=built.terrain.gz[:,0], height=built.terrain.height)
    if certificate != inputs(region): raise RuntimeError('Source recipes changed during content composition')
    products = ('library.glb','library.json','foundation-samples.npz')
    proof.write_text(json.dumps({'schema':1,'region':region,'inputs':certificate,
        'outputs':{p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in products},
        'elapsedSeconds':round(time.monotonic()-started,2)},indent=2)+'\n',encoding='utf-8')
    print(f'{region}: reusable content complete in {time.monotonic()-started:.1f}s',flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--region',choices=BUILDERS,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--force',action='store_true')
    args=parser.parse_args()
    build(args.region,args.output.resolve(),args.force)
