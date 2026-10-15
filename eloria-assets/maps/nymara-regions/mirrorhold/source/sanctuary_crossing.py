"""Carry the Sanctuary Road across the lake to its existing shared causeway.

The geographic road follows a useful XZ route but inherited the lakebed's
height. A modest stone bridge keeps that route at the working shore's level,
with an open water channel between bed-grounded piers. Native water, the old
quay structures and the final 42 m shared causeway remain unchanged.
"""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
from amberwood import mesh as M
import continent_geography as G
import streaming_borders as SB
from verify_runtime import VerticalRayIndex

ROAD = 'mirrorhold-four-gates'
DECK = 'Walk_StreamCauseway_mirrorhold-sanctuary'
HALF_WIDTH = 4.25
HEIGHT = 4.0
THICKNESS = .8
CENTRES = np.array([[175.5,50.5],[174.,50.],[162.,50.],[160.,52.],
                    [158.,52.],[156.,54.],[128.,54.],[124.5,57.5]])
DISTANCE = np.r_[0.,np.cumsum(np.linalg.norm(np.diff(CENTRES,axis=0),axis=1))]


def edges(lateral):
    """Shared miter vertices close bends; the last edge meets the native deck."""
    direction=np.diff(CENTRES,axis=0)
    direction/=np.linalg.norm(direction,axis=1)[:,None]
    sides=np.c_[-direction[:,1],direction[:,0]]
    offsets=[sides[0]]
    for a,b in zip(sides,sides[1:]):
        bisector=a+b
        offsets.append(bisector/float(bisector@b))
    # The existing causeway's inner end is the plane Z=57.5.
    offsets.append(np.array([-1.,0.]))
    return CENTRES+np.asarray(offsets)*lateral


def levels(start_height):
    t=np.clip(DISTANCE/4.,0.,1.)
    return start_height+(HEIGHT-start_height)*t*t*(3.-2.*t)


def quad(points,normal,material):
    mesh=M.quad(points,material=material)
    if np.mean(mesh.normals,axis=0)@np.asarray(normal)<0:
        mesh.flip_winding();mesh.recompute_normals(180)
    mesh.uvs=mesh.positions[:,[0,2]]*.28
    return mesh


def ribbon(inner,outer,height,material):
    a,b=edges(inner),edges(outer)
    return M.merge([quad([[a[i,0],height[i],a[i,1]],
                          [a[i+1,0],height[i+1],a[i+1,1]],
                          [b[i+1,0],height[i+1],b[i+1,1]],
                          [b[i,0],height[i],b[i,1]]],[0,1,0],material)
                    for i in range(len(CENTRES)-1)],material)


def shell(inner,outer,bottom,top,material,include_top=False,close_far=True):
    a,b=edges(inner),edges(outer)
    parts=[ribbon(inner,outer,bottom,material)]
    parts[0].flip_winding();parts[0].recompute_normals(180)
    if include_top:parts.append(ribbon(inner,outer,top,material))
    for sign,points in ((-1.,a),(1.,b)):
        for i in range(len(CENTRES)-1):
            tangent=CENTRES[i+1]-CENTRES[i]
            outward=sign*np.array([-tangent[1],0.,tangent[0]])
            parts.append(quad([[points[i,0],bottom[i],points[i,1]],
                               [points[i+1,0],bottom[i+1],points[i+1,1]],
                               [points[i+1,0],top[i+1],points[i+1,1]],
                               [points[i,0],top[i],points[i,1]]],outward,material))
    for i,normal in ((0,np.r_[-np.diff(CENTRES,axis=0)[0,0],0.,-np.diff(CENTRES,axis=0)[0,1]]),
                     (-1,np.array([0.,0.,1.]))):
        if i==-1 and not close_far:continue
        parts.append(quad([[a[i,0],bottom[i],a[i,1]],[b[i,0],bottom[i],b[i,1]],
                           [b[i,0],top[i],b[i,1]],[a[i,0],top[i],a[i,1]]],normal,material))
    return M.merge(parts,material)


