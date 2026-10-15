"""Actual source geometry regression; isolated CPU process, no package writes."""
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'eloria-assets/maps/nymara-regions/manymouth_delta/source'


def test_authored_east_landing_canopy_preserves_route_sight_and_root_contact():
    result=subprocess.run([sys.executable,'-X','utf8',str(Path(__file__)), '--probe'],
                          cwd=SOURCE,capture_output=True,text=True,check=True)
    proof=json.loads(result.stdout.splitlines()[-1])
    assert proof['oldIntersections']>0, proof
    assert proof['newIntersections']==0, proof
    assert proof['retainedSpecimens']==4, proof
    assert proof['rootsOnGround'] and proof['allVerticesOwned'], proof
    assert proof['minimumMovedTrunkSpacing']>=3., proof
    assert proof['minimumContentPostSpacing']>=7., proof
    assert proof['minimumNativeFootingSpacing']>=4., proof
    print(json.dumps(proof))


def probe():
    import copy
    import numpy as np
    sys.path.insert(0,str(SOURCE))
    import build_manymouth_delta as B
    import continent_geography as GEO
    from amberwood import mesh as M
    # This regression exercises the retained landing recipe before its source
    # geometry is assembled into the new master. Keep its original coordinates.
    legacy = json.loads((ROOT/'eloria-assets/maps/nymara-regions/_continent/legacy-geography.json').read_text(encoding='utf-8'))
    GEO.plan = lambda: legacy
    changed={'palm_0049','palm_0802','palm_0845','palm_0957'}
    before={}
    original=B.COMPACT._open_east_landing_canopy
    def capture(build):
        before.update({p.node:copy.deepcopy(p) for p in build.placements if p.node in changed})
        original(build)
    B.COMPACT._open_east_landing_canopy=capture
    build=B.build_region()
    actor=np.array([311.5,3.756786,-29.5])
    camera=actor+np.array([17.,29.444864,0.])
    targets=[actor+np.array([x,1.,z]) for x in (-3,0,3) for z in (-3,0,3)]

    def triangles(placement):
        item=build.meshes[placement.mesh]
        transform=M.translation(*placement.position)@M.rotation_y(placement.rotation_y)@M.scaling(placement.scale)
        result=[]
        for part in getattr(item,'all_parts',None) or [item]:
            points=part.positions@transform[:3,:3].T+transform[:3,3]
            result.append(points[part.indices].reshape(-1,3,3))
        return np.concatenate(result)

    def hits(tri,target):
        direction=target-camera;length=np.linalg.norm(direction);direction/=length
        a=tri[:,0];e1=tri[:,1]-a;e2=tri[:,2]-a
        h=np.cross(direction,e2);det=np.einsum('ij,ij->i',e1,h)
        inv=np.divide(1.,det,out=np.zeros_like(det),where=np.abs(det)>1e-7)
        s=camera-a;u=inv*np.einsum('ij,ij->i',s,h);q=np.cross(s,e1)
        v=inv*np.einsum('j,ij->i',direction,q);t=inv*np.einsum('ij,ij->i',e2,q)
        return bool(np.any((np.abs(det)>1e-7)&(u>=0)&(v>=0)&(u+v<=1)&(t>0)&(t<length)))

    nearby=[p for p in build.placements if p.node.startswith(('palm_','March_east_landing_treefern'))
            and np.linalg.norm(np.asarray(p.position)[[0,2]]-actor[[0,2]])<45]
    old=sum(hits(triangles(before.get(p.node,p)),target) for p in nearby for target in targets)
    new=sum(hits(triangles(p),target) for p in nearby for target in targets)
    corrected=[p for p in build.placements if p.node in changed]
    record=GEO.plan()['regions']['manymouth_delta']
    translation=np.asarray(record['translation'])[[0,2]]
    owned=all(GEO.inside_polygon(triangles(p).reshape(-1,3)[:,[0,2]]+translation,
                                 record['ownershipPolygon']).all() for p in corrected)
    grounded=all(abs(p.position[1]-float(build.terrain.height_at(p.position[0],p.position[2])))<.15
                 for p in corrected)
    moved=[p for p in corrected if p.node in ('palm_0845','palm_0957')]
    spacing=min(float(np.linalg.norm(np.asarray(p.position)[[0,2]]-np.asarray(q.position)[[0,2]]))
                for p in moved for q in nearby if q.node!=p.node)
    posts=[]
    for collection in ('landmarks','interactives','npc_markers','harvestables','portals','spawns'):
        for item in getattr(build,collection,[]):
            point=item.get('position') or item.get('center')
            if isinstance(point,(list,tuple)) and len(point)==3:posts.append(np.asarray(point)[[0,2]])
    post_spacing=min(float(np.linalg.norm(np.asarray(p.position)[[0,2]]-q)) for p in moved for q in posts)
    boxes=[]
    for placement in build.placements:
        if placement.kind in ('tree','foliage','undergrowth','rock') or not (placement.collides or placement.landmark):continue
        points=triangles(placement).reshape(-1,3)[:,[0,2]]
        if len(points):boxes.append((points.min(0),points.max(0)))
    footing_spacing=min(float(np.linalg.norm(np.maximum(np.maximum(a-np.asarray(p.position)[[0,2]],
                             np.asarray(p.position)[[0,2]]-b),0))) for p in moved for a,b in boxes)
    return dict(oldIntersections=old,newIntersections=new,retainedSpecimens=len(corrected),
                rootsOnGround=grounded,allVerticesOwned=bool(owned),
                minimumMovedTrunkSpacing=spacing,
                minimumContentPostSpacing=post_spacing,minimumNativeFootingSpacing=footing_spacing,
                specimens={p.node:dict(position=list(p.position),scale=p.scale) for p in corrected})


if __name__=='__main__':
    print(json.dumps(probe()))
