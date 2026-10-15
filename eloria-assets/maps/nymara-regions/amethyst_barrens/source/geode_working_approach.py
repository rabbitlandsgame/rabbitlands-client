"""Restore the ordinary bank approach to the geode workers' front shelf.

The public-road landform raised a mound across the former foot approach.
Lower that mound into a broad bank, retaining the accepted cave, its floor,
the overhead arch and every boundary.  The four-metre path is copied from
the resulting soil triangles, rather than laid across them as a flat quad.
"""
import numpy as np
import connector_finish as F

REVISION = 'geode-working-bank-1'
WIDTH = 4.0
FEATHER = 8.0
SUPPORT_HALF_WIDTH = 3.0
CONTROLS = np.array([
    [-76.5, 3.9320, -203.5], [-76.5, 3.5574, -206.5],
    [-78.0, 3.1500, -210.5], [-81.5, 2.7402, -214.5],
])


def smooth(value):
    value=np.clip(value,0.,1.)
    return value*value*(3.-2.*value)


def apply(build):
    if getattr(build,'geode_working_approach',None):
        raise ValueError('Geode working approach applied twice')
    bases=[m for n,m in build.terrain_meshes.items() if F._base(n) and m.triangle_count]
    substrate=F.Substrate(bases)
    substrate.rays=F.VerticalRayIndex(F._triangles(bases))
    lengths=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(CONTROLS[:,[0,2]],axis=0),axis=1))]
    cache={}

    def bank_weight(xz):
        # The isolated former footprint mound beside the unlinked rock
        # cluster is part of the same bank, not a cliff to retain. Give it
        # fourteen metres of lateral run into the existing lower ground.
        r=np.hypot((xz[:,0]+87.)/14.,(xz[:,1]+206.5)/10.)
        return 1-smooth((r-.55)/.45)

    def shape(points):
        result=points.copy();xz=points[:,[0,2]]
        distance,along=F.G._road_coordinates(xz,CONTROLS[:,[0,2]])
        weight=np.maximum(1-smooth((distance-SUPPORT_HALF_WIDTH)/FEATHER),bank_weight(xz))
        # The literal cave begins at z=-213.4179. Preserve its whole front
        # shelf and all ground below that line; feather the approach into it.
        weight*=smooth((xz[:,1]+213.4)/1.8)
        weight*=smooth((F.R._edge_distance(build,'amethyst_barrens',xz)-3.)/3.)
        active=np.flatnonzero(weight>1e-10)
        if not len(active):return result
        unique,lookup=np.unique(np.round(xz[active],7),axis=0,return_inverse=True)
        missing=np.array([p for p in unique if tuple(p) not in cache])
        if len(missing):
            old=substrate.sample(missing)
            d,a=F.G._road_coordinates(missing,CONTROLS[:,[0,2]])
            target=np.interp(a*lengths[-1],lengths,CONTROLS[:,1])
            w=(1-smooth((d-SUPPORT_HALF_WIDTH)/FEATHER))*smooth((missing[:,1]+213.4)/1.8)
            w*=smooth((F.R._edge_distance(build,'amethyst_barrens',missing)-3.)/3.)
            shaped=old+(target-old)*w
            broad=bank_weight(missing)*smooth((missing[:,1]+213.4)/1.8)
            broad*=smooth((F.R._edge_distance(build,'amethyst_barrens',missing)-3.)/3.)
            ceiling=target+.012*np.maximum(d-SUPPORT_HALF_WIDTH,0.)**2
            shaped+=(np.minimum(shaped,ceiling)-shaped)*broad
            cache.update((tuple(p),float(v)) for p,v in zip(missing,shaped-old))
        result[active,1]+=np.array([cache[tuple(p)] for p in unique])[lookup]
        return result

    # Only unlinked natural dressing may follow the bank. Every cave, bridge,
    # prop, worker post, discovery and native walking surface keeps its pose.
    from northern_passes import _fixed_nodes
    fixed=_fixed_nodes(build);moved=[]
    for p in build.placements:
        if p.node in fixed or not F.G._is_scatter(p):continue
        before=np.asarray(p.position,float)[None,:];after=shape(before)
        if abs(after[0,1]-before[0,1])>1e-9:
            p.position=tuple(after[0]);moved.append(p.node)
    changed=[]
    for name,mesh in list(build.terrain_meshes.items()):
        if not name.startswith('Terrain_') or not mesh.triangle_count:continue
        # Refinement preserves existing indexed surface coverage, and lets
        # the narrow useful core meet the broad feather without a tall lip.
        F.R.refine_bed(mesh,[{'stations':CONTROLS}])
        updated=shape(mesh.positions)
        if np.any(np.abs(updated[:,1]-mesh.positions[:,1])>1e-9):
            mesh.positions=updated;mesh.recompute_normals(180);changed.append(name)
    terrain=build.terrain
    pts=np.c_[terrain.gx.ravel(),terrain.height.ravel(),terrain.gz.ravel()]
    terrain.height=shape(pts)[:,1].reshape(terrain.height.shape)

    # Copy the final visible ground. A narrow worn skin gives the opener a
    # genuine authored floor while preserving every native walking array.
    for name in changed:
        if not F._base(name):continue
        mesh=build.terrain_meshes[name].copy()
        d,_=F.G._road_coordinates(mesh.positions[:,[0,2]],CONTROLS[:,[0,2]])
        # The metre actors use their tile centres while the conservative
        # half-metre server fold also samples the uphill quarter corners.
        # Keep those literal gentle earth shoulders in the walking skin.
        mesh=F.R._clip_scalar(mesh,d-SUPPORT_HALF_WIDTH)
        if not mesh.triangle_count:continue
        mesh.positions[:,1]+=.025
        # Retain the actual native earth material, colour and UVs. Identical
        # soil appearance makes the physical skin disappear into the bank
        # at both ends; it is not an isolated decorative paving stamp.
        faces=mesh.indices.reshape(-1,3).copy();tri=mesh.positions[faces]
        down=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])[:,1]<0
        faces[down]=faces[down][:,[0,2,1]];mesh.indices=faces.ravel();mesh.recompute_normals(180)
        node='Walk_GeodeWorkingApproach_'+name
        build.terrain_meshes[node]=mesh
        for frame in build.streaming_borders:
            if name in frame.get('sceneNodes',[]):frame['sceneNodes'].append(node)
    build.geode_working_approach=dict(revision=REVISION,width=WIDTH,feather=FEATHER,supportHalfWidth=SUPPORT_HALF_WIDTH,
        controls=CONTROLS.tolist(),changedTerrainMeshes=changed,reseatedNaturalNodes=moved,
        maximumRaise=max(cache.values(),default=0.),maximumLower=min(cache.values(),default=0.))
    build.notes.append('A broad graded bank restores the ordinary four-metre working approach to the geode mouth, with its cave shelf, workers and overhead road arch retained.')
    return build.geode_working_approach
