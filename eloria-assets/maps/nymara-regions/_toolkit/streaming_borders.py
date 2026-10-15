"""Authored, reciprocal road collars for exterior scene streaming.

Coordinates are tile centres. The seam sits one metre inward from the trigger;
the two-metre arrival offset therefore preserves the traveller's world position.
Approaches are disjoint pieces of the actual region, stored once and shared
between active and resident views. Only an invisible two-metre threshold keeps
the authoritative crossing trigger supported beyond the rendered edge.
"""
import numpy as np
from amberwood.mesh import rotation_y
from amberwood.terrain import _compact

# Each pair shares its surface recipe and road-space texture coordinates.
# Frames are local: the client carries the traveller/camera between them.
LINKS = [
 ('amberwood-whitehorn', ('amberwood','north-pass',[67.5,55.2,-256.5],[0,-1]),
  ('whitehorn_range','west-pass',[-106.5,35.8,-54.5],[-1,0]), 'alpine'),
 ('amberwood-grey', ('amberwood','south-road',[122.5,11.1,107.5],[0,1]),
  ('grey_moors','north-gate',[-8.5,4,-256.5],[0,-1]), 'moor'),
 ('amberwood-mirrorhold', ('amberwood','east-road',[261.5,41.8,-28.5],[1,0]),
  ('mirrorhold','west-gorge',[-110.5,24,20.5],[-1,0]), 'upland'),
 ('whitehorn-mirrorhold', ('whitehorn_range','south-gate',[-1.5,12.1,107.5],[0,1]),
  ('mirrorhold','north-pass',[-76.5,85,-281.5],[0,-1]), 'alpine'),
 ('whitehorn-amethyst', ('whitehorn_range','east-pass',[260.5,36.1,-30.5],[1,0]),
  ('amethyst_barrens','north-pass',[54.5,12,-261.5],[0,-1]), 'scree'),
 ('mirrorhold-amethyst', ('mirrorhold','east-road',[10.5,93,-281.5],[0,-1]),
  ('amethyst_barrens','west-road',[-110.5,8,-192.5],[-1,0]), 'scree'),
 ('grey-westhaven', ('grey_moors','west-waygate',[-105.5,4.95,6.5],[-1,0]),
  ('westhaven','north-road',[190.5,34,-213.5],[0,-1]), 'pasture'),
 ('mirrorhold-four-gates', ('mirrorhold','south-road',[175.5,4,92.5],[0,1]),
  ('four_gates','north',[.5,23,-195.5],[0,-1]), 'causeway'),
 ('four-gates-crownwater', ('four_gates','west',[-195.5,23,-.5],[-1,0]),
  ('crownwater','east-quay',[270.5,4,-10.5],[1,0]), 'causeway'),
 ('amethyst-sunmane', ('amethyst_barrens','south-road',[54.5,19,113.5],[0,1]),
  ('sunmane_steppe','north-track',[20.5,17,-265.5],[0,-1]), 'steppe'),
 ('four-gates-sunmane', ('four_gates','east',[195.5,23,-.5],[1,0]),
  ('sunmane_steppe','west-landing',[-113.5,4,-.5],[-1,0]), 'causeway'),
 ('sunmane-verdant', ('sunmane_steppe','south-track',[54.5,8,113.5],[0,1]),
  ('verdant_stair','east-pass-gate',[244.5,62,-94.5],[1,0]), 'steppe'),
 ('verdant-ssarathi', ('verdant_stair','west-quay-gate',[-102.5,4,.5],[-1,0]),
  ('ssarathi_ruins','east-causeway',[264.5,4,-88.5],[1,0]), 'causeway'),
 ('four-gates-ssarathi', ('four_gates','south',[.5,23,195.5],[0,1]),
  ('ssarathi_ruins','north-stair',[154.5,4,-264.5],[0,-1]), 'causeway'),
]
PALETTES = {
 'alpine': ('alpine_turf','alpine_snowfield','alpine_gravel'),
 'moor': ('meadow_grass','grey_heather_moor','packed_earth'),
 'upland': ('meadow_grass','alpine_turf','alpine_gravel'),
 'scree': ('alpine_turf','alpine_bedrock','alpine_gravel'),
 'pasture': ('meadow_grass','grey_heather_moor','packed_earth'),
 'causeway': ('alpine_gravel','rubble_stone','cobble_paving'),
 'steppe': ('steppe_sward','amethyst_barrens_dust','steppe_dust'),
}
ORIGINS = {'amberwood': (116,116), 'grey_moors': (116,116),
           'amethyst_barrens': (116,116), 'mirrorhold': (120,96),
           'whitehorn_range': (120,120), 'westhaven': (120,172),
           'crownwater': (120,120), 'four_gates': (198,198),
           'sunmane_steppe': (116,116), 'verdant_stair': (108,108),
           'ssarathi_ruins': (116,116)}
