"""Jade-stone inlet bridges on the two new public approach courses.

The new continental roads crossed the old tidal inlet beds. Keep those waters
open and carry the existing courses between their four-metre landings instead.
The northern bridge ends on the dry ridge before the longer temple-side climb.
"""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
from amberwood import mesh as M
import continent_geography as G
import streaming_borders as SB
from verify_runtime import VerticalRayIndex
import ssarathikit as SK

# A diagonal actor tile contributes a folded corner 4.596m from the course.
# Keep that literal support inside the slab and the actor inside the curbs.
HALF_WIDTH = 4.75
THICKNESS = .8
CROSSINGS = {
    'verdant-ssarathi': {
        'name': 'EastInlet',
        'centres': [[222.5,-88.5],[222.,-86.],[222.,-82.],[226.,-78.],
                    [226.,-74.],[228.,-72.],[228.,-60.],[227.5,-58.5]],
        'endSide': [0.,1.], 'endHeight': 4., 'joinsCauseway': True,
        'piers': [6.,14.,22.,29.]},
    'four-gates-ssarathi': {
        'name': 'NorthInlet',
        'centres': [[154.5,-222.5],[152.,-222.],[144.,-222.],[142.,-224.],
                    [130.,-224.],[118.,-236.],[108.,-236.]],
        'endSide': [0.,-1.], 'endHeight': 4.30, 'joinsCauseway': False,
        'piers': [7.,15.,23.,31.,39.,47.]},
}


def quad(points, normal, material):
    mesh=M.quad(points,material=material)
    if np.mean(mesh.normals,axis=0)@np.asarray(normal)<0:
        mesh.flip_winding();mesh.recompute_normals(180)
    mesh.uvs=mesh.positions[:,[0,2]]*.28
    return mesh


def geometry(spec):
    centre=np.asarray(spec['centres'],float)
    distance=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(centre,axis=0),axis=1))]
    directions=np.diff(centre,axis=0);directions/=np.linalg.norm(directions,axis=1)[:,None]
    sides=np.c_[-directions[:,1],directions[:,0]]
    offsets=[sides[0]]
    for a,b in zip(sides,sides[1:]):
        bisector=a+b;offsets.append(bisector/float(bisector@b))
    offsets.append(np.asarray(spec['endSide']))
    offsets=np.asarray(offsets)
    top=4.+(spec['endHeight']-4.)*np.clip((distance-(distance[-1]-10.))/10.,0.,1.)

    def ribbon(inner,outer,height,material):
        a,b=centre+offsets*inner,centre+offsets*outer
        return M.merge([quad([[a[i,0],height[i],a[i,1]], [a[i+1,0],height[i+1],a[i+1,1]],
                             [b[i+1,0],height[i+1],b[i+1,1]], [b[i,0],height[i],b[i,1]]],
                            [0,1,0],material) for i in range(len(centre)-1)],material)

    def shell(inner,outer,low,high,include_top=False):
        a,b=centre+offsets*inner,centre+offsets*outer
        pieces=[ribbon(inner,outer,low,SK.JADE_ASHLAR)]
        pieces[0].flip_winding();pieces[0].recompute_normals(180)
        if include_top:pieces.append(ribbon(inner,outer,high,SK.JADE_ASHLAR))
        for sign,edge in ((-1.,a),(1.,b)):
            for i in range(len(centre)-1):
                tangent=centre[i+1]-centre[i]
                pieces.append(quad([[edge[i,0],low[i],edge[i,1]], [edge[i+1,0],low[i+1],edge[i+1,1]],
                                    [edge[i+1,0],high[i+1],edge[i+1,1]], [edge[i,0],high[i],edge[i,1]]],
                                   sign*np.array([-tangent[1],0.,tangent[0]]),SK.JADE_ASHLAR))
        for i,normal in ((0,[-directions[0,0],0.,-directions[0,1]]),(-1,[directions[-1,0],0.,directions[-1,1]])):
            if i==-1 and spec['joinsCauseway']:continue
            pieces.append(quad([[a[i,0],low[i],a[i,1]], [b[i,0],low[i],b[i,1]],
                                [b[i,0],high[i],b[i,1]], [a[i,0],high[i],a[i,1]]],normal,SK.JADE_ASHLAR))
        return M.merge(pieces,SK.JADE_ASHLAR)

    deck=ribbon(-HALF_WIDTH,HALF_WIDTH,top,SK.JADE_PAVING)
    bodies=[shell(-HALF_WIDTH,HALF_WIDTH,top-THICKNESS,top)]
    for sign in (-1.,1.):
        inner,outer=sorted((sign*4.38,sign*HALF_WIDTH))
        bodies.append(shell(inner,outer,top-.08,top+.32,True))
    return centre,distance,top,deck,M.merge(bodies,SK.JADE_ASHLAR)


