#!/usr/bin/env python3
"""Pad native EWCG collision into the continent's addressable server frame.

Run after the native GLB/collision build, before refine_walk_heights,
open_walk_surfaces, stamp_solid_landmarks and guard_actor_surfaces. Native
blocked cells stay blocked here. Only newly addressable, supported, dry,
gentle ground can open; the shared opener owns authored roads and decks.

    python eloria-assets/tools/expand_continent_collision.py --region crownwater --check
    python eloria-assets/tools/expand_continent_collision.py --all --apply

--check computes a proposed change without writing. --apply changes only the
package's collision.bin, world.json and optional world-lod2.json. It never moves geometry or edits
native source posts, server configuration or registry. Source inputs remain
in their native frame so a native rebuild can be padded again. Repeating on
the same geometry/frame is a no-op, including after downstream grid guards.
Minimap framing follows the owned physical footprint, independently of the
square served grid; render_region_cartography.py produces its image.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
TOOLKIT = ROOT / 'eloria-assets/maps/nymara-regions/_toolkit'
sys.path.insert(0, str(TOOLKIT))
import glb_reader as GLB  # noqa: E402
from open_walk_surfaces import encode  # noqa: E402

HEADER = struct.Struct('<4sHHII')
CELL = .5
SCHEMA = 1
MAX_GRADIENT = .8
WATER_CLEARANCE = .0
EXISTING_WADE_DEPTH = .25  # Same shallow-water allowance as the shared opener/guard.


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pair(value, name, *, integer=False):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f'{name}: expected two coordinates')
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in value):
        raise ValueError(f'{name}: expected numeric coordinates')
    result = np.asarray(value, dtype=float)
    if not np.isfinite(result).all() or (integer and not np.equal(result, np.round(result)).all()):
        raise ValueError(f'{name}: expected finite {"integer " if integer else ""}coordinates')
    return result.astype(int) if integer else result


def frame_spec(entry: dict) -> dict:
    native_origin = pair(entry['nativeServerOrigin'], 'nativeServerOrigin', integer=True)
    native_cells = pair(entry['nativeServerCells'], 'nativeServerCells', integer=True)
    origin = pair(entry['serverOrigin'], 'serverOrigin', integer=True)
    cells = pair(entry['serverCells'], 'serverCells', integer=True)
    shift = pair(entry['serverTileShift'], 'serverTileShift', integer=True)
    if (native_cells <= 0).any() or (cells <= 0).any() or cells[0] != cells[1] or (cells % 6).any():
        raise ValueError('Server cells must be positive, square, and a multiple of six')
    if not np.array_equal(origin - native_origin, shift):
        raise ValueError('serverTileShift disagrees with origin delta')
    if (shift < 0).any() or (shift + native_cells > cells).any():
        raise ValueError('New frame must contain the entire native grid without cropping')
    bounds = [[int(-origin[0]), int(origin[1]-cells[1])],
              [int(cells[0]-origin[0]), int(origin[1])]]
    if not np.array_equal(np.asarray(entry['serverBounds']), bounds):
        raise ValueError('serverBounds disagrees with origin and cells')
    map_bounds=bounds
    if entry.get('ownershipPolygon'):
        polygon=np.asarray(entry['ownershipPolygon'],float)
        translation=np.asarray(entry['translation'],float)[[0,2]]
        local=polygon-translation
        map_bounds=[np.floor(local.min(axis=0)).astype(int).tolist(),
                    np.ceil(local.max(axis=0)).astype(int).tolist()]
    elif entry.get('nativePlayableBounds'):
        map_bounds=entry['nativePlayableBounds']
    return dict(nativeServerOrigin=native_origin.tolist(), nativeServerCells=native_cells.tolist(),
                serverOrigin=origin.tolist(), serverCells=cells.tolist(),
                serverTileShift=shift.tolist(), serverBounds=bounds,mapBounds=map_bounds)


def read_ewcg(raw: bytes):
    if len(raw) < HEADER.size:
        raise ValueError('Truncated EWCG header')
    magic, version, flags, width, height = HEADER.unpack_from(raw)
    if magic != b'EWCG' or version not in (1, 2):
        raise ValueError('Expected EWCG v1 or v2')
    # Both supported versions define this word as reserved. There is no
    # documented extra plane to resize, so an unknown extension must fail.
    if flags != 0:
        raise ValueError(f'Unsupported EWCG flags/reserved word: {flags}')
    if width <= 0 or height <= 0 or len(raw) != HEADER.size + width*height:
        raise ValueError('EWCG length differs from its single height plane (truncated or unexpected tail)')
    grid = np.frombuffer(raw, dtype=np.uint8, offset=HEADER.size).reshape(height, width).copy()
    return grid, version, flags


def gentle_surface(covered, top, maximum=MAX_GRADIENT):
    """Check each visible neighbour pair, so a discontinuity cannot average out.

    Missing neighbours cannot supply ground. A supported edge sample itself
    remains eligible; the final actor-centre guard handles the server fold.
    """
    gentle = covered & np.isfinite(top)
    for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
        ay = slice(0, top.shape[0]-dy)
        by = slice(dy, top.shape[0])
        ax = slice(max(0, -dx), min(top.shape[1], top.shape[1]-dx))
        bx = slice(max(0, dx), min(top.shape[1], top.shape[1]+dx))
        both = covered[ay, ax] & covered[by, bx]
        difference = np.zeros(both.shape)
        np.subtract(top[ay, ax], top[by, bx], out=difference, where=both)
        steep = both & (np.abs(difference) > maximum*CELL*np.hypot(dx, dy)+1e-7)
        gentle[ay, ax] &= ~steep
        gentle[by, bx] &= ~steep
    return gentle


def expanded_grid(old, spec, current_origin, covered, top, wet, water, encoding):
    """Compose the padded mask without ever opening a native blocked cell."""
    width, height = np.asarray(spec['serverCells'])*2
    shape = (int(height), int(width))
    if any(array.shape != shape for array in (covered, top, wet, water)):
        raise ValueError('Sampled geometry does not match expanded half-metre frame')
    old_origin = pair(current_origin, 'current serverOrigin', integer=True)
    shift = (np.asarray(spec['serverOrigin'])-old_origin)*2
    dx, dy = map(int, shift)
    if dx < 0 or dy < 0 or dx+old.shape[1] > shape[1] or dy+old.shape[0] > shape[0]:
        raise ValueError('Current grid cannot be copied into new frame without cropping')
    prior = np.zeros(shape, dtype=bool)
    prior[dy:dy+old.shape[0], dx:dx+old.shape[1]] = old != 0
    native = np.zeros(shape, dtype=bool)
    nx, ny = np.asarray(spec['serverTileShift'])*2
    nw, nh = np.asarray(spec['nativeServerCells'])*2
    native[ny:ny+nh, nx:nx+nw] = True
    supported = covered & np.isfinite(top)
    submerged = wet & (top < water - EXISTING_WADE_DEPTH - 1e-6)
    dry = supported & (~wet | (top >= water + WATER_CLEARANCE - 1e-6))
    # Already-open padding is recomputed too when geometry changes. Native
    # mask ownership is immutable until the explicit shared opener runs.
    padding = ~native & dry & gentle_surface(supported, top)
    opened = (native & prior & supported & ~submerged) | padding
    grid, new_encoding = encode(np.where(opened, top, np.nan), deepcopy(encoding))
    if (native & ~prior & (grid != 0)).any():
        raise AssertionError('Native blocked mask was opened')
    return grid, new_encoding, {
        'nativeBlockedPreserved': int((native & ~prior).sum()),
        'oldWalkableUnsupportedClosed': int((prior & ~supported).sum()),
        'oldWalkableSubmergedClosed': int((prior & supported & submerged).sum()),
        'paddingWalkableCells': int(padding.sum()),
        'walkableCells': int(opened.sum()),
    }


def sample_geometry(path: Path, spec):
    document, body = GLB.load(path)
    # Include the tiny StreamThreshold: it is explicitly authored navigation.
    # Exclude old copied preview variants even when a child is named Terrain_.
    _, parents = GLB.hierarchy(document)
    def native_node(index):
        while True:
            name = document['nodes'][index].get('name', '')
            if name.startswith('StreamView_') or '_StreamOverflow_' in name:
                return False
            if index not in parents:
                return True
            index = parents[index]
    selected = sorted({n for prefix in ('Terrain_', 'Walk_') for n in GLB.named(document, prefix)
                       if native_node(n)})
    water_nodes = [n for n in GLB.named(document, 'Water_') if native_node(n)]
    if not selected:
        raise ValueError('Packaged GLB contains no Terrain_/Walk_ navigation nodes')
    width, height = (np.asarray(spec['serverCells'])*2).tolist()
    ox, oy = spec['serverOrigin']
    # Sample the highest upward surface even if steep, then reject its slope.
    # Otherwise a steep bank could reveal a lower, buried bridge as a floor.
    covered, top = GLB.rasterise(GLB.triangles(document, body, selected), width, height,
                                 -ox, oy, CELL, upward=.001)
    wet, water = GLB.rasterise(GLB.triangles(document, body, water_nodes), width, height,
                              -ox, oy, CELL, upward=.001)
    return covered, top, wet, water


def shifted_tiles(value, delta, path='serverTiles'):
    if isinstance(value, list) and len(value) == 2 and all(isinstance(v, (int, float)) for v in value):
        tile = pair(value, path, integer=True)
        return (tile + delta).tolist()
    if isinstance(value, list):
        return [shifted_tiles(v, delta, path) for v in value]
    if isinstance(value, dict):
        return {k: shifted_tiles(v, delta, path+'.'+k) for k, v in value.items()}
    raise ValueError(f'{path}: unrecognized tile collection')


def shift_metadata(value, delta):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ('serverTile', 'serverTiles'):
                value[key] = shifted_tiles(item, delta, key)
            else:
                shift_metadata(item, delta)
    elif isinstance(value, list):
        for item in value:
            shift_metadata(item, delta)


def restate_metadata(manifest, spec, *, native_metadata):
    if native_metadata:
        delta = np.asarray(spec['serverTileShift'])
        shift_metadata(manifest, delta)
        for theme in manifest.get('contentLayout', {}).get('gauntlets', {}).values():
            for key in ('keeperTile', 'returnTile'):
                if key in theme:
                    theme[key] = shifted_tiles(theme[key], delta, key)
    ox, oy = spec['serverOrigin']
    cells = spec['serverCells']
    low, high = spec['serverBounds']
    frames = {frame['portal']:frame for frame in manifest.get('streamingBorders', [])}
    for portal in manifest.get('portals', []):
        if portal.get('type') == 'map-transition':
            if portal['id'] in frames:
                frame = frames[portal['id']]
                anchor = frame['anchor']
                outward = pair(frame['outward'], 'streaming outward')
                if not np.isfinite(anchor).all() or len(anchor) != 3 or not np.isclose(np.linalg.norm(outward), 1.):
                    raise ValueError('Invalid streaming frame anchor or outward vector')
                # Some native builders snap portals against their smaller old
                # grid after SB places them. Restore the authored trigger one
                # metre beyond the actual boundary before computing its tile.
                portal['position'] = [float(anchor[0]+outward[0]), float(anchor[1]),
                                      float(anchor[2]+outward[1])]
            position = portal['position']
            portal['serverTile'] = [int(np.floor(position[0]+ox)), int(np.floor(oy-position[2]))]
    transform = manifest['coordinateTransform']
    transform.update(serverOrigin=[ox, oy], serverCells=cells,
                     addressableWorldBounds={'min':low, 'max':high})
    asset = manifest['asset']
    asset['serverCells'] = cells[0]
    low,high=spec.get('mapBounds',spec['serverBounds'])
    for key in ('playableBounds', 'mapBounds'):
        bounds = asset.get(key)
        if bounds:
            bounds['min'][0], bounds['min'][-1] = low
            bounds['max'][0], bounds['max'][-1] = high
    # mapBounds controls Tab framing before playableBounds. Keep actual mesh
    # bounds untouched; only the addressable horizontal frame is expanded.
    if not asset.get('playableBounds') and not asset.get('mapBounds'):
        mesh = asset['bounds']
        asset['mapBounds'] = {'min':[low[0],mesh['min'][1],low[1]],
                              'max':[high[0],mesh['max'][1],high[1]]}
    collision = manifest['collision']
    collision.update(width=cells[0]*2, height=cells[1]*2, originMetres=[-ox, oy], cellMetres=CELL)
    if 'cellSize' in collision:
        collision['cellSize'] = CELL
    minimap = manifest['minimap']
    image_size=[round(high[i]-low[i]) for i in range(2)]
    minimap.update(worldMin=low, worldMax=high, imageSize=image_size, pixelsPerMetre=1.,
                   transform={'pixelX':{'scale':1., 'offset':-low[0]},
                              'pixelY':{'scale':1., 'offset':-low[1]},
                              'formula':'pixel_x = world_x * scale + offset; pixel_y = world_z * scale + offset'})
    for key, value in {'pixels':image_size[0], 'size':image_size, 'metresPerPixel':1.,
                       'centre':[(low[0]+high[0])/2,(low[1]+high[1])/2]}.items():
        if key in minimap:
            minimap[key] = value


def serialized(manifest, original):
    text = original.decode('utf-8')
    lines = text.splitlines()
    indent = len(lines[1])-len(lines[1].lstrip(' ')) if len(lines)>1 else 2
    output = json.dumps(manifest, indent=indent or 2, ensure_ascii=False)+'\n'
    return output.replace('\n', '\r\n').encode('utf-8') if '\r\n' in text else output.encode('utf-8')


def sync_lod_metadata(package, main, spec, *, apply=False):
    """The optional LOD manifest uses the same authoritative grid and frame."""
    path=package/'world-lod2.json'
    if not path.is_file():return False
    original=path.read_bytes();lod=json.loads(original)
    origin=lod['coordinateTransform']['serverOrigin']
    cells=lod['asset'].get('serverCells',lod['coordinateTransform'].get('serverCells'))
    cells=[cells,cells] if isinstance(cells,(int,float)) else cells
    native=origin==spec['nativeServerOrigin'] and cells==spec['nativeServerCells']
    expanded=origin==spec['serverOrigin'] and cells==spec['serverCells']
    if not (native or expanded):raise ValueError('LOD metadata is neither native nor expanded frame')
    restate_metadata(lod,spec,native_metadata=native and not expanded)
    nodes=lod['collision'].get('nodeNames')
    lod['collision']=deepcopy(main['collision'])
    if nodes is not None:lod['collision']['nodeNames']=nodes
    lod['continentGeography']=deepcopy(main['continentGeography'])
    lod_glb=package/lod['asset'].get('glb','world-lod2.glb')
    lod['continentGeography']['geometrySha256']=sha(lod_glb.read_bytes())
    lod['continentGeography']['collisionGeometry']='world.glb'
    payload=serialized(lod,original)
    if apply and payload!=original:
        if path.read_bytes()!=original:raise ValueError('LOD metadata changed during padding')
        temporary=path.with_name(path.name+'.continent.tmp');temporary.write_bytes(payload);temporary.replace(path)
    return payload!=original


def expand(package: Path, identity: str, geography: dict, geography_hash: str, *, apply=False):
    package = package.resolve()
    spec = frame_spec(geography['regions'][identity])
    path = package/'world.json'
    original = path.read_bytes()
    manifest = json.loads(original)
    collision = manifest['collision']
    binary = package/collision['binary']
    if binary.resolve().parent != package:
        raise ValueError('Collision binary must be a direct child of its package')
    raw = binary.read_bytes()
    grid, version, flags = read_ewcg(raw)
    transform = manifest['coordinateTransform']
    if float(transform.get('metresPerTile', 0)) != 1 or not transform.get('invertServerY', False):
        raise ValueError('Continent padding requires one-metre tiles with inverted server Y')
    if float(collision.get('cellMetres', collision.get('cellSize', 0))) != CELL:
        raise ValueError('Continent padding requires a half-metre native grid')
    if [collision.get('width'), collision.get('height')] != [grid.shape[1], grid.shape[0]]:
        raise ValueError('Manifest and EWCG dimensions disagree')
    encoding = collision['heightEncoding']
    if not np.isfinite([encoding['origin'], encoding['step']]).all() or encoding['step'] <= 0:
        raise ValueError('Invalid height encoding')
    levels = encoding.get('range', [1, 255])
    if len(levels) != 2 or levels[0] != 1 or not 1 < levels[1] <= 255 or grid.max() > levels[1]:
        raise ValueError('Height encoding must cover every nonzero EWCG byte')
    current_origin = pair(transform['serverOrigin'], 'current serverOrigin', integer=True).tolist()
    native_state = current_origin == spec['nativeServerOrigin'] and [grid.shape[1]//2,grid.shape[0]//2] == spec['nativeServerCells']
    expanded_state = current_origin == spec['serverOrigin'] and [grid.shape[1]//2,grid.shape[0]//2] == spec['serverCells']
    if grid.shape[0] % 2 or grid.shape[1] % 2 or not (native_state or expanded_state):
        raise ValueError('Current manifest/grid is neither the declared native nor expanded frame')
    if 'originMetres' in collision and collision['originMetres'] != [-current_origin[0],current_origin[1]]:
        raise ValueError('Collision origin disagrees with current coordinate transform')
    glb = package/manifest['asset'].get('glb', 'world.glb')
    geometry_hash = sha(glb.read_bytes())
    previous = manifest.get('continentGeography', {})
    marker = dict(schemaVersion=SCHEMA, **spec, geographySha256=geography_hash, geometrySha256=geometry_hash)
    same_inputs = all(previous.get(k) == v for k,v in marker.items() if k != 'geographySha256')
    # Preserve later opener/stamp/guard refinements instead of reopening their
    # rejected padding cells on a repeated publication of unchanged geometry.
    if expanded_state and same_inputs:
        expected = deepcopy(manifest)
        restate_metadata(expected, spec, native_metadata=False)
        if expected != manifest:
            raise ValueError('Expanded metadata was altered after padding; rebuild from native source')
        previous['geographySha256'] = geography_hash
        output = serialized(manifest, original) if previous != json.loads(original)['continentGeography'] else original
        lod_changed=sync_lod_metadata(package,manifest,spec,apply=False)
        if apply and output != original:
            if path.read_bytes() != original or binary.read_bytes() != raw:
                raise ValueError('Package changed during metadata validation')
            temporary = path.with_name(path.name+'.continent.tmp')
            temporary.write_bytes(output)
            temporary.replace(path)
        if apply:sync_lod_metadata(package,manifest,spec,apply=True)
        return dict(region=identity, changed=output != original or lod_changed, alreadyExpanded=True,
                    lodMetadataChanged=lod_changed,
                    collisionSha256=sha(raw), manifestSha256=sha(output), **previous.get('result', {}))
    if expanded_state and not native_state and not previous:
        raise ValueError('Expanded grid has no continentGeography provenance; refusing ambiguous tile shift')
    samples = sample_geometry(glb, spec)
    result, new_encoding, stats = expanded_grid(grid, spec, current_origin, *samples, encoding)
    restate_metadata(manifest, spec, native_metadata=native_state)
    collision = manifest['collision']
    collision.update(heightEncoding=new_encoding, walkableCells=int(np.count_nonzero(result)),
                     walkableFraction=round(float(np.count_nonzero(result))/result.size, 4))
    # These are certificates for the old half-grid, not for the new origin.
    # The required final passes recreate them from the actual geometry.
    for key in ('refinedHeights', 'openedWalkSurfaces', 'actorSurfaceGuard'):
        collision.pop(key, None)
    marker['nativeCollisionSha256'] = sha(raw) if native_state else previous['nativeCollisionSha256']
    marker['result'] = dict(stats, maximumPaddingGradient=MAX_GRADIENT,
                            minimumWaterClearanceMetres=WATER_CLEARANCE,
                            existingWadeDepthMetres=EXISTING_WADE_DEPTH)
    manifest['continentGeography'] = marker
    payload = HEADER.pack(b'EWCG', version, flags, result.shape[1], result.shape[0])+result.tobytes()
    output = serialized(manifest, original)
    lod_changed=sync_lod_metadata(package,manifest,spec,apply=False)
    report = dict(region=identity, changed=(payload != raw or output != original), alreadyExpanded=False,
                  collisionSha256=sha(payload), manifestSha256=sha(output), lodMetadataChanged=lod_changed, **stats)
    if apply:
        if path.read_bytes() != original or binary.read_bytes() != raw or sha(glb.read_bytes()) != geometry_hash:
            raise ValueError('Package changed during sampling; retry after its build has finished')
        # Validate everything before writing either file; each replacement is atomic.
        for target, data in ((binary,payload),(path,output)):
            temporary = target.with_name(target.name+'.continent.tmp')
            temporary.write_bytes(data)
            temporary.replace(target)
        sync_lod_metadata(package,manifest,spec,apply=True)
    return report


def region_packages(root=ROOT):
    registry = json.loads((root/'godot-client/data/maps/registry.json').read_text(encoding='utf-8'))['maps']
    return {key:(root/'godot-client'/entry['manifest'].removeprefix('res://')).resolve().parent
            for key,entry in registry.items() if entry.get('manifest')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--geography', type=Path, default=ROOT/'eloria-assets/maps/nymara-regions/continent-geography.json')
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--region', action='append')
    choice.add_argument('--all', action='store_true')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--apply', action='store_true')
    parser.add_argument('--package', type=Path, help='Explicit package for exactly one --region (isolated fixtures)')
    args = parser.parse_args()
    raw = args.geography.read_bytes()
    geography = json.loads(raw)
    selected = list(geography['regions']) if args.all else args.region
    if args.package and (args.all or len(selected) != 1):
        parser.error('--package requires exactly one --region')
    packages = region_packages() if not args.package else {selected[0]:args.package}
    for identity in selected:
        print(json.dumps(expand(packages[identity],identity,geography,sha(raw),apply=args.apply)), flush=True)


if __name__ == '__main__':
    main()
