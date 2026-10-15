"""Keep geometrically fitted ferry shores stable through the shared road solve.

The constraints cover whole terrain triangles under the quay and boat, not just
the portal coordinate. Selection never changes their bank, ocean bed or limits.
"""
from __future__ import annotations
import numpy as np
from scipy.ndimage import distance_transform_edt
import landscape as L
import ferry_export as F

FEATHER_METRES=12.


def rectangle_vertices(world,center,forward,half_length,half_width):
    """Conservative full-cell coverage of an oriented physical footprint."""
    forward=np.asarray(forward,float);side=np.array([-forward[1],forward[0]])
    dx,dz=world.gx-center[0],world.gz-center[1]
    along=np.maximum(abs(dx*forward[0]+dz*forward[1])-half_length,0)
    across=np.maximum(abs(dx*side[0]+dz*side[1])-half_width,0)
    # Any intersecting 2 m terrain cell has every vertex within its diagonal
    # of the footprint. This also covers tiny slivers at rotated cell corners.
    diagonal=float(np.hypot(world.x[1]-world.x[0],world.z[1]-world.z[0]))
    return np.hypot(along,across)<=diagonal+1e-8


def restore_selected_shores(world):
    """A later trial/forecourt cannot alter an already accepted physical quay."""
    mask=getattr(world,'ferry_shore_mask',None)
    if mask is not None:world.height[mask]=world.ferry_shore_target[mask]


def remember_ferry_fit(world,fit):
    landing=np.asarray(fit['landing']);forward=np.asarray(fit['forward']);reach=float(fit['reach'])
    centre=landing+forward*(reach-4.)/2.
    mask=rectangle_vertices(world,centre,forward,(reach+4.)/2.,F.HALF_WIDTH)
    mask|=rectangle_vertices(world,np.asarray(fit['boatCenter']),forward,3.,1.2)
    if not hasattr(world,'ferry_shore_mask'):
        world.ferry_shore_mask=np.zeros_like(world.height,bool)
        world.ferry_shore_target=world.height.copy()
        world.ferry_shore_records=[]
    overlap=mask&world.ferry_shore_mask
    if overlap.any() and np.max(abs(world.height[overlap]-world.ferry_shore_target[overlap]))>1e-7:
        raise ValueError('A new ferry forecourt moved an already fitted shore')
    # Store the actual surrounding landscape for a local shoulder feather.
    # Previously accepted exact footprint vertices always retain their heights.
    around=distance_transform_edt(~mask,sampling=(world.z[1]-world.z[0],world.x[1]-world.x[0]))<FEATHER_METRES
    refresh=around&~world.ferry_shore_mask
    world.ferry_shore_target[refresh]=world.height[refresh]
    world.ferry_shore_mask|=mask
    world.ferry_shore_records.append({'region':fit['region'],'landing':landing.tolist(),
        'forward':forward.tolist(),'reach':reach,'boatCenter':np.asarray(fit['boatCenter']).tolist(),
        'terrainVertices':int(mask.sum()),'initialContactError':float(fit['contactError']),
        'initialMinimumBoatDepth':float(fit['minimumBoatDepth'])})


def road_shore_constraints(world,active):
    mask=getattr(world,'ferry_shore_mask',None)
    if mask is None:return np.zeros_like(active,bool),world.height
    # The road solves toward the dry bank. Its elevated bridge profile over
    # ocean water remains independent from the fixed seabed underneath it.
    return mask&active&~world.water['mask'],world.ferry_shore_target


def refresh_shore_surroundings(world):
    """Adopt the ground the support stages left around each fitted shore as its feather target.

    The exact quay footprint keeps the heights the landing fit produced; only
    the surrounding band is re-read, so a later road pass restores today's
    bank rather than the one the fit saw before the support stages.
    """
    mask=getattr(world,'ferry_shore_mask',None)
    if mask is None:return
    around=distance_transform_edt(~mask,sampling=(world.z[1]-world.z[0],world.x[1]-world.x[0]))<FEATHER_METRES
    refresh=around&~mask
    world.ferry_shore_target[refresh]=world.height[refresh]


def restore_graded_shores(world,active):
    """Restore the full fitted shore after roads/assembly/drainage postpasses."""
    mask=getattr(world,'ferry_shore_mask',None)
    if mask is None:return
    distance=distance_transform_edt(~mask,sampling=(world.z[1]-world.z[0],world.x[1]-world.x[0]))
    weight=1-L.smoothstep(0,FEATHER_METRES,distance)
    # Solved road triangles keep their graded target outside the physical quay.
    # Feather only ordinary dry shoulders; leave all other drainage unchanged.
    weight[active|world.water['mask']]=0.
    world.height=world.height*(1-weight)+world.ferry_shore_target*weight
    restore_selected_shores(world)


def validate_final_ferries(world):
    """Final actual-ground readback, using exactly the exporter fit contract."""
    results=[]
    for group in F.landing_groups(world):
        fit=F.fit_landing(world,group['landing'],group['region'],
                          ignore_connection_ids=group['connections'])
        results.append({'region':fit['region'],'landing':fit['landing'].tolist(),
            'connections':group['connections'],'forward':fit['forward'].tolist(),'reach':fit['reach'],
            'contactError':fit['contactError'],'maximumGrade':fit['maximumGrade'],
            'minimumBoatDepth':fit['minimumBoatDepth']})
    mask=getattr(world,'ferry_shore_mask',np.zeros_like(world.height,bool))
    change=float(np.max(abs(world.height[mask]-world.ferry_shore_target[mask]))) if mask.any() else 0.
    if change>1e-7:raise ValueError('Final road solve moved fitted ferry terrain')
    world.ferry_shore_report={'terrainVertices':int(mask.sum()),'maximumProtectedHeightChange':change,
        'selected':getattr(world,'ferry_shore_records',[]),'finalFits':results}
    return world.ferry_shore_report