def apply(build):
    if getattr(build,'_inlet_crossings_added',False):raise ValueError('Ssarathi inlet bridges added twice')
    from connector_finish import _native_walk,_subtract_native
    floor=VerticalRayIndex(np.concatenate([m.positions[m.indices.reshape(-1,3)]
        for n,m in build.terrain_meshes.items() if n.startswith('Terrain_')
        and '_StreamCollar_' not in n and '_ContinentBlend_' not in n and m.triangle_count]))
    native=_native_walk(build)
    near_level=native[(native[:,:,1].min(axis=1)>3.)&(native[:,:,1].max(axis=1)<5.)]
    pieces={}
    for road_id,spec in CROSSINGS.items():
        road=next(r for r in build.geography_roads if r['id']==road_id)
        if not np.allclose(np.asarray(road['stations'])[0,[0,2]],spec['centres'][0]):
            raise ValueError('Resurvey the moved Ssarathi inlet landing')
        centre,distance,top,deck,body=geometry(spec)
        prefix='Walk_StreamCauseway_Ssarathi'+spec['name']
        pieces[prefix]=_subtract_native(deck,near_level)
        pieces['Structure_Ssarathi'+spec['name']+'_Ashlar']=_subtract_native(body,near_level)
        piers=[];contacts=[]
        for along in spec['piers']:
            if along>=distance[-1]:continue
            i=min(int(np.searchsorted(distance,along,side='right')-1),len(centre)-2)
            t=(along-distance[i])/(distance[i+1]-distance[i])
            q=centre[i]*(1.-t)+centre[i+1]*t
            direction=centre[i+1]-centre[i];direction/=np.linalg.norm(direction)
            side=np.array([-direction[1],direction[0]])
            corners=[q+direction*a+side*b for a in (-.625,.625) for b in (-3.25,3.25)]
            bed=[floor.top_hit(*p) for p in corners]
            if any(y is None for y in bed):raise ValueError('Inlet pier has no actual bed')
            bottom=min(bed)-.25;high=float(np.interp(along,distance,top))-.7
            if bottom>=high:continue
            pier=M.box((1.25,high-bottom,6.5),material=SK.RUBBLE)
            pier.rotate_y(np.arctan2(-direction[1],direction[0]));pier.translate(q[0],(bottom+high)*.5,q[1])
            piers.append(pier);contacts.append({'xz':q.tolist(),'corners':[p.tolist() for p in corners],'bottom':bottom,'top':high,'bedHeights':bed})
        pieces['Structure_Ssarathi'+spec['name']+'_Piers']=M.merge(piers,SK.RUBBLE)
        road['inletCrossing']={'node':prefix,'centres':centre.tolist(),'heightRange':[float(top.min()),float(top.max())],
                              'slabThickness':THICKNESS,'clearWidth':8.76,'outerWidth':9.5,'piers':contacts}
    specs=deepcopy(build.streaming_borders)
    for spec in specs:spec['sceneNodes']=[]
    extra=SimpleNamespace(terrain_meshes=pieces,water_meshes={},placements=[])
    SB.partition_shared_approaches(extra,specs)
    region=G.plan()['regions']['ssarathi_ruins']
    polygon=np.asarray(region['ownershipPolygon'])-np.asarray(region['translation'])[[0,2]]
    rectangles=G.polygon_rectangles(polygon)
    for name,mesh in extra.terrain_meshes.items():
        mesh=G.clip_owned_mesh(mesh,rectangles)
        if name.startswith('Walk_StreamCauseway_Ssarathi') and mesh.triangle_count:
            faces=mesh.indices.reshape(-1,3);p=mesh.positions[faces]
            reverse=np.cross(p[:,1]-p[:,0],p[:,2]-p[:,0])[:,1]<0.
            faces[reverse]=faces[reverse][:,[0,2,1]]
            mesh.recompute_normals(180)
        if mesh.triangle_count:build.terrain_meshes[name]=mesh
    for spec in specs:
        target=next(s for s in build.streaming_borders if s['id']==spec['id'])
        target['sceneNodes'].extend(n for n in spec['sceneNodes'] if n in build.terrain_meshes)
    build.notes.append('Jade-stone bridges carry the East and North Inlet approaches above the tide, with literal slabs and bed-grounded piers; the basin, ruin bypass and shared landing frames remain intact.')
    build._inlet_crossings_added=True
