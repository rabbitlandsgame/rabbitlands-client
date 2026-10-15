"""Close server tiles unsupported at the actual tile-centre position of an actor.

Run after open_walk_surfaces and stamp_solid_landmarks, before server export:
    python guard_actor_surfaces.py --package <directory>

The inherited conservative fold takes half-cells 2t-1 and 2t. Current actors
stand at tile t+.5, so widening a partial deck for that fold can leave the
rendered body outside it. This final guard reads real navigation and water
triangles at t+.5 and only removes unsupported tiles. It never adds a floor.
"""
import argparse
from pathlib import Path
import json
import numpy as np
import glb_reader as GLB
from open_walk_surfaces import decode


def guarded_grid(grid, encoding, covered, surface, wet, water, tolerance=.8):
    rows, columns = covered.shape
    padded = np.pad(grid, ((1, 0), (1, 0)))
    blocks = padded[:rows*2, :columns*2].reshape(rows, 2, columns, 2)
    walkable = (blocks != 0).all(axis=(1, 3))
    encoded = decode(blocks.max(axis=(1, 3)), encoding)
    unsupported = ~covered | ~np.isfinite(surface)
    submerged = wet & (surface < water-.25)
    mismatch = np.abs(surface-encoded) > tolerance
    bad = walkable & (unsupported | submerged | mismatch)
    # Blocks are disjoint: closing one tile cannot invent or raise another.
    blocks[:] = np.where(bad[:, None, :, None], 0, blocks)
    output = grid.copy()
    output[:rows*2-1, :columns*2-1] = padded[1:rows*2, 1:columns*2]
    return output, bad, encoded, unsupported, submerged, mismatch


def guard(package: Path, write=True):
    grid, manifest = GLB.read_grid(package)
    collision = manifest['collision']
    transform = manifest['coordinateTransform']
    if float(collision.get('cellMetres', collision.get('cellSize', 0))) != .5 or float(transform.get('metresPerTile', 1)) != 1:
        raise ValueError('Actor guard requires a half-metre package with one-metre server tiles.')
    rows, columns = grid.shape[0]//2, grid.shape[1]//2
    doc, body = GLB.load(package/'world.glb')
    prefixes = manifest.get('navigation', {}).get('surfaceNodePrefixes', [])
    if not prefixes:
        raise ValueError('No authored navigation surfaces declared.')
    nodes = sorted({n for prefix in prefixes for n in GLB.named(doc, prefix)})
    x0, z1 = GLB.grid_origin(manifest)
    covered, top = GLB.rasterise(GLB.triangles(doc, body, nodes), columns, rows, x0, z1, 1)
    wet, water = GLB.rasterise(GLB.triangles(doc, body, GLB.named(doc, 'Water_')),
                             columns, rows, x0, z1, 1)
    tolerance = max(.8, float(collision['heightEncoding']['step'])*1.5)
    result, bad, encoded, unsupported, submerged, mismatch = guarded_grid(
        grid, collision['heightEncoding'], covered, top, wet, water, tolerance)
    samples = []
    for y, x in zip(*np.nonzero(bad)):
        samples.append({'tile': [int(x), int(y)], 'encodedY': round(float(encoded[y,x]), 3),
                        'surfaceY': round(float(top[y,x]), 3) if covered[y,x] else None,
                        'unsupported': bool(unsupported[y,x]), 'submerged': bool(submerged[y,x])})
    record = {'method': 'rendered-tile-centre-v1', 'actorTileOffset': [.5,.5],
              'heightToleranceMetres': tolerance, 'closedTiles': int(bad.sum()),
              'unsupportedTiles': int((bad & unsupported).sum()),
              'submergedTiles': int((bad & submerged).sum()),
              'heightMismatchTiles': int((bad & mismatch).sum()), 'samples': samples[:12]}
    if write:
        previous = collision.get('actorSurfaceGuard', {})
        for key in ('closedTiles','unsupportedTiles','submergedTiles','heightMismatchTiles'):
            record[key] += int(previous.get(key, 0))
        if not samples:
            record['samples'] = previous.get('samples', [])
        collision['actorSurfaceGuard'] = record
        collision['walkableCells'] = int(np.count_nonzero(result))
        collision['walkableFraction'] = round(collision['walkableCells']/result.size, 4)
        GLB.write_grid(package, manifest, result)
        GLB.write_manifest(package/'world.json', manifest)
    print(f"[actor guard] {package.name}: {int(bad.sum())} unsupported folded tiles closed", flush=True)
    return dict(record, newlyClosedTiles=int(bad.sum()))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    print(json.dumps(guard(args.package.resolve(), not args.check), indent=2))
