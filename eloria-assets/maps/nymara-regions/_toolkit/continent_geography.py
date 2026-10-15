"""Translation-only geography and actual, disjoint exterior ownership.

The JSON is the coordinate authority. Native geometry is never rotated or
scaled: only peripheral road beds are regraded. Clipping happens after the
shared road recipes, so generated surfaces obey the same ownership as terrain.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import heapq
import json
import math
import numpy as np

PLAN_PATH = Path(__file__).resolve().parents[1] / 'continent-geography.json'
BIOME_BASES = {'whitehorn_range':'alpine_turf','amberwood':'meadow_grass',
    'mirrorhold':'alpine_turf','amethyst_barrens':'amethyst_barrens_dust',
    'grey_moors':'grey_heather_moor','westhaven':'meadow_grass',
    'crownwater':'meadow_grass','four_gates':'meadow_grass',
    'sunmane_steppe':'steppe_sward','ssarathi_ruins':'verdant_jungle_floor',
    'verdant_stair':'verdant_jungle_floor','manymouth_delta':'meadow_grass'}


@lru_cache(maxsize=1)
def plan():
    return json.loads(PLAN_PATH.read_text(encoding='utf-8'))


def region_specs(region, legacy_links=None):
    """The existing streaming frame shape, with one consistent global datum."""
    data = plan()
    if region not in data['regions']:
        return []
    translation = data['regions'][region]['translation']
    result = []
    for connection in data['connections']:
        for index, end in enumerate(connection['ends']):
            if end['region'] != region:
                continue
            other = connection['ends'][1-index]
            identity = connection['id']
            spec = dict(id=identity, portal=end['portal'], destination=other['region'],
                anchor=list(end['anchor']), outward=list(end['outward']),
                globalTranslation=list(translation), globalAnchor=connection['globalAnchor'],
                uvSign=1 if index == 0 else -1, palette=connection['palette'],
                preloadDistance=240, retainDistance=320, blendDistance=90,
                collarDepth=42, halfWidthTiles=3, viewHalfWidth=110, viewDepth=240,
                geometryMode='continent-owned-v1', sceneNodes=[],
                previewPrefix='StreamView_'+identity+'__',
                overflowSuffix='_StreamOverflow_'+identity)
            if connection['profile'] != 'land':
                spec['profile'] = connection['profile']
            if connection['profile'] == 'causeway':
                spec.update(waterBelowDeck=4.0, deckWidth=7.0)
            result.append(spec)
    return result


def boundary_segments(region):
    return [s for s in plan().get('boundaryHeightField',{}).get('segments',[])
            if region in s['regions']]


def boundary_road_recipe(point, native_height, connections=None):
    """Order-independent shared terrain recipe with exact seven-lane throats.

    A nearby road can soften the surrounding slope, but cannot replace another
    road's level. Causeway terrain is the submerged channel, not the Walk deck.
    """
    import streaming_borders as SB
    candidates = []
    point = np.asarray(point, float)
    for connection in (plan()['connections'] if connections is None else connections):
        anchor = np.asarray(connection['globalAnchor'], float)
        forward = np.asarray(connection['normal'], float)
        relative = point-anchor[[0,2]]
        depth = abs(float(relative @ forward))
        lateral = abs(float(relative @ np.array([-forward[1],forward[0]])))
        blend = float(np.clip((42-depth)/18,0,1)*np.clip((138-lateral)/28,0,1))
        blend = blend*blend*(3-2*blend)
        if blend == 0:
            continue
        spec = dict(connection, geometryMode='continent-owned-v1')
        target = (anchor[1]-6 if connection['profile']=='causeway' else
                  anchor[1]+SB._shoulder_rise(spec)*(1-math.exp(-(lateral/30)**2)))
        candidates.append((connection['id'],target,blend,float(relative@relative),
                           depth <= 3 and lateral <= 4))
    if not candidates:
        return float(native_height)
    pinned = [c for c in candidates if c[4]]
    if pinned:
        return min(pinned,key=lambda c:(c[3],c[0]))[1]
    candidates.sort(key=lambda c:c[0])
    weights = [c[2]/(c[3]+1)**2 for c in candidates]
    target = sum(c[1]*w for c,w in zip(candidates,weights))/sum(weights)
    strength = max(c[2] for c in candidates)
    return float(native_height)*(1-strength)+target*strength


def materials_for(region):
    """Import-time material dependencies for authored roads and edge mixtures."""
    if region not in plan()['regions']:
        return set()
    neighbours={n for s in boundary_segments(region) for n in s['regions']}
    return {BIOME_BASES[n] for n in neighbours}|{'packed_earth','cobble_paving'}


def boundary_sample(region, local_points, maximum=24.0, peer=None):
    """Distance and global level on the nearest committed common edge segment."""
    translation = np.asarray(plan()['regions'][region]['translation'])[[0,2]]
    points = np.asarray(local_points,float).reshape(-1,2)+translation
    distance = np.full(len(points), np.inf)
    height = np.zeros(len(points))
    for segment in boundary_segments(region):
        if peer is not None and peer not in segment['regions']:
            continue
        a,b = np.array(segment['start']),np.array(segment['end'])
        low,high = np.minimum(a,b)-maximum,np.maximum(a,b)+maximum
        selected = np.flatnonzero((points>=low).all(axis=1)&(points<=high).all(axis=1))
        if not len(selected):
            continue
        vector = b-a
        along = np.clip((points[selected]-a)@vector/(vector@vector),0,1)
        d = np.linalg.norm(points[selected]-a-along[:,None]*vector,axis=1)
        nearer = d < distance[selected]
        ids = selected[nearer]
        distance[ids] = d[nearer]
        heights = segment['heights']
        height[ids] = heights[0]+along[nearer]*(heights[1]-heights[0])
    return distance,height


def _grade_common_boundary(build,region):
    """A broad graded skirt meets the same real height on both owned sides."""
    if not boundary_segments(region):
        return
    ty=plan()['regions'][region]['translation'][1]
    def shape(points):
        distance,level=boundary_sample(region,points[:,[0,2]])
        weight=1-np.clip(distance/24,0,1)
        weight=weight*weight*(3-2*weight)
        for x,z,radius in build.geography_protected_disks:
            d=np.hypot(points[:,0]-x,points[:,2]-z)
            weight*=np.clip((d-radius)/3,0,1)
        result=points.copy()
        result[:,1]+=(level-ty-points[:,1])*weight
        return result
    _lift_unprotected_scatter(build,shape)
    for name,mesh in build.terrain_meshes.items():
        if name.startswith('Terrain_'):
            mesh.positions=shape(mesh.positions)
            mesh.recompute_normals(180)
    t=build.terrain
    points=np.c_[t.gx.ravel(),t.height.ravel(),t.gz.ravel()]
    t.height=shape(points)[:,1].reshape(t.height.shape)


def _is_scatter(placement):
    return (not placement.landmark and
        (placement.kind in ('tree','foliage','rock','undergrowth','stone','scatter')
         or (placement.kind=='prop' and not placement.collides and not placement.walk_surface)))


def _lift_unprotected_scatter(build,shape):
    """Follow the actual ground change while preserving each authored Y offset."""
    candidates=[]
    for p in build.placements:
        if not _is_scatter(p):continue
        if any(np.hypot(p.position[0]-x,p.position[2]-z)<radius
               for x,z,radius in build.geography_protected_disks):continue
        candidates.append(p)
    if not candidates:return
    points=np.array([p.position for p in candidates],float)
    points[:,1]=build.terrain.height_at(points[:,0],points[:,2])
    changed=shape(points)
    lifts={}
    for p,delta in zip(candidates,changed[:,1]-points[:,1]):
        if abs(delta)<1e-9:continue
        p.position=(p.position[0],p.position[1]+float(delta),p.position[2])
        lifts[p.node]=float(delta)
    landmarks={e.get('id'):e.get('node') for e in build.landmarks}
    seen=set()
    for collection in ('landmarks','interactives','npc_markers','harvestables','portals','spawns'):
        for entry in getattr(build,collection,[]):
            if id(entry) in seen:continue
            seen.add(id(entry))
            node=entry.get('node') or landmarks.get(entry.get('landmark'))
            if node in lifts and 'position' in entry:entry['position'][1]+=lifts[node]
    build.geography_scatter_lifts=getattr(build,'geography_scatter_lifts',0)+len(lifts)


def _snap_boundary_mesh(mesh,region):
    """Split cut edges at every common profile knot, then set exact shared Y.

    Linear interpolation on both sides is now the same function even when
    their native terrain tessellations have different vertices and spacing.
    """
    from amberwood.terrain import _compact
    segments=boundary_segments(region)
    if not segments or not mesh.triangle_count:
        return mesh
    translation=np.asarray(plan()['regions'][region]['translation'])
    distance,level=boundary_sample(region,mesh.positions[:,[0,2]],maximum=.001)
    on=distance<1e-7
    columns=[mesh.positions,mesh.normals,mesh.uvs]
    if mesh.colors is not None:columns.append(mesh.colors)
    values=np.concatenate(columns,axis=1)
    values[on,1]=level[on]-translation[1]
    vertical,horizontal={},{}
    for s in segments:
        a,b=np.array(s['start'])-translation[[0,2]],np.array(s['end'])-translation[[0,2]]
        if abs(a[0]-b[0])<1e-8:
            vertical.setdefault(round(float(a[0]),6),set()).update((a[1],b[1]))
        else:
            horizontal.setdefault(round(float(a[1]),6),set()).update((a[0],b[0]))
    faces=mesh.indices.reshape(-1,3)
    # A real boundary may occupy only part of a long rectangle-cut edge. Its
    # first knot can lie between two vertices that are both interior points;
    # selecting only faces with two boundary vertices misses that T-junction.
    xz=mesh.positions[faces][:,:,[0,2]]
    low,high=xz.min(axis=1),xz.max(axis=1)
    selected=np.zeros(len(faces),bool)
    for s in segments:
        a,b=np.array(s['start'])-translation[[0,2]],np.array(s['end'])-translation[[0,2]]
        selected|=(low<=np.maximum(a,b)+1e-8).all(axis=1)&(high>=np.minimum(a,b)-1e-8).all(axis=1)
    output=[values[faces[~selected]].reshape(-1,values.shape[1])]
    pending=[values[face] for face in faces[selected]]
    while pending:
        face=pending.pop();split=False
        for i in range(3):
            a,b,c=face[i],face[(i+1)%3],face[(i+2)%3]
            if abs(a[0]-b[0])<1e-7:
                axis=2;knots=vertical.get(round(float(a[0]),6),())
            elif abs(a[2]-b[2])<1e-7:
                axis=0;knots=horizontal.get(round(float(a[2]),6),())
            else:continue
            lo,hi=sorted((a[axis],b[axis]))
            cuts=sorted(k for k in knots if lo+1e-7<k<hi-1e-7)
            if not cuts:continue
            if a[axis]>b[axis]:cuts.reverse()
            edge=[a]+[a+(b-a)*((k-a[axis])/(b[axis]-a[axis])) for k in cuts]+[b]
            for left,right in zip(edge,edge[1:]):pending.append(np.array([left,right,c]))
            split=True;break
        if not split:output.append(face)
    all_values=np.concatenate(output)
    distance,level=boundary_sample(region,all_values[:,[0,2]],maximum=.001)
    on=distance<1e-7
    all_values[on,1]=level[on]-translation[1]
    result=mesh.copy()
    result.positions,result.normals,result.uvs=all_values[:,:3],all_values[:,3:6],all_values[:,6:8]
    if result.colors is not None:result.colors=all_values[:,8:12]
    result.indices=np.arange(len(all_values))
    result.recompute_normals(180)
    return _compact(result)


def _blend_boundary_materials(build,region):
    """The same global soil mixture on both sides, fading into local terrain."""
    from amberwood.terrain import _compact
    peers=sorted({n for s in boundary_segments(region) for n in s['regions'] if n!=region})
    t=np.asarray(plan()['regions'][region]['translation'])[[0,2]]
    for name,original in list(build.terrain_meshes.items()):
        if not name.startswith('Terrain_') or not original.triangle_count or '_StreamCollar_' in name:
            continue
        global_points=original.positions[:,[0,2]]+t
        x,z=global_points.T
        for peer in peers:
            distance,_=boundary_sample(region,original.positions[:,[0,2]],peer=peer)
            band=18+3*np.sin(x*.081+z*.067)+2*np.sin(x*.19-z*.11)
            coverage=np.clip((band-distance)/10,0,1)
            # Road recipes have their own shared palette and public paving.
            for connection in plan()['connections']:
                anchor=np.asarray(connection['globalAnchor'])[[0,2]];n=np.asarray(connection['normal']);s=np.array([-n[1],n[0]])
                relative=global_points-anchor
                road=np.clip((42-np.abs(relative@n))/18,0,1)*np.clip((138-np.abs(relative@s))/28,0,1)
                coverage*=1-road
            for px,pz,radius in build.geography_protected_disks:
                coverage*=np.clip((np.hypot(original.positions[:,0]-px,original.positions[:,2]-pz)-radius)/3,0,1)
            if coverage.max(initial=0)<.5:continue
            pair=sorted([region,peer]);materials=[BIOME_BASES[n] for n in pair]
            noise=np.sin(x*.21)+np.cos(z*.17)+.55*np.sin(x*.09+z*.13)
            masks=[np.ones(len(x)),np.clip(.5+noise*.7,0,1)]
            for index,(material,mask) in enumerate(zip(materials,masks)):
                painted=original.copy()
                if painted.colors is None:painted.colors=np.ones((len(x),4))
                painted.colors[:,3]=np.minimum(painted.colors[:,3],coverage*mask)
                faces=painted.indices.reshape(-1,3)
                painted.indices=faces[painted.colors[faces,3].max(axis=1)>=.5].ravel()
                if not painted.triangle_count:continue
                painted.material=material+'_ground'
                painted.positions[:,1]+=.008+index*.008
                painted.uvs=global_points*.28
                build.terrain_meshes[name+'_ContinentBlend_'+peer+'_'+str(index)]=_compact(painted)
                build.vista_materials=getattr(build,'vista_materials',set())|{material}


def inside_polygon(points, polygon):
    """Inclusive point membership; supports the authored concave outlines."""
    points = np.asarray(points, float).reshape(-1, 2)
    polygon = np.asarray(polygon, float)
    x, z = points.T
    inside = np.zeros(len(points), bool)
    boundary = np.zeros(len(points), bool)
    for a, b in zip(polygon, np.roll(polygon, -1, axis=0)):
        v = b-a
        cross = (x-a[0])*v[1]-(z-a[1])*v[0]
        boundary |= ((np.abs(cross) < 1e-8) & (x >= min(a[0], b[0])-1e-8)
                     & (x <= max(a[0], b[0])+1e-8) & (z >= min(a[1], b[1])-1e-8)
                     & (z <= max(a[1], b[1])+1e-8))
        if abs(v[1]) > 1e-12:
            inside ^= ((a[1] > z) != (b[1] > z)) & (x < a[0]+(z-a[1])*v[0]/v[1])
    return inside | boundary


def polygon_rectangles(polygon):
    """Exact disjoint rectangular decomposition of a rectilinear polygon."""
    polygon = np.asarray(polygon, float)
    levels = np.unique(polygon[:, 1])
    pending, result = {}, []
    for low, high in zip(levels, levels[1:]):
        middle = (low+high)*.5
        xs = []
        for a, b in zip(polygon, np.roll(polygon, -1, axis=0)):
            if min(a[1], b[1]) < middle < max(a[1], b[1]):
                if abs(a[0]-b[0]) > 1e-8:
                    raise ValueError('ownership edges must be rectilinear')
                xs.append(a[0])
        xs.sort()
        if len(xs) % 2:
            raise ValueError('ownership polygon has an open scanline')
        current = {}
        for left, right in zip(xs[::2], xs[1::2]):
            key = (left, right)
            prior = pending.pop(key, None)
            current[key] = [left, prior[1] if prior else low, right, high]
        result.extend(pending.values())
        pending = current
    result.extend(pending.values())
    return np.asarray(result, float).reshape(-1, 4)


def _clip_values(values, axis, limit, sign):
    output = []
    for a, b in zip(values, np.roll(values, -1, axis=0)):
        da, db = sign*(a[axis]-limit), sign*(b[axis]-limit)
        if da <= 1e-9:
            output.append(a)
        if (da < -1e-9 and db > 1e-9) or (db < -1e-9 and da > 1e-9):
            output.append(a+(b-a)*(da/(da-db)))
    return np.asarray(output)


def clip_owned_mesh(mesh, rectangles, preserved_rectangle=None):
    """Exact ownership cut with interpolated normals, UVs and vertex colour.

    A native-core face is returned byte-for-byte in the mesh arrays. Boundary
    faces are intersected with disjoint rectangles; no centroid approximation
    can discard a road shoulder or leave an overlapping sliver.
    """
    from amberwood.terrain import _compact
    if not mesh.triangle_count:
        return mesh.copy()
    columns = [mesh.positions, mesh.normals, mesh.uvs]
    if mesh.colors is not None:
        columns.append(mesh.colors)
    values = np.concatenate(columns, axis=1)
    faces = mesh.indices.reshape(-1, 3)
    xz = mesh.positions[:, [0, 2]][faces]
    low, high = xz.min(axis=1), xz.max(axis=1)
    keep = np.zeros(len(faces), bool)
    if preserved_rectangle is not None:
        a, b = np.asarray(preserved_rectangle)
        keep = (low >= a-1e-9).all(axis=1) & (high <= b+1e-9).all(axis=1)
    for left, bottom, right, top in rectangles:
        keep |= ((low[:, 0] >= left-1e-9) & (high[:, 0] <= right+1e-9)
                 & (low[:, 1] >= bottom-1e-9) & (high[:, 1] <= top+1e-9))
    if keep.all():
        return mesh.copy()
    pieces = [values[faces[keep]].reshape(-1, values.shape[1])]
    for left, bottom, right, top in rectangles:
        selected = (~keep & (high[:, 0] > left+1e-9) & (low[:, 0] < right-1e-9)
                    & (high[:, 1] > bottom+1e-9) & (low[:, 1] < top-1e-9))
        for face in faces[selected]:
            clipped = values[face]
            for axis, limit, sign in ((0, left, -1), (0, right, 1),
                                      (2, bottom, -1), (2, top, 1)):
                clipped = _clip_values(clipped, axis, limit, sign)
                if len(clipped) < 3:
                    break
            if len(clipped) >= 3:
                pieces.append(np.asarray([p for i in range(1, len(clipped)-1)
                    for p in (clipped[0], clipped[i], clipped[i+1])]))
    combined = np.concatenate(pieces)
    result = mesh.copy()
    result.positions, result.normals, result.uvs = combined[:, :3], combined[:, 3:6], combined[:, 6:8]
    if mesh.colors is not None:
        result.colors = combined[:, 8:12]
    result.indices = np.arange(len(combined))
    return _compact(result)


def _point_disks(region):
    record = plan()['regions'][region]
    gate_ids = {e['portal'] for c in plan()['connections'] for e in c['ends'] if e['region'] == region}
    return [(p['position'][0], p['position'][2], float(p.get('radius', 3)))
            for p in record['protectedDestinations'] if p['id'] not in gate_ids]


def _structure_disks(build, region):
    """Full transformed structure footprints, including off-centre meshes."""
    from amberwood.mesh import rotation_y
    gate_ids = {e['portal'] for c in plan()['connections'] for e in c['ends'] if e['region'] == region}
    gate_landmarks = {p.get('landmark') for p in build.portals if p.get('id') in gate_ids}
    gate_landmarks.discard(None)
    gate_nodes = {p.get('node') for p in build.landmarks if p.get('id') in gate_landmarks}
    gate_nodes.discard(None)
    result = []
    for p in build.placements:
        if p.node in gate_nodes or p.landmark in gate_landmarks:
            continue
        if not p.collides or p.kind in ('tree','foliage','rock','undergrowth','stone','scatter'):
            continue
        mesh = build.meshes.get(p.mesh)
        if mesh is None or not hasattr(mesh, 'bounds'):
            continue
        low, high = mesh.bounds()
        corners = np.array([[x,y,z] for x in (low[0],high[0]) for y in (low[1],high[1]) for z in (low[2],high[2])])
        world = (corners*p.scale)@rotation_y(p.rotation_y)[:3,:3].T+np.asarray(p.position)
        minimum, maximum = world[:,[0,2]].min(axis=0), world[:,[0,2]].max(axis=0)
        centre = (minimum+maximum)*.5
        radius = float(np.linalg.norm(maximum-minimum)*.5)
        if radius > .5:
            result.append((float(centre[0]),float(centre[1]),radius))
    return result


def _extend_ground(build, region, polygon):
    """Real broad ground outside the native mesh extent, before road grading."""
    from amberwood import mesh as M
    from amberwood.terrain import _compact
    ground = [m for n,m in build.terrain_meshes.items() if n.startswith('Terrain_') and m.triangle_count]
    if not ground:
        raise ValueError(f'{region}: native terrain is missing')
    bounds = np.array([m.bounds() for m in ground])
    low, high = bounds[:,0,:].min(axis=0)[[0,2]], bounds[:,1,:].max(axis=0)[[0,2]]
    own_low, own_high = polygon.min(axis=0), polygon.max(axis=0)
    if np.all(own_low >= low) and np.all(own_high <= high):
        return
    # The source's exact native edge is an explicit grid station, so the new
    # perimeter has neither overlapping triangles nor an unfilled subcell gap.
    xs = np.unique(np.r_[np.arange(math.floor(own_low[0]), math.ceil(own_high[0])+2, 2), low[0], high[0]])
    zs = np.unique(np.r_[np.arange(math.floor(own_low[1]), math.ceil(own_high[1])+2, 2), low[1], high[1]])
    gx,gz = np.meshgrid(xs,zs)
    height = build.terrain.height_at(gx,gz)
    positions = np.c_[gx.ravel(),height.ravel(),gz.ravel()]
    columns = len(xs)
    a = np.arange(len(zs)-1)[:,None]*columns+np.arange(columns-1)[None,:]
    faces = np.stack([a,a+columns,a+columns+1,a,a+columns+1,a+1],axis=-1).reshape(-1,3)
    centre = positions[faces][:,:,[0,2]].mean(axis=1)
    outside = (centre[:,0]<low[0])|(centre[:,0]>high[0])|(centre[:,1]<low[1])|(centre[:,1]>high[1])
    material = max(ground,key=lambda m:m.triangle_count).material
    extension = M.Mesh(positions=positions,normals=np.tile([0.,1,0],(len(positions),1)),
        uvs=positions[:,[0,2]]*.28,indices=faces[outside].ravel(),material=material)
    extension.recompute_normals(180)
    build.terrain_meshes['Terrain_ContinentExtension_'+region] = _compact(extension)


def _road_path(start, finish, polygon, disks, terrain, cell=2.0):
    """Bounded deterministic A* over actual ownership, preserving civic posts."""
    start, finish = np.asarray(start, float), np.asarray(finish, float)
    low = np.floor((np.minimum(start, finish)-70)/cell)*cell
    high = np.ceil((np.maximum(start, finish)+70)/cell)*cell
    xs, zs = np.arange(low[0], high[0]+cell, cell), np.arange(low[1], high[1]+cell, cell)
    gx, gz = np.meshgrid(xs, zs)
    points = np.c_[gx.ravel(), gz.ravel()]
    allowed = inside_polygon(points, polygon).reshape(gx.shape)
    # A complete cart-width bed must fit, including at concave necks.
    for offset in ((4, 0), (-4, 0), (0, 4), (0, -4)):
        allowed &= inside_polygon(points+offset, polygon).reshape(gx.shape)
    for x, z, radius in disks:
        # A road may start at a protected gate/junction, then leave its apron.
        if min(np.hypot(start[0]-x, start[1]-z), np.hypot(finish[0]-x, finish[1]-z)) < radius+5:
            continue
        allowed &= (gx-x)**2+(gz-z)**2 > (radius+4.5)**2
    def index(p):
        return (int(round((p[1]-low[1])/cell)), int(round((p[0]-low[0])/cell)))
    source, target = index(start), index(finish)
    allowed[source] = allowed[target] = True
    heights = terrain.height_at(gx, gz)
    cost, parent, queue = {source: 0.0}, {}, [(0.0, source)]
    directions = [(dz, dx) for dz in (-1, 0, 1) for dx in (-1, 0, 1) if dx or dz]
    while queue:
        _, node = heapq.heappop(queue)
        if node == target:
            reverse = [node]
            while node != source:
                node = parent[node]; reverse.append(node)
            path = np.array([[xs[x], zs[z]] for z, x in reversed(reverse)])
            path[0], path[-1] = start, finish
            # Only remove exactly collinear stations; corner clearance remains explicit.
            keep = [0]
            for i in range(1, len(path)-1):
                a, b = path[i]-path[i-1], path[i+1]-path[i]
                if abs(a[0]*b[1]-a[1]*b[0]) > 1e-8:
                    keep.append(i)
            keep.append(len(path)-1)
            return path[keep]
        z, x = node
        for dz, dx in directions:
            nxt = z+dz, x+dx
            if not (0 <= nxt[0] < len(zs) and 0 <= nxt[1] < len(xs)) or not allowed[nxt]:
                continue
            if dx and dz and not (allowed[z, x+dx] and allowed[z+dz, x]):
                continue
            step = cell*math.hypot(dx, dz)
            elevation = abs(float(heights[nxt]-heights[node]))
            candidate = cost[node]+step+elevation*.8
            if candidate >= cost.get(nxt, math.inf):
                continue
            cost[nxt], parent[nxt] = candidate, node
            remaining = cell*math.hypot(nxt[0]-target[0], nxt[1]-target[1])
            heapq.heappush(queue, (candidate+remaining, nxt))
    raise ValueError(f'no owned public road between {start.tolist()} and {finish.tolist()}')


def _sample_polyline(points, spacing=2):
    lengths = np.r_[0., np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
    samples = np.unique(np.r_[np.arange(0, lengths[-1], spacing), lengths])
    return np.c_[np.interp(samples, lengths, points[:, 0]), np.interp(samples, lengths, points[:, 1])], samples


def _profile(terrain, points, final_level, max_grade=.38):
    points, distance = _sample_polyline(points)
    original = terrain.height_at(points[:, 0], points[:, 1])
    # Keep the real road junction; fixed final level begins at the collar.
    start = float(original[0])
    if abs(final_level-start) > distance[-1]*max_grade:
        raise ValueError(f'road requires grade {abs(final_level-start)/distance[-1]:.3f}; author a longer approach')
    heights = original.copy()
    heights[-1] = final_level
    # End-constrained Lipschitz profile, retaining native undulations where legal.
    for _ in range(4):
        heights[0] = start
        for i in range(1, len(heights)):
            rise = (distance[i]-distance[i-1])*max_grade
            heights[i] = np.clip(heights[i], heights[i-1]-rise, heights[i-1]+rise)
        heights[-1] = final_level
        for i in range(len(heights)-2, -1, -1):
            rise = (distance[i+1]-distance[i])*max_grade
            heights[i] = np.clip(heights[i], heights[i+1]-rise, heights[i+1]+rise)
    heights[0], heights[-1] = start, final_level
    return points, heights, distance


def _road_coordinates(points, stations):
    from amberwood.terrain import _polyline_distance
    return _polyline_distance(points[:, 0], points[:, 1], stations)


def _grade_mesh(mesh, stations, levels, disks):
    distance, along = _road_coordinates(mesh.positions[:, [0, 2]], stations)
    lengths = np.r_[0., np.cumsum(np.linalg.norm(np.diff(stations, axis=0), axis=1))]
    target = np.interp(along, lengths/lengths[-1], levels)
    weight = 1-np.clip((distance-4)/7, 0, 1)
    weight = weight*weight*(3-2*weight)
    for x, z, radius in disks:
        d = np.hypot(mesh.positions[:, 0]-x, mesh.positions[:, 2]-z)
        weight *= np.clip((d-radius)/3, 0, 1)
    mesh.positions[:, 1] += (target-mesh.positions[:, 1])*weight
    if np.any(weight > 0):
        mesh.recompute_normals(180)


def apply_geometry(build, region):
    """Regrade actual terrain and author the gate's connected public road."""
    if region not in plan()['regions']:
        return
    if getattr(build, '_geography_applied', False):
        raise ValueError('geographic shaping must run exactly once per native build')
    build._geography_applied = True
    record = plan()['regions'][region]
    translation = np.asarray(record['translation'])
    polygon = np.asarray(record['ownershipPolygon'])-translation[[0, 2]]
    disks = _point_disks(region)+_structure_disks(build,region)
    build.geography_protected_disks = disks
    build.geography_roads = []
    build.continent_geography = dict(translation=record['translation'],
        ownershipPolygon=record['ownershipPolygon'], serverOrigin=record['serverOrigin'],
        serverCells=record['serverCells'], geometryMode='continent-owned-v1')
    from amberwood import mesh as M
    from amberwood import terrain as T
    _extend_ground(build,region,polygon)
    _grade_common_boundary(build,region)
    for connection in plan()['connections']:
        end = next((e for e in connection['ends'] if e['region'] == region), None)
        if end is None:
            continue
        anchor = np.asarray(end['anchor'], float)
        outward = np.asarray(end['outward'], float)
        start = np.asarray(end['roadStart'])[[0, 2]]
        collar = anchor[[0, 2]]-outward*42
        guides = [start]
        guides.extend(np.asarray(end.get('connectorGlobal', []), float).reshape(-1, 2)-translation[[0, 2]])
        # Explicit connector points may already include the seam. The approach
        # must end at the collar before its final straight shared segment.
        guides = [p for p in guides if np.linalg.norm(p-anchor[[0, 2]]) > 1]
        guides.append(collar)
        path = []
        for a, b in zip(guides, guides[1:]):
            if np.linalg.norm(a-b) < .01:
                continue
            leg = _road_path(a, b, polygon, disks, build.terrain)
            path.extend(leg if not path else leg[1:])
        if len(path) < 2:
            raise ValueError(f'{region}/{connection["id"]}: road has no approach')
        stations, heights, distances = _profile(build.terrain, np.asarray(path), anchor[1])
        stations = np.vstack([stations, anchor[[0, 2]]])
        heights = np.r_[heights, anchor[1]]
        distances = np.r_[distances, distances[-1]+42]
        def shape_road(points):
            temporary=M.Mesh(positions=points.copy())
            _grade_mesh(temporary,stations,heights,disks)
            return temporary.positions
        _lift_unprotected_scatter(build,shape_road)
        for name, mesh in build.terrain_meshes.items():
            if name.startswith('Terrain_'):
                _grade_mesh(mesh, stations, heights, disks)
        t = build.terrain
        points = np.c_[t.gx.ravel(), t.height.ravel(), t.gz.ravel()]
        temp = M.Mesh(positions=points)
        _grade_mesh(temp, stations, heights, disks)
        t.height = temp.positions[:, 1].reshape(t.height.shape)
        distance, _ = _road_coordinates(points[:, [0, 2]], stations)
        t.tree_block |= distance.reshape(t.height.shape) < 8
        # Render a connected seven-metre bed on the actual surveyed levels.
        # Dense independent spans avoid mitre spikes at curved public junctions.
        parts = []
        material = {'causeway':'cobble_paving','steppe':'steppe_dust_ground',
                    'pasture':'packed_earth_ground','land':'packed_earth_ground'}[connection['profile']]
        for i in range(len(stations)-1):
            a, b = stations[i], stations[i+1]
            tangent = b-a; length = np.linalg.norm(tangent)
            if length < .01:
                continue
            normal = np.array([-tangent[1], tangent[0]])/length*3.5
            quad = M.quad([[a[0]-normal[0], heights[i]+.03, a[1]-normal[1]],
                           [b[0]-normal[0], heights[i+1]+.03, b[1]-normal[1]],
                           [b[0]+normal[0], heights[i+1]+.03, b[1]+normal[1]],
                           [a[0]+normal[0], heights[i]+.03, a[1]+normal[1]]], material=material)
            if quad.normals[:, 1].mean() < 0:
                quad.flip_winding(); quad.recompute_normals(180)
            parts.append(quad)
        build.terrain_meshes['Walk_ContinentRoad_'+connection['id']] = M.merge(parts, material)
        build.vista_materials = getattr(build, 'vista_materials', set()) | {material.removesuffix('_ground')}
        # Scatter is cleared by actual public-road proximity, not a gate-centred rectangle.
        kept = []
        for placement in build.placements:
            p = np.asarray(placement.position, float)
            d, _ = _road_coordinates(p[None, [0, 2]], stations)
            protected = any(np.hypot(p[0]-x, p[2]-z) < radius for x, z, radius in disks)
            if _is_scatter(placement) and d[0] < 7 and not protected:
                continue
            kept.append(placement)
        build.placements[:] = kept
        maximum = float(np.max(np.abs(np.diff(heights))/np.diff(distances)))
        build.geography_roads.append(dict(id=connection['id'], portal=end['portal'],
            stations=np.c_[stations[:, 0], heights, stations[:, 1]].tolist(),
            length=float(distances[-1]), maximumGrade=maximum))


