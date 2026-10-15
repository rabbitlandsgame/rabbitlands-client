"""Soften the small north-east three-recipe paint corner after arbitration.

The selected recipe stays on its existing faces. Near its competition edge it
fades into the literal native meadow below, so no competing coplanar recipe is
reintroduced. Only clipped visual copies change; common-line coverage, soil,
walking surfaces, water and placements remain untouched.
"""
from pathlib import Path
import sys
import numpy as np

REGIONS = Path(__file__).resolve().parents[2] / 'nymara-regions'
sys.path[:0] = [str(REGIONS / p) for p in ('_toolkit', '_northern', '_color')]
from amberwood.mesh import Mesh
from amberwood.mesh import merge
from amberwood.materials import base_material
import streaming_borders as SB
import terrain_paint as C
from road_profiles import _clip_scalar

REGION = 'four_gates'
PEERS = ('mirrorhold', 'amethyst_barrens', 'sunmane_steppe')
BOUNDS = (186., 211., -213., -181.)  # x min/max, z min/max, Four local metres
BOX_FEATHER = 4.
COMMON_LINE_FEATHER = .75
RECIPE_INSET = 1.5
RECIPE_FEATHER = 2.
MAX_PAINT_EDGE = .30
COMMON_LINE_KEEP = .20


def smooth(value):
    value = np.clip(value, 0., 1.)
    return value * value * (3. - 2. * value)


def corner_weight(xz, distances):
    """Zero on the common line and box edge; smoothly reaches one inland."""
    x, z = np.asarray(xz).T
    x0, x1, z0, z1 = BOUNDS
    edge_distance = np.minimum.reduce((x-x0, x1-x, z-z0, z1-z))
    return smooth(edge_distance / BOX_FEATHER) * smooth((np.min(distances, axis=1)-COMMON_LINE_KEEP) / COMMON_LINE_FEATHER)


def coverage(xz, distances, peer):
    """Selected opaque coverage declines before a coarse rival-face boundary.

    The 1.5 m inset covers the original one-metre triangle's diagonal, then a
    two-metre wash returns to full selected coverage. Native grass remains the
    continuous underlying colour. Original discarded mask fragments stay out.
    """
    index = PEERS.index(peer)
    rivals = np.min(np.delete(distances, index, axis=1), axis=1)
    retention = smooth((rivals - distances[:, index] - RECIPE_INSET) / RECIPE_FEATHER)
    return 1. - corner_weight(xz, distances) * (1. - retention)


def refine(mesh, maximum=MAX_PAINT_EDGE):
    """Subdivide only paint, barycentrically preserving every old face plane."""
    result = mesh.copy()
    columns = [result.positions, result.normals, result.uvs, result.colors]
    values = np.concatenate(columns, axis=1)[result.indices.reshape(-1, 3)]
    for _ in range(12):
        edge = np.max([np.linalg.norm(values[:, (i+1) % 3, :3] - values[:, i, :3], axis=1)
                       for i in range(3)], axis=0)
        split = edge > maximum + 1e-9
        if not split.any():
            break
        a, b, c = (values[split, i] for i in range(3))
        ab, bc, ca = (a+b)/2, (b+c)/2, (c+a)/2
        values = np.concatenate((values[~split], np.stack((a, ab, ca), axis=1),
                                 np.stack((ab, b, bc), axis=1), np.stack((ca, bc, c), axis=1),
                                 np.stack((ab, bc, ca), axis=1)))
    else:
        raise ValueError('Corner paint failed to reach bounded visual spacing')
    v = values.reshape(-1, values.shape[-1])
    return Mesh(positions=v[:, :3], normals=v[:, 3:6], uvs=v[:, 6:8], colors=v[:, 8:12],
                indices=np.arange(len(v)), material=mesh.material)


