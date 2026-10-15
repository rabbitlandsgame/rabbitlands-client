"""A broad dry ridge carries the southern cartway into Verdant's high crest.

The fixed route and common boundary determine the ridge height. The surrounding
earth rises gradually from the native steppe instead of keeping a narrow road
embankment beside a straight transverse grass cliff.
"""
import numpy as np
import connector_finish as F


def smooth(value):
    value=np.clip(value,0.,1.)
    return value*value*(3.-2.*value)


def _subset(mesh,faces,material):
    indices=mesh.indices.reshape(-1,3)[faces].reshape(-1)
    used,inverse=np.unique(indices,return_inverse=True)
    return F.M.Mesh(positions=mesh.positions[used].copy(),normals=mesh.normals[used].copy(),
                    uvs=mesh.uvs[used].copy(),colors=None if mesh.colors is None else mesh.colors[used].copy(),
                    indices=inverse,material=material)


def apply(build):
    if getattr(build,'_sun_south_landform',False):raise ValueError('Southern ridge applied twice')
    bases=[mesh for name,mesh in build.terrain_meshes.items() if F._base(name) and mesh.triangle_count]
    substrate=F.Substrate(bases)
    # Freeze fallback triangles before the first terrain mesh is reshaped.
    substrate.rays=F.VerticalRayIndex(F._triangles(bases))
    road=next(r for r in build.geography_roads if r['id']=='sunmane-verdant')
    controls=np.asarray(road.get('contactStations',road['stations']),float)
    lengths=np.r_[0,np.cumsum(np.linalg.norm(np.diff(controls[:,[0,2]],axis=0),axis=1))]
    road_meshes=[mesh for name,mesh in build.terrain_meshes.items() if name.startswith('Walk_ContinentRoad_sunmane-verdant')]
    road_ray=F.VerticalRayIndex(F._triangles(road_meshes))
    control_y=np.array([road_ray.top_hit(*p[[0,2]]) for p in controls],object)
    control_y=np.array([p[1] if y is None else y-.03 for p,y in zip(controls,control_y)],float)
    feet=F._footing_polygons(build)
    water_tri=F._triangles(list(build.water_meshes.values()))
    water=F.VerticalRayIndex(water_tri) if len(water_tri) else None
    cache={};references={}

    def envelope(xz):
        x,z=xz[:,0],xz[:,1]
        return smooth((x-118.)/18.)*(1-smooth((x-212.)/18.))*smooth((z-48.)/16.)*(1-smooth((z-118.5)/3.))

    def shape(points):
        result=points.copy();xz=points[:,[0,2]]
        active=np.flatnonzero(envelope(xz)>1e-10)
        if not len(active):return result
        unique,lookup=np.unique(np.round(xz[active],7),axis=0,return_inverse=True)
        missing=np.array([q for q in unique if tuple(q) not in cache])
        if len(missing):
            old=substrate.sample(missing)
            x,z=missing[:,0],missing[:,1]
            for value in np.unique(x):
                key=float(value)
                if key not in references:
                    references[key]=substrate.sample(np.array([[key,48.],[key,118.5]]))
            ends=np.array([references[float(value)] for value in x])
            bank=ends[:,0]+(ends[:,1]-ends[:,0])*smooth((z-48.)/70.5)
            distance,along=F.G._road_coordinates(missing,controls[:,[0,2]])
            route=np.interp(along*lengths[-1],lengths,control_y)
            # An asymmetric buttress gives the western face a longer slope;
            # small longitudinal changes avoid a ruler-straight grass verge.
            width=np.where(x<166.5,35.,29.)+2.*np.sin((z-52.)/19.)
            shoulder=1-smooth((distance-4.25)/width)
            target=bank+(np.maximum(route,bank)-bank)*shoulder
            weight=envelope(missing)*smooth((F.R._edge_distance(build,'sunmane_steppe',missing)-3.)/3.)
            # No change under the actual road or its conservative shoulder.
            weight*=smooth((distance-4.4)/2.6)
            for polygon in feet:
                near=(weight>1e-10)&np.all(missing>=polygon.min(0)-4.5,axis=1)&np.all(missing<=polygon.max(0)+4.5,axis=1)
                if near.any():weight[near]*=smooth((F._footing_distance(missing[near],polygon)-1.5)/3.)
            if water is not None:
                for i in np.flatnonzero(weight>1e-10):
                    wet=water.top_hit(*missing[i])
                    if wet is not None and old[i]<=wet+.15:weight[i]=0.
            delta=(target-old)*weight
            cache.update((tuple(q),float(d)) for q,d in zip(missing,delta))
        result[active,1]+=np.array([cache[tuple(q)] for q in unique])[lookup]
        return result

    F.G._lift_unprotected_scatter(build,shape)
    changed=[]
    for name,mesh in list(build.terrain_meshes.items()):
        if not name.startswith('Terrain_') or not mesh.triangle_count:continue
        updated=shape(mesh.positions)
        if not np.any(np.abs(updated[:,1]-mesh.positions[:,1])>1e-9):continue
        mesh.positions=updated;mesh.recompute_normals(180);changed.append(name)
    terrain=build.terrain
    points=np.c_[terrain.gx.ravel(),terrain.height.ravel(),terrain.gz.ravel()]
    terrain.height=shape(points)[:,1].reshape(terrain.height.shape)
    additions={}
    for name in changed:
        mesh=build.terrain_meshes[name]
        if 'steppe_sward' not in mesh.material:continue
        tri=F._triangles([mesh]);centres=tri.mean(1)
        normal=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
        grade=np.linalg.norm(normal[:,[0,2]],axis=1)/np.maximum(np.abs(normal[:,1]),1e-12)
        distance,_=F.G._road_coordinates(centres[:,[0,2]],controls[:,[0,2]])
        exposed=(grade>.6)&(envelope(centres[:,[0,2]])>.2)&(distance>7.)
        exposed&=F.R._edge_distance(build,'sunmane_steppe',centres[:,[0,2]])>6.
        if not exposed.any():continue
        additions[name+'_SouthRidgeSoil']=_subset(mesh,exposed,'steppe_dust')
        build.terrain_meshes[name]=_subset(mesh,~exposed,mesh.material)
        for frame in build.streaming_borders:
            if name in frame.get('sceneNodes',[]):frame['sceneNodes'].append(name+'_SouthRidgeSoil')
    build.terrain_meshes.update(additions)
    build._sun_south_landform=True
    build.south_landform={'changedTerrainMeshes':changed,'soilMeshes':list(additions),'widthMetres':[35.,29.],
                          'maximumRaise':max(cache.values(),default=0.),'maximumLower':min(cache.values(),default=0.)}
    build.notes.append('The southern road sits on a broad asymmetric earth ridge, with gradual steppe shoulders and exposed dry soil on steep faces; its walking surface and the common crest stay fixed.')
    return build.south_landform
