"""One sampled continent, followed by named ownership and travel planning."""
from __future__ import annotations
import heapq
import hashlib
import json
import math
import numpy as np
from scipy.ndimage import gaussian_filter, distance_transform_edt, binary_dilation, label, maximum_filter
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import cg
import landscape as L
import ownership_contract as OWNERSHIP
from storage_bounds import StorageBounds, authoring_storage, frame_values

CELL=2.0
# Graded road corridors through the natural bank apron and beside partial footing feathers.
ROAD_APRON_FEATHER_METRES=8.
ROAD_APRON_FEATHER_MAX_METRES=48.
ROAD_APRON_FLANK_GRADE=.45
ROAD_APRON_CONTENT_MARGIN_METRES=4.
# Ground that retained content stands on, or that a footing feather blends
# toward it at this weight or more, is never moved by a road pass.
ROAD_STANDING_WEIGHT=.5
# Road alignment. A retained solid (a compact colliding structure, its box
# widened by two metres so a four-metre road surface clears it) is impassable
# for the alignment and for every edge between stations; colliding boxes over
# 1600 square metres (enclosures, plazas, halls with walked interiors) keep the
# former soft clearance penalty. A hub inside a solid starts its roads at the
# nearest open ground. Ground steeper than the walkable grade across a station
# is penalised so roads traverse hillsides on their gentle parts.
SOLID_MARGIN_METRES=2.
SOLID_MAXIMUM_AREA_SQUARE_METRES=1600.
SOLID_SOFT_PENALTY=400.
ROUTE_RETRY_STEP_METRES=4.
ROUTE_EDGE_SAMPLE_METRES=2.
ROUTE_EXIT_SEARCH_METRES=30.
ROUTE_END_CANDIDATES=6
ROUTE_END_CANDIDATES_PER_CLASS=2
ROUTE_END_SOLID_RADIUS_METRES=6.
# Terrain terms of the alignment cost. The seam-terminal term is on since the
# sixteenth: the fifteenth's amberwood--mirrorhold crossing put its Amberwood
# terminal inside Watchtower 5 and the amberwood--four_gates crossing its
# terminal in a retained solid, and the entry legs cut through them. The three
# station terms are available and tested but stand at zero: with them on
# (cross-slope 25/40, relief 25, step 600) six of ten public roads re-align by
# more than 6 m, steep road-core samples fall from 8,827 to 4,712, and the
# strict contracts lose 59 records to site arrangements tuned around the
# former alignments (the Mirrorhold civic junction, the Ssarathi temple entry,
# the Amberwood--Four Gates seam approach, the Amberwood estate posts, the
# Whitehorn and Manymouth doors). Turning them on is per-site work.
SEAM_TERMINAL_SOLID_PENALTY=60.  # metres per road terminal of a seam crossing standing in a retained solid
SEAM_RIVER_SIDE_PENALTY=150.     # metres per seam terminal standing across a river from its own hub
SEAM_ANCHOR_ALTERNATIVES=10      # next-best seam stations kept for a seam road that cannot be routed
SEAM_ANCHOR_ALTERNATIVE_SPACING_METRES=6.   # ...each this far from the chosen station and every earlier alternative
SEAM_ROAD_WIDTH_METRES=4.
ROUTE_CROSS_SLOPE_START=.55
ROUTE_CROSS_SLOPE_LINEAR=0.     # per metre of station cross-slope beyond the start
ROUTE_CROSS_SLOPE_SQUARE=0.     # per metre, times the square of that excess
# Ground between two stations that drops below the lower station, or rises
# above the higher one, is a chasm or a ridge the stations alone cannot see: a
# road there is a deck or a cut as deep as the relief. Penalised per metre of
# relief beyond what a graded profile absorbs within one station spacing.
ROUTE_RELIEF_ALLOWANCE_METRES=2.
ROUTE_RELIEF_PENALTY=0.
ROUTE_RELIEF_APRON_METRES=42.   # the outer reach of the natural bank apron the drainage restoration keeps
# A station step steeper than the road's own profile grade (.35) is a deck or
# a cut as tall as the excess, and the excess accumulates down an escarpment:
# a direct descent at grade 1 leaves the road fifteen metres in the air. The
# square of the excess is charged so traverses win over direct descents.
ROUTE_STEP_GRADE=.35
ROUTE_STEP_PENALTY=0.
# The station terms per territory (cross-slope linear, cross-slope square,
# relief, step grade). The territories whose contract sites the fifteenth
# measured as tuned around the former alignments (Mirrorhold's civic
# junction, the Ssarathi temple entry, the Amberwood--Four Gates seam
# approach, the Amberwood estate posts, the Whitehorn and Manymouth doors)
# keep the module weights above until those sites are re-seated; the wild
# territories take the measured weights, so their traverses leave the steep
# hillsides for the gentle ground. Westhaven keeps the module weights too:
# with the measured ones its discovery branch 835 re-aligned ten metres
# through Yard Shed 1 on flat ground (the shed's cells carry a neighbour's
# solid id, so the alignment could not see it).
ROUTE_TERRAIN_TERMS={region:(25.,40.,25.,600.) for region in
    ('grey_moors','crownwater','verdant_stair','amethyst_barrens','sunmane_steppe','mirrorhold',
     'ssarathi_ruins','amberwood','four_gates','whitehorn_range','manymouth_delta','westhaven')}


def terrain_terms(region):
    """(cross-slope linear, cross-slope square, relief, step) weights for a territory's alignments."""
    return ROUTE_TERRAIN_TERMS.get(region,(ROUTE_CROSS_SLOPE_LINEAR,ROUTE_CROSS_SLOPE_SQUARE,ROUTE_RELIEF_PENALTY,ROUTE_STEP_PENALTY))
ROAD_WADE_DEPTH_METRES=.3   # a road bed in shallow water stays this close to the surface (the fold wades .35)
CHUNK=96.0
# Earthworks (owner, 2026-09-16): outside footings a road cuts at most 4 m and fills at most 3 m into the ground it
# finds, and what it does is written into the ground. A routed leg whose ground cannot carry a profile of
# ROAD_EARTHWORKS_GRADE within those limits is rerouted (a cost penalty on the offending stations, up to
# ROUTE_EARTHWORKS_PASSES passes); what still exceeds is reported for an authored switchback.
ROAD_CUT_METRES=4.
ROAD_FILL_METRES=3.
ROAD_EARTHWORKS_GRADE=.45            # the corridor grade settle_roads reconciles roads to (corridor_grade)
ROUTE_EARTHWORKS_PASSES=3
ROUTE_EARTHWORKS_PENALTY=12.         # per metre of alignment on a station within the radius below of an offending one
ROUTE_EARTHWORKS_RADIUS_METRES=8.
ROUTE_EARTHWORKS_TOLERANCE_METRES=.05
# Roads whose routing may fail without failing the composition: they are reported (World.unrouted) instead.
ROUTE_OPTIONAL_KINDS=('door-','discovery-','trail-')


def lipschitz_majorant(values,distances,grade):
    """The smallest function over ``values`` whose slope along the line stays within ``grade``."""
    result=np.asarray(values,float).copy();step=np.diff(np.asarray(distances,float))*grade
    for i in range(1,len(result)):result[i]=max(result[i],result[i-1]-step[i-1])
    for i in range(len(result)-2,-1,-1):result[i]=max(result[i],result[i+1]-step[i])
    return result


def lipschitz_minorant(values,distances,grade):
    """The largest function under ``values`` whose slope along the line stays within ``grade``."""
    return -lipschitz_majorant(-np.asarray(values,float),distances,grade)


def graded_profile(target, distances, floor=None, maximum_grade=.35, cut=None, fill=None, free=None):
    """A bounded-grade profile over ``target`` (the ground along a line), held above any water floor.

    The profile is the mean of the smoothed target's largest and smallest ``maximum_grade`` envelopes (the ground
    itself wherever it is no steeper than the grade), clamped between the grade envelopes of: the two ends (a road
    end stays on its ground; it is never lifted or sunk to make a grade), the water floor (a deck over deep water),
    and the earthworks limits, no lower than ``target - cut`` and no higher than ``target + fill`` (except at ``free``
    stations: a footing's, which fits the road to itself). When those cannot all hold at the grade, the floor, then
    the limits, then the ends win in that order and the profile is steeper there; ``earthworks_excess`` reports such
    a line before it is built.
    """
    target=np.asarray(target,float);distance=np.asarray(distances,float)
    if len(target)<2:return target.copy()
    cut=np.inf if cut is None else float(cut);fill=np.inf if fill is None else float(fill)
    free=np.zeros(len(target),bool) if free is None else np.asarray(free,bool)
    floor=np.full(len(target),-np.inf) if floor is None else np.asarray(floor,float)
    big=1e9
    grade=float(maximum_grade);span=distance[-1]
    ends_low=np.maximum(target[0]-grade*distance,target[-1]-grade*(span-distance))
    ends_high=np.minimum(target[0]+grade*distance,target[-1]+grade*(span-distance))
    limit_low=np.where(free,-big,target-cut);limit_high=np.where(free,big,target+fill)
    floor_low=lipschitz_majorant(np.where(np.isfinite(floor),floor,-big),distance,grade)
    limits_low=lipschitz_majorant(np.minimum(limit_low,big),distance,grade)
    limits_high=lipschitz_minorant(np.maximum(limit_high,-big),distance,grade)
    lower=np.maximum.reduce([floor_low,limits_low,ends_low]);upper=np.minimum(limits_high,ends_high)
    smooth=gaussian_filter(target,sigma=2,mode='nearest')
    if np.any(lower>upper+1e-9):
        # Drop the end cones first; when the limits and the grade still cannot both hold, the profile is the
        # smoothed ground held within the raw limits station by station (steep only where the ground itself is),
        # rather than a grade envelope that would pull it off the ground for a hundred metres around a gully.
        lower=np.maximum(floor_low,limits_low);upper=np.maximum(limits_high,floor_low)
        if np.any(lower>upper+1e-9):
            lower=np.maximum(np.where(np.isfinite(floor),floor,-big),limit_low);upper=np.maximum(limit_high,lower)
            for i in (0,-1):
                if not np.isfinite(floor[i]):lower[i]=upper[i]=target[i]
            return np.clip(np.where(np.isfinite(floor),np.maximum(smooth,floor),smooth),lower,upper)
        for i in (0,-1):
            if not np.isfinite(floor[i]):lower[i]=upper[i]=target[i]
    base=(lipschitz_minorant(smooth,distance,grade)+lipschitz_majorant(smooth,distance,grade))*.5
    return np.clip(base,lower,upper)


def earthworks_excess(target,distances,free=None,cut=ROAD_CUT_METRES,fill=ROAD_FILL_METRES,grade=ROAD_EARTHWORKS_GRADE):
    """Stations where the line's best profile within the cut and fill limits still climbs steeper than ``grade``
    (True = offending): the limited graded_profile, whose steep segments stand where the ground itself is too
    steep for the limits to smooth, so the flags sit on the escarpment, not on the whole line around it."""
    target=np.asarray(target,float);distance=np.asarray(distances,float)
    if len(target)<2:return np.zeros(len(target),bool)
    free=np.zeros(len(target),bool) if free is None else np.asarray(free,bool)
    profile=graded_profile(target,distance,maximum_grade=grade,cut=cut,fill=fill,free=free)
    steep=np.abs(np.diff(profile))>np.maximum(np.diff(distance),1e-9)*grade+ROUTE_EARTHWORKS_TOLERANCE_METRES
    return (np.r_[steep,False]|np.r_[False,steep])&~free


