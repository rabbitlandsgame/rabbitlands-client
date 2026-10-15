"""Open the continental north road into a broad limestone hillside cut.

The road drops below the native upper terrace. Its former narrow seating band
left leaf-painted walls beside the traveller. A wider, asymmetric cut gives
that descent room while retaining the burn, ruins and aqueduct foundations.
"""
import copy
import numpy as np
import connector_finish as F
import north_burn as W

RESEATED_RUINS={'Ruin_deep_jungle_00','Ruin_deep_jungle_02',
               'Ruin_deep_jungle_04','Ruin_north_watch_00'}


def natural(placement):
    return F.G._is_scatter(placement) or placement.kind in ('fern','vine')


def trunk_root(mesh, scale):
    """Trunk contact, excluding fronds which can hang below palm roots."""
    trunks=[part for part in getattr(mesh,'all_parts',[mesh])
            if part.triangle_count and 'bark' in part.material.lower()]
    if not trunks:
        raise ValueError('A north-bank tree has no identifiable trunk')
    return min(float(part.positions[:,1].min())*scale for part in trunks)


def smooth(value):
    value=np.clip(value,0.,1.)
    return value*value*(3.-2.*value)


def envelope(xz):
    x,z=xz[:,0],xz[:,1]
    return (smooth((x+48.)/14.)*(1-smooth((x-75.)/20.))
            *smooth((z+257.)/9.)*(1-smooth((z+202.)/16.)))


def rock_banks(build,before):
    additions={};count=0
    for name,prior in before.items():
        mesh=build.terrain_meshes[name];mask=W._exposed_rock(mesh,prior)
        if not mask.any():continue
        faces=mesh.indices.reshape(-1,3);vertices=mesh.positions[faces[mask]]
        normals=np.cross(vertices[:,1]-vertices[:,0],vertices[:,2]-vertices[:,0])
        axes=np.argmax(abs(normals),axis=1);uv=np.empty((len(vertices),3,2))
        for axis,plane in enumerate(((2,1),(0,2),(0,1))):
            use=axes==axis;uv[use]=vertices[use][:,:,plane]*.26
        p=vertices.reshape(-1,3)
        rock=F.M.Mesh(positions=p,normals=mesh.normals[faces[mask]].reshape(-1,3),
                      uvs=uv.reshape(-1,2),indices=np.arange(len(p)),material='verdant_wet_limestone')
        rock.recompute_normals(180)
        mesh.indices=faces[~mask].ravel();mesh.recompute_normals(180)
        added='Terrain_NorthApproach_RockBank_'+name
        additions[added]=rock;count+=int(mask.sum())
        for spec in build.streaming_borders:
            if name in spec.get('sceneNodes',[]):spec['sceneNodes'].append(added)
    build.terrain_meshes.update(additions)
    return count