def apply(build):
    previous = getattr(build, 'four_corner_paint', None)
    if previous is not None:
        return previous
    if getattr(build, 'geographic_paint_finish', None) is None:
        raise ValueError('Four corner paint requires the frozen recipe arbitration first')
    x0, x1, z0, z1 = BOUNDS
    edge = np.array([(x0+x1)/2, 0.])
    forward, side = np.array([0., 1.]), np.array([1., 0.])
    changed = []
    import corner_material as CM
    recipes = {}
    for name, mesh in list(build.terrain_meshes.items()):
        match = C.BLEND.search(name)
        if not name.startswith('Terrain_') or not match or match.group(1) not in PEERS or not mesh.triangle_count:
            continue
        referenced = mesh.positions[np.unique(mesh.indices)][:, [0, 2]]
        low, high = referenced.min(axis=0), referenced.max(axis=0)
        if high[0] <= x0 or low[0] >= x1 or high[1] <= z0 or low[1] >= z1:
            continue
        if mesh.colors is None:
            raise ValueError('Authored recipe unexpectedly lacks its coverage mask: ' + name)
        inside = SB.clip_rect(mesh, edge, forward, side, z0, z1, (x1-x0)/2)
        if not inside.triangle_count:
            continue
        outside = SB.outside_rect(mesh, edge, forward, side, z0, z1, (x1-x0)/2)
        distances = np.stack([C.G.boundary_sample(REGION, inside.positions[:, [0, 2]], maximum=np.inf, peer=p)[0]
                              for p in PEERS], axis=1)
        common = _clip_scalar(inside, distances.min(axis=1)-COMMON_LINE_KEEP)
        inside = _clip_scalar(inside, COMMON_LINE_KEEP-distances.min(axis=1))
        outside = merge([outside, common], material=mesh.material)
        # Preserve the literal MASK contour before replacing its semantics
        # with ordinary opaque PBR. At zero feather weight, coverage is exactly
        # the original binary cutout, not raw fractional vertex alpha.
        inside = _clip_scalar(inside, .5-inside.colors[:, 3])
        soft_name = name + '_CornerBlend'
        if inside.triangle_count:
            inside = refine(inside)
            points = inside.positions[:, [0, 2]]
            distances = np.stack([C.G.boundary_sample(REGION, points, maximum=np.inf, peer=p)[0]
                                  for p in PEERS], axis=1)
            if not np.isfinite(distances).all():
                raise ValueError('Missing actual corner recipe boundary')
            # An ordinary opaque baked material removes binary grain aliasing.
            # The exact old MASK contour has already been clipped as geometry.
            root = C.substrate_name(name)
            bases = [m for n, m in build.terrain_meshes.items() if n == root or n.startswith(root+'_StreamCell_')]
            if not bases:
                raise ValueError('Corner blend has no literal native substrate: '+root)
            base = merge(bases, material=bases[0].material)
            # Compacted native UVs need not be affine over the entire map.
            # Prove the actual local field before baking; never alter it.
            base = SB.clip_rect(base, edge, forward, side, z0, z1, (x1-x0)/2)
            paint_source = SB.clip_rect(mesh, edge, forward, side, z0, z1, (x1-x0)/2)
            material = CM.PREFIX + match.group(1) + '_' + base_material(mesh.material)
            recipes[material] = {'peer': match.group(1), 'paintMaterial': mesh.material,
                'paintUv': CM.affine_uv(paint_source), 'baseMaterial': base.material, 'baseUv': CM.affine_uv(base)}
            inside.colors[:, 3] = 1.
            inside.uvs = (points-np.array([x0, z0]))/np.array([x1-x0, z1-z0])
            inside.material = material
            build.terrain_meshes[soft_name] = inside
        if outside.triangle_count:
            build.terrain_meshes[name] = outside
        else:
            del build.terrain_meshes[name]
        for frame in build.streaming_borders:
            if name in frame.get('sceneNodes', []):
                if inside.triangle_count:
                    frame['sceneNodes'].append(soft_name)
                if not outside.triangle_count:
                    frame['sceneNodes'].remove(name)
        changed.append({'source': name, 'soft': soft_name if inside.triangle_count else None,
                        'outsideTriangles': outside.triangle_count, 'softTriangles': inside.triangle_count})
    report = {'version': 1, 'bounds': list(BOUNDS), 'boxFeatherMetres': BOX_FEATHER,
              'commonLineFeatherMetres': COMMON_LINE_FEATHER, 'recipeInsetMetres': RECIPE_INSET,
              'recipeFeatherMetres': RECIPE_FEATHER, 'maximumVisualEdgeMetres': MAX_PAINT_EDGE,
              'physicalMeshesChanged': 0, 'paintHeightChanges': 0, 'changed': changed,
              'coverageMode': 'opaque linear-light albedo and normalized normal PBR bake',
              'commonLineMaterialCutTargetMetres': COMMON_LINE_KEEP,
              'commonLineSemantics': 'Original material retained at the line; interpolated cut at polyline vertices may be inside the nominal strip, where the bake still uses the original recipe at full weight.',
              'bakedTextureSize': [800, 1024]}
    build.four_corner_paint = report
    build.four_corner_materials = recipes
    build.notes.append('The small north-east recipe corner uses an ordinary opaque PBR wash into existing meadow; physical surfaces and the literal common-line material remain unchanged.')
    return report