def corridor_grade(target, active, maximum_grade=.45):
    """Reconcile intersecting roads as one surface, including each junction.

    Axis-constrained lower and upper envelopes bound the actual triangle
    gradient, rather than only a road's longitudinal centreline slope.
    """
    lower=np.where(active,target,-np.inf).copy()
    upper=np.where(active,target,np.inf).copy()
    step=CELL*maximum_grade/math.sqrt(2)
    for _ in range(sum(active.shape)):
        lo=lower.copy();hi=upper.copy()
        for dst,src in ((np.s_[1:,:],np.s_[:-1,:]),(np.s_[:-1,:],np.s_[1:,:]),
                        (np.s_[:,1:],np.s_[:,:-1]),(np.s_[:,:-1],np.s_[:,1:])):
            lo[dst]=np.maximum(lo[dst],lower[src]-step)
            hi[dst]=np.minimum(hi[dst],upper[src]+step)
        lo[~active]=-np.inf;hi[~active]=np.inf
        difference=max(np.max(lo[active]-lower[active],initial=0),np.max(upper[active]-hi[active],initial=0))
        lower,upper=lo,hi
        if difference<1e-7:
            result=target.copy();result[active]=(lo[active]+hi[active])*.5
            return result
    raise ValueError('Shared road junction grading did not converge')


def fit_road_to_footings(target,active,fixed_height,fixed,maximum_grade=.60):
    """Fit approaches to immutable courtyard floors through the road graph."""
    if not np.any(fixed):return target,0
    lower=np.where(fixed,fixed_height,-np.inf);upper=np.where(fixed,fixed_height,np.inf)
    step=CELL*maximum_grade/math.sqrt(2)
    for _ in range(sum(active.shape)):
        lo=lower.copy();hi=upper.copy()
        for dst,src in ((np.s_[1:,:],np.s_[:-1,:]),(np.s_[:-1,:],np.s_[1:,:]),
                        (np.s_[:,1:],np.s_[:,:-1]),(np.s_[:,:-1],np.s_[:,1:])):
            lo[dst]=np.maximum(lo[dst],lower[src]-step)
            hi[dst]=np.minimum(hi[dst],upper[src]+step)
        lo[~active]=-np.inf;hi[~active]=np.inf
        if np.array_equal(lo,lower) and np.array_equal(hi,upper):break
        lower,upper=lo,hi
    feasible=active&(lower<=upper+1e-6)
    # Contradictory architectural pins still require a continuous roadbed.
    # Leaving the unrelated original target in just the infeasible cells cuts
    # a cliff along their boundary with fitted cells. Both propagated envelopes
    # have the same graph grade bound; ordering and clipping between them keeps
    # that bound across the entire road. Actual footings are restored separately
    # by settle_roads, and the conflict count/strict collision retain any real
    # architectural impossibility for redesign instead of hiding it here.
    low=np.minimum(lower,upper);high=np.maximum(lower,upper)
    result=target.copy();result[active]=np.clip(result[active],low[active],high[active])
    return result,int(np.count_nonzero(active&~feasible))


def propagate_envelope(values,active,step,upper):
    """Grade envelope over a road corridor graph: the smallest majorant (upper=False) or largest minorant
    (upper=True) of ``values`` whose axis steps between active neighbours stay within ``step``."""
    sign=1. if upper else -1.
    value=np.where(active,values,sign*np.inf).astype(float)
    for _ in range(sum(active.shape)):
        new=value.copy()
        for dst,src in ((np.s_[1:,:],np.s_[:-1,:]),(np.s_[:-1,:],np.s_[1:,:]),(np.s_[:,1:],np.s_[:,:-1]),(np.s_[:,:-1],np.s_[:,1:])):
            new[dst]=np.minimum(new[dst],value[src]+step) if upper else np.maximum(new[dst],value[src]-step)
        new[~active]=sign*np.inf
        if np.array_equal(new,value):return value
        value=new
    return value


def limit_corridor_earthworks(target,active,limited,reference,cut=ROAD_CUT_METRES,fill=ROAD_FILL_METRES,grade=ROAD_EARTHWORKS_GRADE):
    """(target, report): the solved corridor clamped between the grade envelopes of the earthworks limits on
    ``limited`` vertices (outside footings); where no corridor of that grade fits the limits, the limits themselves."""
    report={'limitedVertices':int(limited.sum()),'cutMetres':cut,'fillMetres':fill,'grade':grade}
    if not limited.any():
        report.update(infeasibleVertices=0,changedVertices=0);return target,report
    step=CELL*grade/math.sqrt(2)
    low=np.where(limited,reference-cut,-np.inf);high=np.where(limited,reference+fill,np.inf)
    lower=propagate_envelope(np.where(limited,low,-1e9),limited,step,False)
    upper=propagate_envelope(np.where(limited,high,1e9),limited,step,True)
    feasible=lower<=upper+1e-9
    bottom=np.where(feasible,lower,low);top=np.where(feasible,upper,high)
    result=target.copy()
    result[limited]=np.clip(target[limited],np.minimum(bottom,top)[limited],np.maximum(bottom,top)[limited])
    report.update(infeasibleVertices=int(np.count_nonzero(limited&~feasible)),
                  changedVertices=int(np.count_nonzero(np.abs(result-target)>1e-9)),
                  maximumCorrectionMetres=float(np.max(np.abs(result-target),initial=0)))
    return result,report


def road_shoulder_field(target,active,base,distance,fixed=None):
    """Blend adjacent road banks without nearest-road Voronoi walls.

    Every solved road vertex remains a Dirichlet boundary. Actual structure
    cores and ground beyond the 24 m shoulder are also fixed. Only the empty
    exterior bank interpolates between those geographic constraints.
    """
    fixed=np.zeros_like(active) if fixed is None else np.asarray(fixed,bool)
    free=(distance<24.)&~active&~fixed
    free[[0,-1],:]=False;free[:,[0,-1]]=False
    result=np.asarray(base,float).copy();result[active]=target[active]
    if not free.any():return result
    count=int(free.sum());index=np.full(active.shape,-1,np.int32);index[free]=np.arange(count)
    rows=[np.arange(count)];cols=[rows[0]];values=[np.full(count,4.)]
    rhs=np.zeros(count)
    for axis,offset in ((0,-1),(0,1),(1,-1),(1,1)):
        adjacent=np.roll(index,offset,axis=axis)[free];interior=adjacent>=0
        rows.append(np.flatnonzero(interior));cols.append(adjacent[interior]);values.append(np.full(int(interior.sum()),-1.))
        boundary=np.roll(result,offset,axis=axis)[free]
        rhs+=np.where(interior,0.,boundary)
    matrix=coo_matrix((np.concatenate(values),(np.concatenate(rows),np.concatenate(cols))),shape=(count,count)).tocsr()
    solution,status=cg(matrix,rhs,x0=result[free],rtol=1e-8,atol=1e-6,maxiter=400)
    if status or not np.isfinite(solution).all():raise ValueError('Road exterior shoulder solve did not converge')
    result[free]=solution
    return result


def outline(mask, x0, z0, cell=CELL):
    """Trace the exact outer boundary of a connected pixel ownership mask."""
    mask=np.asarray(mask,bool)
    padded=np.pad(mask,1)
    edges={}
    for dz,dx,a,b in ((-1,0,(0,0),(1,0)),(0,1,(1,0),(1,1)),(1,0,(1,1),(0,1)),(0,-1,(0,1),(0,0))):
        exposed=mask & ~padded[1+dz:1+dz+mask.shape[0],1+dx:1+dx+mask.shape[1]]
        zs,xs=np.nonzero(exposed)
        for z,x in zip(zs.tolist(),xs.tolist()): edges[(x+a[0],z+a[1])]=(x+b[0],z+b[1])
    if not edges: return []
    start=min(edges,key=lambda p:(p[1],p[0]));points=[start];current=edges[start]
    while current!=start:
        points.append(current)
        if current not in edges: raise ValueError('Ownership contour is open')
        current=edges[current]
        if len(points)>len(edges): raise ValueError('Ownership contour did not close')
    result=[]
    for i,p in enumerate(points):
        a=np.subtract(p,points[i-1]);b=np.subtract(points[(i+1)%len(points)],p)
        if a[0]*b[1]!=a[1]*b[0]: result.append([x0+p[0]*cell,z0+p[1]*cell])
    return result


def triangle_sample(grid,x,z,x0=0,z0=0,cell=CELL):
    x,z=np.broadcast_arrays(np.asarray(x,float),np.asarray(z,float))
    fx=np.clip((x-x0)/cell,0,grid.shape[1]-1.0000001)
    fz=np.clip((z-z0)/cell,0,grid.shape[0]-1.0000001)
    ix,iz=fx.astype(int),fz.astype(int);u,v=fx-ix,fz-iz
    a,b,c,d=grid[iz,ix],grid[iz,ix+1],grid[iz+1,ix],grid[iz+1,ix+1]
    return np.where(u+v<=1,a+(b-a)*u+(c-a)*v,d+(c-d)*(1-u)+(b-d)*(1-v))


def ownership_sites(plan,ids):
    """Extra ownership sites per region as {region:(n,2) array of [x, z] in continent metres}.

    A territory owns the ground nearest any of its extra sites as well as the ground nearest
    its own centre, so a region can carry a tail past what one Voronoi centre alone gives it.
    A region with no extra site is absent here and scores exactly as it did before.
    """
    bounds=plan.get('bounds');sites={}
    for region,points in (plan.get('ownership_sites') or {}).items():
        if region not in ids:raise ValueError(f'ownership_sites: no region {region!r} in this plan; it names {list(ids)}')
        points=np.asarray(points,float)
        if points.size==0:continue
        if points.ndim!=2 or points.shape[1]!=2 or not np.isfinite(points).all():
            raise ValueError(f'ownership_sites[{region!r}]: every site must be one finite [x, z] in continent metres')
        if bounds is not None:
            away=(points[:,0]<bounds[0])|(points[:,0]>bounds[2])|(points[:,1]<bounds[1])|(points[:,1]>bounds[3])
            if away.any():raise ValueError(f'ownership_sites[{region!r}]: site {points[away][0].tolist()} lies outside the plan bounds {list(bounds)}')
        sites[region]=points
    return sites


def ownership_map(plan,cell=CELL,ids=None):
    """(ids, owner, x0, z0): which territory owns every cell of the plan's bounds, ``cell`` metres apart.

    ``ids`` are the plan's regions in its own order, or exactly the list given. ``owner`` is an int grid of
    indices into them, row 0 at ``z0`` and column 0 at ``x0``, whose cell [row][column] covers the metres
    [x0+column*cell, x0+(column+1)*cell) by [z0+row*cell, z0+(row+1)*cell) and is scored at their centre.

    An explicit hash-pinned ``ownership_contract`` samples canonical polygons;
    boundary ties use lexical region IDs, independently of output index order.
    Without it the partition is centres, ``ownership_bias`` and ``ownership_sites`` alone -- no heights, no water, no
    sampled continent -- so a plan editor can draw it at 8 m without building a World. A region's score at a
    cell is the least squared distance to its centre and to any extra site it declares, less its bias; the
    lowest score owns the cell and a tie keeps the region listed first. The constructor reads this at CELL
    on its own grid, so the preview and the world it previews cannot drift apart.
    """
    regions={r['id']:r for r in plan['regions']}
    ids=list(regions) if ids is None else list(ids)
    contract=OWNERSHIP.for_plan(plan,ids)
    if contract is not None:
        if isinstance(cell,bool) or not np.isfinite(cell) or cell<=0:
            raise ValueError('ownership cell spacing must be finite and positive')
        x0,z0,x1,z1=contract.bounds
        # A preview may have a partial final cell (1500 m is not divisible by
        # 8 m). Sample its actual center inside the domain, not beyond it.
        x=np.arange(x0,x1,cell);z=np.arange(z0,z1,cell)
        gx,gz=np.meshgrid((x+np.minimum(x+cell,x1))*.5,
                         (z+np.minimum(z+cell,z1))*.5)
        return ids,contract.sample(gx,gz,ids),x0,z0
    centers=np.array([regions[region]['center'] for region in ids],float)
    sites=ownership_sites(plan,ids);bias=plan.get('ownership_bias',{})
    x0,z0,x1,z1=plan['bounds']
    x=np.arange(x0,x1+cell*.5,cell);z=np.arange(z0,z1+cell*.5,cell)
    gx,gz=np.meshgrid(x[:-1]+cell*.5,z[:-1]+cell*.5)
    points=np.c_[gx.ravel(),gz.ravel()]
    scores=np.full(len(points),np.inf);owners=np.zeros(len(points),int)
    for index,(region,center) in enumerate(zip(ids,centers)):
        # Nearest of the region's own centre and any extra ownership site it declares.
        score=np.sum((points-center)**2,axis=1)
        for site in sites.get(region,()):score=np.minimum(score,np.sum((points-site)**2,axis=1))
        score=score-bias.get(region,0)
        selected=score<scores;owners[selected]=index;scores[selected]=score[selected]
    return ids,owners.reshape(len(z)-1,len(x)-1),x0,z0