def apply(build):
    if getattr(build,'north_approach_finish',None):
        raise ValueError('North approach applied twice')
    original=[m.copy() for n,m in build.terrain_meshes.items() if F._base(n) and m.triangle_count]
    substrate=F.Substrate(original)
    substrate.rays=F.VerticalRayIndex(F._triangles(original))
    road=next(r for r in build.geography_roads if r['id']=='sunmane-verdant')
    controls=np.array(road.get('contactStations',road['stations']),float)
    controls=controls[(controls[:,0]<100.)&(controls[:,2]<-190.)]
    lengths=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(controls[:,[0,2]],axis=0),axis=1))]
    v=np.diff(controls[:,[0,2]],axis=0)
    keep=np.r_[True,abs(v[:-1,0]*v[1:,1]-v[:-1,1]*v[1:,0])>1e-8,True]
    plan=controls[keep][:,[0,2]]
    road_ray=F.VerticalRayIndex(F._triangles([m for n,m in build.terrain_meshes.items()
                                            if n.startswith('Walk_ContinentRoad_sunmane-verdant')]))
    levels=np.array([road_ray.top_hit(*p[[0,2]]) for p in controls],object)
    levels=np.array([p[1] if y is None else y-.03 for p,y in zip(controls,levels)])
    linked={row.get('node') for key in ('landmarks','interactives','npc_markers','harvestables','portals','spawns')
            for row in getattr(build,key,[]) if row.get('node')}
    if linked & RESEATED_RUINS:
        raise ValueError('A north-road decorative ruin gained a content reference; review its grounding contract')
    structural=copy.copy(build)
    structural.placements=[p for p in build.placements if (not natural(p) or p.node in linked)
                           and p.node not in RESEATED_RUINS]
    feet=F._footing_polygons(structural)
    cache={}

    def unconstrained(missing):
        old=substrate.sample(missing)
        across,along=F.G._road_coordinates(missing,plan)
        road_y=np.interp(along*lengths[-1],lengths,levels)
        run=np.maximum(across-4.6,0.)
        grade=np.where(missing[:,0]<17.5,.43,.51)
        grade+=.035*np.sin((missing[:,1]+238.)/15.)
        cap=road_y+.10+grade*run+.0025*run*run
        weight=envelope(missing)*smooth((F.R._edge_distance(build,'verdant_stair',missing)-3.)/2.)
        weight*=smooth((across-4.5)/1.5)
        return np.minimum(cap-old,0.)*weight

    # These four small, unlinked fragments were left on artificial high soil
    # pins. Move each intact assembly onto the new hillside at the same XZ.
    # Retain its entire original footing shape, translated by one shared Y.
    ruin_shifts={};ruin_feet=[]
    for placement in build.placements:
        if placement.node not in RESEATED_RUINS:continue
        delta=float(unconstrained(np.array([placement.position])[:,[0,2]])[0])
        ruin_shifts[placement.node]=delta
        single=copy.copy(build);single.placements=[placement]
        ruin_feet.extend((polygon,delta) for polygon in F._footing_polygons(single))

    def shape(points):
        result=points.copy();xz=points[:,[0,2]]
        active=np.flatnonzero(envelope(xz)>1e-10)
        if not len(active):return result
        unique,lookup=np.unique(np.round(xz[active],7),axis=0,return_inverse=True)
        missing=np.array([q for q in unique if tuple(q) not in cache])
        if len(missing):
            delta=unconstrained(missing)
            for polygon in feet:
                near=(abs(delta)>1e-10)&np.all(missing>=polygon.min(0)-5.,axis=1)&np.all(missing<=polygon.max(0)+5.,axis=1)
                if near.any():
                    delta[near]*=smooth((F._footing_distance(missing[near],polygon)-1.2)/3.8)
            for polygon,shift in ruin_feet:
                near=np.all(missing>=polygon.min(0)-5.,axis=1)&np.all(missing<=polygon.max(0)+5.,axis=1)
                if near.any():
                    influence=1-smooth((F._footing_distance(missing[near],polygon)-1.2)/3.8)
                    delta[near]+=(shift-delta[near])*influence
            cache.update((tuple(q),float(d)) for q,d in zip(missing,delta))
        result[active,1]+=np.array([cache[tuple(q)] for q in unique])[lookup]
        return result

    # Refine the wider banks, not just the walking strip, before changing height.
    guides=[]
    for offset in (-36.,-24.,-12.,0.,12.,24.,36.):
        guides.append({'stations':[[17.5+offset,35.,-250.],[17.5+offset,35.,-193.]]})
    before={};changed=[]
    for name,mesh in build.terrain_meshes.items():
        if not name.startswith('Terrain_') or not mesh.triangle_count:continue
        if not np.any(envelope(mesh.positions[:,[0,2]])>1e-10):continue
        F.R.refine_bed(mesh,guides)
        prior=mesh.positions[:,1].copy()
        mesh.positions=shape(mesh.positions)
        if np.any(abs(mesh.positions[:,1]-prior)>1e-9):
            changed.append(name)
            if F._base(name):before[name]=prior
        mesh.recompute_normals(180)
        if not F._base(name):
            # Cut rock cannot retain a separate leaf/sward coating above it.
            mask=W._exposed_rock(mesh,prior)
            mesh.indices=mesh.indices.reshape(-1,3)[~mask].ravel()
    rock_faces=rock_banks(build,before)
    terrain=build.terrain
    points=np.c_[terrain.gx.ravel(),terrain.height.ravel(),terrain.gz.ravel()]
    terrain.height=shape(points)[:,1].reshape(terrain.height.shape)
    final_ground=F.VerticalRayIndex(F._triangles([m for n,m in build.terrain_meshes.items()
                                                if F._base(n) and m.triangle_count]))
    removed=[];moved=[];roots=[]
    for placement in build.placements:
        if placement.node in ruin_shifts:
            delta=ruin_shifts[placement.node]
        elif natural(placement) and placement.node not in linked:
            point=np.array([placement.position],float)
            delta=float(shape(point)[0,1]-point[0,1])
            if placement.kind=='tree' and envelope(point[:,[0,2]])[0]>.05:
                # The old source placement may already carry a terrain offset.
                # Seat the actual root on the final triangle, rather than
                # carrying that error down with the analytic height change.
                y=final_ground.top_hit(point[0,0],point[0,2])
                if y is None:raise ValueError(f'No soil under north-bank tree {placement.node}')
                root=trunk_root(build.meshes[placement.mesh],placement.scale)
                delta=float(y-root-point[0,1])
                roots.append({'node':placement.node,'verticalMove':delta,'soilHeight':float(y)})
            # Vines attached to the removed cliff cannot hang in open air.
            if placement.kind=='vine' and delta<-.5:
                removed.append(placement.node);continue
        else:continue
        if abs(delta)>1e-9:
            p=placement.position;placement.position=(p[0],p[1]+delta,p[2]);moved.append(placement.node)
    build.placements[:]=[p for p in build.placements if p.node not in removed]
    for spec in build.streaming_borders:
        spec['sceneNodes']=[name for name in spec.get('sceneNodes',[]) if name not in removed]
    report={'changedTerrainMeshes':changed,'newRockFaces':rock_faces,
            'maximumLowering':-min(cache.values(),default=0.),
            'roadAndWaterUnchanged':True,'retainedStructuralPosesUnchanged':True,
            'reseatedUnlinkedRuins':ruin_shifts,'groundedNaturalObjects':moved,
            'actualTrunkRoots':roots,
            'removedUnlinkedCliffVines':removed}
    build.north_approach_finish=report
    build.notes.append('The northern road descends through a broad asymmetric limestone cut; the old narrow leaf-painted walls are lowered around retained ruin and aqueduct foundations.')
    return report