VIEW_PREFIX = 'StreamView_'
HALF_WIDTH = 110.0
VIEW_DEPTH = 240.0
SHOULDER_WIDTH = 28.0


def region_specs(region):
    from continent_geography import region_specs as geographic_specs
    return geographic_specs(region, LINKS)


def legacy_region_specs(region):
    """Legacy recipe defaults; geographic gates are authored separately."""
    result=[]
    for identity,a,b,palette in LINKS:
        for here,there,sign in ((a,b,1),(b,a,-1)):
            if here[0] == region:
                spec = dict(id=identity, portal=here[1], destination=there[0],
                    anchor=here[2], outward=here[3], uvSign=sign, palette=palette,
                    preloadDistance=240, retainDistance=320, blendDistance=90,
                    collarDepth=42, halfWidthTiles=3, viewHalfWidth=HALF_WIDTH,
                    viewDepth=VIEW_DEPTH, previewPrefix=VIEW_PREFIX+identity+'__',
                    overflowSuffix='_StreamOverflow_'+identity,
                    geometryMode='shared-cells-v2', sceneNodes=[])
                if palette == 'causeway':
                    spec.update(profile='causeway', waterBelowDeck=4.0, deckWidth=7.0)
                elif palette == 'pasture':
                    spec.update(profile='pasture')
                elif palette == 'steppe':
                    spec.update(profile='steppe')
                result.append(spec)
    return result


def materials_for(region):
    import continent_geography as geography
    specs = region_specs(region)
    result = {name for spec in specs for name in PALETTES[spec['palette']]}
    result |= geography.materials_for(region)
    if any(spec.get('profile') == 'causeway' for spec in specs):
        result |= {'water_lake', 'pale_ashlar'}
    return result


def _causeway_meshes(build, spec):
    """One shared bridge section meets the region's native deck at depth -42.

    Its walk skin, slab, curbs and piers have separate names so grounding never
    treats a parapet as the carriageway. The ordinary strip clipper partitions
    these world-space meshes into active, overflow and receiving geometry.
    """
    from amberwood import mesh as M
    edge = np.asarray(spec['anchor'], float)
    forward = np.asarray(spec['outward'], float)
    side = np.array([-forward[1], forward[0]])
    half = spec['deckWidth'] / 2
    def point(depth, lateral, rise=0):
        p = edge.copy()
        p[[0,2]] += forward * depth + side * lateral
        p[1] += rise
        return p
    # Ordering is relative to outward and its left normal: the top faces up.
    top = M.quad([point(-42,-half), point(80,-half), point(80,half), point(-42,half)],
                 material='cobble_paving')
    if top.normals[:,1].mean() < 0:
        top.flip_winding(); top.recompute_normals(180)
    relative = top.positions[:,[0,2]] - edge[[0,2]]
    top.uvs = np.stack([relative @ side, relative @ forward], axis=1) * spec['uvSign'] * .28
    build.terrain_meshes['Walk_StreamCauseway_' + spec['id']] = top
    parts = []
    for sign in (-1,1):
        parts.append(M.quad([point(-42,sign*half,-.8), point(80,sign*half,-.8),
                            point(80,sign*half), point(-42,sign*half)], material='pale_ashlar'))
        # A low curb marks the edge without hiding players or the lake.
        curb = M.box((122,.48,.38), material='pale_ashlar')
        curb.rotate_y(np.arctan2(-forward[1], forward[0]))
        centre = point(19,sign*(half+.19),.16)
        parts.append(curb.translate(*centre))
    for depth in range(-40,81,16):
        pier = M.box((1.25,6.0,6.5), material='rubble_stone')
        pier.rotate_y(np.arctan2(-forward[1], forward[0]))
        parts.append(pier.translate(*point(depth,0,-3.81)))
    for material in ('pale_ashlar','rubble_stone'):
        build.terrain_meshes['Structure_StreamCauseway_' + spec['id'] + '_' + material] = M.merge(
            [part for part in parts if part.material == material], material=material)
    for name, original in list(build.water_meshes.items()):
        build.water_meshes[name] = outside_rect(original, edge[[0,2]], forward, side, -42, 80)
    water = M.quad([point(-42,-HALF_WIDTH,-4), point(80,-HALF_WIDTH,-4),
                    point(80,HALF_WIDTH,-4), point(-42,HALF_WIDTH,-4)], material='water_lake')
    if water.normals[:,1].mean() < 0:
        water.flip_winding(); water.recompute_normals(180)
    relative = water.positions[:,[0,2]] - edge[[0,2]]
    water.uvs = np.stack([relative @ side, relative @ forward], axis=1) * spec['uvSign'] * .075
    build.water_meshes['Water_StreamCauseway_' + spec['id']] = water