def owner_components(plan,region,cell=8.):
    """One territory's ground as 4-connected component masks over ``ownership_map``'s grid, largest first.

    Each mask carries that grid's own shape, row 0 at z0, so a caller counts its cells with
    ``np.count_nonzero`` and reads its metres with ``component_extent``. One mask is one body of land;
    every mask past the first is a detached island, ground the region wins on the far side of a
    neighbour. ``outline`` traces a single contour, so an island is quietly missing from
    ``World.polygons`` and from the ``bounds`` and ``address`` read off it: this is how to see one.
    """
    ids,owner=ownership_map(plan,cell)[:2]
    if region not in ids:raise ValueError(f'owner_components: no region {region!r} in this plan; it names {list(ids)}')
    labels,count=label(owner==ids.index(region))
    sizes=np.bincount(labels.ravel(),minlength=count+1)
    return [labels==value for value in sorted(range(1,count+1),key=lambda value:(-int(sizes[value]),value))]


def owner_islands(plan,region,cell=8.):
    """A territory's detached components: ``owner_components`` past its largest, empty when it is one body."""
    return owner_components(plan,region,cell)[1:]


def component_extent(mask,x0,z0,cell=8.):
    """One component mask as {'cells': int, 'bounds': [x0, z0, x1, z1]}, the metre rectangle its cells cover."""
    rows,columns=np.nonzero(np.asarray(mask,bool))
    if not len(rows):return {'cells':0,'bounds':[]}
    return {'cells':int(len(rows)),'bounds':[float(x0+columns.min()*cell),float(z0+rows.min()*cell),
        float(x0+(columns.max()+1)*cell),float(z0+(rows.max()+1)*cell)]}


