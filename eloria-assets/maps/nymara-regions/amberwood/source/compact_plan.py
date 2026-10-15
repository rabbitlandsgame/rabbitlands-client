"""384 m Amberwood: the village stays full size; wilderness journeys shorten."""
from copy import deepcopy
import numpy as np
from compact_landscape import Axis,CompactLandscape

SERVER_CELLS=384
SERVER_ORIGIN=(116.0,116.0)
PLAY_MIN_X=-116.0
PLAY_MAX_X=267.0
PLAY_MIN_Z=-267.0
PLAY_MAX_Z=116.0
PLAN=CompactLandscape(Axis(-174,402,-116,268,(-20,85)),
                      Axis(-402,174,-268,116,(-238,-140)),
                      (174,174),SERVER_ORIGIN)

def content_layout(layout):
    out=PLAN.metadata(deepcopy(layout))
    out['npcs']={k:PLAN.point(p) for k,p in layout['npcs'].items()}
    for category in ('harvest','wildlife'):
        out[category]={k:[[round(float(PLAN.x(x)),2),round(float(PLAN.z(z)),2),r*.7]
                          for x,z,r in patches] for k,patches in layout[category].items()}
    return out

def lines(lines):
    return {k:[(float(PLAN.x(p[0])),float(PLAN.z(p[1]))) for p in pts] for k,pts in lines.items()}

def clear_routes(build, routes):
    """Restore human clearance after shortening outdoor travel distances."""
    from amberwood.terrain import _polyline_distance
    roads=list(lines(routes).values())
    xs=np.array([p.position[0] for p in build.placements])
    zs=np.array([p.position[2] for p in build.placements])
    distances=np.full(xs.shape,np.inf)
    for road in roads:
        distances=np.minimum(distances,_polyline_distance(xs,zs,np.asarray(road))[0])
    kept=[]
    for p,distance in zip(build.placements,distances):
        x,_,z=p.position
        if p.kind in ('tree','foliage','rock','fallenlog','stump','undergrowth'):
            clearance=7.0 if p.kind in ('tree','foliage') else 2.5
            harbour=np.hypot(x-float(PLAN.x(-80)),z-float(PLAN.z(30)))<16
            if distance<clearance or (harbour and p.kind in ('tree','foliage')):continue
        kept.append(p)
    build.placements[:]=kept
    used={p.mesh for p in kept}
    build.meshes={k:v for k,v in build.meshes.items() if k in used}
