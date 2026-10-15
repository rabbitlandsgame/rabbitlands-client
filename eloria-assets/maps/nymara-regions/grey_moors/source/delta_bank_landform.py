"""A sloping moor bank replaces the retained diagonal road-cut wall.

Local exception: inward vertices of the old three-metre ownership band are
reshaped. The actual shared boundary line and native walking/structures stay
fixed. This is authored terrain geometry, not collision-mask relaxation.
"""
import numpy as np
import connector_finish as F
from manymouth_approach import collar_height


def smooth(value):
    value=np.clip(value,0.,1.)
    return value*value*(3.-2.*value)


def subset(mesh, mask, material=None):
    ids=mesh.indices.reshape(-1,3)[mask].ravel()
    used,inverse=np.unique(ids,return_inverse=True)
    return F.M.Mesh(positions=mesh.positions[used].copy(),normals=mesh.normals[used].copy(),
        uvs=mesh.uvs[used].copy(),colors=None if mesh.colors is None else mesh.colors[used].copy(),
        indices=inverse,material=material or mesh.material)


def apply(build, controls, mouth):
    if getattr(build,'_delta_bank_landform',False):
        return
    road_tri=F._triangles([m for n,m in build.terrain_meshes.items() if n.startswith('Walk_ContinentRoad_grey-manymouth')])
    road_ray=F.VerticalRayIndex(road_tri)
    # The raised mouth meets the solved curve on its actual triangle edges.
    # A coarse soil triangle must not interpolate a high outside point across
    # that road boundary and cover the exposed paving.
    near=np.all(road_tri[:,:,[0,2]].max(1)>=mouth.min(0)-6.,axis=1)&np.all(road_tri[:,:,[0,2]].min(1)<=mouth.max(0)+6.,axis=1)
    cutters=road_tri[near]
    for name,mesh in list(build.terrain_meshes.items()):
        if not name.startswith('Terrain_') or not mesh.triangle_count:continue
        tri=F._triangles([mesh]);active=np.all(tri[:,:,[0,2]].max(1)>=mouth.min(0)-6.,axis=1)&np.all(tri[:,:,[0,2]].min(1)<=mouth.max(0)+6.,axis=1)
        if not active.any():continue
        conformed=F._split_native_landing(subset(mesh,active),cutters,[dict(stations=controls)],None)
        face=conformed.indices.reshape(-1,3).copy();t=conformed.positions[face]
        down=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0])[:,1]<0;face[down]=face[down][:,[0,2,1]];conformed.indices=face.ravel()
        build.terrain_meshes[name]=F.M.merge([subset(mesh,~active),conformed],material=mesh.material)
    bases=[m for n,m in build.terrain_meshes.items() if F._base(n) and m.triangle_count]
    ground=F.Substrate(bases)
    ground.rays=F.VerticalRayIndex(F._triangles(bases))
    controls=np.asarray(controls,float)
    lengths=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(controls[:,[0,2]],axis=0),axis=1))]
    heights=np.array([road_ray.top_hit(*p[[0,2]]) for p in controls],object)
    heights=np.array([p[1] if y is None else y-.03 for p,y in zip(controls,heights)])
    spec=F.G.plan()['regions']['grey_moors']
    polygon=np.asarray(spec['ownershipPolygon'])-np.asarray(spec['translation'])[[0,2]]
    edges=np.stack([polygon,np.roll(polygon,-1,axis=0)],axis=1)
    # Long boundary segments may cross the local envelope even when their
    # midpoint lies outside it. Include by segment bounds, not midpoint.
    edges=edges[np.all(edges.min(1)<=np.array([295.,162.]),axis=1)&
                np.all(edges.max(1)>=np.array([205.,68.]),axis=1)]
    feet=F._footing_polygons(build)
    water_tri=F._triangles(list(build.water_meshes.values()))
    water=F.VerticalRayIndex(water_tri) if len(water_tri) else None
    cache={}

    def envelope(xz):
        x,z=xz.T
        return smooth((x-210)/12)*(1-smooth((x-275)/19))*smooth((z-70)/20)*(1-smooth((z-149)/12))

    def field(xz):
        answer=np.zeros(len(xz))
        active=np.flatnonzero(envelope(xz)>1e-10)
        unique,lookup=np.unique(np.round(xz[active],7),axis=0,return_inverse=True)
        missing=np.array([p for p in unique if tuple(p) not in cache])
        if len(missing):
            old=ground.sample(missing)
            distances=[];projected=[]
            for a,b in edges:
                v=b-a;t=np.clip((missing-a)@v/(v@v),0,1)
                q=a+t[:,None]*v
                distances.append(np.linalg.norm(missing-q,axis=1));projected.append(q)
            distance=np.asarray(distances);owner=np.argmin(distance,axis=0)
            edge=np.min(distance,axis=0);edge_point=np.asarray(projected)[owner,np.arange(len(missing))]
            edge_y=ground.sample(edge_point)
            d,along=F.G._road_coordinates(missing,controls[:,[0,2]])
            along*=lengths[-1]
            q=np.c_[np.interp(along,lengths,controls[:,0]),np.interp(along,lengths,controls[:,2])]
            road_y=np.interp(along,lengths,heights)
            md,ma=F.G._road_coordinates(missing,mouth)
            use=md<d
            q[use]=mouth[0]+ma[use,None]*(mouth[-1]-mouth[0])
            road_y[use]=collar_height(missing[use,0]);d=np.minimum(d,md)
            # Grade the bank facing the boundary. The road's exact floor and
            # full conservative shoulder remain unchanged.
            side=np.sum((missing-q)*(edge_point-q),axis=1)>0
            blend=edge/np.maximum(edge+np.maximum(d-4.4,0),1e-9)
            target=edge_y+(road_y-edge_y)*blend
            target=np.where(side,target,road_y)
            weight=envelope(missing)*np.where(side,smooth((d-4.4)/1.2),1-smooth((d-4.4)/35.))
            weight[d<=4.4]=0.
            mouth_inside=md<=4.4
            # The flared inward mouth is an actual raised bank. Follow any
            # existing road there exactly, and use the same gentle descent
            # only where its conservative edge needs visible new ground.
            for i in np.flatnonzero(mouth_inside):
                road_top=road_ray.top_hit(*missing[i])
                if road_top is None:road_top=F._nearest_road_height(road_ray,missing[i],radius=8.)
                if road_top is None:raise ValueError('Delta bank mouth has no adjacent actual road')
                target[i]=road_top-.03
            weight[mouth_inside]=1.
            weight[F.R._edge_distance(build,'grey_moors',missing)<1e-6]=0.
            for foot in feet:
                near=(weight>1e-9)&np.all(missing>=foot.min(0)-3.,axis=1)&np.all(missing<=foot.max(0)+3.,axis=1)
                if near.any():weight[near]*=smooth(F._footing_distance(missing[near],foot)/2.)
            if water is not None:
                for i in np.flatnonzero(weight>1e-9):
                    y=water.top_hit(*missing[i])
                    if y is not None and old[i]<=y+.15:weight[i]=0.
            delta=(target-old)*weight
            cache.update((tuple(p),float(v)) for p,v in zip(missing,delta))
        if len(active):answer[active]=np.array([cache[tuple(p)] for p in unique])[lookup]
        return answer

    def shape(points):
        result=points.copy();result[:,1]+=field(points[:,[0,2]])
        return result

    F.G._lift_unprotected_scatter(build,shape)
    changed=[];edge_count=0
    for name,mesh in list(build.terrain_meshes.items()):
        if not name.startswith('Terrain_') or not mesh.triangle_count:continue
        old=mesh.positions.copy();mesh.positions=shape(mesh.positions)
        if not np.any(np.abs(mesh.positions[:,1]-old[:,1])>1e-8):continue
        edge=F.R._edge_distance(build,'grey_moors',old[:,[0,2]])<=1e-6
        assert np.array_equal(old[edge],mesh.positions[edge]),name
        edge_count+=int(edge.sum());mesh.recompute_normals(180);changed.append(name)
    t=build.terrain;points=np.c_[t.gx.ravel(),t.height.ravel(),t.gz.ravel()]
    active=(envelope(points[:,[0,2]])>1e-10)&F.G.inside_polygon(points[:,[0,2]],polygon)
    points[active,1]=ground.sample(points[active][:,[0,2]])+field(points[active][:,[0,2]])
    t.height=points[:,1].reshape(t.height.shape)
    # Expose actual stone faces with vertical texture projection; no painted
    # grass curtain is retained over the same steep triangles.
    additions={}
    for name in changed:
        mesh=build.terrain_meshes[name];tri=F._triangles([mesh]);c=tri.mean(1)
        normal=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
        grade=np.linalg.norm(normal[:,[0,2]],axis=1)/np.maximum(np.abs(normal[:,1]),1e-12)
        d,_=F.G._road_coordinates(c[:,[0,2]],controls[:,[0,2]])
        exposed=(grade>.7)&(envelope(c[:,[0,2]])>.25)&(d>4.4)
        if not exposed.any():continue
        if F._base(name):
            rock=subset(mesh,exposed,'cliff_rock')
            ids=rock.indices.reshape(-1,3);p=rock.positions[ids].reshape(-1,3)
            normals=np.cross(p.reshape(-1,3,3)[:,1]-p.reshape(-1,3,3)[:,0],p.reshape(-1,3,3)[:,2]-p.reshape(-1,3,3)[:,0])
            axis=np.repeat(np.abs(normals[:,0])>=np.abs(normals[:,2]),3)
            rock.positions=p;rock.normals=rock.normals[ids].reshape(-1,3)
            rock.colors=None if rock.colors is None else rock.colors[ids].reshape(-1,4)
            rock.uvs=np.c_[np.where(axis,p[:,2],p[:,0]),p[:,1]]*.22
            rock.indices=np.arange(len(p))
            new=name+('_DeltaBankRock' if '_StreamCell_' in name else '_StreamCell_DeltaBankRock')
            additions[new]=rock
            for frame in build.streaming_borders:
                if name in frame.get('sceneNodes',[]):frame['sceneNodes'].append(new)
        build.terrain_meshes[name]=subset(mesh,~exposed)
    build.terrain_meshes.update(additions)
    build._delta_bank_landform=True
    build.delta_bank_landform=dict(changedMeshes=changed,rockMeshes=list(additions),fixedSharedEdgeVertices=edge_count,
        minimumDelta=min(cache.values(),default=0.),maximumDelta=max(cache.values(),default=0.),
        exception='Local inward vertices of the former 3m band; exact shared boundary and native walking retained')