def clip_plane(mesh, edge, normal, limit=0.):
    """Exact half-space clip, preserving UVs, colour coverage and winding."""
    if not mesh.triangle_count: return mesh.copy()
    columns=[mesh.positions,mesh.normals,mesh.uvs]
    if mesh.colors is not None: columns.append(mesh.colors)
    values=np.concatenate(columns,axis=1)
    distances=(mesh.positions[:,[0,2]]-edge)@normal-limit
    faces=mesh.indices.reshape(-1,3)
    fd=distances[faces]
    keep=fd.max(axis=1)<=1e-9
    crossing=(fd.min(axis=1)<-1e-9)&~keep
    extra=[]
    for face in faces[crossing]:
        polygon=[]
        for j in range(3):
            a,b=int(face[j]),int(face[(j+1)%3]); da,db=distances[a],distances[b]
            if da<=0: polygon.append(values[a])
            if (da<0<db) or (db<0<da):
                polygon.append(values[a]+(values[b]-values[a])*(da/(da-db)))
        for j in range(1,len(polygon)-1): extra.extend((polygon[0],polygon[j],polygon[j+1]))
    kept=values[faces[keep]].reshape(-1,values.shape[1])
    if extra: kept=np.concatenate([kept,np.asarray(extra)])
    result=mesh.copy()
    result.positions,result.normals,result.uvs=kept[:,:3],kept[:,3:6],kept[:,6:8]
    if result.colors is not None: result.colors=kept[:,8:12]
    result.indices=np.arange(len(kept))
    return _compact(result)


def clip_rect(mesh, edge, forward, side, near, far, width=None):
    if width is None: width = HALF_WIDTH
    result=clip_plane(mesh,edge,forward,far)
    result=clip_plane(result,edge,-forward,-near)
    result=clip_plane(result,edge,side,width)
    return clip_plane(result,edge,-side,width)


def outside_rect(mesh, edge, forward, side, near, far, width=None):
    """Disjoint complement for replacing a water patch without coplanar overlap."""
    if width is None: width = HALF_WIDTH
    from amberwood.mesh import merge
    middle = clip_plane(clip_plane(mesh,edge,forward,far),edge,-forward,-near)
    return merge([clip_plane(mesh,edge,forward,near),
                  clip_plane(mesh,edge,-forward,-far),
                  clip_plane(middle,edge,side,-width),
                  clip_plane(middle,edge,-side,-width)], material=mesh.material)


def split_overflow(mesh, edge, forward, side):
    # Disjoint complement of the receiving strip. Unlike centroid clipping,
    # even a huge backdrop triangle has an exact edge with no missing sliver.
    behind=clip_plane(mesh,edge,forward)
    beyond=clip_plane(mesh,edge,-forward)
    left=clip_plane(beyond,edge,side,-HALF_WIDTH)
    right=clip_plane(beyond,edge,-side,-HALF_WIDTH)
    from amberwood.mesh import merge
    return merge([behind,left,right], material=mesh.material), clip_rect(mesh,edge,forward,side,0,100000)



