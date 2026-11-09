#!/usr/bin/env python3
"""Bake a descent's floor pool (the server's generated layouts) into one sectioned interior map.

OWNER-APPROVED BAKE. Procedural generators were retired on 2026-10-16. The owner approved this bake on 2026-11-09
(chat: "baked pool for now is okay", The Serpent Deep descent); it runs only with --owner-approved "<who, when, what>".
It draws nothing of its own: build_underground.py (re-enabled by the owner on 2026-10-20) draws every floor's shell from
its theme table, and the floors' walls and set pieces are the reviewed Meshy kit pieces of the Serpent themes
(`catacomb`, `undercity`, `sunken`), placed by tools/prepare_underground_scenery.py from build_underground.dressing().

THE LAYOUTS come from the server's descent generator (rabbitlands-server `eloria/descent.py`, contract in the server
handbook's Descent-Runs.md, "The pool map"): `descent.pool_design(plan, entrance)` is the builder source of the whole
pool, every generated variant of every floor as a section of one map (`serpent_deep_descent`, 840 x 840 tiles of 1 m,
sections `serpent_deep_f<depth>v<variant>`). Its geometry is pinned by the plan's `pool.signature`
(`descent.pool_signature`): the server refuses a bake whose signature differs, so a plan change under `floors`,
`floor_defaults` or `pool` is a re-bake. This script refuses a plan whose recorded signature is not the generator's.

  content/serpent_deep_descent.json   the builder source, written from the server's generator (`generated` records
                                      the server commit, the plan's and generator's hashes and the pool signature)
  ../serpent_deep_descent/client/     the package: world.glb (images in the shared pool), collision.bin,
                                      served-grid.escg.gz, world.json, minimap.webp

THE FRAME: build_underground.py reads its map frame (CELLS) from content/underground.json at import, and every
published interior pins its hash (landfall_insides' provenance, landfall_town's imports), so it is not edited: this
script imports it and sets its frame to the source's own `map.cells` while it builds, then restores it, as
build_town_interiors.py does with its own frame. The cave package is untouched by a descent bake.

    python -B eloria-assets/maps/continent-v2/_continent_v2/build_descent_pool.py --server ../rabbitlands-server \
        --owner-approved "<who, when, what>"            # regenerate the source from the server, then build
    python -B .../build_descent_pool.py --server <checkout> --source-only --owner-approved "..."  # the source only
    python -B .../build_descent_pool.py --server <checkout> --build-only --owner-approved "..."   # the package only
    python -B .../build_descent_pool.py --server <checkout> --check   # the source is still the generator's (exit 1)

Then (the landfall_insides README's publish sequence):

    python -B tools/prepare_underground_scenery.py --map serpent_deep_descent --configs-only
    python -B eloria-assets/tools/render_map_backgrounds.py --map serpent_deep_descent --work <scratch> --apply

--server is a rabbitlands-server checkout holding the descent generator (`eloria/descent.py`) and the served-grid codec
(`eloria/served_grid.py`); both are imported read-only (no bytecode is written).
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True  # neither this checkout nor the server checkout gets __pycache__

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_underground as B  # noqa: E402  the cave builder, never edited (its hash pins the published caves)
import underground_source as S  # noqa: E402

SOURCE = HERE/'content/serpent_deep_descent.json'
SCHEMA = 'eloria-descent-pool-v1'
PLAN = 'config/eloria/descents/serpent_deep.json'   # in the server checkout
GENERATOR = 'eloria/descent.py'
# The temple door every first floor's way up leads to (Warden Sethra's temple beside the Serpent Catacombs, Suncoil):
# the server moves a party in and out itself; these are the baked portals' return tiles.
ENTRANCE = {'map': 'suncoil', 'marker': 'suncoil--serpent-deep-temple', 'tile': [283, 747], 'position': [0, 0, 0],
            'returnTile': [285, 749]}
PARENT_REGION = 'suncoil'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _git(server, *args):
    return subprocess.run(['git', '-C', str(server), *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def generate(server):
    """(design, generated note) from the server's generator: the pool's builder source with the temple door."""
    server = Path(server).resolve()
    if str(server) not in sys.path:
        sys.path.insert(0, str(server))
    from eloria import descent
    plan = descent.load_plan(server/PLAN)
    signature = descent.pool_signature(plan)
    recorded = plan.raw.get('pool', {}).get('signature')
    if signature != recorded:
        raise SystemExit(f'{PLAN}: pool.signature {recorded} is not the generator\'s {signature}: the plan or the '
                         'generator changed; re-sign the pool on the server first')
    design = descent.pool_design(plan, entrance=dict(ENTRANCE))
    design = {'schema': SCHEMA, **design}
    dirty = _git(server, 'status', '--porcelain', '--', GENERATOR, PLAN)
    note = {'generator': f'rabbitlands-server {GENERATOR} pool_design', 'branch': _git(server, 'rev-parse',
            '--abbrev-ref', 'HEAD'), 'commit': _git(server, 'rev-parse', '--short', 'HEAD'),
            'clean': not dirty, 'plan': PLAN, 'planSha256': sha(server/PLAN),
            'generatorSha256': sha(server/GENERATOR), 'poolSignature': signature}
    return design, note


def source_text(design, note):
    """The source in content/underground.json's layout (underground_source.dump), with the `generated` note."""
    text = S.dump(design).replace('[\n\n      ]', '[]')  # a floor with no props
    head = f'  "map": {S.compact(design["map"])},\n'
    if text.count(head) != 1:
        raise SystemExit('unexpected source layout')
    return text.replace(head, head+f'  "generated": {S.compact(note)},\n')


