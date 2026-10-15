"""The new western causeway clears the actual ruin wall, not its round bounds."""
import numpy as np


def clear_west_channel(build):
    frame=next((s for s in getattr(build,'streaming_borders',[])
                if s['id']=='ssarathi-manymouth'),None)
    if frame is None:return
    anchor=np.asarray(frame['anchor'],float);forward=np.asarray(frame['outward'],float)
    side=np.array([-forward[1],forward[0]])

    def shape(points, road=False):
        result=points.copy();relative=points[:,[0,2]]-anchor[[0,2]]
        depth=relative@forward;lateral=abs(relative@side)
        # The real Ruin_0 wall ends7.664m from the road centre. Preserve it,
        # with a feather that ends before that wall; its circumscribed disk
        # otherwise leaves a21m hill through this4m causeway's outer lane.
        weight=np.clip((7.5-lateral)/2.75,0,1)
        weight*=np.clip((depth+48)/4,0,1)*np.clip((-depth+1)/3,0,1)
        weight=weight*weight*(3-2*weight)
        target=anchor[1] if road else anchor[1]-6
        result[:,1]+=weight*(np.minimum(result[:,1],target)-result[:,1])
        return result

    for name,mesh in build.terrain_meshes.items():
        if name.startswith('Terrain_') or name.startswith('Walk_ContinentRoad_ssarathi-manymouth'):
            mesh.positions=shape(mesh.positions,road=name.startswith('Walk_'))
            mesh.recompute_normals(180)
    terrain=build.terrain
    # Trees and small rocks follow the cut; every native built structure stays.
    markers={m.get('node') for m in build.landmarks};removed=set()
    for placement in build.placements:
        if placement.kind not in ('tree','foliage','rock','undergrowth','stone','scatter'):continue
        if placement.node in markers:continue
        p=np.asarray(placement.position,float);ground=float(terrain.height_at(p[0],p[2]))
        changed=shape(np.array([[p[0],ground,p[2]]]))[0,1]
        if changed==ground:continue
        if changed<-.5:removed.add(placement.node);continue
        p[1]+=changed-ground;placement.position=tuple(p)
    build.placements[:]=[p for p in build.placements if p.node not in removed]
    for frame in build.streaming_borders:
        frame['sceneNodes']=[n for n in frame.get('sceneNodes',[]) if n not in removed]
    points=np.c_[terrain.gx.ravel(),terrain.height.ravel(),terrain.gz.ravel()]
    terrain.height=shape(points)[:,1].reshape(terrain.height.shape)