def _refine_collar(mesh, edge, forward, side):
    """Keep the material edge below a metre instead of a repeated triangle saw."""
    columns = [mesh.positions, mesh.normals, mesh.uvs]
    if mesh.colors is not None: columns.append(mesh.colors)
    values = np.concatenate(columns, axis=1)
    faces = mesh.indices.reshape(-1, 3)
    for _ in range(3):
        triangles = values[faces, :3]
        centres = triangles.mean(axis=1)[:, [0, 2]] - edge
        depth, lateral = centres @ forward, centres @ side
        longest = np.maximum.reduce([np.linalg.norm(triangles[:, a] - triangles[:, b], axis=1)
                                     for a, b in ((0, 1), (1, 2), (2, 0))])
        selected = (depth > -44) & (depth < 5) & (abs(lateral) < HALF_WIDTH + 20) & (longest > 1.8)
        if not selected.any(): break
        old = faces[selected]
        mids = np.stack([(values[old[:, a]] + values[old[:, b]]) / 2
                         for a, b in ((0, 1), (1, 2), (2, 0))], axis=1)
        ids = np.arange(len(values), len(values) + 3 * len(old)).reshape(-1, 3)
        values = np.concatenate([values, mids.reshape(-1, values.shape[1])])
        a, b, c = old.T; ab, bc, ca = ids.T
        faces = np.concatenate([faces[~selected], np.stack([a, ab, ca], axis=1),
            np.stack([ab, b, bc], axis=1), np.stack([ca, bc, c], axis=1), np.stack([ab, bc, ca], axis=1)])
    mesh.positions, mesh.normals, mesh.uvs = values[:, :3], values[:, 3:6], values[:, 6:8]
    if mesh.colors is not None: mesh.colors = values[:, 8:12]
    mesh.indices = faces.reshape(-1)


def _shoulder_rise(spec):
    if spec.get('geometryMode') == 'continent-owned-v1':
        return {'moor': 1.4, 'pasture': 1.4, 'steppe': 2., 'scree': 4.,
                'upland': 5., 'alpine': 8.}.get(spec['palette'], 2.)
    return {'pasture': 1.4, 'steppe': 2.0}.get(spec.get('profile'), 8.0)


def _owned_threshold(build, spec):
    """Invisible final source cells; all visible terrain belongs to its region.

    Explicit support keeps a narrow nonconvex border neck from requiring an
    overlapping visible extension just to reach the server's trigger at +1m.
    """
    from amberwood import mesh as M
    f = np.asarray(spec['outward'], float); side = np.array([-f[1], f[0]])
    edge = np.asarray(spec['anchor'], float)
    lateral = np.linspace(-4., 4., 17)
    points = []
    # Ownership cuts use integer edges while actors stand at half metres.
    # The conservative EWCG fold also samples .75m behind each actor. Cover
    # that inner half-cell gap using the same invisible authoritative cap.
    for depth in (-1.01, 1., 2.01):
        for across in lateral:
            p = edge.copy(); p[[0,2]] += f * depth + side * across
            if spec.get('profile') != 'causeway':
                p[1] += _shoulder_rise(spec) * (1 - np.exp(-(across/30)**2))
            points.append(p)
    faces = []
    for row in range(2):
        for col in range(16):
            a = row * 17 + col
            faces.extend([a, a+17, a+1, a+1, a+17, a+18])
    mesh = M.Mesh(positions=np.asarray(points), normals=np.tile([0.,1.,0.],(51,1)),
                  uvs=np.zeros((51,2)), indices=np.asarray(faces), material=PALETTES[spec['palette']][2])
    mesh.recompute_normals(180)
    if mesh.normals[:,1].mean() < 0:
        mesh.flip_winding(); mesh.recompute_normals(180)
    build.terrain_meshes['Walk_StreamThreshold_'+spec['id']] = mesh