def write_source(server):
    design, note = generate(server)
    if not note['clean']:
        raise SystemExit(f'{GENERATOR} or {PLAN} has uncommitted changes in {server}: bake from a commit')
    text = source_text(design, note)
    if json.loads(text) != json.loads(json.dumps({**design, 'generated': note})):
        raise SystemExit('the laid-out source does not read back as the design')
    SOURCE.write_bytes(text.encode('utf-8'))
    B.load_design(SOURCE)   # checks the doors and passages (underground_source.check)
    print(json.dumps({'source': SOURCE.relative_to(B.CHECKOUT).as_posix(), 'sections': len(design['sections']),
                      'passages': len(design['passages']), **note}))


def check_source(server):
    """True when content/serpent_deep_descent.json is the generator's design (its `generated` note aside)."""
    design, _note = generate(server)
    on_file = json.loads(SOURCE.read_text(encoding='utf-8'))
    on_file.pop('generated', None)
    same = on_file == json.loads(json.dumps(design))
    print(json.dumps({'source': SOURCE.relative_to(B.CHECKOUT).as_posix(), 'current': same}))
    return same


@contextmanager
def frame(cells):
    """build_underground's map frame set to `cells` for the duration (world(), section_bounds(), the cutaway centres
    and build()'s own frame check read B.CELLS), then restored."""
    previous = B.CELLS
    B.CELLS = cells
    try:
        yield
    finally:
        B.CELLS = previous


def build(server, out=None):
    """Build the package from content/serpent_deep_descent.json with build_underground.build(), then state the map's
    own parent region and provenance in world.json (the cave builder writes landfall_insides')."""
    design = json.loads(SOURCE.read_text(encoding='utf-8'))
    ident, cells = design['map']['id'], design['map']['cells']
    out = Path(out or HERE.parent/ident/'client')
    with frame(cells):
        summary = B.build(Path(server).resolve(), source=SOURCE, out=out, registry=out == HERE.parent/ident/'client')
    manifest_path = out/'world.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest['asset']['parentRegion'] = PARENT_REGION
    manifest['provenance'] = {
        'source': f'_continent_v2/content/{SOURCE.name}', 'sourceSha256': sha(SOURCE),
        'builder': f'_continent_v2/{Path(__file__).name}', 'builderSha256': sha(__file__),
        'imports': {f'_continent_v2/{name}': sha(HERE/name) for name in ('build_underground.py', 'underground_source.py')},
        'generated': design.get('generated', {})}
    manifest_path.write_bytes((json.dumps(manifest, indent=2, ensure_ascii=False)+'\n').encode('utf-8'))
    files = {name: (out/name).stat().st_size for name in ('world.glb', 'collision.bin', 'served-grid.escg.gz',
                                                          'world.json', 'minimap.webp')}
    summary = {**summary, 'files': files, 'totalBytes': sum(files.values())}
    print(json.dumps(summary))
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--server', type=Path, required=True, help='a rabbitlands-server checkout (read only)')
    parser.add_argument('--owner-approved', metavar='NOTE',
                        help="the owner's approval for this bake (the generators were retired on 2026-10-16)")
    parser.add_argument('--source-only', action='store_true', help='write the source; build nothing')
    parser.add_argument('--build-only', action='store_true', help='build the package from the source as it stands')
    parser.add_argument('--check', action='store_true', help='compare the source with the generator; write nothing')
    parser.add_argument('--out', type=Path, help='a scratch package folder (the registry row is not checked)')
    args = parser.parse_args(argv)
    if args.check:
        return 0 if check_source(args.server) else 1
    if not args.owner_approved:
        raise RuntimeError('build_descent_pool.py bakes with the retired underground builder (procedural models and '
                           'generators were archived on 2026-10-16; see docs/procedural-model-archive.md). It runs only '
                           'with --owner-approved "<who, when, what>" (the owner approved the Serpent Deep pool on '
                           '2026-11-09). No outputs were written.')
    if not args.build_only:
        write_source(args.server)
    if not args.source_only:
        build(args.server, args.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