class World:
    def hub(self,region):
        """Inhabited arrival is independent of the territory's geographic seed."""
        return np.asarray(self.plan.get('inhabited_hubs',{}).get(region,self.regions[region]['center']),float)

    def __init__(self, plan=None, *, region_contracts=None, require_authored_storage=False):
        self.plan=L.load_plan() if plan is None else plan
        self.regions={r['id']:r for r in self.plan['regions']}
        self.ids=list(self.regions)
        self.ownership_contract=OWNERSHIP.for_plan(self.plan,self.ids)
        self.ownership_source_dependencies=OWNERSHIP.source_dependencies(self.plan)
        self._install_storage_contracts(region_contracts, require_authored_storage)
        self.centers=np.array([r['center'] for r in self.regions.values()],float)
        self.x0,self.z0,self.x1,self.z1=self.plan['bounds']
        self.x=np.arange(self.x0,self.x1+CELL*.5,CELL)
        self.z=np.arange(self.z0,self.z1+CELL*.5,CELL)
        self.gx,self.gz=np.meshgrid(self.x,self.z)
        self.height=L.height_at(self.gx,self.gz,self.plan)
        self.water=L.water_fields(self.gx,self.gz,height=self.height,plan=self.plan)
        self.original_height=self.height.copy()
        self.ownership_sites=({} if self.ownership_contract is not None else
                              ownership_sites(self.plan,self.ids))
        # Scored by the module-level partition, so an editor's preview at another spacing cannot drift from it.
        self.owner=ownership_map(self.plan,CELL,self.ids)[1]
        self.polygons=(self.ownership_contract.polygons() if self.ownership_contract is not None else
                       {r:outline(self.owner==i,self.x0,self.z0) for i,r in enumerate(self.ids)})
        self.obstacles=np.zeros_like(self.height,dtype=bool)
        self.solids=np.zeros_like(self.height,dtype=bool)
        self.routing=[]
        self.roads=[]
        self.road_distance=np.full_like(self.height,np.inf)
        self.road_nearest=np.full_like(self.height,np.inf)
        self.road_target=self.height.copy()
        self.foundation_weight=np.zeros_like(self.height)
        self.foundation_target=np.zeros_like(self.height)
        self.assembly_weight=np.zeros_like(self.height)
        self.assembly_target=self.height.copy()
        self.connections=[]
        self.quay_contacts=[]

    def height_at(self,x,z): return triangle_sample(self.height,x,z,self.x0,self.z0)

    def bounds(self,region):
        p=np.array(self.polygons[region]);return p.min(axis=0),p.max(axis=0)

    def address(self,region):
        source=getattr(self,'_source_storage',{}).get(region)
        if source is not None:
            origin,bounds=source
            return list(origin),[bounds.width,bounds.height]
        contract=getattr(self,'ownership_contract',None)
        if contract is not None:
            # A polygon edit must never rebase existing logical coordinates.
            # Later storage migration may expand this baseline independently.
            return contract.frame(region)['serverOrigin'],contract.storage(region)['serverCells']
        lo,hi=self.bounds(region);center=self.centers[self.ids.index(region)]
        local_lo=np.floor(lo-center)-4;local_hi=np.ceil(hi-center)+4
        cells=int(math.ceil(max(local_hi-local_lo)/6)*6)
        origin=[int(-local_lo[0]),int(local_hi[1])]
        return origin,[cells,cells]

    def _install_storage_contracts(self, contracts, require_authored):
        """Install validated source addresses before terrain or address consumers.

        Production selected composition requires every region. Synthetic worlds
        may deliberately omit all source contracts and use ownership baselines.
        """
        from authoring_catalog import RegionContract
        self._source_storage={}
        self._storage_contracts={}
        contracts={} if contracts is None else dict(contracts)
        if set(contracts)-set(self.ids):
            raise ValueError('storage contracts name unknown regions')
        if require_authored and self.ownership_contract is not None and set(contracts)!=set(self.ids):
            raise ValueError('selected production requires authored storage contracts for every region; missing '+
                             ', '.join(sorted(set(self.ids)-set(contracts))))
        for region,contract in contracts.items():
            if not isinstance(contract,RegionContract) or contract.id!=region or contract.spec_sha256 is None:
                raise ValueError(f'{region}: expected a validated hash-bound RegionContract')
            payload=contract.spec_path.read_bytes()
            if hashlib.sha256(payload).hexdigest()!=contract.spec_sha256:
                raise ValueError(f'{region}: authoring spec changed before World construction')
            document=json.loads(payload)
            server=document['server']
            bounds=authoring_storage(server)
            if (document.get('regionId')!=region or tuple(server['origin'])!=contract.server_origin or
                    (bounds.width,bounds.height)!=contract.server_cells or
                    (bounds.min_x,bounds.min_y)!=contract.server_tile_min or
                    server.get('serverStorageVersion')!=contract.server_storage_version or
                    tuple(server['collisionOriginMetres'])!=contract.collision_origin_metres or
                    frame_values(server)!=contract.server_frame or
                    tuple(document['continentTranslation'])!=contract.continent_translation):
                raise ValueError(f'{region}: source storage/frame differs from validated contract')
            center=self.regions[region]['center']
            if contract.continent_translation!=(center[0],0,center[1]):
                raise ValueError(f'{region}: authored translation differs from immutable plan frame')
            if self.ownership_contract is not None:
                OWNERSHIP.validate_authoring_frame({'binding':{'regionId':region},
                    'coordinateFrame':self.ownership_contract.frame(region),
                    'baselineStorage':self.ownership_contract.storage(region)},document)
            self._source_storage[region]=(contract.server_origin,bounds)
            self._storage_contracts[region]=contract

    def storage(self,region):
        """Logical bounds; array indices subtract minima, transforms do not."""
        source=getattr(self,'_source_storage',{}).get(region)
        if source is not None:return source[1]
        contract=getattr(self,'ownership_contract',None)
        if contract is not None:
            baseline=contract.storage(region)
            return StorageBounds(*baseline['serverCells'],*baseline['serverTileMin'])
        return StorageBounds(*self.address(region)[1])

    def storage_contract(self,region):
        """Portable effective address and exact source identity for export caches."""
        origin,cells=self.address(region)
        result={'serverOrigin':origin,'serverCells':cells,**self.storage(region).metadata()}
        contract=getattr(self,'_storage_contracts',{}).get(region)
        if contract is not None:
            if hashlib.sha256(contract.spec_path.read_bytes()).hexdigest()!=contract.spec_sha256:
                raise ValueError(f'{region}: storage source changed; recompose before export')
            result['authoringSpecSha256']=contract.spec_sha256
        return result

    def owner_at(self,x,z):
        contract=getattr(self,'ownership_contract',None)
        if contract is not None:
            return contract.sample(x,z,self.ids)
        ix=np.clip(((np.asarray(x)-self.x0)/CELL).astype(int),0,self.owner.shape[1]-1)
        iz=np.clip(((np.asarray(z)-self.z0)/CELL).astype(int),0,self.owner.shape[0]-1)
        outside=(np.asarray(x)<self.x0)|(np.asarray(x)>self.x1)|(np.asarray(z)<self.z0)|(np.asarray(z)>self.z1)
        return np.where(outside,-1,self.owner[iz,ix])

    def foundation(self,center,radius,height,feather=16,obstacle=False):
        """Accumulate compatible footing constraints; settle all sites together."""
        x,z=center
        ix0=max(0,int((x-radius-feather-self.x0)/CELL));ix1=min(len(self.x),int((x+radius+feather-self.x0)/CELL)+2)
        iz0=max(0,int((z-radius-feather-self.z0)/CELL));iz1=min(len(self.z),int((z+radius+feather-self.z0)/CELL)+2)
        sl=np.s_[iz0:iz1,ix0:ix1]
        d=np.hypot(self.gx[sl]-x,self.gz[sl]-z)
        weight=1-L.smoothstep(radius,radius+feather,d)
        self.foundation_weight[sl]+=weight
        self.foundation_target[sl]+=weight*height
        if obstacle: self.obstacles[sl]|=d<max(1,radius-1)

    def settle_foundations(self):
        weight=np.clip(self.foundation_weight,0,1)
        target=self.foundation_target/np.maximum(self.foundation_weight,1e-12)
        self.height=self.original_height*(1-weight)+target*weight
        self.height=self.height*(1-self.assembly_weight)+self.assembly_target*self.assembly_weight
        # Drainage remains the global authority beneath any settlement. A
        # structure spanning a channel needs a real floor and supports.
        river=self.water['river_mask']&(self.water['depth']>.35)
        self.height[river]=self.original_height[river]
        self.restore_drainage_corridor('foundations')
        self.water=L.water_fields(self.gx,self.gz,height=self.height,plan=self.plan)

    def earthworks_free(self):
        """Ground a road's earthworks are not limited on: a settlement's rigid footing, which fits the road to its own
        plane, and the civic ground a settlement releases to its designed street grading (Mirrorhold's city survey
        between its buildings, apply_mirror_street_footings). Every other road vertex -- open country, a footing's
        feather, a single placement's pad -- keeps within ROAD_CUT_METRES and ROAD_FILL_METRES of the ground the
        road pass finds, so a road network can no longer sink a court or a village it passes."""
        assembly=getattr(self,'assembly_weight',None)
        if assembly is None:return np.zeros(self.height.shape,bool)
        footing=getattr(self,'road_footing_weight',assembly)
        return (footing>=.999)|((assembly>=.05)&(footing<assembly-1e-9))

    def standing_weight(self):
        """How firmly retained content or its footing feather claims each vertex (0..1)."""
        footing=getattr(self,'road_footing_weight',getattr(self,'assembly_weight',None))
        footing=np.zeros_like(self.height) if footing is None else footing
        foundation=np.clip(getattr(self,'foundation_weight',np.zeros_like(self.height)),0,1)
        return np.maximum(footing,foundation)

    def restore_drainage_corridor(self,stage):
        """Keep the natural bank apron through later cut/fill operations.

        Real footing cores stay fixed. A 32 m transition around them preserves
        settlement support without cutting a hard rectangular hole in the bank
        protection. Road cores keep their earthworks through the apron only
        outside the river setback (river_crossings.setback_metres at its
        minimum): inside it, where only a bridge's landings stand, the natural
        bank returns.
        """
        # The natural channel depends on the original ground and the plan alone; both are fixed once the prepare
        # stages have run, so it is measured once per original ground.
        signature=(id(self.original_height),float(np.sum(self.original_height)))
        cached=getattr(self,'_natural_channel',None)
        if cached is None or cached[0]!=signature:
            natural=L.water_fields(self.gx,self.gz,height=self.original_height,plan=self.plan)
            cached=(signature,natural['river_mask'])
            self._natural_channel=cached
        channel=cached[1]
        if not np.any(channel):return
        distance=distance_transform_edt(~channel)*CELL
        apron=1-L.smoothstep(10,42,distance)
        hard=self.assembly_weight>=.999
        for quay in getattr(self,'quay_contacts',[]):
            hard|=np.hypot(self.gx-quay['center'][0],self.gz-quay['center'][1])<=4
        # Channel beds were already made authoritative by the calling stage.
        # Buildings alongside them are retained, but cannot fill flowing water.
        hard&=~channel
        clearance=distance_transform_edt(~hard)*CELL if np.any(hard) else np.full_like(apron,np.inf)
        weight=apron*L.smoothstep(0,32,clearance)
        # A graded road keeps its corridor through the bank apron: a road along
        # a bank is a bench cut into it, feathered over 8 m. The channel bed
        # itself stays natural below (restored unconditionally further down).
        core=binary_dilation(self.road_distance<=1.65,iterations=1) if getattr(self,'roads',None) else np.zeros_like(apron,dtype=bool)
        if core.any():
            # Only where the bench's own flank stays clear of retained content
            # and its footing feathers: a bench flank through a walked yard cut
            # the content off the hub, and rigid floors cannot follow a partial
            # change. Each core cell's flank reaches rise/.45 (8-48 m).
            standing=self.standing_weight()
            content_distance=distance_transform_edt(standing<ROAD_STANDING_WEIGHT*.5)*CELL
            reach=np.clip(np.abs(self.height-self.original_height)/ROAD_APRON_FLANK_GRADE,ROAD_APRON_FEATHER_METRES,ROAD_APRON_FEATHER_MAX_METRES)
            core&=content_distance>reach+ROAD_APRON_CONTENT_MARGIN_METRES
        setback=self.river_setback(None)
        if core.any() and setback is not None:
            core&=distance>setback
        if core.any():
            # The bench flank must itself be walkable: feather over at least
            # 8 m, and over rise/.45 where the road sits far above or below
            # the natural bank.
            outside,nearest=distance_transform_edt(~core,return_indices=True)
            rise=np.abs(self.height-self.original_height)[nearest[0],nearest[1]]
            feather=np.clip(rise/ROAD_APRON_FLANK_GRADE,ROAD_APRON_FEATHER_METRES,ROAD_APRON_FEATHER_MAX_METRES)
            weight*=L.smoothstep(0,1,outside*CELL/feather)
        conflict=hard&(apron>.05)&(np.abs(self.height-self.original_height)>.5)
        delta=self.height-self.original_height
        before=self.height.copy()
        self.height=self.height*(1-weight)+self.original_height*weight
        self.height[channel]=self.original_height[channel]
        report={'apronMetres':10,'outerMetres':42,'footingFeatherMetres':32,
            'restoredVertices':int(np.count_nonzero(weight>0)),'roadCoreVertices':int(core.sum()),
            'conflictingHardVertices':int(conflict.sum()),
            'maximumRetainedFill':float(np.max(delta[conflict],initial=0)),
            'maximumRetainedCut':float(np.max(-delta[conflict],initial=0)),
            'maximumCorrection':float(np.max(np.abs(self.height-before),initial=0))}
        if not hasattr(self,'drainage_restoration'):self.drainage_restoration={}
        self.drainage_restoration[stage]=report
        self.water=L.water_fields(self.gx,self.gz,height=self.height,plan=self.plan)
        return report

    def assembly_foundation(self,sl,target,weight):
        replace=weight>self.assembly_weight[sl]
        self.assembly_target[sl]=np.where(replace,target,self.assembly_target[sl])
        self.assembly_weight[sl]=np.maximum(self.assembly_weight[sl],weight)

    def structure_obstacle(self,low,high,clearance=6,solid=True):
        """Keep road and grove placement outside actual structure bounds.

        A compact structure is also a solid: no road alignment passes through
        its box (widened by SOLID_MARGIN_METRES). Boxes over
        SOLID_MAXIMUM_AREA_SQUARE_METRES are enclosures, plazas or halls whose
        interiors are walked, and a caller passes ``solid=False`` for a gate,
        arch or arcade built to be passed; those only carry the soft
        clearance penalty.
        """
        lo=np.asarray(low)[[0,2]]-clearance;hi=np.asarray(high)[[0,2]]+clearance
        ix0=max(0,int((lo[0]-self.x0)/CELL));ix1=min(len(self.x),int((hi[0]-self.x0)/CELL)+2)
        iz0=max(0,int((lo[1]-self.z0)/CELL));iz1=min(len(self.z),int((hi[1]-self.z0)/CELL)+2)
        self.obstacles[iz0:iz1,ix0:ix1]=True
        size=np.asarray(high)[[0,2]]-np.asarray(low)[[0,2]]
        if not hasattr(self,'solids'):self.solids=np.zeros_like(self.obstacles)
        if solid and np.all(np.isfinite(size)) and np.all(size>=0) and float(size.prod())<=SOLID_MAXIMUM_AREA_SQUARE_METRES:
            lo=np.asarray(low)[[0,2]]-SOLID_MARGIN_METRES;hi=np.asarray(high)[[0,2]]+SOLID_MARGIN_METRES
            ix0=max(0,int((lo[0]-self.x0)/CELL));ix1=min(len(self.x),int((hi[0]-self.x0)/CELL)+2)
            iz0=max(0,int((lo[1]-self.z0)/CELL));iz1=min(len(self.z),int((hi[1]-self.z0)/CELL)+2)
            self.solids[iz0:iz1,ix0:ix1]=True
            # Each solid keeps its own identity, so a road end inside one
            # structure frees that structure alone, never a whole village.
            if not hasattr(self,'solid_ids'):self.solid_ids=np.zeros(self.obstacles.shape,np.int32)
            self.solid_ids[iz0:iz1,ix0:ix1]=int(self.solid_ids.max())+1

    def prepare_quay_court(self,center):
        d=np.hypot(self.gx-center[0],self.gz-center[1])
        elevation=max(1.8,float(self.height_at(*center)))
        dry=~self.water['mask']
        weight=(1-L.smoothstep(4,12,d))*dry
        self.height=self.height*(1-weight)+elevation*weight
        self.quay_contacts.append({'center':list(center),'elevation':elevation})

    def settle_roads(self,respect_standing=False):
        if not self.roads:return
        # All full-width roads agree before any shoulders are blended. This
        # prevents the last outgoing road from cutting a cliff through another.
        # Include a full triangle ring outside the walking corridor. Otherwise
        # a half-metre server sample at a bend can share an ungraded shoulder
        # vertex even though the centreline itself has an acceptable grade.
        authored=np.asarray(getattr(self,'authored_terrain_authority',np.zeros_like(self.height,dtype=bool)),bool)
        if authored.shape!=self.height.shape:
            raise ValueError('authored terrain authority does not match the shared road grid')
        # A saved preview is already the complete roadbed inside its authored
        # terrain.  Its incidental overlap with an unrelated procedural road
        # shoulder is not a structural footing: propagating that height across
        # the entire shared road graph can reshape a distant served approach.
        # Solve only the procedural side; the exact saved side and their shared
        # handoff are checked by the final seam/served-collision gates.
        active=binary_dilation(self.road_distance<=1.65,iterations=1)&~authored
        target=corridor_grade(self.road_target,active)
        dz,dx=np.gradient(self.assembly_target,CELL)
        footing_weight=getattr(self,'road_footing_weight',self.assembly_weight)
        fixed=active&(footing_weight>=.999)&(np.hypot(dx,dz)<.5)&~self.water['mask']
        fixed_height=self.assembly_target.copy();quay_fixed=np.zeros_like(active)
        if authored.any():
            authored_height=np.asarray(self.authored_terrain_height)
            if authored_height.shape!=self.height.shape:
                raise ValueError('authored terrain height does not match the shared road grid')
        # After the support stages, ground that retained content stands on, or
        # that a footing feather blends toward it, is never moved by a road:
        # the road is fitted to it. Pinned footings hold their surveyed plane,
        # feathers their current blended ground (rigid assemblies cannot follow
        # a partial change and nothing repairs it afterwards). The first pass
        # may still shape those zones: the support stages refit them after it.
        standing=self.standing_weight() if respect_standing else np.zeros_like(self.height)
        feather=active&(standing>=ROAD_STANDING_WEIGHT)&~fixed&~self.water['mask']
        fixed_height[feather]=self.height[feather];fixed|=feather
        for quay in self.quay_contacts:
            d=np.hypot(self.gx-quay['center'][0],self.gz-quay['center'][1])
            mask=active&(d<=4)&~self.water['mask']
            fixed_height[mask]=quay['elevation'];fixed|=mask;quay_fixed|=mask
        from ferry_support import road_shore_constraints,restore_graded_shores
        ferry_fixed,ferry_height=road_shore_constraints(self,active)
        fixed_height[ferry_fixed]=ferry_height[ferry_fixed];fixed|=ferry_fixed
        target,conflicts=fit_road_to_footings(target,active,fixed_height,fixed)
        # Earthworks outside footings (owner, 2026-09-16): the corridor stays within ROAD_CUT_METRES below and
        # ROAD_FILL_METRES above the ground it found, at the corridor grade where the ground allows it.
        before=self.height.copy()
        outside_footings=~self.earthworks_free()&~self.water['mask']
        limited=active&~fixed&outside_footings
        target,earthworks=limit_corridor_earthworks(target,active,limited,before)
        distance=distance_transform_edt(~active)*CELL
        footing_weight=getattr(self,'road_footing_weight',self.assembly_weight)
        target=road_shoulder_field(target,active,self.height,distance,(footing_weight>=.999)|authored)
        weight=1-L.smoothstep(0,24,distance)
        weight[authored]=0
        # Shoulders inside standing ground stay as they are; the road's shoulder
        # influence fades out continuously as the standing weight rises, so no
        # step forms along the zone's contour.
        standing_hold=L.smoothstep(ROAD_STANDING_WEIGHT*.5,ROAD_STANDING_WEIGHT,standing)
        weight*=np.where(active,1.,1-standing_hold)
        wet=self.water['mask']&(self.water['depth']>.35)
        weight[wet]=0
        self.height=self.height*(1-weight)+target*weight
        # Built courtyards and thresholds retain their surveyed support plane.
        # Roads approach these constraints; they cannot excavate beneath them.
        # A partial footing feather keeps pulling a road's shoulders toward its
        # plane: the yards standing on that feather are walked, and letting the
        # road's shoulder win there tilted them (fourteenth attempt). The
        # cross-fall at the road edge in such feathers is per-site support work.
        support=np.where(active,(footing_weight>=.999).astype(float),footing_weight)
        protected=self.height*(1-support)+self.assembly_target*support
        self.height=np.where(wet|authored,self.height,protected)
        # What the road pass writes outside footings is bounded by the same limits (shoulders included).
        bounded=outside_footings&~wet&~quay_fixed&~ferry_fixed&~authored
        change=self.height-before
        earthworks['clampedVertices']=int(np.count_nonzero(bounded&((change<-ROAD_CUT_METRES-1e-9)|(change>ROAD_FILL_METRES+1e-9))))
        self.height=np.where(bounded,before+np.clip(change,-ROAD_CUT_METRES,ROAD_FILL_METRES),self.height)
        self.height[quay_fixed]=fixed_height[quay_fixed]
        if authored.any():self.height[authored]=authored_height[authored]
        self._respect_standing=bool(respect_standing)
        self.restore_drainage_corridor('roads')
        restore_graded_shores(self,active)
        if authored.any():self.height[authored]=authored_height[authored]
        target[ferry_fixed]=self.height[ferry_fixed]
        self.refresh_road_heights(target)
        self.road_grading_passes=getattr(self,'road_grading_passes',[])
        self.road_grading={'pass':len(self.road_grading_passes)+1,'respectsStandingGround':bool(respect_standing),
            'standingVertices':int(feather.sum()),'corridorVertices':int(active.sum()),'targetMaximumTriangleGrade':.45,
            'fixedFootingVertices':int(fixed.sum()),'conflictingFootingCorridorVertices':conflicts,'earthworks':earthworks,
            'exceptions':'Original drainage beds and surveyed assembly support remain authoritative; exported collision and bridge tests verify actual traversability.'}
        self.road_grading_passes.append(self.road_grading)

    def refresh_road_heights(self,target=None):
        """Every road station stands on the ground under it (the road pass wrote its earthworks there): over deep
        water, where a bridge carries it, it keeps the solved corridor or its own profile, never below the deck
        clearance. Called after the road pass and again once the support stages have finished the ground."""
        for road in self.roads:
            points=np.asarray(road['points'],float)
            if not len(points):continue
            ground=triangle_sample(self.height,points[:,0],points[:,2],self.x0,self.z0)
            water=L.water_fields(points[:,0],points[:,2],height=ground,plan=self.plan) if 'rivers' in (getattr(self,'plan',None) or {}) else None
            deep=water['mask']&(water['depth']>.35) if water is not None else np.zeros(len(points),bool)
            carried=points[:,1] if target is None else triangle_sample(target,points[:,0],points[:,2],self.x0,self.z0)
            if water is not None:carried=np.maximum(carried,water['surface']+.85)
            points[:,1]=np.where(deep,carried,ground)
            road['points']=points.tolist()

    def adjacent_edges(self):
        pairs={}
        # Every edge is an actual common terrain grid edge, so reciprocal
        # samples and server addresses share exact metre coordinates.
        for axis in (0,1):
            a=self.owner[:-1,:] if axis==0 else self.owner[:,:-1]
            b=self.owner[1:,:] if axis==0 else self.owner[:,1:]
            zs,xs=np.nonzero(a!=b)
            for z,x in zip(zs.tolist(),xs.tolist()):
                ia,ib=int(a[z,x]),int(b[z,x]);pair=tuple(sorted((ia,ib)))
                if axis==0:
                    start=[self.x0+x*CELL,self.z0+(z+1)*CELL];end=[start[0]+CELL,start[1]]
                else:
                    start=[self.x0+(x+1)*CELL,self.z0+z*CELL];end=[start[0],start[1]+CELL]
                pairs.setdefault(pair,[]).append([start,end])
        return pairs

    def plan_connections(self):
        desired=[('whitehorn_range','grey_moors'),('whitehorn_range','amberwood'),('whitehorn_range','amethyst_barrens'),
            ('grey_moors','amberwood'),('grey_moors','westhaven'),('amberwood','mirrorhold'),('amberwood','four_gates'),
            ('mirrorhold','amethyst_barrens'),('mirrorhold','sunmane_steppe'),('mirrorhold','four_gates'),
            ('mirrorhold','verdant_stair'),('amethyst_barrens','sunmane_steppe'),('sunmane_steppe','verdant_stair'),
            ('four_gates','westhaven'),('four_gates','manymouth_delta'),('westhaven','manymouth_delta'),
            ('manymouth_delta','verdant_stair'),('verdant_stair','ssarathi_ruins')]
        edges=self.adjacent_edges()
        for ra,rb in desired:
            ia,ib=self.ids.index(ra),self.ids.index(rb);pair=tuple(sorted((ia,ib)))
            if pair not in edges: continue
            segments=np.array(edges[pair]);mid=segments.mean(axis=1)
            heights=self.height_at(mid[:,0],mid[:,1])
            water=L.water_fields(mid[:,0],mid[:,1],height=heights,plan=self.plan)
            ca,cb=self.centers[ia],self.centers[ib]
            score=np.linalg.norm(mid-ca,axis=1)+np.linalg.norm(mid-cb,axis=1)+heights*.9+water['depth'].clip(0)*45
            # Pick a straight 14m run where possible for seven crossing lanes.
            straight=[]
            by_axis={}
            for i,s in enumerate(segments):
                vertical=abs(s[0,0]-s[1,0])<1e-8
                constant=s[0,0] if vertical else s[0,1]
                variable=mid[i,1] if vertical else mid[i,0]
                by_axis.setdefault((vertical,constant),set()).add(variable)
            for i,s in enumerate(segments):
                vertical=abs(s[0,0]-s[1,0])<1e-8;constant=s[0,0] if vertical else s[0,1];variable=mid[i,1] if vertical else mid[i,0]
                available=by_axis[(vertical,constant)]
                if all(variable+k*CELL in available for k in range(-3,4)): straight.append(i)
            identity='--'.join(sorted((ra,rb)))
            authored=self.plan.get('connection_sites',{}).get(identity)
            # The model prefers a station on a straight run, where the seven lanes of
            # its gate lie across the border as surveyed. An authored station is a
            # decision already taken and may stand on a step of the seam: every border
            # is now crossed along its length, and a gate lane a step puts on its own
            # side of the border is dropped when the seam's lanes are drawn
            # (crossings.departs_outward), so what it needs is the safe footprint and
            # the dry terminals asked of any station.
            pool=range(len(mid)) if authored is not None or not straight else straight
            candidates=np.array(pool)
            # The full receiving footprint must belong to the two actual
            # neighbours. A triple junction cannot supply seven safe lanes.
            safe=[]
            for candidate in candidates:
                x,z=mid[candidate]
                xx,zz=np.meshgrid(x+np.arange(-5,6),z+np.arange(-5,6))
                if np.isin(self.owner_at(xx,zz),(ia,ib)).all():safe.append(candidate)
            if not safe:raise ValueError(f'{ra}/{rb}: no crossing clear of the third territory or world edge')
            candidates=np.asarray(safe)
            def oriented(candidate):
                vertical=abs(segments[candidate,0,0]-segments[candidate,1,0])<1e-8
                normal=np.array([1.,0.]) if vertical else np.array([0.,1.])
                return -normal if np.dot(normal,cb-ca)<0 else normal
            # Seam terminals stand on dry land outside the seam road's river setback: every station the road lays
            # straight across the seam (9 and 4 m either side, and the anchor), not only the anchor.
            rivers=getattr(self,'river_water_distance',None) is not None
            setback=self.river_setback(SEAM_ROAD_WIDTH_METRES) if rivers else None
            def terminals_dry(candidate):
                if setback is None:return True
                normal=oriented(candidate)
                import river_crossings as RC
                return all(float(RC.water_distance_at(self,*(mid[candidate]+normal*k)))>setback for k in (-9.,-4.,0.,4.,9.))
            if authored is None:
                dry=[c for c in candidates if terminals_dry(c)]
                if dry:candidates=np.asarray(dry)
                else:self.__dict__.setdefault('wet_seam_terminals',[]).append(identity)
                # A crossing whose road terminals stand inside retained solids
                # (a ruined watch-post on the pass) costs sixty metres per
                # terminal, so an open crossing nearby wins; so does one whose
                # terminal shares a bank with its hub (no river between them).
                penalties=np.zeros(len(candidates))
                for k,candidate in enumerate(candidates):
                    normal=oriented(candidate)
                    penalties[k]=self.seam_terminal_penalty(mid[candidate],normal)+(self.seam_river_penalty((ra,rb),mid[candidate],normal) if rivers else 0.)
                order=np.argsort(score[candidates]+penalties,kind='stable')
                index=int(candidates[order[0]])
                # Alternatives are spread along the seam: the stations beside a failed one usually fail for the same
                # reason (a channel between them and the hub), so each keeps a spacing from the anchor and the others.
                alternatives=[]
                for k in order[1:]:
                    station=int(candidates[k])
                    if all(np.linalg.norm(mid[station]-mid[other])>=SEAM_ANCHOR_ALTERNATIVE_SPACING_METRES for other in [index]+alternatives):
                        alternatives.append(station)
                        if len(alternatives)==SEAM_ANCHOR_ALTERNATIVES:break
            else:
                delta=np.linalg.norm(mid[candidates]-np.asarray(authored,float),axis=1)
                if delta.min()>1e-6:
                    raise ValueError(identity+': authored crossing is not a safe shared boundary station')
                index=int(candidates[np.argmin(delta)]);alternatives=[]
                if not terminals_dry(index):
                    raise ValueError(identity+': authored crossing puts a seam road terminal in river water or its setback')
            anchor=mid[index];normal=oriented(index)
            self.connections.append({'id':identity,'type':'walk','regions':[ra,rb],
                                     'anchor':anchor.tolist(),'normal':normal.tolist(),'edgeSegments':segments.tolist(),
                                     'alternatives':[{'anchor':mid[k].tolist(),'normal':oriented(k).tolist()} for k in alternatives]})
        for ra,rb in (('westhaven','crownwater'),('manymouth_delta','crownwater'),('ssarathi_ruins','crownwater')):
            self.connections.append({'id':'--'.join(sorted((ra,rb))),'type':'ferry','regions':[ra,rb]})

    def natural_channel_apron(self):
        """Vertices within the natural bank apron: there the drainage restoration returns the original ground under any road."""
        cached=getattr(self,'_natural_channel_apron',None)
        if cached is None:
            if getattr(self,'original_height',None) is None or not getattr(self,'plan',None):return None
            try:natural=L.water_fields(self.gx,self.gz,height=self.original_height,plan=self.plan)
            except KeyError:return None
            channel=natural.get('river_mask')
            cached=np.zeros_like(self.height,dtype=bool) if channel is None or not np.any(channel) else distance_transform_edt(~channel)*CELL<=ROUTE_RELIEF_APRON_METRES
            self._natural_channel_apron=cached
        return cached

    def cell_of(self,point):
        return (int(np.clip(round((point[1]-self.z0)/CELL),0,self.height.shape[0]-1)),
                int(np.clip(round((point[0]-self.x0)/CELL),0,self.height.shape[1]-1)))

    def route(self,start,goal,region=None,step=6,own=None,width=None,public=False,name=None):
        """A* road alignment that favours manageable grades, gentle traverses and narrow crossings.

        Retained solids are impassable for every station and for every edge
        between stations, except the solid that holds one of the road's own
        ends (a door, a discovery, a hub inside a hall); a caller whose start
        is no structure of its own (a trail from a road station) passes the
        solids of its far end as ``own``. When no alignment
        exists at the normal station spacing the search threads closer
        stations between the solids; when none exists at all it runs once more
        with solids as a heavy penalty only, and the road is recorded as a
        solid fallback.

        River water and its setback (river_crossings.setback_metres for the
        road's half ``width``) are impassable in every attempt, the solid
        fallback included; a river is crossed only on a bridge edge between a
        crossing's two routed landings. When no attempt finds a way the search
        runs again with the last-resort crossings of the territory. The routed
        road claims the crossings it uses (``public`` roads make them cheaper
        for the roads after them), and a leg whose ground cannot carry the
        earthworks grade within the cut and fill limits is rerouted around the
        offending stations up to ROUTE_EARTHWORKS_PASSES times.
        """
        routing=self.__dict__.setdefault('routing',[])
        start=np.asarray(start,float);goal=np.asarray(goal,float)
        if own is None:own=self.solids_at_ends(start,goal)
        blocked=set();found=None
        for last_resort in (False,True):
            if last_resort and not self.has_last_resort_crossings(region):break
            for _ in range(4):
                found=self._route_attempts(start,goal,region,step,own,width,last_resort,blocked)
                if found is None:break
                conflicts=self.crossing_conflicts(found[0][1].get('crossings',[]))
                if not conflicts:break
                # Every crossing within the spacing of the ones this alignment keeps is closed for the next search.
                import river_crossings as RC
                blocked|=set(conflicts)|RC.within_spacing(self,[key for key in found[0][1].get('crossings',[]) if key not in conflicts]);found=None
            if found is not None:break
        if found is None:
            raise ValueError(f'No road alignment from {start} to {goal} in {region}')
        (points,record),(origin,target,spacing,hard)=found
        record['solidFallback']=not hard;record['lastResortSearch']=bool(last_resort)
        excess=self.alignment_excess(points)
        passes=0;penalty=None;offending=excess
        while excess['metres']>0 and passes<ROUTE_EARTHWORKS_PASSES:
            penalty=self.earthworks_penalty(offending['points'],penalty)
            passes+=1
            retry=self._route(origin,target,region,spacing,hard,own,width=width,last_resort=last_resort,blocked=blocked,extra=penalty)
            if retry is None or self.crossing_conflicts(retry[1].get('crossings',[])):break
            offending=self.alignment_excess(retry[0])
            if offending['metres']<excess['metres']:
                points,record=retry;record['solidFallback']=not hard;record['lastResortSearch']=bool(last_resort);excess=offending
        record['earthworks']={'passes':passes,'excessMetres':excess['metres'],
                              'excessAt':[[round(float(v),1) for v in p] for p in excess['points'][::5]]}
        if origin is not start:
            points=np.vstack([self.end_leg(start,origin,region,own,width),points[1:]]);record['exitMetres']=round(float(np.linalg.norm(origin-start)),2)
        if target is not goal:
            points=np.vstack([points[:-1],self.end_leg(target,goal,region,own,width)]);record['entryMetres']=round(float(np.linalg.norm(target-goal)),2)
        if record.get('crossings'):
            import river_crossings as RC
            record['sites']=RC.claim(self,record['crossings'],name or f'road {len(routing)}',public)
        record['width']=None if width is None else float(width);record['public']=bool(public)
        if name is not None:record['name']=name
        routing.append(record)
        return points

    def _route_attempts(self,start,goal,region,step,own,width,last_resort,blocked):
        """The first alignment over the end candidates and station spacings: ((points, record), attempt) or None."""
        origins=self.open_ground_candidates(start,region,width=width);targets=self.open_ground_candidates(goal,region,width=width)
        pairs=sorted(((i+j,i,j) for i in range(len(origins)) for j in range(len(targets))))
        attempts=[(origins[i],targets[j],spacing,True) for _,i,j in pairs for spacing in (step,ROUTE_RETRY_STEP_METRES)]
        attempts.append((origins[0],targets[0],step,False))
        for origin,target,spacing,hard in attempts:
            result=self._route(origin,target,region,spacing,hard,own,width=width,last_resort=last_resort,blocked=blocked)
            if result is not None:return result,(origin,target,spacing,hard)
        return None

    def has_last_resort_crossings(self,region):
        if not getattr(self,'crossing_candidates',None):return False
        import river_crossings as RC
        return len(RC.available_crossings(self,region,True))>len(RC.available_crossings(self,region,False))

    def crossing_conflicts(self,keys):
        """Crossings of one alignment that would stand within the minimum spacing of another it also uses."""
        if len(keys)<2 or not getattr(self,'crossing_candidates',None):return []
        import river_crossings as RC
        return RC.conflicting(self,keys)

    def alignment_excess(self,points,step=2.):
        """{'metres', 'points'}: where an alignment's ground cannot carry the earthworks grade within the limits."""
        points=np.asarray(points,float)
        if len(points)<2 or not hasattr(self,'foundation_weight'):return {'metres':0.,'points':np.zeros((0,2))}
        seg=np.linalg.norm(np.diff(points,axis=0),axis=1);cum=np.r_[0,np.cumsum(seg)]
        if cum[-1]<step:return {'metres':0.,'points':np.zeros((0,2))}
        s=np.r_[np.arange(0,cum[-1],step),cum[-1]]
        xz=np.c_[np.interp(s,cum,points[:,0]),np.interp(s,cum,points[:,1])]
        ground=self.height_at(xz[:,0],xz[:,1])
        standing=triangle_sample(self.earthworks_free().astype(float),xz[:,0],xz[:,1],self.x0,self.z0)
        wet=triangle_sample(self.water['mask'].astype(float),xz[:,0],xz[:,1],self.x0,self.z0)>.5 if getattr(self,'water',None) else np.zeros(len(s),bool)
        bad=earthworks_excess(ground,s,free=(standing>=.5)|wet)
        return {'metres':float(bad.sum()*step),'points':xz[bad]}

    def earthworks_penalty(self,points,previous=None):
        """A per-vertex alignment penalty around offending stations, added to any earlier pass's."""
        penalty=np.zeros(self.height.shape) if previous is None else previous.copy()
        radius=ROUTE_EARTHWORKS_RADIUS_METRES;cells=int(math.ceil(radius/CELL))
        for x,z in np.asarray(points,float).reshape(-1,2):
            iz,ix=self.cell_of((x,z))
            sl=np.s_[max(0,iz-cells):iz+cells+1,max(0,ix-cells):ix+cells+1]
            near=np.hypot(self.gx[sl]-x,self.gz[sl]-z)<=radius
            penalty[sl]=np.where(near,np.maximum(penalty[sl],ROUTE_EARTHWORKS_PENALTY),penalty[sl])
        return penalty

    def end_leg(self,a,b,region,own,width=None):
        """The short run between a road end and its open ground: a close-station search that crosses
        the end's own solids freely and any other only as a heavy penalty, so it threads a gap
        between tents or finds the gate in a wall where a straight line would cut through them. It
        may cross the river setback it leaves (never river water) and uses no bridge."""
        result=self._route(a,b,region,ROUTE_RETRY_STEP_METRES,False,own,width=width,setback=False,crossings=False)
        if result is None:return np.vstack([np.asarray(a,float)[None,:],np.asarray(b,float)[None,:]])
        return result[0]

    def seam_river_penalty(self,regions,anchor,normal,reach=9.):
        """Metres of penalty for a seam crossing whose road terminal stands across a river from its own hub."""
        if getattr(self,'river_water',None) is None:return 0.
        import river_crossings as RC
        penalty=0.
        for side,region in enumerate(regions):
            terminal=np.asarray(anchor,float)-np.asarray(normal,float)*reach*(1 if side==0 else -1)
            if int(RC.bank_of(self,region,terminal)[0])!=int(RC.bank_of(self,region,self.hub(region))[0]):penalty+=SEAM_RIVER_SIDE_PENALTY
        return penalty

    def seam_terminal_penalty(self,anchor,normal,reach=9.):
        """Metres of penalty for a seam crossing whose road terminals stand in retained solids."""
        solids=getattr(self,'solids',None)
        if solids is None or not solids.any():return 0.
        anchor=np.asarray(anchor,float);normal=np.asarray(normal,float)
        return SEAM_TERMINAL_SOLID_PENALTY*sum(1 for point in (anchor-normal*reach,anchor,anchor+normal*reach) if solids[self.cell_of(point)])

    def solids_at_ends(self,*points,radius=ROUTE_END_SOLID_RADIUS_METRES):
        """Identities of the retained solids within ``radius`` of a road's ends: its own hall, market platform or gate towers."""
        ids=getattr(self,'solid_ids',None)
        if ids is None:return set()
        own=set()
        cells=int(math.ceil(radius/CELL))
        for point in points:
            z,x=self.cell_of(point)
            window=ids[max(0,z-cells):z+cells+1,max(0,x-cells):x+cells+1]
            wz,wx=np.mgrid[max(0,z-cells):z+cells+1,max(0,x-cells):x+cells+1]
            near=np.hypot((wz-z)*CELL,(wx-x)*CELL)<=radius
            own.update(int(v) for v in np.unique(window[near]) if v)
        return own

    def river_setback(self,width=None):
        """Metres a road of this half width keeps from river water, or None before the water is prepared."""
        if getattr(self,'river_water_distance',None) is None:return None
        import river_crossings as RC
        return RC.setback_metres(RC.policy_of(self),width)

    def water_blocked(self,width=None,setback=True):
        """Composed vertices a road may not stand on: river water, and its setback unless ``setback`` is False."""
        distance=getattr(self,'river_water_distance',None)
        if distance is None:return None
        return distance<=self.river_setback(width) if setback else self.river_water

    def open_ground_candidates(self,point,region=None,limit=ROUTE_END_CANDIDATES,toward=None,width=None):
        """The point itself, or open ground near it for a road end that stands inside a retained solid
        or within the river setback.

        A hub inside a hall or on a market platform starts its roads at the
        structure's open side instead of threading its own walls; a seam
        terminal inside a ruined watch-post is entered by a leg from open
        ground. Candidates within ROUTE_EXIT_SEARCH_METRES are ordered by the
        retained solids their straight leg would cross (none first), then by
        distance (or by distance to ``toward`` when given: ranking by the
        road's other end sent the Whitehorn watch-cave road in through the
        watch house instead of the cave mouth, so the default stays nearest
        first); the caller tries them in turn because the nearest open cell
        can lie in a pocket the structures seal. An end beside a river (a
        quay door, a hub on a bank) is left the same way, by open ground
        outside the setback whose straight leg crosses no river water.
        """
        solids=getattr(self,'solids',None)
        water=self.water_blocked(width)
        cell=self.cell_of(point)
        in_solid=solids is not None and bool(solids[cell])
        in_water=water is not None and bool(water[cell])
        if not in_solid and not in_water:return [point]
        ids=getattr(self,'solid_ids',None)
        own=self.solids_at_ends(point)
        region_id=self.ids.index(region) if region else None
        river=getattr(self,'river_water',None)
        point=np.asarray(point,float);found=[]
        for radius in np.arange(CELL,ROUTE_EXIT_SEARCH_METRES+1e-9,CELL):
            for angle in np.linspace(0,2*math.pi,16,endpoint=False):
                candidate=point+radius*np.array([math.cos(angle),math.sin(angle)])
                if not (self.x0<=candidate[0]<=self.x1 and self.z0<=candidate[1]<=self.z1):continue
                c=self.cell_of(candidate)
                if solids is not None and solids[c]:continue
                if water is not None and water[c]:continue
                if region_id is not None and int(self.owner_at(candidate[0],candidate[1]))!=region_id:continue
                count=max(1,int(math.ceil(radius)))
                if river is not None and any(river[self.cell_of(point+(candidate-point)*k/count)] for k in range(1,count)):continue
                crossed={int(ids[self.cell_of(point+(candidate-point)*k/count)]) for k in range(1,count)} if ids is not None else set()
                rank=float(radius) if toward is None else float(np.linalg.norm(candidate-np.asarray(toward,float)))
                found.append((len(crossed-own-{0}),rank,len(found),candidate))
        if not found:return [point]
        found.sort(key=lambda item:item[:3])
        # The nearest open cells can all lie in one pocket the structures seal:
        # keep the two nearest of each crossing class so an exit that crosses a
        # wall is still tried after the pocket.
        chosen=[];per_class={}
        for crossings,_,_,candidate in found:
            if per_class.get(crossings,0)>=ROUTE_END_CANDIDATES_PER_CLASS:continue
            per_class[crossings]=per_class.get(crossings,0)+1;chosen.append(candidate)
            if len(chosen)>=limit:break
        return chosen

    def open_ground_near(self,point,region=None):
        return self.open_ground_candidates(point,region)[0]

    def _water_passage(self,stride,width,setback):
        """(station_clear, edge_clear by direction) for river water and its setback at this station stride, cached."""
        blocked=self.water_blocked(width,setback)
        if blocked is None:return None,None,None
        key=(stride,round(float(self.river_setback(width)),3) if setback else None,id(self.river_water_distance))
        cache=self.__dict__.setdefault('_water_passage_cache',{})
        if key in cache:return cache[key]
        rows,columns=self.height.shape;spacing=stride*CELL
        shape=self.height[::stride,::stride].shape
        zz,xx=np.mgrid[0:shape[0],0:shape[1]]
        passable=~blocked
        station=passable[np.minimum(zz*stride,rows-1),np.minimum(xx*stride,columns-1)]
        edges={}
        for dz,dx in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
            clear=np.ones(shape,bool);count=int(math.ceil(math.hypot(dz,dx)*spacing/ROUTE_EDGE_SAMPLE_METRES))
            for k in range(1,count):
                f=k/count
                sz=np.clip(np.rint((zz+dz*f)*stride).astype(int),0,rows-1);sx=np.clip(np.rint((xx+dx*f)*stride).astype(int),0,columns-1)
                clear&=passable[sz,sx]
            edges[(dz,dx)]=clear
        shelf=None
        if setback:
            import river_crossings as RC
            policy=RC.policy_of(self)
            band=(self.river_water_distance>self.river_setback(width))&(self.river_water_distance<=float(policy['bank_shelf_metres']))
            shelf=band[np.minimum(zz*stride,rows-1),np.minimum(xx*stride,columns-1)]
        cache[key]=(station,edges,shelf)
        return cache[key]

    def _bridge_edges(self,stride,spacing,region,width,last_resort,blocked,passable_station,region_id,node):
        """Bridge edges of the leg's available crossings: {station: [(station, cost, key, landing, landing)]}."""
        if not getattr(self,'crossing_candidates',None) and not getattr(self,'crossing_sites',None):return {}
        import river_crossings as RC
        shape=passable_station.shape;river=self.river_water;edges={}
        def landing_node(point):
            base=node(point);best=None
            for dz in range(-2,3):
                for dx in range(-2,3):
                    z,x=base[0]+dz,base[1]+dx
                    if not(0<=z<shape[0] and 0<=x<shape[1]) or not passable_station[z,x]:continue
                    position=np.array([self.x0+x*spacing,self.z0+z*spacing])
                    if region_id is not None and int(self.owner_at(position[0],position[1]))!=region_id:continue
                    gap=float(np.linalg.norm(position-point))
                    if gap>1.6*spacing:continue
                    count=max(1,int(math.ceil(gap)))
                    if any(river[self.cell_of(point+(position-point)*k/count)] for k in range(0,count+1)):continue
                    if best is None or gap<best[0]:best=(gap,(z,x))
            return best
        for crossing in RC.available_crossings(self,region,last_resort):
            if crossing['key'] in blocked:continue
            a=np.asarray(crossing['routeLandings'][0],float);b=np.asarray(crossing['routeLandings'][1],float)
            na=landing_node(a);nb=landing_node(b)
            if na is None or nb is None or na[1]==nb[1]:continue
            cost=na[0]+float(np.linalg.norm(b-a))+nb[0]+RC.crossing_cost(self,crossing)
            edges.setdefault(na[1],[]).append((nb[1],cost,crossing['key'],a,b))
            edges.setdefault(nb[1],[]).append((na[1],cost,crossing['key'],b,a))
        return edges

    def _route(self,start,goal,region,step,hard,own=None,width=None,setback=True,crossings=True,last_resort=False,blocked=(),extra=None):
        stride=max(1,int(step/CELL));h=self.height[::stride,::stride];spacing=stride*CELL
        rows,columns=self.height.shape
        def node(point): return (int(np.clip(round((point[1]-self.z0)/spacing),0,h.shape[0]-1)),int(np.clip(round((point[0]-self.x0)/spacing),0,h.shape[1]-1)))
        origin,target=node(start),node(goal)
        record={'start':[float(start[0]),float(start[1])],'goal':[float(goal[0]),float(goal[1])],'region':region,'stations':2,'maximumSlope':0.,'stationMetres':float(spacing)}
        if origin==target:return np.vstack([np.asarray(start,float),np.asarray(goal,float)]),record
        region_id=self.ids.index(region) if region else None
        civic=(self.mirror_street_distance[::stride,::stride]<=1.25
               if region=='mirrorhold' and hasattr(self,'mirror_street_distance') else None)
        # Ground steepness across the whole corridor width at each station: the
        # steepest 2 m gradient within the station's block.
        gz,gx=np.gradient(self.height,CELL)
        slope=maximum_filter(np.hypot(gx,gz),size=stride)[::stride,::stride]
        solids=getattr(self,'solids',None)
        if solids is None:solids=np.zeros_like(self.obstacles)
        station_clear=edge_clear=None
        zz,xx=np.mgrid[0:h.shape[0],0:h.shape[1]]
        if solids.any():
            ids=getattr(self,'solid_ids',None)
            if ids is None:ids=solids.astype(np.int32)
            if own is None:own=self.solids_at_ends(start,goal)
            passable=~solids if not own else ~(solids&~np.isin(ids,list(own)))
            # Station solids and, per direction, solids on the edge to that neighbour.
            station_clear=passable[np.minimum(zz*stride,rows-1),np.minimum(xx*stride,columns-1)]
            edge_clear={}
            for dz,dx in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
                clear=np.ones(h.shape,bool);count=int(math.ceil(math.hypot(dz,dx)*spacing/ROUTE_EDGE_SAMPLE_METRES))
                for k in range(1,count):
                    f=k/count
                    sz=np.clip(np.rint((zz+dz*f)*stride).astype(int),0,rows-1);sx=np.clip(np.rint((xx+dx*f)*stride).astype(int),0,columns-1)
                    clear&=passable[sz,sx]
                edge_clear[(dz,dx)]=clear
        # River water and its setback: impassable for stations and edges in every attempt (the solid fallback
        # included); the bank shelf beyond the setback costs extra. A river is crossed only on a bridge edge.
        water_station,water_edge,shelf=self._water_passage(stride,width,setback)
        bridges={}
        if crossings and water_station is not None:
            usable=water_station.copy()
            if station_clear is not None and hard:usable&=station_clear
            bridges=self._bridge_edges(stride,spacing,region,width,last_resort,set(blocked),usable,region_id,node)
        extra_station=None if extra is None else extra[np.minimum(zz*stride,rows-1),np.minimum(xx*stride,columns-1)]
        import river_crossings as RC
        shelf_penalty=float(RC.policy_of(self)['bank_shelf_penalty']) if shelf is not None else 0.
        # Relief between stations, per direction: how far the ground between a
        # station and its neighbour drops below the lower of the two or rises
        # above the higher (a slot gorge, a stream cut, a knife ridge). Inside
        # the natural bank apron the original ground is the relief: a
        # foundation pad may have filled a canyon for now, but the drainage
        # restoration returns the channel and its banks under any road.
        apron=self.natural_channel_apron()
        relief_height=self.height if apron is None else np.where(apron,self.original_height,self.height)
        hr=relief_height[::stride,::stride]
        relief={}
        for dz,dx in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
            count=int(math.ceil(math.hypot(dz,dx)*spacing/ROUTE_EDGE_SAMPLE_METRES))
            nz_=np.clip(zz+dz,0,h.shape[0]-1);nx_=np.clip(xx+dx,0,h.shape[1]-1)
            low=np.minimum(hr,hr[nz_,nx_]);high=np.maximum(hr,hr[nz_,nx_])
            deepest=np.zeros(h.shape);tallest=np.zeros(h.shape)
            for k in range(1,count):
                f=k/count
                sz=np.clip(np.rint((zz+dz*f)*stride).astype(int),0,rows-1);sx=np.clip(np.rint((xx+dx*f)*stride).astype(int),0,columns-1)
                sample=relief_height[sz,sx]
                deepest=np.maximum(deepest,low-sample);tallest=np.maximum(tallest,sample-high)
            relief[(dz,dx)]=np.maximum(0.,np.maximum(deepest,tallest)-ROUTE_RELIEF_ALLOWANCE_METRES)
        cross_linear,cross_square,relief_penalty,step_penalty=terrain_terms(region)
        costs={origin:0.};parents={};via={};queue=[(0.,origin)];done=set()
        while queue:
            _,current=heapq.heappop(queue)
            if current in done:continue
            if current==target:break
            done.add(current);z,x=current
            for dz,dx in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
                nz,nx=z+dz,x+dx
                if not(0<=nz<h.shape[0] and 0<=nx<h.shape[1]):continue
                neighbor=(nz,nx)
                if neighbor in done:continue
                gx_,gz_=self.x0+nx*spacing,self.z0+nz*spacing
                # The goal is authoritative: its own station may round onto a neighbour's ground.
                if region_id is not None and neighbor!=target and int(self.owner_at(gx_,gz_))!=region_id:continue
                # The goal's own station may round into the setback; the edge to it may still cross no water.
                if water_station is not None and not ((water_station[nz,nx] or neighbor==target) and water_edge[(dz,dx)][z,x]):continue
                solid=station_clear is not None and not (station_clear[nz,nx] and edge_clear[(dz,dx)][z,x])
                if solid and hard:continue
                length=math.hypot(dx,dz)*spacing;grade=abs(h[nz,nx]-h[z,x])/length
                blocked_=self.obstacles[min(nz*stride,rows-1),min(nx*stride,columns-1)]
                excess=max(0.,float(slope[nz,nx])-ROUTE_CROSS_SLOPE_START)
                steep=max(0.,grade-ROUTE_STEP_GRADE)
                penalty=(1+grade*grade*32+max(0,grade-.4)*70+steep*steep*step_penalty
                         +excess*cross_linear+excess*excess*cross_square
                         +float(relief[(dz,dx)][z,x])*relief_penalty
                         +(65 if h[nz,nx]<.3 else 0)+(150 if blocked_ and neighbor not in (origin,target) else 0)
                         +(SOLID_SOFT_PENALTY if solid else 0)
                         +(shelf_penalty if shelf is not None and shelf[nz,nx] else 0)
                         +(float(extra_station[nz,nx]) if extra_station is not None else 0))
                # In the steep city, the surveyed civic network provides the
                # real switchbacks between terraces. Prefer its circulation
                # over cutting a competing shortcut through the city slope.
                if civic is not None and civic[nz,nx] and not blocked_:penalty*=.05
                cost=costs[current]+length*penalty
                if cost<costs.get(neighbor,np.inf):
                    costs[neighbor]=cost;parents[neighbor]=current;via.pop(neighbor,None)
                    heuristic=math.hypot(nx-target[1],nz-target[0])*spacing
                    if civic is not None:heuristic*=.05
                    heapq.heappush(queue,(cost+heuristic,neighbor))
            for neighbor,edge_cost,key,near,far in bridges.get(current,()):
                if neighbor in done:continue
                cost=costs[current]+edge_cost
                if cost<costs.get(neighbor,np.inf):
                    costs[neighbor]=cost;parents[neighbor]=current;via[neighbor]=(key,near,far)
                    heuristic=math.hypot(neighbor[1]-target[1],neighbor[0]-target[0])*spacing
                    if civic is not None:heuristic*=.05
                    heapq.heappush(queue,(cost+heuristic,neighbor))
        if target not in costs:return None
        path=[target]
        while path[-1]!=origin:path.append(parents[path[-1]])
        path=list(reversed(path))
        points=[];fixed=[];used=[]
        for index,(z,x) in enumerate(path):
            if index and path[index] in via:
                key,near,far=via[path[index]]
                fixed.extend([len(points)-1,len(points),len(points)+1,len(points)+2])
                points.extend([near,far]);used.append(key)
            points.append([self.x0+x*spacing,self.z0+z*spacing])
        points=np.array(points,float)
        points[0]=start;points[-1]=goal
        steepest=float(max(slope[z,x] for z,x in path[1:-1]) if len(path)>2 else 0.)
        # A broad low-pass bend removes eight-direction grid kinks; endpoints
        # remain the exact surveyed road mouths. Bridge landings and the stations
        # beside them keep their places, so a span stays square to its river.
        if len(points)>5:
            smoothed=gaussian_filter(points,sigma=(1.2,0),mode='nearest')
            smoothed[:2]=points[:2];smoothed[-2:]=points[-2:]
            # A curve must not cut the inside of a bend through a building, or drift into a river's setback.
            iz=np.clip(((smoothed[:,1]-self.z0)/CELL).astype(int),0,len(self.z)-1)
            ix=np.clip(((smoothed[:,0]-self.x0)/CELL).astype(int),0,len(self.x)-1)
            valid=~(self.obstacles[iz,ix]|solids[iz,ix])
            water=self.water_blocked(width,setback)
            if water is not None:
                wz=np.clip(np.rint((smoothed[:,1]-self.z0)/CELL).astype(int),0,len(self.z)-1)
                wx=np.clip(np.rint((smoothed[:,0]-self.x0)/CELL).astype(int),0,len(self.x)-1)
                valid&=~water[wz,wx]
            valid[[i for i in fixed if 0<=i<len(valid)]]=False
            points[valid]=smoothed[valid]
        if civic is not None:
            from mirror_streets import trim_civic_approach
            points=trim_civic_approach(self,points)
        record.update(stations=int(len(points)),maximumSlope=round(steepest,3))
        if used:record['crossings']=used
        return points,record

    def solid_crossings(self,solids):
        """Road stations inside retained solids, per road and structure, in metres of alignment."""
        crossings=[]
        boxes=[(region,node,np.asarray(low,float)[[0,2]],np.asarray(high,float)[[0,2]]) for region,node,low,high in solids]
        for road in self.roads:
            points=np.asarray(road['points'],float)[:,[0,2]]
            if len(points)<2:continue
            dense=[]
            for a,b in zip(points,points[1:]):
                count=max(1,int(math.ceil(np.linalg.norm(b-a))))
                dense.extend(a+(b-a)*k/count for k in range(count))
            dense=np.vstack([dense,points[-1]])
            low=dense.min(axis=0);high=dense.max(axis=0)
            for region,node,lo,hi in boxes:
                if np.any(hi<low) or np.any(lo>high):continue
                inside=(dense[:,0]>=lo[0])&(dense[:,0]<=hi[0])&(dense[:,1]>=lo[1])&(dense[:,1]<=hi[1])
                if inside.any():
                    crossings.append({'road':road['id'],'region':region,'node':node,'metres':int(inside.sum())})
        crossings.sort(key=lambda c:(-c['metres'],c['road'],c['node']))
        return crossings

    def routing_report(self):
        routes=getattr(self,'routing',[])
        return {'routes':len(routes),'solidFallbacks':[r for r in routes if r.get('solidFallback')],
                'steepestStationSlope':max((r['maximumSlope'] for r in routes),default=0.),
                'solidMarginMetres':SOLID_MARGIN_METRES,'solidMaximumAreaSquareMetres':SOLID_MAXIMUM_AREA_SQUARE_METRES,
                'retryStationMetres':ROUTE_RETRY_STEP_METRES,'closeStationRoutes':sum(1 for r in routes if r.get('stationMetres',6.)<6. and not r.get('solidFallback')),
                'hubExits':sum(1 for r in routes if r.get('exitMetres')),'endEntries':sum(1 for r in routes if r.get('entryMetres')),
                'exitSearchMetres':ROUTE_EXIT_SEARCH_METRES,'endSolidRadiusMetres':ROUTE_END_SOLID_RADIUS_METRES,'seamTerminalSolidPenalty':SEAM_TERMINAL_SOLID_PENALTY,
                'crossSlope':{'start':ROUTE_CROSS_SLOPE_START,'linear':ROUTE_CROSS_SLOPE_LINEAR,'square':ROUTE_CROSS_SLOPE_SQUARE},
                'relief':{'allowanceMetres':ROUTE_RELIEF_ALLOWANCE_METRES,'penaltyPerMetre':ROUTE_RELIEF_PENALTY,'naturalApronMetres':ROUTE_RELIEF_APRON_METRES},
                'stepGrade':{'grade':ROUTE_STEP_GRADE,'penalty':ROUTE_STEP_PENALTY},
                'terrainTermsByTerritory':{region:list(weights) for region,weights in ROUTE_TERRAIN_TERMS.items()},
                'riverCrossings':{'sitesClaimed':len(getattr(self,'crossing_sites',[])),'candidates':len(getattr(self,'crossing_candidates',[])),
                    'routesCrossingRivers':sum(1 for r in routes if r.get('sites')),'lastResortSearches':sum(1 for r in routes if r.get('lastResortSearch')),
                    'wetSeamTerminals':list(getattr(self,'wet_seam_terminals',[])),'seamRiverSidePenalty':SEAM_RIVER_SIDE_PENALTY},
                'earthworks':{'cutMetres':ROAD_CUT_METRES,'fillMetres':ROAD_FILL_METRES,'grade':ROAD_EARTHWORKS_GRADE,'passes':ROUTE_EARTHWORKS_PASSES,
                    'reroutedLegs':sum(1 for r in routes if r.get('earthworks',{}).get('passes')),
                    'legsStillExceeding':[{'region':r['region'],'name':r.get('name'),'start':r['start'],'goal':r['goal'],'excessMetres':r['earthworks']['excessMetres'],'at':r['earthworks']['excessAt']}
                                          for r in routes if r.get('earthworks',{}).get('excessMetres',0)>0]},
                'unrouted':list(getattr(self,'unrouted',[])),
                'policy':'River water and its setback (max(6 m, half width + 4 m)) are impassable for every alignment and edge; a plan river is crossed only on a bridge edge between the routed landings of a crossing site (river_crossings.py), which the road then claims; retained solids up to 1600 square metres, widened by 2 m, are impassable for alignments and their edges except the solids within 6 m of a road end, first at 6 m stations then at 4 m; a road end inside a solid starts or ends with a close-station leg from open ground; a sealed end falls back to solids as a heavy penalty; larger boxes keep the soft clearance penalty; the seam-terminal term stands at its listed weight; the cross-slope, relief and step-grade terms stand at their listed module weights (zero: off) except in the territories listed under terrainTermsByTerritory.'}

    def road_profile(self,points):
        """Return the exact dense XZ stations and bounded earthwork profile used by ``add_road``."""
        points=np.asarray(points,float)
        dense=[]
        for a,b in zip(points,points[1:]):
            count=max(1,int(np.ceil(np.linalg.norm(b-a)/2)))
            dense.extend(a+(b-a)*t for t in np.arange(count)/count)
        points=np.vstack([dense,points[-1]])
        heights=self.height_at(points[:,0],points[:,1])
        water=L.water_fields(points[:,0],points[:,1],height=heights,plan=self.plan)
        # Deeper than the wade limit the road is a deck above the water; shallower,
        # its bed stays within the wade depth of the surface, so the corridor cut
        # never sinks a tile the fold would refuse.
        floor=np.where(water['mask']&(water['depth']>.35),water['surface']+.85,
                       np.where(water['mask'],water['surface']-ROAD_WADE_DEPTH_METRES,-np.inf))
        distances=np.r_[0,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
        # A road follows its ground within the earthworks limits; a footing holds its own stations.
        free=triangle_sample(self.earthworks_free().astype(float),points[:,0],points[:,1],self.x0,self.z0)>=.5 if hasattr(self,'assembly_weight') else None
        profile=graded_profile(heights,distances,floor,maximum_grade=ROAD_EARTHWORKS_GRADE,cut=ROAD_CUT_METRES,fill=ROAD_FILL_METRES,free=free)
        return points,profile

    def add_road(self,points,width=3.5,name='road'):
        points,profile=self.road_profile(points)
        self.roads.append({'id':name,'points':np.c_[points[:,0],profile,points[:,1]].tolist(),'width':width})
        for i,(a,b) in enumerate(zip(points,points[1:])):
            shoulder=max(16,width*4)
            low=np.minimum(a,b)-width-shoulder;high=np.maximum(a,b)+width+shoulder
            ix0=max(0,int((low[0]-self.x0)/CELL));ix1=min(len(self.x),int((high[0]-self.x0)/CELL)+2)
            iz0=max(0,int((low[1]-self.z0)/CELL));iz1=min(len(self.z),int((high[1]-self.z0)/CELL)+2)
            sl=np.s_[iz0:iz1,ix0:ix1];dx,dz=b-a
            t=np.clip(((self.gx[sl]-a[0])*dx+(self.gz[sl]-a[1])*dz)/max(dx*dx+dz*dz,1e-9),0,1)
            d=np.hypot(self.gx[sl]-a[0]-t*dx,self.gz[sl]-a[1]-t*dz)
            self.road_distance[sl]=np.minimum(self.road_distance[sl],d/width)
            target=profile[i]*(1-t)+profile[i+1]*t
            closer=d<self.road_nearest[sl]
            self.road_target[sl]=np.where(closer,target,self.road_target[sl])
            self.road_nearest[sl]=np.minimum(self.road_nearest[sl],d)