def _apply_one(build, spec, peers):
    edge = np.array(spec['anchor'])[[0, 2]]
    forward = np.array(spec['outward'], float)
    side = np.array([-forward[1], forward[0]])
    level = spec['anchor'][1]
    causeway = spec.get('profile') == 'causeway'
    owned = spec.get('geometryMode') == 'continent-owned-v1'
    disks = getattr(build, 'geography_protected_disks', []) if owned else []

    def unprotected(points):
        weight = np.ones(len(points))
        for x,z,radius in disks:
            distance = np.linalg.norm(points[:,[0,2]] - [x,z], axis=1)
            fade = np.clip((distance-radius)/8., 0, 1)
            weight = np.minimum(weight, fade*fade*(3-2*fade))
        return weight

    def grade(points, water=False):
        points = points.copy()
        # A lake can extend underneath dry ground. Grading that hidden plane
        # into a land saddle floods the approach and closes its collision.
        # Only a causeway has a surveyed replacement water elevation.
        if water and not causeway:
            return points
        relative = points[:, [0, 2]] - edge
        depth, lateral = relative @ forward, relative @ side
        # One broad saddle, open across the road and rising into both shoulders.
        if causeway:
            # A navigable bridge above a lake channel, never an earth plug.
            target = np.full_like(lateral, level - spec['waterBelowDeck'] - (0 if water else 2.0))
        else:
            rise = _shoulder_rise(spec)
            target = level + rise * (1 - np.exp(-(lateral / 30)**2))
        blend = np.clip((depth + 42) / 32, 0, 1)
        blend = blend * blend * (3 - 2 * blend)
        shoulder_width = 8 if causeway else SHOULDER_WIDTH
        shoulder = np.clip((abs(lateral) - HALF_WIDTH) / shoulder_width, 0, 1)
        blend *= 1 - shoulder * shoulder * (3 - 2 * shoulder)
        if owned and not water:
            blend *= unprotected(points)
        # A nearby second road may blend its outer shoulder into this region,
        # but never change another road's surveyed receiving strip. Mirrorhold
        # has two north-facing cols only 87m apart. Fade protection outside the
        # 40m cut so the unsplit ground stays continuous between the cols.
        for peer in peers:
            if peer['id'] == spec['id']: continue
            pf=np.asarray(peer['outward'],float);ps=np.array([-pf[1],pf[0]])
            pr=points[:,[0,2]]-np.asarray(peer['anchor'])[[0,2]]
            pd,pl=pr@pf,pr@ps
            protection=np.clip((pd+42)/32,0,1)
            protection=protection*protection*(3-2*protection)
            outside=np.clip((abs(pl)-HALF_WIDTH)/3,0,1)
            outside=outside*outside*(3-2*outside)
            blend*=1-protection*(1-outside)
        points[:, 1] += (target - points[:, 1]) * blend
        return points

    for bucket in (build.terrain_meshes, build.water_meshes):
        for name, original in list(bucket.items()):
            if name.startswith(VIEW_PREFIX) or '_StreamOverflow_' in name or '_StreamCauseway_' in name:
                continue
            if owned and bucket is build.terrain_meshes and not name.startswith(('Terrain_', 'Walk_ContinentRoad_')):
                continue
            # New road spans can be a single 42m quad. Sampling only their
            # two outer edges raises the entire centre to the shoulder level.
            # Refine the authored connector too; native decks remain intact.
            if name.startswith('Terrain_') or (owned and name.startswith('Walk_ContinentRoad_')):
                _refine_collar(original, edge, forward, side)
            if owned and name.startswith('Walk_ContinentRoad_'):
                road = original.positions.copy(); road[:,1] -= .03
                original.positions = grade(road); original.positions[:,1] += .03
            else:
                original.positions = grade(original.positions, water=bucket is build.water_meshes)
            original.recompute_normals(180)
            # Both directions use the same gravel and UV frame for the last
            # few metres. A ragged inner edge blends back to each region's soil.
            if name.startswith('Terrain_') and not causeway:
                faces = original.indices.reshape(-1, 3)
                coords = original.positions[:, [0, 2]] - edge
                depth, lateral = coords @ forward, coords @ side
                near = np.minimum(np.clip(.5 + (depth + 32 - 6.0 * np.sin(lateral * .055)
                                             - 2.0 * np.sin(lateral * .17)) / 6.0, 0, 1),
                                  np.clip((HALF_WIDTH + 20 - abs(lateral)) / 12, 0, 1))
                if owned: near *= unprotected(original.positions)
                if near.max(initial=0) > .5:
                    if original.colors is None: original.colors = np.ones((len(original.positions), 4))
                    alpha = original.colors[:, 3].copy()
                    u, v = lateral * spec['uvSign'], depth * spec['uvSign']
                    road = np.clip(.5 + (3.4 + .4 * np.sin(v * .3) - abs(u)) / 1.0, 0, 1)
                    frost = np.minimum(np.clip((abs(u) - 7) / 1.2, 0, 1),
                        np.clip(.5 + (np.sin(u * .17) + np.cos(v * .23) +
                            .45 * np.sin((u + v) * .37) - .35) / .8, 0, 1))
                    # Continuous substrate below the cutout paint prevents
                    # cracks where interpolated masks meet inside a triangle.
                    # Centimetre offsets avoid coplanar depth fighting.
                    for suffix, mask, material, lift in [
                            ('Turf', np.ones_like(road), PALETTES[spec['palette']][0] + '_ground', .008),
                            ('Frost', frost, PALETTES[spec['palette']][1] + '_ground', .016),
                            ('Road', road, PALETTES[spec['palette']][2] + '_ground', .024)]:
                        gravel = original.copy()
                        gravel.positions[:, 1] += lift
                        gravel.colors[:, 3] = np.minimum.reduce([alpha, near, mask])
                        gravel.indices = faces[gravel.colors[faces, 3].max(axis=1) >= .5].reshape(-1)
                        gravel.material = material
                        gravel.uvs = np.stack([u, v], axis=1) * .28
                        bucket[name + '_StreamCollar_' + spec['id'] + '_' + suffix] = _compact(gravel)
            bucket[name] = _compact(original)
        for name, original in list(bucket.items()):
            if owned: continue
            if not original.triangle_count or '_StreamOverflow_' in name: continue
            front,overflow=split_overflow(original,edge,forward,side)
            bucket[name]=_compact(front)
            if overflow.triangle_count: bucket[name+spec['overflowSuffix']]=_compact(overflow)
    kept = []
    lifted = {}
    for placement in build.placements:
        p = np.asarray(placement.position, float)
        relative = p[[0, 2]] - edge
        depth, lateral = relative @ forward, relative @ side
        if depth > -42 and abs(lateral) < HALF_WIDTH + SHOULDER_WIDTH:
            # The receiving scene supplies this side of the border. Removing
            # only perimeter dressing leaves services and landmarks unchanged.
            if owned and (placement.kind not in ('tree', 'foliage', 'rock', 'undergrowth', 'fallenlog')
                          or unprotected(p[None,:])[0] < .999):
                kept.append(placement)
                continue
            if (not owned and depth > 0 and abs(lateral) < HALF_WIDTH) or (abs(lateral) < 7 and placement.kind in ('tree', 'foliage', 'rock', 'undergrowth')):
                continue
            if causeway:
                # Authored structures stand on their own deck/footings; never
                # lower a bridge or lighthouse with the seabed beneath it.
                kept.append(placement)
                continue
            ground=p.copy();ground[1]=build.terrain.height_at(p[0],p[2])
            lift=float(grade(ground[None,:])[0,1]-ground[1])
            p[1]+=lift
            placement.position=tuple(p)
            lifted[placement.node]=lift
        kept.append(placement)
    build.placements[:] = kept
    landmark_nodes={entry.get('id'):entry.get('node') for entry in build.landmarks}
    def linked_node(entry):
        if entry.get('node'): return entry['node']
        if entry.get('landmark'): return landmark_nodes.get(entry['landmark'])
        if entry.get('secret'): return 'Secret_'+entry['secret'].replace('-','_')
        return None
    portal_nodes={entry.get('id'):linked_node(entry) for entry in build.portals}
    seen=set()
    for name in ('landmarks','interactives','npc_markers','harvestables','portals','spawns'):
        for entry in getattr(build,name,[]):
            # Some builders reuse one record in multiple collections. Move it
            # once, by its physical prop's delta, preserving authored offsets.
            if id(entry) in seen: continue
            seen.add(id(entry))
            node=linked_node(entry)
            if node is None and name=='spawns': node=portal_nodes.get(entry.get('id'))
            lift=lifted.get(node)
            if lift is not None and 'position' in entry:
                entry['position'][1]+=lift
    t=build.terrain
    points=np.stack([t.gx.ravel(),t.height.ravel(),t.gz.ravel()],axis=1)
    t.height=grade(points)[:,1].reshape(t.height.shape)


