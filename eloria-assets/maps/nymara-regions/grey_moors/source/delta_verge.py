"""Retain displaced moor scrub in natural pockets beside the new delta bend."""
import hashlib
import numpy as np
import connector_finish as F


def apply(build,controls):
    road=F.VerticalRayIndex(F._triangles([m for n,m in build.terrain_meshes.items()
        if n.startswith(('Walk_ContinentRoad_grey-manymouth','Walk_DeltaRoadBankMouth'))]))
    ground=F.VerticalRayIndex(F._triangles([m for n,m in build.terrain_meshes.items() if F._base(n)]))
    water_tri=F._triangles(list(build.water_meshes.values()))
    water=F.VerticalRayIndex(water_tri) if len(water_tri) else None
    spec=F.G.plan()['regions']['grey_moors'];polygon=np.asarray(spec['ownershipPolygon'])-np.asarray(spec['translation'])[[0,2]]
    protected=getattr(build,'geography_protected_disks',[])
    from northern_passes import _fixed_nodes
    fixed=_fixed_nodes(build);audit=[]
    for p in build.placements:
        if not p.node.startswith('Scatter_Scrub_') or p.node in fixed:continue
        x,_,z=p.position
        if not (218<x<283 and 88<z<139):continue
        mesh=build.meshes[p.mesh];rotation=F.M.rotation_y(p.rotation_y)[:3,:3]
        local=np.concatenate([m.positions for m in getattr(mesh,'all_parts',[mesh])])
        local=local*p.scale@rotation.T;relative=local[:,[0,2]]
        unique=np.unique(np.round(relative,5),axis=0)
        points=unique+np.array([x,z])
        d,_=F.G._road_coordinates(points,np.asarray(controls)[:,[0,2]])
        near=points[d<=5.5]
        if not any(road.top_hit(*q) is not None for q in near):continue
        old=np.asarray(p.position,float);old_ground=ground.top_hit(x,z)
        if old_ground is None:raise ValueError('Covered scrub has no original bank: '+p.node)
        radius=np.linalg.norm(unique,axis=1).max()
        angle=(int(hashlib.sha256(p.node.encode()).hexdigest()[:8],16)%360)*np.pi/180
        chosen=None
        for distance in (6.,8.,10.,12.,15.,18.):
            for theta in angle+np.arange(16)*np.pi/8:
                q=old[[0,2]]+distance*np.array([np.cos(theta),np.sin(theta)])
                shifted=unique+q
                if not F.G.inside_polygon(shifted,polygon).all():continue
                if any(np.linalg.norm(q-np.array([a,c]))<r+radius for a,c,r in protected):continue
                separation,_=F.G._road_coordinates(shifted,np.asarray(controls)[:,[0,2]])
                if separation.min()<5.25:continue
                if any(np.linalg.norm(q-np.asarray(other.position)[[0,2]])<radius+1.
                       for other in build.placements if other is not p and other.node.startswith('Scatter_Scrub_')):continue
                floor=ground.top_hit(*q);wet=water.top_hit(*q) if water else None
                if floor is None or (wet is not None and floor<wet+.2):continue
                chosen=(q,floor);break
            if chosen is not None:break
        if chosen is None:raise ValueError('No clear owned verge pocket for '+p.node)
        q,floor=chosen;p.position=(float(q[0]),float(floor+old[1]-old_ground),float(q[1]))
        audit.append(dict(node=p.node,before=old.tolist(),after=list(p.position),mesh=p.mesh,scale=p.scale,
            minimumRoadClearance=float(F.G._road_coordinates(unique+q,np.asarray(controls)[:,[0,2]])[0].min())))
    build.delta_verge_relocations=audit
    return audit