def finalize_geometry(build, region):
    """Cut all physical surface ownership once, preserving nav-only thresholds."""
    if region not in plan()['regions']:
        return
    record = plan()['regions'][region]
    translation = np.asarray(record['translation'])[[0, 2]]
    polygon = np.asarray(record['ownershipPolygon'])-translation
    rectangles = polygon_rectangles(polygon)
    for bucket in (build.terrain_meshes, build.water_meshes):
        for name, mesh in list(bucket.items()):
            if '_StreamThreshold_' in name:
                continue
            clipped = clip_owned_mesh(mesh, rectangles, record['nativePlayableBounds'])
            if name.startswith('Terrain_'):
                clipped = _snap_boundary_mesh(clipped,region)
            if clipped.triangle_count:
                bucket[name] = clipped
            else:
                del bucket[name]
    # Whole props have one owner determined by their authored root. Trees keep
    # complete canopies; clipped terrain, not clipped branches, owns the land.
    retained = []
    for placement in build.placements:
        p = np.asarray(placement.position)[[0, 2]]
        if inside_polygon(p[None], polygon)[0]:
            retained.append(placement)
        elif placement.landmark:
            raise ValueError(f'{region}: protected landmark {placement.node} is outside ownership')
    build.placements[:] = retained
    _blend_boundary_materials(build,region)
    available = set(build.terrain_meshes) | set(build.water_meshes) | {p.node for p in retained}
    for spec in getattr(build, 'streaming_borders', []):
        spec['sceneNodes'] = [name for name in spec.get('sceneNodes', []) if name in available]
    build.notes.append('Continent ownership is actual clipped geometry in one translation-only frame; native structures retain their scale and pose.')