def apply(build):
    if getattr(build,'_sanctuary_crossing_added',False):
        raise ValueError('Sanctuary lake crossing added twice')
    road=next(r for r in build.geography_roads if r['id']==ROAD)
    original=np.asarray(road['stations'])
    if not np.allclose(original[0,[0,2]],CENTRES[0],atol=1e-8):
        raise ValueError('The working shore junction moved; resurvey the bridge')
    if not np.allclose(original[-1,[0,2]],[124.5,99.5],atol=1e-8):
        raise ValueError('The fixed Sanctuary border moved')
    floor=VerticalRayIndex(np.concatenate([m.positions[m.indices.reshape(-1,3)]
        for n,m in build.terrain_meshes.items() if n.startswith('Terrain_')
        and '_StreamCollar_' not in n and '_ContinentBlend_' not in n and m.triangle_count]))
    road_ray=VerticalRayIndex(np.concatenate([m.positions[m.indices.reshape(-1,3)]
        for n,m in build.terrain_meshes.items() if n.startswith('Walk_ContinentRoad_'+ROAD) and m.triangle_count]))
    start_height=road_ray.top_hit(*CENTRES[0])
    if start_height is None or abs(start_height-HEIGHT)>.12:
        raise ValueError('The dry bank is not at the surveyed four-metre level')
    top=levels(start_height)
    pieces={DECK:ribbon(-HALF_WIDTH,HALF_WIDTH,top,'cobble_paving')}
    masonry=[shell(-HALF_WIDTH,HALF_WIDTH,top-THICKNESS,top,'pale_ashlar',close_far=False)]
    # The 7.76m clear strip admits seven actor lanes and their folded samples.
    for sign in (-1.,1.):
        inner,outer=sorted((sign*3.88,sign*HALF_WIDTH))
        masonry.append(shell(inner,outer,top-.08,top+.32,'pale_ashlar',include_top=True))
    pieces['Structure_SanctuaryBridge_Ashlar']=M.merge(masonry,'pale_ashlar')
    # The elbow reaches a few square metres of the existing causeway. Keep
    # that literal slab, and remove the exact overlapping new top/soffit.
    from connector_finish import _native_walk, _subtract_native
    existing=_native_walk(build)
    existing=existing[(existing[:,:,1].min(axis=1)>HEIGHT-1.) &
                      (existing[:,:,1].max(axis=1)<HEIGHT+1.)]
    pieces[DECK]=_subtract_native(pieces[DECK],existing)
    pieces['Structure_SanctuaryBridge_Ashlar']=_subtract_native(
        pieces['Structure_SanctuaryBridge_Ashlar'],existing)
    piers=[];contacts=[]
    for along in (8.,18.,28.,38.,48.,53.):
        i=min(int(np.searchsorted(DISTANCE,along,side='right')-1),len(CENTRES)-2)
        t=(along-DISTANCE[i])/(DISTANCE[i+1]-DISTANCE[i])
        centre=CENTRES[i]*(1.-t)+CENTRES[i+1]*t
        direction=CENTRES[i+1]-CENTRES[i];direction/=np.linalg.norm(direction)
        side=np.array([-direction[1],direction[0]])
        corners=[centre+direction*a+side*b for a in (-.625,.625) for b in (-3.25,3.25)]
        bed=[floor.top_hit(*p) for p in corners]
        if any(y is None for y in bed):raise ValueError('Sanctuary bridge pier has no actual lakebed')
        bottom=min(bed)-.3
        pier_top=float(np.interp(along,DISTANCE,top))-.7
        if bottom>=pier_top:continue
        pier=M.box((1.25,pier_top-bottom,6.5),material='rubble_stone')
        pier.rotate_y(np.arctan2(-direction[1],direction[0]))
        pier.translate(centre[0],(bottom+pier_top)/2,centre[1]);piers.append(pier)
        contacts.append(dict(along=along,xz=centre.tolist(),bottom=bottom,top=pier_top,
                             corners=[p.tolist() for p in corners],bedHeights=bed))
    pieces['Structure_SanctuaryBridge_Piers']=M.merge(piers,'rubble_stone')
    # Partition just the new native pieces. Existing water/decks are untouched.
    specs=deepcopy(build.streaming_borders)
    for spec in specs:spec['sceneNodes']=[]
    extra=SimpleNamespace(terrain_meshes=pieces,water_meshes={},placements=[])
    SB.partition_shared_approaches(extra,specs)
    region=G.plan()['regions']['mirrorhold']
    polygon=np.asarray(region['ownershipPolygon'])-np.asarray(region['translation'])[[0,2]]
    rectangles=G.polygon_rectangles(polygon)
    for name,mesh in extra.terrain_meshes.items():
        mesh=G.clip_owned_mesh(mesh,rectangles)
        if name.startswith(DECK) and mesh.triangle_count:
            # Short miter cells can retain the opposite fan winding after
            # subtraction. A walking top must agree with upward raster rays.
            faces=mesh.indices.reshape(-1,3)
            p=mesh.positions[faces]
            reverse=np.cross(p[:,1]-p[:,0],p[:,2]-p[:,0])[:,1]<0.
            faces[reverse]=faces[reverse][:,[0,2,1]]
            mesh.recompute_normals(180)
        if mesh.triangle_count:build.terrain_meshes[name]=mesh
    for spec in specs:
        target=next(s for s in build.streaming_borders if s['id']==spec['id'])
        target['sceneNodes'].extend(n for n in spec['sceneNodes'] if n in build.terrain_meshes)
    road['wetCrossing']={'nativeDeck':DECK,'centres':CENTRES.tolist(),
        'height':HEIGHT,'dryStartHeight':start_height,'slabThickness':THICKNESS,
        'outerWidth':HALF_WIDTH*2,'clearWidth':7.76,'piers':contacts,
        'contacts':['Working shore at [175.5,50.5]','Existing shared causeway at [124.5,57.5]']}
    build.notes.append('Sanctuary Road crosses the lake on a stone bridge at working-quay level, with six bed-grounded piers, open water between supports and the original shared causeway beyond.')
    build._sanctuary_crossing_added=True
