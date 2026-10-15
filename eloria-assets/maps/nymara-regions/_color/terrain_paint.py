"""Resolve geographic paint corners after all physical landscape finishing.

Only Terrain paint copies are edited. Competing neighboring recipes own whole
shared terrain faces by their distance to the actual finite common edge. The
two members of a continent recipe, and all three members of a road recipe,
stay together. Their authored alpha masks and UVs remain unchanged.
"""
from collections import defaultdict
import re

import numpy as np

import continent_geography as G
from landscape_finish import Substrate, substrate_name, collar_layers

REGIONS = ('crownwater', 'four_gates', 'manymouth_delta', 'ssarathi_ruins', 'grey_moors')
BLEND = re.compile(r'_ContinentBlend_(.*?)_([01])(?=_StreamCell_|$)')


def paint_record(name, connections, region):
    """Return a bundle and its visual layer, excluding nested recipe copies."""
    if not name.startswith('Terrain_'):
        return None
    collars = collar_layers(name)
    if len(collars) > 1:
        return {'nested': True}
    if collars:
        identity, layer = collars[0]
        peers = [e['region'] for e in connections[identity]['ends'] if e['region'] != region]
        if len(peers) != 1:
            raise ValueError(f'Paint recipe {identity} has no unique neighboring region')
        return {'family': 'collar', 'bundle': identity, 'peer': peers[0],
                'bias': {'Turf': .002, 'Frost': .004, 'Road': .006}[layer]}
    match = BLEND.search(name)
    if match:
        return {'family': 'continent', 'bundle': match.group(1), 'peer': match.group(1),
                'bias': .012 + .008 * int(match.group(2))}
    return None


def _face_keys(mesh):
    xz = mesh.positions[mesh.indices.reshape(-1, 3)][:, :, [0, 2]]
    order = np.lexsort((xz[:, :, 1], xz[:, :, 0]), axis=1)
    sorted_xz = np.take_along_axis(xz, order[:, :, None], axis=1)
    return np.ascontiguousarray(np.rint(sorted_xz.reshape(-1, 6) * 1e6).astype('<i8'))


def assign_faces(meshes, records, distance):
    """Retain one full recipe per common face; ties use sorted bundle identity.

The candidate set comes from existing paint faces, so a neighbor whose band
does not reach this face cannot suppress the authored recipe that does.
"""
    names = sorted(records)
    if not names:
        return 0
    keys = [_face_keys(meshes[name]) for name in names]
    sizes = np.array([len(k) for k in keys])
    if not sizes.sum():
        return 0
    joined = np.concatenate(keys)
    dtype = np.dtype((np.void, joined.dtype.itemsize * 6))
    unique, inverse = np.unique(joined.view(dtype).ravel(), return_inverse=True)
    points = unique.view('<i8').reshape(-1, 3, 2).mean(axis=1) / 1e6
    per_name = dict(zip(names, np.split(inverse, np.cumsum(sizes)[:-1])))
    bundles = sorted({r['bundle'] for r in records.values()})
    best = np.full(len(unique), np.inf)
    winners = np.full(len(unique), -1, np.int32)
    for index, bundle in enumerate(bundles):
        members = [name for name in names if records[name]['bundle'] == bundle]
        ids = np.unique(np.concatenate([per_name[name] for name in members]))
        d = distance(records[members[0]]['peer'], points[ids])
        if not np.isfinite(d).all():
            raise ValueError(f'Paint bundle {bundle} has no finite shared edge')
        nearer = d < best[ids] - 1e-9
        best[ids[nearer]], winners[ids[nearer]] = d[nearer], index
    removed = 0
    for name in names:
        mesh = meshes[name]
        faces = mesh.indices.reshape(-1, 3)
        keep = winners[per_name[name]] == bundles.index(records[name]['bundle'])
        removed += int((~keep).sum())
        mesh.indices = faces[keep].ravel()
    return removed


def apply(build, region):
    if region not in REGIONS:
        return None
    previous = getattr(build, 'geographic_paint_finish', None)
    if previous is not None:
        return previous
    connections = {c['id']: c for c in G.plan()['connections']}
    records, dropped = {}, set()
    for name, mesh in build.terrain_meshes.items():
        record = paint_record(name, connections, region)
        if not record:
            continue
        if record.get('nested'):
            dropped.add(name)
        elif mesh.triangle_count:
            records[name] = record
    # Each family has its own visual level. Within a family, both layers of a
    # neighboring recipe agree on ownership of the same underlying face.
    removed = {}
    for family in ('continent', 'collar'):
        selected = {n: r for n, r in records.items() if r['family'] == family}
        removed[family] = assign_faces(build.terrain_meshes, selected,
            lambda peer, xz: G.boundary_sample(region, xz, maximum=np.inf, peer=peer)[0])
    bases = defaultdict(list)
    for name, mesh in build.terrain_meshes.items():
        if name.startswith('Terrain_') and not paint_record(name, connections, region) and mesh.triangle_count:
            bases[substrate_name(name)].append(mesh)
    samplers = {}
    seated_vertices = 0
    for name in sorted(records):
        mesh = build.terrain_meshes[name]
        if not mesh.triangle_count:
            dropped.add(name)
            continue
        root = substrate_name(name)
        if root not in samplers:
            if root not in bases:
                raise ValueError(f'Geographic paint lost its actual substrate: {name}')
            samplers[root] = Substrate(bases[root])
        # Unreferenced vertices need not be sampled: ownership clipping may
        # legitimately have removed their matching physical substrate.
        ids = np.unique(mesh.indices)
        mesh.positions[ids, 1] = samplers[root].sample(mesh.positions[ids][:, [0, 2]]) + records[name]['bias']
        mesh.recompute_normals(180)
        seated_vertices += len(ids)
    for name in dropped:
        del build.terrain_meshes[name]
    for spec in getattr(build, 'streaming_borders', []):
        if 'sceneNodes' in spec:
            spec['sceneNodes'] = [name for name in spec['sceneNodes'] if name not in dropped]
    report = {'version': 1, 'region': region, 'removedCompetingFaces': removed,
              'removedPaintNodes': sorted(dropped), 'seatedPaintVertices': seated_vertices,
              'physicalMeshesChanged': 0, 'maximumVisualBiasMetres': .020}
    build.geographic_paint_finish = report
    build.notes.append('Geographic paint corners use the nearest actual shared edge; each full neighboring recipe stays together above unchanged physical substrate.')
    return report