def apply(build, region):
    import continent_geography as geography
    geography.apply_geometry(build, region)
    specs=region_specs(region)
    build.streaming_borders=specs
    build.vista_materials=getattr(build,'vista_materials',set())|materials_for(region)
    # Owned terrain and real neighbours supply the horizon. Old distant rings
    # were painted outside the former square map; retaining them after the
    # ownership expansion would put false mountains across the new approaches.
    owned = any(s.get('geometryMode') == 'continent-owned-v1' for s in specs)
    for bucket in (build.terrain_meshes,build.water_meshes):
        for name in list(bucket):
            if name.startswith('Backdrop_' if owned else 'Backdrop_Neighbour'):
                del bucket[name]
    build.border_vistas=[]
    for spec in specs:
        if spec.get('profile') == 'causeway':
            _causeway_meshes(build,spec)
        _apply_one(build,spec,specs)
        if spec.get('geometryMode') == 'continent-owned-v1':
            _owned_threshold(build, spec)
        anchor=np.asarray(spec['anchor'],float); forward=np.asarray(spec['outward'],float)
        # Source metadata and the server's trigger use the same tile centres.
        for portal in build.portals:
            if portal.get('id')==spec['portal']:
                p=anchor.copy();p[[0,2]]+=forward
                portal['position']=p.tolist()
                ox,oy=geography.plan()['regions'][region]['nativeServerOrigin']
                portal['serverTile']=[int(np.floor(p[0]+ox)),int(np.floor(oy-p[2]))]
    partition_shared_approaches(build, specs)
    # The final ownership cut also covers generated causeways. Invisible
    # threshold cells remain for the server's last source-map movement step.
    geography.finalize_geometry(build, region)


def partition_shared_approaches(build, specs):
    """Store each surface triangle and each prop once, with view membership.

    The old export doubled receiving scenery and drew a fabricated extension
    until loading finished. A resident now exposes the same nodes later used
    by the active region. Prop bounds keep complete canopies and landmarks.
    """
    for bucket in (build.terrain_meshes, build.water_meshes):
        for name in list(bucket):
            if '_StreamOverflow_' not in name:
                continue
            mesh = bucket.pop(name)
            identity = name.split('_StreamOverflow_', 1)[1]
            spec = next(s for s in specs if s['id'] == identity)
            # The server changes map at depth +1. Its final standing cell
            # still needs source-map collision, but never duplicate scenery.
            if bucket is build.terrain_meshes and name.startswith(('Terrain_', 'Walk_')):
                edge = np.asarray(spec['anchor'])[[0, 2]]
                forward = np.asarray(spec['outward'], float)
                side = np.array([-forward[1], forward[0]])
                threshold = clip_rect(mesh, edge, forward, side, 0, 2.01, 4.0)
                if threshold.triangle_count:
                    bucket[name.replace('_StreamOverflow_', '_StreamThreshold_')] = _compact(threshold)

    local_corners={}
    candidates=[]
    for p in build.placements:
        if p.mesh not in local_corners:
            mesh=build.meshes.get(p.mesh)
            if mesh is None or not mesh.triangle_count:
                local_corners[p.mesh]=None
            else:
                low,high=mesh.bounds()
                local_corners[p.mesh]=np.array([
                    [x,y,z] for x in (low[0],high[0])
                    for y in (low[1],high[1]) for z in (low[2],high[2])])
        corners=local_corners[p.mesh]
        if corners is None: continue
        world=(corners*p.scale)@rotation_y(p.rotation_y)[:3,:3].T+np.asarray(p.position)
        candidates.append((p,world[:,[0,2]]))
    for spec in specs:
        edge=np.asarray(spec['anchor'])[[0,2]];forward=np.asarray(spec['outward'],float)
        side=np.array([-forward[1],forward[0]])
        for bucket in (build.terrain_meshes,build.water_meshes):
            for name,mesh in list(bucket.items()):
                if '_StreamThreshold_' in name: continue
                part=clip_rect(mesh,edge,forward,side,-VIEW_DEPTH,0)
                if part.triangle_count:
                    cell = name + '_StreamCell_' + spec['id']
                    bucket[cell] = _compact(part)
                    bucket[name] = _compact(outside_rect(mesh,edge,forward,side,-VIEW_DEPTH,0))
                    spec['sceneNodes'].append(cell)
                    # Intersecting approaches share one atom; cutting a later
                    # road may divide an earlier cell but must not erase it
                    # from that earlier resident's view.
                    for previous in specs:
                        if previous is not spec and name in previous['sceneNodes']:
                            previous['sceneNodes'].append(cell)
                    if not bucket[name].triangle_count:
                        del bucket[name]
                        for previous in specs:
                            if name in previous['sceneNodes']:
                                previous['sceneNodes'].remove(name)
        for p,corners in candidates:
            relative=corners-edge
            depth,lateral=relative@forward,relative@side
            if (depth.max()>=-VIEW_DEPTH and depth.min()<=0
                    and lateral.max()>=-HALF_WIDTH and lateral.min()<=HALF_WIDTH):
                spec['sceneNodes'].append(p.node)
