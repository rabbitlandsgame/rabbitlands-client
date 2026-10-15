"""Export the UNION of river-crossing road surfaces in one global frame.

Independent outgoing/incoming road ribbons must never become separate decks
over the same channel. This exporter solves one common 1m height field, clips
its faces to a smooth road capsule union, and partitions it once by territory.
The sampled continent terrain is read-only. Failed bank fits are explicit.

Since the roads pass (R1) a deck is only a bridge: a claimed crossing site's
span plus landings of at most the plan's crossing_policy.deck_landing_metres,
or the same over deep water a road crosses away from any site (a sea channel).
Piers stand only under the span, over water. Floors are named per site
(Walk_ContinentalBridgeUnion_<site id + 1>_<territory>; decks away from a
site number from 500). Elevated walks that are not bridges belong to the
designed decks the plan names (landscape.designed_deck_entry).
"""
from __future__ import annotations

from pathlib import Path
import sys
import math
import io
from types import SimpleNamespace

import numpy as np
import shapely as SH
from scipy.ndimage import binary_dilation, label, find_objects
from scipy.sparse import coo_matrix, csr_matrix, hstack, lil_matrix
from scipy.sparse.linalg import spsolve
from scipy.optimize import linprog

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'_toolkit'))
import landscape as L
import bridge_profiles as BP
import coastal_bridge_export as C
import assemblies as A
import collision_export as CE
from content import walk_through as content_walk_through
from world_layout import (triangle_sample,SOLID_MARGIN_METRES,
                          SOLID_MAXIMUM_AREA_SQUARE_METRES)
from amberwood import gltf as G, mesh as M

CELL=1.
GRADE=.65
RETIRED_PLAN_KEYS=('bridge_approach_aprons','bridge_approach_connections')
TRIM_PASSES=6     # landing cells lifted over their bank beyond the deck lift limit are dropped and the deck solved again
SITE_BANK_LANDINGS={'horn_tributary@124':(4.,6.)}  # keep the Whitehorn keeper's existing bank route
SOLVE_GRADE=.64  # Margin for narrow clipped faces in float32 continent coordinates.
TERRAIN_CELL=2.
ROAD_CUT_METRES=4.
ROAD_FILL_METRES=3.
PROFILE_SLOPE_CHANGE_PER_METRE=.08
CURVATURE_FALLBACK_CEILING_PER_METRE=.09
ACTOR_HALF_WIDTH_METRES=float(CE.CELL)
DECK_FASCIA_DEPTH_METRES=.32
NEGLIGIBLE_FLOOR_AREA=1e-6  # square metres; a clipped outline below this is a sliver, not a floor
PRECISION_REMNANT_AREA=1e-4      # square metres: an encoded face failing the grade under this area is a remnant
PRECISION_REMNANT_ALTITUDE=.01   # metres: or thinner than this across its longest edge
CROSS=np.array([[0,1,0],[1,1,1],[0,1,0]],bool)
CAP_ARC_STEPS=12
POLYGON_EPS=1e-9
SITE8_SOLID_MARGIN_RELEASE={
    (416,414):(552,('Prop_PierSkiff_0',)),
    (416,415):(552,('Prop_PierCrate_0','Prop_PierSkiff_0')),
    (417,414):(552,('Prop_PierSkiff_0',)),
}
MIRROR_OUTLET_SOLID_RELEASE_KEY='mirror_outlet@16'
SITE8_SOLID_SOURCE_BOUNDS={
    'Prop_PierCrate_0':((833.6202436103217,829.8254436103217),(834.7373563896783,830.9425563896783)),
    'Prop_PierSkiff_0':((831.8788000476837,833.5318),(836.4787999523163,835.0318)),
}


def _area_xz(polygon):
    x,z=polygon[:,0],polygon[:,2]
    # Shift before the shoelace sum to avoid cancellation at continent scale.
    x=x-x[0];z=z-z[0]
    return float(np.sum(x*np.roll(z,-1)-z*np.roll(x,-1))*.5)


def _clip_halfplane(polygon,a,b,inside=True):
    """Clip XYZ while preserving its original deck triangle plane."""
    edge=b-a
    distance=edge[0]*(polygon[:,2]-a[1])-edge[1]*(polygon[:,0]-a[0])
    if not inside:distance=-distance
    keep=distance>=-POLYGON_EPS
    if keep.all():return polygon
    if not keep.any():return np.empty((0,3))
    output=[]
    for i in range(len(polygon)):
        j=(i-1)%len(polygon)
        if keep[i]!=keep[j]:
            t=distance[j]/(distance[j]-distance[i])
            output.append(polygon[j]+t*(polygon[i]-polygon[j]))
        if keep[i]:output.append(polygon[i])
    result=np.asarray(output)
    # Coincident vertices are common where neighbouring capsules overlap.
    distinct=np.linalg.norm(result-np.roll(result,1,axis=0),axis=1)>1e-8
    result=result[distinct]
    return result if len(result)>=3 and abs(_area_xz(result))>1e-10 else np.empty((0,3))


class RoadOutline:
    """Deterministic convex-capsule union, without a geometry dependency.

    Each cap is inscribed with a maximum 15-degree angular step. The greatest
    inset is <0.009 times the road half-width (about 3cm on a normal road).
    Subtracting previously covered convex pieces prevents overlapping faces.
    """
    bin_size=8.

    def __init__(self,world):
        unique=set()
        for road in world.roads:
            points=np.asarray(road['points'],float)[:,[0,2]]
            for a,b in zip(points,points[1:]):
                if np.linalg.norm(b-a)<1e-8:continue
                a,b=sorted((tuple(a),tuple(b)))
                unique.add((*a,*b,float(road['width'])))
        self.segments=np.asarray(sorted(unique),float).reshape(-1,5)
        self.polygons=[];self.bins={}
        for index,(ax,az,bx,bz,width) in enumerate(self.segments):
            angle=math.atan2(bz-az,bx-ax)
            arc=angle+np.linspace(-math.pi*.5,math.pi*.5,CAP_ARC_STEPS+1)
            polygon=np.concatenate((np.c_[bx+width*np.cos(arc),bz+width*np.sin(arc)],
                                    np.c_[ax-width*np.cos(arc),az-width*np.sin(arc)]))
            self.polygons.append(polygon)
            low=np.floor(polygon.min(axis=0)/self.bin_size).astype(int)
            high=np.floor(polygon.max(axis=0)/self.bin_size).astype(int)
            for x in range(low[0],high[0]+1):
                for z in range(low[1],high[1]+1):self.bins.setdefault((x,z),[]).append(index)

    def candidates(self,low,high=None):
        low=np.floor(np.asarray(low)/self.bin_size).astype(int)
        high=low if high is None else np.floor(np.asarray(high)/self.bin_size).astype(int)
        return sorted({i for x in range(low[0],high[0]+1) for z in range(low[1],high[1]+1)
                       for i in self.bins.get((x,z),())})

    @staticmethod
    def inside(polygon,points,tolerance=0.):
        a=polygon;b=np.roll(polygon,-1,axis=0);d=b-a
        distance=d[:,0]*(points[...,1,None]-a[:,1])-d[:,1]*(points[...,0,None]-a[:,0])
        return np.all(distance>=-(POLYGON_EPS+tolerance*np.linalg.norm(d,axis=1)),axis=-1)

    def contains(self,x,z,tolerance=0.):
        x,z=np.broadcast_arrays(np.asarray(x,float),np.asarray(z,float));shape=x.shape
        points=np.c_[x.ravel(),z.ravel()];result=np.zeros(len(points),bool)
        if not len(points):return result.reshape(shape)
        bins=np.floor(points/self.bin_size).astype(int)
        keys,inverse=np.unique(bins,axis=0,return_inverse=True)
        for group,key in enumerate(keys):
            members=np.flatnonzero(inverse==group)
            for index in self.bins.get(tuple(key),()):
                remaining=members[~result[members]]
                if not len(remaining):break
                result[remaining]|=self.inside(self.polygons[index],points[remaining],tolerance)
        return result.reshape(shape)

    def clip(self,triangle):
        candidates=self.candidates(triangle[:,[0,2]].min(axis=0),triangle[:,[0,2]].max(axis=0))
        # Almost every interior triangle fits inside one capsule unchanged.
        for index in candidates:
            if self.inside(self.polygons[index],triangle[:,[0,2]]).all():return [triangle]
        uncovered=[triangle];covered=[]
        for index in candidates:
            capsule=self.polygons[index];remaining=[]
            for piece in uncovered:
                inside=piece
                for a,b in zip(capsule,np.roll(capsule,-1,axis=0)):
                    outside=_clip_halfplane(inside,a,b,False)
                    if len(outside):remaining.append(outside)
                    inside=_clip_halfplane(inside,a,b)
                    if not len(inside):break
                if len(inside):covered.append(inside)
            uncovered=remaining
            if not uncovered:break
        return self._outer_loops(covered,triangle,candidates)

    def _outer_loops(self,pieces,triangle,candidates):
        """Remove internal Boolean cuts before triangulating the deck.

        Overlapping end caps often leave almost coincident internal slivers.
        They have no effect on the outline, but separate float32 triangles
        would turn them into steep or degenerate collision faces.
        """
        if len(pieces)<2:return pieces
        edges=np.concatenate([np.stack((p,np.roll(p,-1,axis=0)),axis=1) for p in pieces])
        a,b=edges[:,0],edges[:,1];delta=(b-a)[:,[0,2]]
        lengths=np.linalg.norm(delta,axis=1)
        outward=np.c_[-delta[:,1],delta[:,0]]/np.maximum(lengths[:,None],1e-20)
        sample=(a+b)[:,[0,2]]*.5+outward*1e-6
        inside_triangle=self.inside(triangle[::-1][:,[0,2]],sample)
        inside_union=np.zeros(len(sample),bool)
        for index in candidates:
            remaining=np.flatnonzero(inside_triangle&~inside_union)
            if not len(remaining):break
            inside_union[remaining]|=self.inside(self.polygons[index],sample[remaining])
        boundary=edges[~(inside_triangle&inside_union)&(lengths>1e-8)]
        if not len(boundary):return pieces
        vertices,index=np.unique(np.round(boundary.reshape(-1,3),7),axis=0,return_inverse=True)
        links=index.reshape(-1,2)
        if len(np.unique(links[:,0]))!=len(links) or len(np.unique(links[:,1]))!=len(links):return pieces
        next_vertex=dict(links);loops=[]
        while next_vertex:
            first=min(next_vertex);current=first;loop=[]
            for _ in range(len(next_vertex)+1):
                loop.append(current)
                if current not in next_vertex:return pieces
                current=next_vertex.pop(current)
                if current==first:break
            else:return pieces
            polygon=vertices[loop]
            if len(polygon)<3 or _area_xz(polygon)>=0:return pieces  # Retain exact pieces if there is a hole.
            loops.append(polygon)
        return loops


def precision_remnants(faces,areas):
    """Faces too small or too thin to carry a floor grade: area under a square centimetre, or altitude under a centimetre."""
    xz=np.asarray(faces)[:,:,[0,2]]
    longest=np.max(np.linalg.norm(np.roll(xz,-1,axis=1)-xz,axis=2),axis=1)
    altitude=2*np.asarray(areas)/np.maximum(longest,1e-12)
    return (np.asarray(areas)<PRECISION_REMNANT_AREA)|(altitude<PRECISION_REMNANT_ALTITUDE)


def normalize_floor_polygon(polygon):
    """Remove redundant boundary vertices without applying an area policy."""
    polygon=np.asarray(polygon)
    if len(polygon)<3:return polygon[:0]
    # Collapse redundant outside-boundary vertices at sub-millimetre scale.
    # This is below GLB precision at continent coordinates, not an art change.
    changed=True
    while changed and len(polygon)>3:
        changed=False
        for i in range(len(polygon)):
            a,b,c=polygon[[i-1,i,(i+1)%len(polygon)],:][:,[0,2]]
            chord=c-a;length=np.linalg.norm(chord)
            distance=abs(chord[0]*(b[1]-a[1])-chord[1]*(b[0]-a[0]))/max(length,1e-20)
            if (np.linalg.norm(b-a)<1e-5 or
                    (distance<1e-6 and np.dot(b-a,c-b)>=0)):
                polygon=np.delete(polygon,i,axis=0);changed=True;break
    return polygon


def triangulate_floor(polygon,minimum_area=NEGLIGIBLE_FLOOR_AREA,normalize=True,_retrace_retry=False):
    """Stable ear clipping of a clockwise, possibly concave floor outline."""
    polygon=np.asarray(polygon)
    # A deck cell clipped at a tangent of the road outline can leave a sliver
    # a tenth of a millimetre across (float32 at continent coordinates): no
    # emitted floor at all, not a failure. Terrain-overlay callers pass zero
    # and retain their own smaller geometric threshold.
    if len(polygon)<3 or abs(_area_xz(polygon))<minimum_area:return []
    if normalize:polygon=normalize_floor_polygon(polygon)
    if len(polygon)<3:return []
    indices=list(range(len(polygon)));result=[]
    while len(indices)>3:
        best=None;best_score=-1.
        for i in range(len(indices)):
            ids=[indices[i-1],indices[i],indices[(i+1)%len(indices)]]
            face=polygon[ids];area=-_area_xz(face)
            if area<1e-12:continue
            other=[j for j in indices if j not in ids]
            if other and RoadOutline.inside(face[::-1][:,[0,2]],polygon[other][:,[0,2]]).any():continue
            longest=max(np.linalg.norm(face[1,[0,2]]-face[0,[0,2]]),np.linalg.norm(face[2,[0,2]]-face[1,[0,2]]),
                        np.linalg.norm(face[0,[0,2]]-face[2,[0,2]]))
            score=area/max(longest,1e-20)
            if score>best_score:best=i;best_score=score
        if best is None:
            # The clipped road union can retrace a vertex by less than one
            # exported float32 XZ unit. That loop has no legal ear even though
            # removing the duplicate preserves its area and simple footprint.
            # Keep this fallback local to the failed outline; all other
            # polygons retain the existing exact ear-clipping path.
            if not _retrace_retry:
                remaining=polygon[indices]
                ulp=float(np.abs(np.spacing(remaining[:,[0,2]].astype(np.float32))).max())
                area=_area_xz(remaining)
                for j in range(len(remaining)):
                    neighbour=remaining[(j+1)%len(remaining)]
                    if np.linalg.norm(remaining[j,[0,2]]-neighbour[[0,2]])>ulp:continue
                    candidate=np.delete(remaining,j,axis=0)
                    candidate_area=_area_xz(candidate)
                    if (len(candidate)<3 or np.sign(candidate_area)!=np.sign(area) or
                            abs(candidate_area-area)>1e-8 or
                            not SH.Polygon(candidate[:,[0,2]]).is_valid):continue
                    return result+triangulate_floor(candidate,minimum_area=0.,normalize=False,
                                                    _retrace_retry=True)
            raise ValueError('Clipped bridge outline could not be triangulated')
        ids=[indices[best-1],indices[best],indices[(best+1)%len(indices)]]
        result.append(polygon[ids]);indices.pop(best)
    if len(indices)==3:result.append(polygon[indices])
    return result


class SpanOutline:
    """A road-capsule union clipped to exact site-axis join and width planes."""
    def __init__(self,base,origin,axis,start,end,half=None):
        self.base=base;self.origin=np.asarray(origin,float);self.axis=np.asarray(axis,float)
        self.across=np.array([-self.axis[1],self.axis[0]])
        self.start=float(start);self.end=float(end);self.half=None if half is None else float(half)

    def clip(self,triangle):
        low=self.origin+self.axis*self.start;high=self.origin+self.axis*self.end;pieces=[]
        for polygon in self.base.clip(triangle):
            # A half-plane can intersect a concave road-union loop in several
            # disconnected pieces.  Sutherland-Hodgman on that loop joins them
            # by a zero-area retraced boundary, which is not a simple polygon.
            # Triangulate the simple union loop first; clipping each convex face
            # then preserves the full intersection as separate simple pieces.
            simple=normalize_floor_polygon(polygon)
            if len(simple)<3:continue
            # RoadOutline preserves the caller's winding. Terrain-overlay
            # triangles are counterclockwise while deck cells are clockwise;
            # the floor triangulator's explicit contract is clockwise.
            if _area_xz(simple)>0:simple=simple[::-1].copy()
            edge=np.roll(simple,-1,axis=0)[:,[0,2]]-simple[:,[0,2]]
            turn=edge[:,0]*np.roll(edge,-1,axis=0)[:,1]-edge[:,1]*np.roll(edge,-1,axis=0)[:,0]
            # The overwhelming majority are already convex cell/capsule
            # intersections. Avoid an O(vertices^2) ear search for them.
            faces=[simple] if np.all(turn<=0.) else triangulate_floor(simple,minimum_area=0.)
            for face in faces:
                face=_clip_halfplane(face,low,low-self.across)
                if len(face):face=_clip_halfplane(face,high,high+self.across)
                if len(face) and self.half is not None:
                    side_low=self.origin-self.across*self.half
                    side_high=self.origin+self.across*self.half
                    face=_clip_halfplane(face,side_low,side_low+self.axis)
                    if len(face):face=_clip_halfplane(face,side_high,side_high-self.axis)
                if len(face):pieces.append(face)
        return pieces

    def contains(self,x,z,tolerance=0.):
        x,z=np.broadcast_arrays(np.asarray(x,float),np.asarray(z,float))
        delta=np.stack((x,z),axis=-1)-self.origin;station=delta@self.axis
        result=self.base.contains(x,z,tolerance=tolerance)&(station>=self.start-tolerance)&(station<=self.end+tolerance)
        if self.half is not None:result&=np.abs(delta@self.across)<=self.half+tolerance
        return result


class ShapelyWorldOutline:
    """Positive world-XZ polygons exposed through the terrain clip contract."""
    def __init__(self,geometry):self.geometry=geometry

    def clip(self,triangle):
        subject=SH.Polygon(np.asarray(triangle,float)[:,[0,2]])
        intersection=self.geometry.intersection(subject);result=[]
        for polygon in SH.get_parts(intersection):
            if polygon.geom_type!='Polygon' or polygon.is_empty or polygon.area<=0.:continue
            coordinates=np.asarray(polygon.exterior.coords[:-1],float)
            result.append(np.c_[coordinates[:,0],np.zeros(len(coordinates)),coordinates[:,1]])
        return result


def vertices_for_cells(mask):
    result=np.zeros((mask.shape[0]+1,mask.shape[1]+1),bool)
    result[:-1,:-1]|=mask;result[:-1,1:]|=mask
    result[1:,:-1]|=mask;result[1:,1:]|=mask
    return result


def bounded_floor(lower,active,maximum_grade=SOLVE_GRADE):
    """Smallest majorant with axis slopes <= grade/sqrt(2).

    Each grid triangle then has Euclidean slope <= grade. Max propagation
    preserves all terrain/water lower bounds and cannot create a folded face.
    """
    if not 0<maximum_grade<=GRADE:raise ValueError('Bridge grade must be in (0,.65]')
    if not np.isfinite(np.asarray(lower)[active]).all():raise ValueError('Non-finite bridge lower bound')
    value=np.where(active,lower,-np.inf).astype(float)
    step=maximum_grade/math.sqrt(2)*CELL
    for _ in range(active.size+1):
        new=value.copy()
        new[1:]=np.maximum(new[1:],value[:-1]-step)
        new[:-1]=np.maximum(new[:-1],value[1:]-step)
        new[:,1:]=np.maximum(new[:,1:],value[:,:-1]-step)
        new[:,:-1]=np.maximum(new[:,:-1],value[:,1:]-step)
        new[~active]=-np.inf
        if np.max(new[active]-value[active],initial=0)<1e-9:return new
        value=new
    raise ValueError('Common bridge profile did not converge')


def bank_profile(lower,active,water):
    """Harmonic bank-to-bank grade, held above the water-clearance floor."""
    unknown=active&water;fixed=active&~unknown
    if not unknown.any():return lower.copy()
    if not fixed.any():raise ValueError('A continental bridge requires an actual dry bank')
    index=np.full(active.shape,-1,int);index[unknown]=np.arange(int(unknown.sum()))
    rows,cols=np.nonzero(unknown);matrix_rows=[];matrix_cols=[];values=[]
    rhs=np.zeros(len(rows));degree=np.zeros(len(rows))
    for dz,dx in ((0,-1),(0,1),(-1,0),(1,0)):
        nz,nx=rows+dz,cols+dx
        valid=(nz>=0)&(nx>=0)&(nz<active.shape[0])&(nx<active.shape[1])
        current=np.flatnonzero(valid);nz=nz[valid];nx=nx[valid]
        valid=active[nz,nx];current=current[valid];nz=nz[valid];nx=nx[valid]
        degree[current]+=1
        neighbor=index[nz,nx];known=neighbor<0
        rhs[current[known]]+=lower[nz[known],nx[known]]
        matrix_rows.extend(current[~known]);matrix_cols.extend(neighbor[~known]);values.extend([-1.]*int((~known).sum()))
    matrix_rows.extend(range(len(rows)));matrix_cols.extend(range(len(rows)));values.extend(degree)
    matrix=coo_matrix((values,(matrix_rows,matrix_cols)),shape=(len(rows),len(rows))).tocsc()
    solved=spsolve(matrix,rhs)
    if not np.isfinite(solved).all():raise ValueError('Bridge bank profile is not connected to dry ground')
    result=lower.copy();result[unknown]=np.maximum(lower[unknown],solved)
    return result


def road_footprint(world):
    """Conservative grid for the later exact capsule clip.

    Testing only cell centres cuts diagonal shoulders off before clipping.
    Half a cell diagonal keeps every cell touched by the true road outline.
    """
    nx=int(round((world.x1-world.x0)/CELL));nz=int(round((world.z1-world.z0)/CELL))
    mask=np.zeros((nz,nx),bool)
    for road in world.roads:
        points=np.asarray(road['points'],float)[:,[0,2]];width=float(road['width'])+CELL/math.sqrt(2)
        for a,b in zip(points,points[1:]):
            low=np.minimum(a,b)-width;high=np.maximum(a,b)+width
            ix0=max(0,int(np.floor((low[0]-world.x0)/CELL)));ix1=min(nx,int(np.ceil((high[0]-world.x0)/CELL)))
            iz0=max(0,int(np.floor((low[1]-world.z0)/CELL)));iz1=min(nz,int(np.ceil((high[1]-world.z0)/CELL)))
            if ix0>=ix1 or iz0>=iz1:continue
            x,z=np.meshgrid(world.x0+(np.arange(ix0,ix1)+.5)*CELL,world.z0+(np.arange(iz0,iz1)+.5)*CELL)
            dx,dz=b-a;length=dx*dx+dz*dz
            if length<1e-12:continue
            t=np.clip(((x-a[0])*dx+(z-a[1])*dz)/length,0,1)
            mask[iz0:iz1,ix0:ix1]|=np.hypot(x-a[0]-t*dx,z-a[1]-t*dz)<=width
    return mask


def frontier_vertices(cells,road):
    """Vertices where a bridge joins the continuing dry road footprint."""
    result=np.zeros((cells.shape[0]+1,cells.shape[1]+1),bool)
    outside=road&~cells
    across=(cells[:,:-1]&outside[:,1:])|(outside[:,:-1]&cells[:,1:])
    result[:-1,1:-1]|=across;result[1:,1:-1]|=across
    across=(cells[:-1]&outside[1:])|(outside[:-1]&cells[1:])
    result[1:-1,:-1]|=across;result[1:-1,1:]|=across
    return result


def deck_policy(world):
    """(landing, lift, clearance metres) from the plan's crossing policy."""
    plan=getattr(world,'plan',None) or {}
    for key in RETIRED_PLAN_KEYS:
        if key in plan:
            raise ValueError(f'{key}: retired by the roads pass (R1): a bridge deck is its site span plus landings of at most '
                             'crossing_policy.deck_landing_metres; remove the key from diagonal-plan.json')
    policy=L.crossing_policy(plan)
    return float(policy['deck_landing_metres']),float(policy['deck_lift_metres']),float(policy['deck_clearance_metres'])


def site_span_cells(world,site,road,landing,conservative=False):
    """Road footprint cells on a crossing site's span: along its axis from landing metres before the first wet edge
    to landing metres beyond the last, and across it within the widest road plus a cell."""
    left,right=np.asarray(site['wetEdges'][0],float),np.asarray(site['wetEdges'][1],float)
    axis=right-left;length=float(np.linalg.norm(axis))
    if length<1e-9:return np.zeros_like(road)
    axis/=length;across=np.array([-axis[1],axis[0]])
    half=max((float(r['width']) for r in world.roads),default=4.)+CELL
    start=left-axis*landing;span=length+2*landing
    corners=np.array([start+across*half,start-across*half,start+axis*span+across*half,start+axis*span-across*half])
    lo=np.floor((corners.min(axis=0)-[world.x0,world.z0])/CELL).astype(int);hi=np.ceil((corners.max(axis=0)-[world.x0,world.z0])/CELL).astype(int)
    ix0,iz0=max(0,lo[0]),max(0,lo[1]);ix1,iz1=min(road.shape[1],hi[0]+1),min(road.shape[0],hi[1]+1)
    cells=np.zeros_like(road)
    if ix0>=ix1 or iz0>=iz1:return cells
    x,z=np.meshgrid(world.x0+(np.arange(ix0,ix1)+.5)*CELL,world.z0+(np.arange(iz0,iz1)+.5)*CELL)
    along=(x-start[0])*axis[0]+(z-start[1])*axis[1];side=(x-start[0])*across[0]+(z-start[1])*across[1]
    # Prepared geometry uses conservative cell membership before its exact
    # station/capsule clip. Legacy fields retain their established raster.
    radius=CELL/math.sqrt(2) if conservative else 0.
    cells[iz0:iz1,ix0:ix1]=(along>=-radius)&(along<=span+radius)&(np.abs(side)<=half+radius)
    return cells&road


def _site_frame(site):
    left,right=np.asarray(site['wetEdges'],float)
    axis=right-left;length=float(np.linalg.norm(axis))
    if length<1e-9:raise BP.ProfileError('claimed bridge has an empty wet span')
    axis/=length
    return left,right,axis,np.array([-axis[1],axis[0]]),length


def _serving_roads(world,site,strict=False):
    mapping=getattr(world,'crossing_site_roads',{})
    if site['id'] not in mapping:
        if strict:raise BP.ProfileError('claimed bridge has no named serving-road attribution')
        return list(world.roads)  # legacy fixture/world without attribution
    ids=mapping[site['id']]
    if ids is True:
        if strict:raise BP.ProfileError('claimed bridge attribution cannot use every world road')
        return list(world.roads)
    if not ids:return []
    roads=[road for road in world.roads if road.get('id') in ids]
    if strict and {road.get('id') for road in roads}!=set(ids):
        raise BP.ProfileError('claimed bridge names a missing serving road')
    if not strict and not roads:return list(world.roads)
    return roads


def _linear_interval(offset,slope,low,high):
    if abs(slope)<1e-12:return (-np.inf,np.inf) if low<=offset<=high else None
    a,b=(low-offset)/slope,(high-offset)/slope
    return min(a,b),max(a,b)


def _interval_intersection(*parts):
    if any(part is None for part in parts):return None
    low=max(part[0] for part in parts);high=min(part[1] for part in parts)
    return (low,high) if high>low else None


def _capsule_line_intervals(base,across,a,b,radius):
    """Exact line section of one segment capsule, independent of deck cells."""
    vector=b-a;length=float(np.linalg.norm(vector))
    if length<1e-12:return []
    tangent=vector/length;normal=np.array([-tangent[1],tangent[0]]);delta=base-a
    along0,along_slope=float(delta@tangent),float(across@tangent)
    side0,side_slope=float(delta@normal),float(across@normal)
    result=[]
    middle=_interval_intersection(_linear_interval(along0,along_slope,0.,length),
                                  _linear_interval(side0,side_slope,-radius,radius))
    if middle is not None:result.append(middle)
    for centre,bound,below in ((a,0.,True),(b,length,False)):
        d=base-centre;mid=-float(d@across);perpendicular2=float(d@d)-mid*mid
        circle=None
        if perpendicular2<radius*radius:
            reach=math.sqrt(max(0.,radius*radius-perpendicular2));circle=(mid-reach,mid+reach)
        side=_linear_interval(along0,along_slope,-np.inf if below else bound,bound if below else np.inf)
        part=_interval_intersection(circle,side)
        if part is not None:result.append(part)
    return result


def _merge_intervals(intervals,epsilon=1e-8):
    result=[]
    for low,high in sorted((min(a,b),max(a,b)) for a,b in intervals if abs(a-b)>epsilon):
        if result and low<=result[-1][1]+epsilon:result[-1][1]=max(result[-1][1],high)
        else:result.append([float(low),float(high)])
    return result


def serving_join_intervals(world,site,station,strict=False,clip_to_nominal=True,
                           nominal_half=None):
    """Analytic serving-road cross-section, never inferred from raster cells."""
    left,_,axis,across,_=_site_frame(site);base=left+axis*station
    roads=_serving_roads(world,site,strict=strict)
    if not roads:raise BP.ProfileError('claimed bridge has no serving road')
    half=(max(float(road['width']) for road in roads) if nominal_half is None
          else float(nominal_half));intervals=[]
    for road in roads:
        points=np.asarray(road['points'],float)[:,[0,2]]
        for a,b in zip(points,points[1:]):
            intervals.extend(_capsule_line_intervals(base,across,a,b,float(road['width'])))
    intervals=_merge_intervals(intervals)
    if not clip_to_nominal:return intervals
    return _merge_intervals((max(low,-half),min(high,half)) for low,high in intervals
                            if max(low,-half)<min(high,half))


def _excluded_join_intervals(intervals,half,epsilon=1e-8):
    """Parts of analytic serving-road coverage outside the nominal deck band."""
    excluded=[]
    for low,high in intervals:
        if low<-half-epsilon:excluded.append([float(low),float(min(high,-half))])
        if high>half+epsilon:excluded.append([float(max(low,half)),float(high)])
    return _merge_intervals(excluded,epsilon=epsilon)


def _terrain_interpolation(world,x,z,height=None):
    height=world.height if height is None else height
    fx=np.clip((float(x)-world.x0)/TERRAIN_CELL,0,world.height.shape[1]-1.0000001)
    fz=np.clip((float(z)-world.z0)/TERRAIN_CELL,0,world.height.shape[0]-1.0000001)
    ix,iz=int(fx),int(fz);u,v=fx-ix,fz-iz
    nodes=(((iz,ix,1-u-v),(iz,ix+1,u),(iz+1,ix,v)) if u+v<=1 else
           ((iz+1,ix+1,u+v-1),(iz+1,ix,1-u),(iz,ix+1,1-v)))
    return float(sum(height[r,c]*w for r,c,w in nodes)),nodes


def _terrain_row(world,x,z,node_vars,size):
    base,nodes=_terrain_interpolation(world,x,z);row=np.zeros(size)
    for r,c,w in nodes:
        if (r,c) in node_vars:row[node_vars[(r,c)]]+=w
    return base,row


def _append_mutable_dry_constraint(rows,limits,trow,baseline,water_surface,guard):
    """Keep changed dry terrain dry; immutable source terrain needs no LP row."""
    if not np.any(trow):return False
    rows.append(-trow);limits.append(baseline-float(water_surface)+.015-guard)
    return True


def _per_station_profile_constraints(stations,middle,rise):
    """Profile-only rows for grade, one crest, and slope-change reporting."""
    return BP.per_station_single_crest_constraints(
        stations,middle,rise,SOLVE_GRADE)


def _terrain_triangles(world,bounds):
    ix0,ix1,iz0,iz1=bounds
    for iz in range(iz0,iz1):
        for ix in range(ix0,ix1):
            x0=world.x0+ix*TERRAIN_CELL;z0=world.z0+iz*TERRAIN_CELL
            x1=x0+TERRAIN_CELL;z1=z0+TERRAIN_CELL
            yield ((iz,ix),(iz,ix+1),(iz+1,ix)),np.array([[x0,0,z0],[x1,0,z0],[x0,0,z1]],float)
            yield ((iz+1,ix+1),(iz+1,ix),(iz,ix+1)),np.array([[x1,0,z1],[x0,0,z1],[x1,0,z0]],float)


def _clip_area(outline,triangle):
    return sum(abs(_area_xz(piece)) for piece in outline.clip(triangle))


def _central_join_interval(intervals,side):
    """The finite serving-road section connected to the site-axis join point."""
    central=[row for row in intervals if row[0]<=0.<=row[1]]
    if len(central)!=1:
        raise BP.ProfileError(f'{side} join has no unique serving-road interval through the site axis')
    return central[0]


def _convex_polygons_overlap(a,b):
    """Exact finite convex-set adjacency; touching capsule pieces connect."""
    a=np.asarray(a,float);b=np.asarray(b,float)
    for polygon in (a,b):
        edges=np.roll(polygon,-1,axis=0)-polygon
        for edge in edges:
            axis=np.array([-edge[1],edge[0]])
            if np.max(a@axis)<np.min(b@axis) or np.max(b@axis)<np.min(a@axis):
                return False
    return True


def _polygon_line_interval(polygon,base,across):
    """Intersection of one convex RoadOutline capsule piece with a join line."""
    polygon=np.asarray(polygon,float)
    area=np.sum(polygon[:,0]*np.roll(polygon[:,1],-1)-
                polygon[:,1]*np.roll(polygon[:,0],-1))*.5
    if area<0.:polygon=polygon[::-1]
    low,high=-np.inf,np.inf
    for a,b in zip(polygon,np.roll(polygon,-1,axis=0)):
        edge=b-a;c0=_cross2(edge,np.asarray(base,float)-a);c1=_cross2(edge,across)
        if c1>0.:low=max(low,-c0/c1)
        elif c1<0.:high=min(high,-c0/c1)
        elif c0<0.:return None
    return [float(low),float(high)] if low<high else None


def _line_interval_arithmetic_bound(polygons,base,across):
    """Forward-error bound for the cross-product quotients in a line clip."""
    base=np.asarray(base,float);across=np.asarray(across,float);maximum=0.
    for polygon in np.asarray(polygons,float):
        area=np.sum(polygon[:,0]*np.roll(polygon[:,1],-1)-
                    polygon[:,1]*np.roll(polygon[:,0],-1))*.5
        if area<0.:polygon=polygon[::-1]
        low,high=-np.inf,np.inf;low_error=high_error=0.
        for a,b in zip(polygon,np.roll(polygon,-1,axis=0)):
            edge=b-a;delta=base-a;c1=_cross2(edge,across)
            if c1==0.:continue
            c0=_cross2(edge,delta);quotient=-c0/c1
            c0_scale=abs(edge[0]*delta[1])+abs(edge[1]*delta[0])
            c1_scale=abs(edge[0]*across[1])+abs(edge[1]*across[0])
            propagated=(c0_scale+abs(quotient)*c1_scale)/abs(c1)
            error=64*np.finfo(float).eps*(propagated+max(1.,abs(quotient)))
            if c1>0. and quotient>low:low,low_error=quotient,error
            elif c1<0. and quotient<high:high,high_error=quotient,error
        if low<high:maximum=max(maximum,low_error,high_error)
    return float(maximum)


def _component_join_intervals(outline,indices,origin,axis,station):
    across=np.array([-axis[1],axis[0]]);base=np.asarray(origin,float)+axis*station
    rows=[_polygon_line_interval(outline.polygons[index],base,across) for index in indices]
    return _merge_intervals((row for row in rows if row is not None),epsilon=0.)


def _bounded_crossing_component(outline,origin,axis,length,start,end):
    """Unique slab component owning both authored wet-edge anchor points."""
    across=np.array([-axis[1],axis[0]]);low=origin+axis*start;high=origin+axis*end
    clipped={}
    for index,polygon in enumerate(outline.polygons):
        face=np.c_[polygon[:,0],np.zeros(len(polygon)),polygon[:,1]]
        face=_clip_halfplane(face,low,low-across)
        if len(face):face=_clip_halfplane(face,high,high+across)
        if len(face):clipped[index]=face[:,[0,2]]
    adjacency={index:set() for index in clipped}
    keys=sorted(clipped)
    for position,index in enumerate(keys):
        for other in keys[position+1:]:
            if _convex_polygons_overlap(clipped[index],clipped[other]):
                adjacency[index].add(other);adjacency[other].add(index)
    components=[];remaining=set(keys)
    while remaining:
        stack=[min(remaining)];component=set()
        while stack:
            index=stack.pop()
            if index in component:continue
            component.add(index);remaining.discard(index);stack.extend(adjacency[index]-component)
        components.append(sorted(component))
    crossing=[];seeded=[];component_rows=[]
    for component in components:
        left=_component_join_intervals(outline,component,origin,axis,0.)
        right=_component_join_intervals(outline,component,origin,axis,length)
        owns=[]
        for point in (origin,origin+axis*length):
            owns.append(any(RoadOutline.inside(clipped[index],point[None]).item()
                            for index in component))
        row={'members':component,'wetEdgeIntervals':{'left':left,'right':right},
             'ownsAuthoredWetEdgeAnchors':owns}
        component_rows.append(row)
        if left and right:
            crossing.append((component,left,right))
            if all(owns):seeded.append((component,left,right))
    if len(seeded)!=1:
        raise BP.ProfileError(
            'site join has no unique finite serving-road capsule component owning both authored wet-edge anchors')
    component,left,right=seeded[0]
    return component,{'componentCountInBoundedSlab':len(components),
                      'crossingComponentCandidates':len(crossing),
                      'wetSeedComponentCandidates':len(seeded),
                      'components':components,'selectedComponent':component,
                      'componentEvidence':component_rows,
                      'wetEdgeIntervals':{'left':left,'right':right}}


def _wet_seeded_crossing_backbone(world,site_id,outline,origin,axis,length,start,end):
    """Local left-to-right road backbone seeded by actual encoded water.

    An attributed road graph may include dry bank-parallel branches inside the
    axial landing slab.  They remain ordinary terrain roads.  The bridge owns
    the unique component at both wet anchors, every capsule that touches the
    emitted water, and only the dry graph paths needed to reach the nearest
    outer join interval on each bank.
    """
    component,report=_bounded_crossing_component(outline,origin,axis,length,start,end)
    across=np.array([-axis[1],axis[0]]);low=origin+axis*start;high=origin+axis*end
    clipped={}
    for index in component:
        polygon=outline.polygons[index]
        face=np.c_[polygon[:,0],np.zeros(len(polygon)),polygon[:,1]]
        face=_clip_halfplane(face,low,low-across)
        if len(face):face=_clip_halfplane(face,high,high+across)
        if len(face):clipped[index]=face[:,[0,2]]
    points=np.vstack(list(clipped.values()))
    lo=np.floor((points.min(axis=0)-[world.x0,world.z0])/TERRAIN_CELL).astype(int)-1
    hi=np.ceil((points.max(axis=0)-[world.x0,world.z0])/TERRAIN_CELL).astype(int)+1
    bounds=(max(0,int(lo[0])),min(world.height.shape[1]-1,int(hi[0])),
            max(0,int(lo[1])),min(world.height.shape[0]-1,int(hi[1])))
    water_faces=np.asarray(_encoded_water_authority(world,bounds)['faces'],float)
    water=SH.union_all([SH.Polygon(face[:,[0,2]]) for face in water_faces
                        if SH.Polygon(face[:,[0,2]]).area>0.])
    wet={index for index,polygon in clipped.items()
         if not water.is_empty and SH.Polygon(polygon).intersection(water).area>0.}
    if not wet:raise BP.ProfileError('serving-road crossing has no actual emitted-water capsule seed')
    adjacency={index:set() for index in component}
    for position,index in enumerate(component):
        for other in component[position+1:]:
            if _convex_polygons_overlap(clipped[index],clipped[other]):
                adjacency[index].add(other);adjacency[other].add(index)
    station_middle={index:float(((outline.segments[index,:2]+outline.segments[index,2:4])*.5-origin)@axis)
                    for index in component}
    targets={}
    for side,station in (('left',start),('right',end)):
        candidates=[]
        for index in component:
            intervals=_component_join_intervals(outline,[index],origin,axis,station)
            for interval in intervals:
                distance=max(float(interval[0]),0.,-float(interval[1]))
                segment=outline.segments[index];vector=segment[2:4]-segment[:2]
                alignment=abs(float(vector@axis))/float(np.linalg.norm(vector))
                candidates.append((distance,-alignment,-float(segment[4]),index,interval))
        if not candidates:raise BP.ProfileError(f'wet-seeded crossing has no {side} outer road join')
        best=min(candidates);chosen=[best[3]]
        targets[side]={'segmentIndices':chosen,'distanceFromWetAxisMetres':best[0],
                       'intervals':[best[4]],'absoluteAxisAlignment':-best[1]}

    def shortest_path(starts,goals,side=None):
        queue=list(sorted(starts));parent={index:None for index in queue}
        found=next((index for index in queue if index in goals),None)
        while queue and found is None:
            index=queue.pop(0)
            for other in sorted(adjacency[index]):
                if other in parent:continue
                if side=='left' and station_middle[other]<station_middle[index]:continue
                if side=='right' and station_middle[other]>station_middle[index]:continue
                parent[other]=index;queue.append(other)
                if other in goals:found=other;break
        if found is None:return None
        path=[]
        while found is not None:path.append(found);found=parent[found]
        return path

    kept=set(wet);bank_paths={}
    for side in ('left','right'):
        path=shortest_path(targets[side]['segmentIndices'],wet,side=side)
        if path is None:raise BP.ProfileError(f'wet-seeded crossing has no monotone {side} bank path')
        kept.update(path);bank_paths[side]=path
    # Every genuine wet capsule remains part of one connected floor.  Join a
    # separately wet route by the shortest graph path; dry dead-end branches
    # are never terminals and therefore cannot enter the result.
    while True:
        reached=set();queue=[min(kept)]
        while queue:
            index=queue.pop()
            if index in reached:continue
            reached.add(index);queue.extend((adjacency[index]&kept)-reached)
        missing=wet-reached
        if not missing:break
        path=shortest_path(reached,missing)
        if path is None:raise BP.ProfileError('actual-water road capsules are disconnected')
        kept.update(path)
    kept=sorted(kept)
    for side in ('left','right'):
        if not set(targets[side]['segmentIndices'])<=set(kept):
            raise BP.ProfileError(f'wet-seeded crossing lost its {side} bank join')
    if not wet<=set(kept):raise BP.ProfileError('wet-seeded crossing lost an emitted-water road capsule')
    selected_left=_component_join_intervals(outline,kept,origin,axis,start)
    selected_right=_component_join_intervals(outline,kept,origin,axis,end)
    if len(selected_left)!=1 or len(selected_right)!=1:
        raise BP.ProfileError('wet-seeded crossing has a discontinuous outer join')
    report={**report,'preWaterSelectedComponent':component,
            'selectedComponent':kept,'actualWaterSeedSegments':sorted(wet),
            'dryBankParallelSegments':sorted(set(component)-set(kept)),
            'outerJoinTargets':targets,'monotoneBankPaths':bank_paths,
            'waterClassificationBounds':list(bounds),
            'wetSeedWaterFaces':len(water_faces),
            'wetEdgeIntervals':{'left':selected_left,'right':selected_right}}
    return kept,report


def _selected_outline(outline,indices,expected_segments=None):
    indices=np.asarray(indices,int)
    if expected_segments is not None and not np.array_equal(
            outline.segments[indices,:4],np.asarray(expected_segments,float)):
        raise BP.ProfileError('guarded serving-road segment order changed')
    selected=object.__new__(RoadOutline);selected.bin_size=outline.bin_size
    selected.segments=outline.segments[indices].copy()
    selected.polygons=[outline.polygons[int(index)] for index in indices];selected.bins={}
    for index,polygon in enumerate(selected.polygons):
        low=np.floor(polygon.min(axis=0)/selected.bin_size).astype(int)
        high=np.floor(polygon.max(axis=0)/selected.bin_size).astype(int)
        for x in range(low[0],high[0]+1):
            for z in range(low[1],high[1]+1):selected.bins.setdefault((x,z),[]).append(index)
    return selected


def _contract_join_intervals(world,site,station,geometry,clip_to_nominal=True):
    roads=_serving_roads(world,site,strict=True)
    outline=RoadOutline(SimpleNamespace(roads=roads))
    indices=geometry['servingSegmentIndices']
    _selected_outline(outline,indices,geometry['servingSegmentXZ'])
    origin,_,axis,_,_=_site_frame(site)
    intervals=_component_join_intervals(outline,indices,origin,axis,station)
    if not clip_to_nominal:return intervals
    half=float(geometry['nominalHalf'])
    clipped=[(max(low,-half),min(high,half)) for low,high in intervals
             if max(low,-half)<min(high,half)]
    return _merge_intervals(clipped,epsilon=0.)


def _claimed_geometry_v7(world,site,landing,roads):
    """Nested source/nominal bounds derived from float32 XZ encoding.

    The encoded source edge stays inside the six-metre policy cap.  The
    independent nominal promise is one further guard inside that source edge,
    while the source is one guard wider than the analytic road half-width.
    """
    left,_,axis,across,length=_site_frame(site)
    bank_landings=SITE_BANK_LANDINGS.get(str(site.get('key','')),(landing,landing))
    left_landing,right_landing=map(float,bank_landings)
    if (not np.isfinite([left_landing,right_landing]).all()
            or not 0.<left_landing<=landing or not 0.<right_landing<=landing):
        raise BP.ProfileError('claimed bridge bank landing is outside its positive policy cap')
    policy_start=-left_landing;policy_end=length+right_landing
    roads=list(roads)
    nominal_outline=RoadOutline(SimpleNamespace(roads=roads))
    if hasattr(world,'height') and hasattr(world,'water'):
        selected_indices,component_report=_wet_seeded_crossing_backbone(
            world,int(site['id']),nominal_outline,left,axis,length,policy_start,policy_end)
    else:
        selected_indices,component_report=_bounded_crossing_component(
            nominal_outline,left,axis,length,policy_start,policy_end)
        component_report={**component_report,
            'preWaterSelectedComponent':selected_indices,
            'actualWaterSeedSegments':selected_indices,
            'dryBankParallelSegments':[],'outerJoinTargets':{},
            'waterClassificationBounds':None,'wetSeedWaterFaces':None}
    half=float(np.max(nominal_outline.segments[selected_indices,4]))
    outline_points=np.concatenate([nominal_outline.polygons[index] for index in selected_indices])
    finite_half=half
    for _ in range(4):
        policy=np.array([left+axis*s+across*t for s in (policy_start,policy_end)
                         for t in (-finite_half,finite_half)],float)
        authority=np.vstack((policy,outline_points))
        ulp=np.abs(np.spacing(authority.astype(np.float32))).astype(float)
        axis_guard=float(np.max(ulp@np.abs(axis),initial=0.))
        cross_guard=float(np.max(ulp@np.abs(across),initial=0.))
        road_guard=float(np.max(np.linalg.norm(ulp,axis=1),initial=0.))
        if not np.isfinite([axis_guard,cross_guard,road_guard]).all():
            raise BP.ProfileError('nonfinite float32 bridge producer guard')
        construction_start=policy_start+axis_guard
        construction_end=policy_end-axis_guard
        raw={side:_component_join_intervals(nominal_outline,selected_indices,left,axis,station)
             for side,station in (('left',construction_start),('right',construction_end))}
        disconnected={side:_merge_intervals([
            interval for component in component_report['components']
            if component!=component_report['selectedComponent']
            for interval in _component_join_intervals(
                nominal_outline,component,left,axis,station)],epsilon=0.)
            for side,station in (('left',construction_start),('right',construction_end))}
        if any(len(intervals)!=1 for intervals in raw.values()):
            raise BP.ProfileError('finite serving-road crossing has a discontinuous join section')
        raw_required=max(half,*[abs(value) for intervals in raw.values() for interval in intervals
                                for value in interval])
        numeric_guard=road_guard+cross_guard
        numeric_expansion=max(0.,raw_required-half)
        required=(half if numeric_expansion<=numeric_guard else raw_required)
        if required<=finite_half:break
        finite_half=required
    else:
        raise BP.ProfileError('finite serving-road join width did not converge')
    nominal_start=construction_start+axis_guard
    nominal_end=construction_end-axis_guard
    if (nominal_start>=0. or nominal_end<=length or construction_start<policy_start
            or construction_end>policy_end):
        raise BP.ProfileError('float32 bridge producer guard escaped the six-metre landing cap')
    return {'policyStart':policy_start,'policyEnd':policy_end,
            'constructionStart':construction_start,'constructionEnd':construction_end,
            'nominalStart':nominal_start,'nominalEnd':nominal_end,
            'baseRoadHalf':half,'nominalHalf':finite_half,
            'constructionHalf':finite_half+road_guard+cross_guard,
            'axisGuardMetres':axis_guard,'crossGuardMetres':cross_guard,
            'roadCapsuleGuardMetres':road_guard,
            'rawRequiredHalfMetres':raw_required,
            'numericJoinExpansionMetres':numeric_expansion,
            'numericJoinExpansionGuardMetres':numeric_guard,
            'allowedRoadCapsuleGuardMetres':2.*road_guard,
            'allowedCrossHalf':finite_half+road_guard+2.*cross_guard,
            'finiteServingJoinIntervals':raw,
            'servingSegmentIndices':[int(value) for value in selected_indices],
            'servingSegmentXZ':nominal_outline.segments[selected_indices,:4].tolist(),
            'servingComponentAuthority':component_report,
            'unclaimedDisconnectedJoinIntervals':disconnected,
            'leftLandingMetres':left_landing,'rightLandingMetres':right_landing,
            'maximumLandingMetres':landing}


def _guarded_serving_roads(roads,geometry):
    """Source-only capsule/cap expansion; nominal road authority is unchanged."""
    guard=float(geometry['roadCapsuleGuardMetres'])
    return [{**road,'width':float(road['width'])+guard} for road in roads]


def _selected_span_outline(roads,geometry,origin,axis):
    guarded=RoadOutline(SimpleNamespace(roads=_guarded_serving_roads(roads,geometry)))
    selected=_selected_outline(guarded,geometry['servingSegmentIndices'],geometry['servingSegmentXZ'])
    return SpanOutline(selected,origin,axis,geometry['constructionStart'],
                       geometry['constructionEnd'],geometry['constructionHalf'])


def _actor_center_outline(roads,geometry):
    """Selected road union inset by the current EWCG actor half-width."""
    inset=[]
    for road in roads:
        width=float(road['width'])-ACTOR_HALF_WIDTH_METRES
        if width<=0.:raise BP.ProfileError('serving road is narrower than the current actor policy')
        inset.append({**road,'width':width})
    outline=RoadOutline(SimpleNamespace(roads=inset))
    return _selected_outline(outline,geometry['servingSegmentIndices'],geometry['servingSegmentXZ'])


def _side_junction_geometry(roads,geometry,origin,axis):
    """Actor-centre continuation where excluded dry branches meet the deck."""
    excluded=geometry['servingComponentAuthority']['dryBankParallelSegments']
    if not excluded:return None,SH.GeometryCollection()
    inset=[]
    for road in roads:
        width=float(road['width'])-ACTOR_HALF_WIDTH_METRES
        if width<=0.:raise BP.ProfileError('serving road is narrower than the current actor policy')
        inset.append({**road,'width':width})
    outline=RoadOutline(SimpleNamespace(roads=inset))
    actor=_selected_outline(outline,excluded)
    origin=np.asarray(origin,float);axis=np.asarray(axis,float);across=np.array([-axis[1],axis[0]])
    polygons=[]
    for polygon in actor.polygons:
        delta=np.asarray(polygon,float)-origin
        candidate=SH.Polygon(np.c_[delta@axis,delta@across])
        if not candidate.is_empty and candidate.area>0.:polygons.append(candidate)
    if not polygons:return None,SH.GeometryCollection()
    ring=TERRAIN_CELL*math.sqrt(2.)
    branch=SH.union_all(polygons);_,side_low,_,side_high=branch.bounds
    branch=branch.intersection(SH.box(
        geometry['constructionStart']-ring,side_low-1.,
        geometry['constructionEnd']+ring,side_high+1.))
    floor=_shapely_selected_union_uv(
        roads,geometry,origin,axis,geometry['roadCapsuleGuardMetres'],
        geometry['constructionStart'],geometry['constructionEnd'],geometry['constructionHalf'])
    approach=branch.difference(floor).intersection(floor.buffer(ring))
    world_polygons=[]
    for polygon in _positive_shapely_polygons(approach):
        exterior=np.asarray(polygon.exterior.coords,float)
        xz=origin+exterior[:,0,None]*axis+exterior[:,1,None]*across
        world_polygons.append(SH.Polygon(xz))
    world=SH.union_all(world_polygons) if world_polygons else SH.GeometryCollection()
    return (ShapelyWorldOutline(world) if not world.is_empty else None),branch


def _side_junction_contact_samples(world,site,faces,geometry):
    """Actual encoded floor-edge extrema where dry side roads continue."""
    roads=_serving_roads(world,site,strict=True);origin,_,axis,across,_=_site_frame(site)
    _,branch=_side_junction_geometry(roads,geometry,origin,axis)
    if branch.is_empty:return []
    faces=np.asarray(faces,float);edges={}
    for face_index,face in enumerate(faces):
        for a,b in zip(face[:,[0,2]],np.roll(face[:,[0,2]],-1,axis=0)):
            key=tuple(sorted((tuple(a),tuple(b))))
            edges.setdefault(key,[]).append(face_index)
    samples=[]
    for (a,b),owners in edges.items():
        if len(owners)!=1:continue
        face_index=owners[0];xz=np.asarray((a,b),float);delta=xz-origin
        line=SH.LineString(np.c_[delta@axis,delta@across]).intersection(branch)
        if line.is_empty or line.length<=0.:continue
        for _,_,overlay in _face_overlays(world,faces[face_index]):
            overlay_delta=np.asarray(overlay,float)-origin
            terrain=SH.Polygon(np.c_[overlay_delta@axis,overlay_delta@across])
            intersection=line.intersection(terrain)
            for part in SH.get_parts(intersection):
                if part.geom_type!='LineString' or part.is_empty or part.length<=0.:continue
                coordinates=np.asarray(part.coords,float)
                for uv in (coordinates[0],coordinates[-1]):
                    samples.append((face_index,origin+uv[0]*axis+uv[1]*across))
    unique={}
    for face_index,point in samples:unique[(int(face_index),*map(float,point))]=(face_index,point)
    return [unique[key] for key in sorted(unique)]


def _selected_span_cells(world,site,geometry,span):
    cells=site_span_cells(world,site,road_footprint(world),
                          float(geometry['maximumLandingMetres']),conservative=True)
    rows,cols=np.nonzero(cells)
    if len(rows):
        x=world.x0+(cols+.5)*CELL;z=world.z0+(rows+.5)*CELL
        keep=span.contains(x,z,tolerance=CELL/math.sqrt(2.))
        cells[rows[~keep],cols[~keep]]=False
    return cells


def _arch_vertex_stations(xz,origin,axis,join_stations=()):
    """Stations used by both the LP face basis and the actual deck producer."""
    xz=np.asarray(xz,float);station=(xz-np.asarray(origin,float))@np.asarray(axis,float)
    for join in join_stations:
        on=np.abs(station-float(join))<=_float32_axis_error(xz,axis)
        station[on]=float(join)
    return station


def _terrain_gradient_displacement_bound(world,reference,node_vars,canonical,actual):
    """Interval terrain-rise bound along one source-to-encoded XZ displacement."""
    canonical=np.asarray(canonical,float);actual=np.asarray(actual,float);delta=actual-canonical
    probes=(canonical,actual,(canonical+actual)*.5);triangles={}
    for point in probes:
        _,nodes=_terrain_interpolation(world,*point,reference)
        key=tuple((r,c) for r,c,_ in nodes)
        triangles[key]=nodes
    maximum=0.;details=[]
    for key,nodes in triangles.items():
        coords=np.array([[world.x0+c*TERRAIN_CELL,world.z0+r*TERRAIN_CELL] for r,c,_ in nodes])
        matrix=coords[1:]-coords[0]
        condition=float(np.linalg.cond(matrix))
        if not np.isfinite(condition) or condition>1e12:
            raise BP.ProfileError('ill-conditioned terrain triangle in join encoding bound')
        bounds=[]
        for r,c,_ in nodes:
            value=float(reference[r,c]);bounds.append((value-ROAD_CUT_METRES,value+ROAD_FILL_METRES)
                          if (r,c) in node_vars else (value,value))
        values=[]
        for y0 in bounds[0]:
            for y1 in bounds[1]:
                for y2 in bounds[2]:
                    gradient=np.linalg.solve(matrix,np.array([y1-y0,y2-y0]))
                    values.append(float(gradient@delta))
        rise=max(0.,max(values));maximum=max(maximum,rise)
        details.append({'nodes':[[int(r),int(c)] for r,c,_ in nodes],
                        'condition':condition,'minimumDeltaYMetres':min(values),
                        'maximumDeltaYMetres':max(values)})
    return maximum,details


def _join_profile_rows(faces_xz,points,origin,axis,stations,basis,join_stations):
    """Legacy diagnostic point lookup; the joint fit carries edge provenance."""
    result=[]
    for point in np.asarray(points,float):
        matches=[]
        for face in np.asarray(faces_xz,float):
            try:
                matrix=(face[1:]-face[0]).T;uv=np.linalg.solve(matrix,point-face[0])
            except np.linalg.LinAlgError:
                continue
            if uv[0]>=-1e-10 and uv[1]>=-1e-10 and uv.sum()<=1.+1e-10:
                matches.append(_encoded_face_profile_rows(face,[point],origin,axis,stations,basis,
                                                           join_stations=join_stations)[0])
        if not matches:raise BP.ProfileError('actual encoded join point has no deck face basis')
        if max(np.max(np.abs(row-matches[0])) for row in matches)>1e-10:
            raise BP.ProfileError('actual encoded join point has inconsistent deck face bases')
        result.append(matches[0])
    return np.asarray(result)


def _join_profile_rows_from_provenance(faces_xz,provenance,origin,axis,stations,basis,
                                       join_stations):
    """Interpolate profile rows using the exact emitted edge that made each point."""
    result=[]
    for sample in provenance:
        candidates=[]
        for source in sample['sources']:
            face=np.asarray(faces_xz[int(source['faceIndex'])],float)
            vertex_station=_arch_vertex_stations(face,origin,axis,join_stations)
            vertex_rows=BP.interpolated_basis(vertex_station,stations,basis)
            weights=np.asarray(source['barycentricWeights'],float)
            candidates.append(weights@vertex_rows)
        if not candidates:raise BP.ProfileError('actual encoded join point has no carried deck face basis')
        if max(np.max(np.abs(row-candidates[0])) for row in candidates)>1e-10:
            raise BP.ProfileError('actual encoded join shared edge has inconsistent deck face bases')
        result.append(candidates[0])
    return np.asarray(result)


def _canonical_join_provenance(faces_xz,provenance):
    """Canonical exact-XZ face/edge geometry, independent of index order.

    The requested offset and separately carried encoded contact point identify
    the physical interpolation point.  Raw barycentric weights are deliberately
    excluded: reversing an edge can evaluate ``1 - (1 - r)`` instead of ``r``
    and change a redundant float64 bit without changing either geometry or the
    requested physical point.
    """
    faces_xz=np.asarray(faces_xz,float);result=[]
    for sample in provenance:
        sources=[]
        for source in sample['sources']:
            face=faces_xz[int(source['faceIndex'])]
            weights=np.asarray(source['barycentricWeights'],float)
            if weights.shape!=(3,) or not np.isfinite(weights).all():
                raise BP.ProfileError('join provenance has invalid barycentric weights')
            vertices=[(float(vertex[0]),float(vertex[1])) for vertex in face]
            edge_indices=np.asarray(source['edgeVertexIndices'],int)
            if (edge_indices.shape!=(2,) or np.any(edge_indices<0)
                    or np.any(edge_indices>=3) or edge_indices[0]==edge_indices[1]):
                raise BP.ProfileError('join provenance has invalid edge vertex indices')
            active=sorted(vertices[int(index)] for index in edge_indices)
            sources.append({'triangleXZ':sorted(vertices),
                            'activeEdgeXZ':active})
        sources.sort(key=lambda row:(row['triangleXZ'],row['activeEdgeXZ']))
        result.append({'wantedOffsetMetres':float(sample['wantedOffsetMetres']),
                       'sources':sources})
    return result


def _join_margin_v4(world,reference,node_vars,canonical,actual,axis):
    """A-priori construction margin; final geometry still checks 0.025 exactly."""
    records=[]
    for source,encoded in zip(np.asarray(canonical,float),np.asarray(actual,float)):
        terrain,triangles=_terrain_gradient_displacement_bound(
            world,reference,node_vars,source,encoded)
        displacement=encoded-source
        profile=SOLVE_GRADE*abs(float(displacement@axis))
        deck_y=_world_y_guard(world);terrain_y=_world_y_guard(world)
        scale=max(1.,abs(float(_terrain_interpolation(world,*source,reference)[0])))
        arithmetic=128*np.finfo(float).eps*scale
        total=terrain+profile+deck_y+terrain_y+arithmetic
        if not np.isfinite(total):raise BP.ProfileError('nonfinite outer-join encoding margin')
        records.append({'canonicalXZ':source.tolist(),'encodedXZ':encoded.tolist(),
                        'displacementMetres':displacement.tolist(),
                        'terrainGradientDisplacementMetres':terrain,
                        'profileStationDisplacementMetres':profile,
                        'deckYEncodingMetres':deck_y,'terrainYEncodingMetres':terrain_y,
                        'rowArithmeticMetres':arithmetic,'totalMetres':total,
                        'terrainTriangles':triangles})
    return max((row['totalMetres'] for row in records),default=0.),records


def _candidate_components(world,site,road,landing,profile,strict=False):
    left,_,axis,_,length=_site_frame(site)
    roads=_serving_roads(world,site,strict=strict)
    if not roads:raise BP.ProfileError('claimed bridge has no serving road')
    half=max(float(road['width']) for road in roads)
    geometry=_claimed_geometry_v7(world,site,landing,roads)
    guarded_roads=_guarded_serving_roads(roads,geometry)
    serving_world=SimpleNamespace(roads=guarded_roads,x0=world.x0,z0=world.z0,x1=world.x1,z1=world.z1)
    span=_selected_span_outline(roads,geometry,left,axis)
    # Labels are formed only from the site's serving roads.  A nearby unrelated
    # road cannot enlarge or join the claimed deck before the exact clip.
    cells=(_selected_span_cells(serving_world,site,geometry,span) if strict else
           site_span_cells(serving_world,site,road_footprint(serving_world),landing,conservative=True))
    labels,count=label(cells,structure=np.ones((3,3)))
    if strict and count!=1:
        raise BP.ProfileError(f'claimed bridge selected span raster has {count} disconnected components')
    meshes=[];components=[]
    for number,sl in enumerate(find_objects(labels),1):
        if sl is None:continue
        mask=labels[sl]==number;active=vertices_for_cells(mask)
        iz0,iz1=sl[0].start,sl[0].stop;ix0,ix1=sl[1].start,sl[1].stop
        gx,gz=np.meshgrid(world.x0+np.arange(ix0,ix1+1)*CELL,world.z0+np.arange(iz0,iz1+1)*CELL)
        distance=(gx-left[0])*axis[0]+(gz-left[1])*axis[1]
        deck=np.full_like(gx,-np.inf);deck[active]=profile.at(distance[active])
        component={'id':site['id']+1,'sites':[site['id']],'slice':sl,'cells':mask,'height':deck,
                   'arch':{'profile':profile,'origin':left,'axis':axis,'prepared':strict,
                           'joinStations':[geometry['constructionStart'],geometry['constructionEnd']]},
                   'outline':span,'geometry':geometry}
        mesh,_=deck_mesh(world,component)
        if len(mesh.indices):meshes.append(mesh);components.append(component)
    if not meshes:raise BP.ProfileError('claimed bridge emitted no floor')
    return meshes,components


def _float32_axis_error(xz,axis):
    xz=np.asarray(xz,float);ulp=np.abs(np.spacing(xz.astype(np.float32))).astype(float)
    return ulp@np.abs(axis)


def _emitted_join(faces,origin,axis,across,station):
    vertices=np.unique(np.asarray(faces,float).reshape(-1,3),axis=0);xz=vertices[:,[0,2]]
    on=np.abs((xz-origin)@axis-station)<=_float32_axis_error(xz,axis)
    intervals=[]
    for face in np.asarray(faces,float):
        face_xz=face[:,[0,2]];face_on=np.abs((face_xz-origin)@axis-station)<=_float32_axis_error(face_xz,axis)
        for i in range(3):
            j=(i+1)%3
            if face_on[i] and face_on[j]:intervals.append(((face_xz[[i,j]]-origin)@across).tolist())
    error=float(np.max(_float32_axis_error(xz,across),initial=0.))
    return vertices[on],_merge_intervals(intervals,epsilon=max(1e-8,2*error)),error


def _require_join_coverage(expected,actual,error,side,maximum_expansion=0.):
    if not expected:raise BP.ProfileError(f'{side} analytic serving-road join is empty')
    if len(expected)!=1:
        raise BP.ProfileError(f'{side} serving-road join is discontinuous across the nominal deck width')
    if len(expected)!=len(actual):
        raise BP.ProfileError(f'{side} join has {len(actual)} emitted intervals for {len(expected)} analytic road intervals')
    for wanted,found in zip(expected,actual):
        if found[0]>wanted[0]+error or found[1]<wanted[1]-error:
            raise BP.ProfileError(f'{side} join does not cover its analytic serving-road cross-section')
        if found[0]<wanted[0]-maximum_expansion or found[1]>wanted[1]+maximum_expansion:
            raise BP.ProfileError(f'{side} join escapes its derived encoded expansion guard')


def _cross2(a,b):
    return float(a[0]*b[1]-a[1]*b[0])


def _terrain_join_points(world,origin,axis,across,station,intervals):
    """Every endpoint where the join crosses a 2m terrain triangle edge."""
    base=np.asarray(origin,float)+np.asarray(axis,float)*station
    offsets=[value for interval in intervals for value in interval]
    endpoints=np.array([base+across*value for value in offsets])
    low=np.floor((endpoints.min(axis=0)-[world.x0,world.z0])/TERRAIN_CELL).astype(int)-1
    high=np.ceil((endpoints.max(axis=0)-[world.x0,world.z0])/TERRAIN_CELL).astype(int)+1
    bounds=(max(0,low[0]),min(world.height.shape[1]-1,high[0]),
            max(0,low[1]),min(world.height.shape[0]-1,high[1]))
    scale=max(1.,float(np.max(np.abs(endpoints))));epsilon=128*np.finfo(float).eps*scale
    for _,triangle in _terrain_triangles(world,bounds):
        xz=triangle[:,[0,2]]
        for a,b in zip(xz,np.roll(xz,-1,axis=0)):
            edge=b-a;denominator=_cross2(across,edge);delta=a-base
            if abs(denominator)>epsilon:
                offset=_cross2(delta,edge)/denominator;along=_cross2(delta,across)/denominator
                if -epsilon<=along<=1+epsilon and any(lo-epsilon<=offset<=hi+epsilon for lo,hi in intervals):
                    offsets.append(float(offset))
            elif abs(_cross2(delta,across))<=epsilon:
                for point in (a,b):
                    offset=float((point-base)@across)
                    if any(lo-epsilon<=offset<=hi+epsilon for lo,hi in intervals):offsets.append(offset)
    offsets.sort();unique=[]
    for value in offsets:
        if not unique or abs(value-unique[-1])>epsilon:unique.append(value)
    return np.array([base+across*value for value in unique]),np.asarray(unique)


def _emitted_join_heights(faces,origin,axis,across,station,offsets,*,return_provenance=False):
    """Interpolate Y from actual float32 edges lying on one exact join plane."""
    segments=[];all_xz=np.asarray(faces,float)[:,:,[0,2]].reshape(-1,2)
    station_error=float(np.max(_float32_axis_error(all_xz,axis),initial=0.))
    cross_error=float(np.max(_float32_axis_error(all_xz,across),initial=0.))
    for face_index,face in enumerate(np.asarray(faces,float)):
        xz=face[:,[0,2]];on=np.abs((xz-origin)@axis-station)<=_float32_axis_error(xz,axis)
        for i in range(3):
            j=(i+1)%3
            if on[i] and on[j]:
                offset=(xz[[i,j]]-origin)@across
                segments.append((float(offset[0]),float(offset[1]),float(face[i,1]),float(face[j,1]),
                                 xz[i],xz[j],face_index,i,j))
    result=[];actual_points=[];provenance=[]
    for wanted in offsets:
        values=[];points=[];sources=[]
        for low,high,y0,y1,xz0,xz1,face_index,i,j in segments:
            if min(low,high)-2*cross_error<=wanted<=max(low,high)+2*cross_error:
                ratio=np.clip((wanted-low)/(high-low) if high!=low else 0.,0.,1.)
                values.append(y0+ratio*(y1-y0))
                points.append(xz0+ratio*(xz1-xz0))
                weights=np.zeros(3);weights[i]=1.-ratio;weights[j]=ratio
                sources.append({'faceIndex':int(face_index),'edgeVertexIndices':[int(i),int(j)],
                                'edgeRatio':float(ratio),'barycentricWeights':weights.tolist(),
                                'actualXZ':points[-1].tolist()})
        if not values:raise BP.ProfileError('actual encoded join has no floor at a terrain breakline')
        y_error=max((abs(np.spacing(np.float32(value))) for value in values),default=0.)
        if max(values)-min(values)>2*y_error:
            raise BP.ProfileError('actual encoded join has inconsistent heights on a shared edge')
        result.append(values[0]);actual_points.append(points[0])
        provenance.append({'wantedOffsetMetres':float(wanted),'chosenSource':0,'sources':sources})
    basic=(np.asarray(result),np.asarray(actual_points),station_error,cross_error)
    return basic+(provenance,) if return_provenance else basic


def _triangle_height(triangle,xz):
    """Height on one non-vertical emitted or terrain triangle."""
    triangle=np.asarray(triangle,float);xz=np.asarray(xz,float)
    matrix=(triangle[1:,[0,2]]-triangle[0,[0,2]]).T
    weight=np.linalg.solve(matrix,xz-triangle[0,[0,2]])
    return float(triangle[0,1]+weight@(triangle[1:,1]-triangle[0,1]))


def _encoded_face_profile_rows(face_xz,points,origin,axis,stations,basis,join_stations=()):
    """Profile coefficients on the actual encoded triangle plane.

    ``deck_mesh`` encodes XZ first, evaluates the shared PL profile at those
    three vertices, then emits their triangle.  Interpolate those same three
    coefficient rows here; re-evaluating the 1D profile at an interior XZ can
    disagree where float32 moves a station-cut vertex across a profile kink.
    """
    face=np.asarray(face_xz,float);points=np.atleast_2d(np.asarray(points,float))
    vertex_station=_arch_vertex_stations(face,origin,axis,join_stations)
    vertex_rows=BP.interpolated_basis(vertex_station,stations,basis)
    matrix=(face[1:]-face[0]).T
    uv=np.linalg.solve(matrix,(points-face[0]).T).T
    barycentric=np.c_[1.-uv.sum(axis=1),uv]
    return barycentric@vertex_rows


def _face_overlays(world,face):
    """Clip an actual encoded deck face by every underlying 2m terrain face."""
    xz=np.asarray(face,float)[:,[0,2]]
    lo=np.floor((xz.min(axis=0)-[world.x0,world.z0])/TERRAIN_CELL).astype(int)
    hi=np.ceil((xz.max(axis=0)-[world.x0,world.z0])/TERRAIN_CELL).astype(int)
    bounds=(max(0,lo[0]),min(world.height.shape[1]-1,hi[0]),
            max(0,lo[1]),min(world.height.shape[0]-1,hi[1]))
    subject=np.c_[xz[:,0],np.zeros(3),xz[:,1]]
    for nodes,terrain_triangle in _terrain_triangles(world,bounds):
        polygon=subject
        for a,b in zip(terrain_triangle,np.roll(terrain_triangle,-1,axis=0)):
            polygon=_clip_halfplane(polygon,a[[0,2]],b[[0,2]])
            if not len(polygon):break
        if len(polygon):yield nodes,terrain_triangle,polygon[:,[0,2]]


def _site_local_bounds(world,site,landing):
    """Terrain-cell envelope for one complete deck, joins, and incident ring."""
    left,_,axis,across,length=_site_frame(site);roads=_serving_roads(world,site,strict=True)
    geometry=_claimed_geometry_v7(world,site,landing,roads);ring=TERRAIN_CELL*math.sqrt(2.)
    corners=np.array([left+axis*s+across*t
        for s in (geometry['constructionStart']-ring,geometry['constructionEnd']+ring)
        for t in (-geometry['constructionHalf']-ring,geometry['constructionHalf']+ring)])
    low=np.floor((corners.min(axis=0)-[world.x0,world.z0])/TERRAIN_CELL).astype(int)-1
    high=np.ceil((corners.max(axis=0)-[world.x0,world.z0])/TERRAIN_CELL).astype(int)+1
    return (max(0,low[0]),min(world.height.shape[1]-1,high[0]),
            max(0,low[1]),min(world.height.shape[0]-1,high[1]))


def _encoded_water_authority(world,bounds):
    """Actual terrain_export float32 water faces for a bounded cell envelope."""
    from terrain_export import clipped_water_surface
    nz,nx=world.height.shape;ix0,ix1,iz0,iz1=bounds
    row,col=np.indices((iz1-iz0,ix1-ix0));a=((row+iz0)*nx+col+ix0).ravel()
    cells=np.stack((a,a+nx,a+1,a+1,a+nx,a+nx+1),axis=1)
    positions=np.c_[world.gx.ravel(),world.height.ravel(),world.gz.ravel()]
    mesh=clipped_water_surface(world,positions,cells)
    local_source=np.asarray(mesh['sourceCells'],int)
    width=ix1-ix0
    source=(iz0+local_source//width)*(nx-1)+ix0+local_source%width
    faces=mesh['positions'][mesh['triangles']]
    wet=np.asarray(world.water['mask'],bool)[iz0:iz1+1,ix0:ix1+1]
    surface=np.asarray(world.water['surface'],float)[iz0:iz1+1,ix0:ix1+1]
    return {'faces':faces,'sourceCells':source.astype(np.int32),
            'sourceWetMask':wet.copy(),'sourceWetSurface':surface[wet].copy(),
            'bounds':list(map(int,bounds))}


def _same_water_authority(before,after):
    """Require identical source wet geometry and actual emitted float32 water."""
    keys=('sourceCells','sourceWetMask','sourceWetSurface','faces')
    equal={key:np.array_equal(np.asarray(before[key]),np.asarray(after[key])) for key in keys}
    return all(equal.values()),equal


def _water_face_bins(faces,size=8.):
    bins={}
    for index,face in enumerate(faces):
        low=np.floor(face[:,[0,2]].min(axis=0)/size).astype(int)
        high=np.floor(face[:,[0,2]].max(axis=0)/size).astype(int)
        for ix in range(low[0],high[0]+1):
            for iz in range(low[1],high[1]+1):bins.setdefault((ix,iz),[]).append(index)
    return bins


def _convex_xz_overlap(subject,clip):
    """Clip one XYZ triangle to another triangle's exact XZ half-planes."""
    polygon=np.asarray(subject,float);clip=np.asarray(clip,float)
    inside=_area_xz(clip)>0.
    for a,b in zip(clip,np.roll(clip,-1,axis=0)):
        polygon=_clip_halfplane(polygon,a[[0,2]],b[[0,2]],inside)
        if not len(polygon):break
    return polygon


def _continuous_emitted_water_check(faces,water_faces,clearance):
    """Exact affine clearance on every positive actual-F32 overlap polygon."""
    bins=_water_face_bins(water_faces);minimum=np.inf;pieces=0;area=0.
    for face in np.asarray(faces,float):
        low=np.floor(face[:,[0,2]].min(axis=0)/8.).astype(int)
        high=np.floor(face[:,[0,2]].max(axis=0)/8.).astype(int)
        candidates=sorted({index for ix in range(low[0],high[0]+1)
                            for iz in range(low[1],high[1]+1) for index in bins.get((ix,iz),())})
        for index in candidates:
            water=water_faces[index];polygon=_convex_xz_overlap(face,water)
            if not len(polygon):continue
            overlap=abs(_area_xz(polygon))
            if overlap<=0.:continue
            water_y=np.array([_triangle_height(water,point[[0,2]]) for point in polygon])
            gap=polygon[:,1]-water_y
            if np.any(gap<float(clearance)):
                raise BP.ProfileError('actual encoded deck misses continuous water clearance')
            minimum=min(minimum,float(gap.min()));pieces+=1;area+=overlap
    return {'positiveOverlapPieces':pieces,'overlapAreaSquareMetres':area,
            'minimumClearanceMetres':None if not np.isfinite(minimum) else minimum,
            'authority':'actual float32 emitted deck and terrain_export water triangles; affine extrema at overlap vertices'}


def _join_misses_water(world,site,faces,water_faces,geometry):
    left,_,axis,across,_=_site_frame(site);report={}
    for side,station in zip(('left','right'),(geometry['constructionStart'],geometry['constructionEnd'])):
        expected=_contract_join_intervals(world,site,station,geometry);base=left+axis*station;wet=[]
        for face in water_faces:
            interval=_polygon_line_interval(face[:,[0,2]],base,across)
            if interval is None:continue
            for low,high in expected:
                overlap=[max(low,interval[0]),min(high,interval[1])]
                if overlap[1]>overlap[0]:wet.append(overlap)
        if wet:raise BP.ProfileError(f'{side} full-width join intersects final encoded water union')
        report[side]={'requiredIntervals':expected,'wetIntersectionIntervals':[]}
    return report


def _encoded_grade(triangle):
    triangle=np.asarray(triangle,float)
    normal=np.cross(triangle[1]-triangle[0],triangle[2]-triangle[0])
    if normal[1]<=0:raise BP.ProfileError('encoded bridge/approach triangle has invalid winding')
    return float(np.hypot(normal[0],normal[2])/normal[1])


def _world_y_guard(world):
    """One float32 Y ulp over every permitted bridge earthwork elevation."""
    if hasattr(world,'claimed_bridge_y_guard'):return float(world.claimed_bridge_y_guard)
    magnitude=float(np.max(np.abs(world.height),initial=1.))+max(ROAD_CUT_METRES,ROAD_FILL_METRES)+1.
    return float(abs(np.spacing(np.float32(magnitude))))


def _claimed_ground_support_offset(world, *, outer_join):
    """Required deck height above final terrain for a claimed named arch.

    The authored 25 mm contact fit applies at both complete full-width outer
    joins.  Inside that named deck, the physical requirement is terrain
    nonpenetration; one world-scale float32 Y guard keeps the encoded result on
    the safe side without turning the contact fit into a universal lift.
    """
    return _world_y_guard(world)+(BP.DRY_CLEARANCE_METRES if outer_join else 0.)


def _face_samples(face,spacing=.25):
    """Bounded water-field samples on an actual encoded face."""
    face=np.asarray(face,float);length=max(np.linalg.norm(face[1,[0,2]]-face[0,[0,2]]),
                                          np.linalg.norm(face[2,[0,2]]-face[0,[0,2]]),
                                          np.linalg.norm(face[2,[0,2]]-face[1,[0,2]]))
    count=max(1,int(math.ceil(length/spacing)));points=[]
    for i in range(count+1):
        for j in range(count+1-i):
            points.append(((count-i-j)*face[0]+i*face[1]+j*face[2])/count)
    return np.asarray(points)


def _deck_clears_object_above(face,polygon,low,high):
    """True only for an object wholly below the deck fascia and actor floor."""
    if face is None:return False
    square=np.array([[low[0],0,low[2]],[high[0],0,low[2]],
                     [high[0],0,high[2]],[low[0],0,high[2]]],float)
    clipped=polygon
    for a,b in zip(square,np.roll(square,-1,axis=0)):
        clipped=_clip_halfplane(clipped,a[[0,2]],b[[0,2]])
        if not len(clipped):return True
    if abs(_area_xz(clipped))<=NEGLIGIBLE_FLOOR_AREA:return True
    floor=min(_triangle_height(face,point[[0,2]]) for point in clipped)
    fascia_bottom=floor-DECK_FASCIA_DEPTH_METRES
    actor_bottom=floor+CE.ACTOR_FLOOR_CLEARANCE
    actor_top=floor+CE.ACTOR_HEIGHT
    return float(high[1])<min(fascia_bottom,actor_bottom,actor_top)


def _solid_overlap(world,polygon,released_margin_nodes=(),face=None):
    """Exact XZ area shared by a deck polygon and nearest-node solid cells."""
    polygon=np.asarray(polygon,float)
    released_margin_nodes={tuple(node) for node in released_margin_nodes}
    low=np.floor((polygon[:,[0,2]].min(axis=0)-[world.x0,world.z0])/TERRAIN_CELL-.5).astype(int)
    high=np.ceil((polygon[:,[0,2]].max(axis=0)-[world.x0,world.z0])/TERRAIN_CELL+.5).astype(int)
    for iz in range(max(0,low[1]),min(world.solids.shape[0]-1,high[1])+1):
        for ix in range(max(0,low[0]),min(world.solids.shape[1]-1,high[0])+1):
            if not world.solids[iz,ix] or (iz,ix) in released_margin_nodes:continue
            x=world.x0+ix*TERRAIN_CELL;z=world.z0+iz*TERRAIN_CELL;half=TERRAIN_CELL*.5
            square=np.array([[x-half,0,z-half],[x+half,0,z-half],
                             [x+half,0,z+half],[x-half,0,z+half]],float)
            clipped=polygon
            for a,b in zip(square,np.roll(square,-1,axis=0)):
                clipped=_clip_halfplane(clipped,a[[0,2]],b[[0,2]])
                if not len(clipped):break
            if len(clipped) and abs(_area_xz(clipped))>NEGLIGIBLE_FLOOR_AREA:
                sources=getattr(world,'claimed_bridge_solid_clearance_sources',{}).get((iz,ix))
                if sources is None or any(not _deck_clears_object_above(face,polygon,low,high)
                                          for _,low,high in sources):return True
    objects=getattr(world,'claimed_bridge_colliding_objects',None)
    if objects is None:
        objects=[(None,np.r_[low[0],-np.inf,low[1]],np.r_[high[0],np.inf,high[1]])
                 for low,high in getattr(world,'claimed_bridge_colliding_boxes',())]
    for _,low,high in objects:
        square=np.array([[low[0],0,low[2]],[high[0],0,low[2]],
                         [high[0],0,high[2]],[low[0],0,high[2]]],float)
        clipped=polygon
        for a,b in zip(square,np.roll(square,-1,axis=0)):
            clipped=_clip_halfplane(clipped,a[[0,2]],b[[0,2]])
            if not len(clipped):break
        if (len(clipped) and abs(_area_xz(clipped))>NEGLIGIBLE_FLOOR_AREA
                and not _deck_clears_object_above(face,polygon,low,high)):return True
    return False


def _retained_footprints(content):
    """Current placed content footprints whose ground support is immutable."""
    support=[];colliding=[]
    if content is None:return support,colliding
    for item in getattr(content,'objects',()):
        if 'low' not in item or 'high' not in item:continue
        low=np.asarray(item['low'],float)[[0,2]];high=np.asarray(item['high'],float)[[0,2]]
        if np.any(high<=low):continue
        if item.get('collides') and not item.get('walk'):
            colliding.append((low.copy(),high.copy()))
        if item.get('collides') or item.get('assembly') or item.get('attachment'):
            support.append({'kind':'box','low':low.copy(),'high':high.copy(),'source':'placed-object'})
    # Assembly foundations use their authored footprint rectangles, which can
    # extend 1.5 m beyond member bounds or form the Four Gates civic terrace.
    # Reconstruct them from the same final placed records and refuse a count
    # mismatch rather than silently protecting only object roots.
    by_assembly={}
    for item in getattr(content,'objects',()):
        if item.get('assembly'):by_assembly.setdefault(item['assembly'],[]).append(item)
    for identity,record in getattr(content,'assembly_records',{}).items():
        footprints=[]
        if identity=='four_gates.civic':
            shift=np.asarray(record['translation'],float)[[0,2]]
            for z in range(-112,112,8):
                half=math.sqrt(max(0,112**2-(z+4)**2))
                footprints.append((np.array([-half,z],float)+shift,
                                   np.array([half,z+8],float)+shift))
        for item in by_assembly.get(identity,()):
            placement=item.get('source',{});region=item.get('region','')
            placements=getattr(content,'metadata',{}).get(region,{}).get('placements',())
            companion=A.companions(region,placements).get(placement.get('node')) if placements else None
            camp=(identity=='amberwood.ridge-camp' and placement.get('node','').startswith(
                ('Prop_Tent_ridge_camp_','Brazier_ridge_camp_')))
            natural_companion=companion is not None and companion.get('node')!=placement.get('node')
            site=identity in A.SITE_PULL
            if ((A.supports_ground(placement) or camp or natural_companion
                 or (site and A.site_supports_ground(placement))) and identity not in A.D.REFERENCES):
                footprints.append((np.asarray(item['low'],float)[[0,2]]-1.5,
                                   np.asarray(item['high'],float)[[0,2]]+1.5))
        expected=int(record.get('foundationFootprints',0))
        if len(footprints)!=expected:
            raise BP.ProfileError(f'{identity}: reconstructed {len(footprints)} of {expected} assembly support footprints')
        support.extend({'kind':'box','low':low,'high':high,'source':'assembly-footprint'}
                       for low,high in footprints)
    # A separately authored retained footing is a circle about the final
    # placement pivot. It can exist without collision/assembly flags.
    for region,entries in getattr(getattr(content,'world',None),'plan',{}).get('retained_footings',{}).items():
        for entry in entries:
            radius=float(entry.get('radius',0.))
            item=getattr(content,'placement_by_name',{}).get((region,entry.get('node')))
            if radius<=0. or item is None:continue
            center=(np.asarray(item['sourcePivot'],float)+np.asarray(item['shift'],float))[[0,2]]
            support.append({'kind':'circle','center':center,'radius':radius,'source':'retained-footing'})
    return support,colliding


def _crop_footprints(world,boxes,bounds_rows):
    """Discard retained boxes outside all bounded site influence envelopes."""
    envelopes=[]
    for ix0,ix1,iz0,iz1 in bounds_rows:
        envelopes.append((np.array([world.x0+ix0*TERRAIN_CELL,world.z0+iz0*TERRAIN_CELL]),
                          np.array([world.x0+ix1*TERRAIN_CELL,world.z0+iz1*TERRAIN_CELL])))
    result=[]
    for footprint in boxes:
        if isinstance(footprint,dict):
            if footprint['kind']=='circle':
                low=footprint['center']-footprint['radius'];high=footprint['center']+footprint['radius']
            else:low,high=footprint['low'],footprint['high']
        else:low,high=footprint
        if any(np.all(high>floor) and np.all(low<ceiling) for floor,ceiling in envelopes):result.append(footprint)
    return result


def _site8_known_solid_margin_nodes(world,content):
    """Exact source-owned raster-margin nodes approved for site 8 only."""
    if content is None or not hasattr(world,'solid_ids'):return set()
    objects=[]
    for item in getattr(content,'objects',()):
        if not item.get('collides') or item.get('walk') or content_walk_through(item.get('node','')):continue
        name=item.get('node')
        low=np.asarray(item.get('low',()),float);high=np.asarray(item.get('high',()),float)
        if low.shape!=(3,) or high.shape!=(3,):continue
        size=high[[0,2]]-low[[0,2]]
        if (not np.all(np.isfinite(size)) or np.any(size<0.)
                or float(size.prod())>SOLID_MAXIMUM_AREA_SQUARE_METRES):continue
        if name in SITE8_SOLID_SOURCE_BOUNDS:
            expected=np.asarray(SITE8_SOLID_SOURCE_BOUNDS[name],float)
            if (item.get('region')!='mirrorhold'
                    or not np.array_equal(np.stack((low[[0,2]],high[[0,2]])),expected)):return set()
        objects.append((name,low[[0,2]],high[[0,2]]))
    if [item[0] for item in objects if item[0] in SITE8_SOLID_SOURCE_BOUNDS].count('Prop_PierCrate_0')!=1:return set()
    if [item[0] for item in objects if item[0] in SITE8_SOLID_SOURCE_BOUNDS].count('Prop_PierSkiff_0')!=1:return set()
    offset=np.asarray(world.regions['amberwood']['center'],float)-[510.,540.]
    landing=np.array([510.,541.5])+offset;foot=np.array([503.,557.])+offset
    direction=(landing-foot)/np.linalg.norm(landing-foot);far=landing-direction*45.
    precontent=[(np.minimum(landing,far)-2.6,np.maximum(landing,far)+2.6),
                (np.minimum([484.,472.],[505.,472.])+offset-4.4,
                 np.maximum([484.,472.],[505.,472.])+offset+4.4)]
    approved=set()
    for node,(solid_id,expected_names) in SITE8_SOLID_MARGIN_RELEASE.items():
        iz,ix=node
        if not bool(world.solids[node]) or int(world.solid_ids[node])!=solid_id:continue
        contributors=[];precontent_hit=False
        for name,low,high in objects:
            lo=low-SOLID_MARGIN_METRES;hi=high+SOLID_MARGIN_METRES
            ix0=max(0,int((lo[0]-world.x0)/TERRAIN_CELL))
            ix1=min(len(world.x),int((hi[0]-world.x0)/TERRAIN_CELL)+2)
            iz0=max(0,int((lo[1]-world.z0)/TERRAIN_CELL))
            iz1=min(len(world.z),int((hi[1]-world.z0)/TERRAIN_CELL)+2)
            if iz0<=iz<iz1 and ix0<=ix<ix1:contributors.append(name)
        for low,high in precontent:
            lo=low-SOLID_MARGIN_METRES;hi=high+SOLID_MARGIN_METRES
            ix0=max(0,int((lo[0]-world.x0)/TERRAIN_CELL));ix1=min(len(world.x),int((hi[0]-world.x0)/TERRAIN_CELL)+2)
            iz0=max(0,int((lo[1]-world.z0)/TERRAIN_CELL));iz1=min(len(world.z),int((hi[1]-world.z0)/TERRAIN_CELL)+2)
            precontent_hit|=iz0<=iz<iz1 and ix0<=ix<ix1
        if not precontent_hit and tuple(contributors)==expected_names:approved.add(node)
    return approved


def _site8_solid_clearance_sources(world,content):
    """Known complete contributors for site-8 solid cells eligible for 3-D clearance."""
    if content is None or not hasattr(world,'solid_ids'):return {}
    objects=[]
    for item in getattr(content,'objects',()):
        if not item.get('collides') or item.get('walk') or content_walk_through(item.get('node','')):continue
        low=np.asarray(item.get('low',()),float);high=np.asarray(item.get('high',()),float)
        if low.shape!=(3,) or high.shape!=(3,):continue
        size=high[[0,2]]-low[[0,2]]
        if (not np.all(np.isfinite(size)) or np.any(size<0.)
                or float(size.prod())>SOLID_MAXIMUM_AREA_SQUARE_METRES):continue
        name=item.get('node');expected=SITE8_SOLID_SOURCE_BOUNDS.get(name)
        if expected is not None and not np.array_equal(
                np.stack((low[[0,2]],high[[0,2]])),np.asarray(expected,float)):return {}
        objects.append((name,low,high))
    expected_names=set(SITE8_SOLID_SOURCE_BOUNDS)
    if any(sum(name==expected for name,_,_ in objects)!=1 for expected in expected_names):return {}
    offset=np.asarray(world.regions['amberwood']['center'],float)-[510.,540.]
    landing=np.array([510.,541.5])+offset;foot=np.array([503.,557.])+offset
    direction=(landing-foot)/np.linalg.norm(landing-foot);far=landing-direction*45.
    precontent=[(np.minimum(landing,far)-2.6,np.maximum(landing,far)+2.6),
                (np.minimum([484.,472.],[505.,472.])+offset-4.4,
                 np.maximum([484.,472.],[505.,472.])+offset+4.4)]
    result={}
    candidate_nodes=set()
    raster=[]
    for name,low,high in objects:
        lo=low[[0,2]]-SOLID_MARGIN_METRES;hi=high[[0,2]]+SOLID_MARGIN_METRES
        ix0=max(0,int((lo[0]-world.x0)/TERRAIN_CELL));ix1=min(len(world.x),int((hi[0]-world.x0)/TERRAIN_CELL)+2)
        iz0=max(0,int((lo[1]-world.z0)/TERRAIN_CELL));iz1=min(len(world.z),int((hi[1]-world.z0)/TERRAIN_CELL)+2)
        nodes={(iz,ix) for iz in range(iz0,iz1) for ix in range(ix0,ix1)}
        raster.append((name,low,high,nodes))
        if name in expected_names:candidate_nodes.update(nodes)
    for node in candidate_nodes:
        contributors=[(name,low,high) for name,low,high,nodes in raster if node in nodes]
        if (not bool(world.solids[node]) or int(world.solid_ids[node])!=552
                or not contributors or any(name not in expected_names for name,_,_ in contributors)):continue
        precontent_hit=False
        for low,high in precontent:
            lo=low-SOLID_MARGIN_METRES;hi=high+SOLID_MARGIN_METRES
            ix0=max(0,int((lo[0]-world.x0)/TERRAIN_CELL));ix1=min(len(world.x),int((hi[0]-world.x0)/TERRAIN_CELL)+2)
            iz0=max(0,int((lo[1]-world.z0)/TERRAIN_CELL));iz1=min(len(world.z),int((hi[1]-world.z0)/TERRAIN_CELL)+2)
            precontent_hit|=iz0<=node[0]<iz1 and ix0<=node[1]<ix1
        if precontent_hit:continue
        result[node]=tuple(contributors)
    return result


def _site_solid_margin_release_nodes(world,site,support_boxes,water_nodes,reference):
    """Revalidate complete incident terrain before releasing known margin pins."""
    # Crossing ids are assigned from the current candidate inventory and can
    # shift when an unrelated upstream candidate is added or removed.  The
    # reviewed exception belongs to this authored reach, not to an ordinal.
    if site.get('key')!=MIRROR_OUTLET_SOLID_RELEASE_KEY:return set()
    candidates=set(getattr(world,'claimed_bridge_solid_margin_source_nodes',()))
    released=set()
    for node in candidates:
        iz,ix=node
        incident=[triangle for nodes,triangle in _terrain_triangles(
            world,(ix-1,ix+1,iz-1,iz+1)) if node in nodes]
        x=world.x0+ix*TERRAIN_CELL;z=world.z0+iz*TERRAIN_CELL
        wet=bool(np.asarray(L.water_fields(np.array([x]),np.array([z]),
            height=np.array([reference[node]]),plan=world.plan)['mask'])[0])
        if (len(incident)==6 and node not in water_nodes and not wet
                and not any(_footprint_intersects_triangle(footprint,triangle)
                            for triangle in incident for footprint in support_boxes)):
            released.add(node)
    return released


def _rectangle_intersects_triangle(low,high,triangle):
    square=np.array([[low[0],0,low[1]],[high[0],0,low[1]],
                     [high[0],0,high[1]],[low[0],0,high[1]]],float)
    clipped=np.asarray(triangle,float)
    for a,b in zip(square,np.roll(square,-1,axis=0)):
        clipped=_clip_halfplane(clipped,a[[0,2]],b[[0,2]])
        if not len(clipped):return False
    return abs(_area_xz(clipped))>0.


def _footprint_intersects_triangle(footprint,triangle):
    if not isinstance(footprint,dict):return _rectangle_intersects_triangle(*footprint,triangle)
    if footprint['kind']=='box':
        return _rectangle_intersects_triangle(footprint['low'],footprint['high'],triangle)
    center=np.asarray(footprint['center'],float);radius=float(footprint['radius'])
    xz=np.asarray(triangle,float)[:,[0,2]]
    signs=np.array([_cross2(b-a,center-a) for a,b in zip(xz,np.roll(xz,-1,axis=0))])
    if np.all(signs>=0.) or np.all(signs<=0.):return True
    radius2=radius*radius
    if np.any(np.sum((xz-center)**2,axis=1)<radius2):return True
    for a,b in zip(xz,np.roll(xz,-1,axis=0)):
        edge=b-a;ratio=np.clip(np.dot(center-a,edge)/np.dot(edge,edge),0.,1.)
        if np.dot(a+ratio*edge-center,a+ratio*edge-center)<radius2:return True
    return False


def _site_terrain_selection(world,site,landing):
    """Independent geometric stencil and its complete incident triangles."""
    left,_,axis,_,_=_site_frame(site);roads=_serving_roads(world,site,strict=True)
    geometry=_claimed_geometry_v7(world,site,landing,roads)
    half=float(geometry['nominalHalf']);ring=TERRAIN_CELL*math.sqrt(2.)
    span=_selected_span_outline(roads,geometry,left,axis)
    actor_center=_actor_center_outline(roads,geometry)
    side_approach,_=_side_junction_geometry(roads,geometry,left,axis)
    approach=[SpanOutline(actor_center,left,axis,geometry['constructionStart']-ring,
                          geometry['constructionStart']),
              SpanOutline(actor_center,left,axis,geometry['constructionEnd'],
                          geometry['constructionEnd']+ring)]
    if side_approach is not None:approach.append(side_approach)
    approach=tuple(approach)
    geometry['actorHalfWidthMetres']=ACTOR_HALF_WIDTH_METRES
    geometry['sideJunctionApproachAreaSquareMetres']=(
        0. if side_approach is None else float(side_approach.geometry.area))
    bounds=_site_local_bounds(world,site,landing)
    terrain=list(_terrain_triangles(world,bounds))
    deck=[item for item in terrain if _clip_area(span,item[1])>0.]
    approaches=[item for item in terrain if any(_clip_area(part,item[1])>0. for part in approach)]
    nodes={node for item in deck+approaches for node in item[0]}
    return geometry,span,approach,terrain,deck,approaches,nodes,bounds


def declared_site_stencil(world,site_id):
    """Pre-fit node authority used by runners to prove no outside change."""
    landing,_,_=deck_policy(world)
    matches=[site for site in getattr(world,'crossing_sites',()) if site['id']==site_id]
    if len(matches)!=1:raise BP.ProfileError(f'claimed bridge {site_id} is absent or ambiguous')
    *_,nodes,bounds=_site_terrain_selection(world,matches[0],landing)
    return {'site':site_id,'nodes':sorted(nodes),'bounds':list(map(int,bounds))}


def _nominal_floor_certificate_inputs(world,site,faces,geometry):
    """Production exact-set certificate plus numeric join diagnostics."""
    left,_,axis,across,_=_site_frame(site);faces=np.asarray(faces,float)
    station=(faces[:,:,[0,2]].reshape(-1,2)-left)@axis
    inside_cap=bool(station.min()>=geometry['policyStart'] and
                    station.max()<=geometry['policyEnd'])
    joins={}
    for side,value in zip(('left','right'),(geometry['nominalStart'],geometry['nominalEnd'])):
        base=left+axis*value
        arithmetic_bound=_line_interval_arithmetic_bound(faces[:,:,[0,2]],base,across)
        intervals=_merge_intervals([interval for face in faces
                                    if (interval:=_polygon_line_interval(face[:,[0,2]],base,across)) is not None],
                                   epsilon=arithmetic_bound)
        required=_contract_join_intervals(world,site,value,geometry)
        complete=(len(required)==1 and any(found[0]<=required[0][0] and found[1]>=required[0][1]
                                           for found in intervals))
        joins[side]={'stationMetres':value,'requiredIntervals':required,
                     'actualIntervals':intervals,'intervalArithmeticBoundMetres':arithmetic_bound,
                     'complete':complete}
    if not inside_cap:raise BP.ProfileError('actual encoded named deck escaped the six-metre landing cap')
    if not all(row['complete'] for row in joins.values()):
        raise BP.ProfileError(f'actual encoded deck misses a nominal join segment: {joins}')
    spatial=_prepared_floor_set_certificate(world,site,faces,geometry)
    return {'actualEncodedFaces':faces.tolist(),'geometry':geometry,
            'actualStationRangeMetres':[float(station.min()),float(station.max())],
            'insideSixMetrePolicyCap':inside_cap,'joinSegments':joins,
            'spatialSetCertificate':spatial}


def _validate_join_postcheck_gaps(physical_gaps,lift_limit,identity_residuals,
                                   identity_bounds,side):
    """Keep physical full-width limits separate from carried-row arithmetic."""
    physical_gaps=np.asarray(physical_gaps,float)
    identity_residuals=np.asarray(identity_residuals,float)
    identity_bounds=np.asarray(identity_bounds,float)
    if (not np.isfinite(lift_limit) or not np.isfinite(physical_gaps).all()
            or not np.isfinite(identity_residuals).all()
            or not np.isfinite(identity_bounds).all()):
        raise BP.ProfileError(f'{side} join postcheck contains a nonfinite value')
    if (not len(physical_gaps) or np.any(physical_gaps<BP.DRY_CLEARANCE_METRES)
            or np.any(physical_gaps>lift_limit)):
        raise BP.ProfileError(f'{side} actual encoded join escapes physical ground-gap bounds')
    if (identity_residuals.shape!=identity_bounds.shape or not len(identity_residuals)
            or np.any(identity_residuals>identity_bounds)):
        raise BP.ProfileError(f'{side} carried join contact row failed encoded constraint')


def _bridge_progress(world,phase,**details):
    callback=getattr(world,'claimed_bridge_progress',None)
    if callback is not None:callback(phase,**details)


def _fit_postcheck(world,site,road,landing,lift_limit,clearance,profile,deltas,
                   released_margin_nodes=()):
    """Check the actual float32 deck and affected emitted terrain after joint fit."""
    left,_,axis,across,length=_site_frame(site)
    meshes,_=_candidate_components(world,site,road,landing,profile,strict=True)
    faces=np.concatenate([mesh.positions[mesh.indices.reshape(-1,3)] for mesh in meshes])
    _bridge_progress(world,'postcheck-mesh-built',site=int(site['id']),faces=len(faces))
    encoded_height=np.asarray(world.height,np.float32).astype(float)
    deck_grades=np.array([_encoded_grade(face) for face in faces])
    if np.any(deck_grades>GRADE):
        raise BP.ProfileError('actual encoded claimed deck exceeds the .65 grade limit')

    contract=getattr(world,'claimed_bridge_v7_contracts',{}).get(site['id'])
    if contract is None:raise BP.ProfileError('missing representation-v7 join contract')
    geometry=contract['geometry'];half=float(geometry['nominalHalf']);join_report={}
    for side,station in zip(('left','right'),
                            (geometry['constructionStart'],geometry['constructionEnd'])):
        vertices,actual,xz_error=_emitted_join(faces,left,axis,across,station)
        expected=_contract_join_intervals(world,site,station,geometry)
        raw=_contract_join_intervals(world,site,station,geometry,clip_to_nominal=False)
        excluded=_excluded_join_intervals(raw,half)
        maximum_expansion=max(float(geometry['allowedRoadCapsuleGuardMetres']),
                              float(geometry['allowedCrossHalf'])-half)
        _require_join_coverage(expected,actual,max(2*xz_error,np.finfo(np.float32).eps),side,
                               maximum_expansion=maximum_expansion)
        if not len(vertices):raise BP.ProfileError(f'{side} final join emitted no vertices')
        break_points,break_offsets=_terrain_join_points(world,left,axis,across,station,expected)
        carried=contract['joinContactRows'][side]
        if not np.array_equal(break_offsets,np.asarray(carried['terrainBreakOffsetsMetres'],float)):
            raise BP.ProfileError(f'{side} actual terrain breaklines differ from carried join contact rows')
        break_y,break_actual,_,_,provenance=_emitted_join_heights(
            faces,left,axis,across,station,break_offsets,return_provenance=True)
        actual_canonical=_canonical_join_provenance(faces[:,:,[0,2]],provenance)
        if (not np.array_equal(break_actual,np.asarray(carried['encodedContactPoints'],float))
                or actual_canonical!=carried['canonicalFaceVertexProvenance']):
            raise BP.ProfileError(f'{side} actual join contact-row provenance changed after solve')
        points=np.vstack((vertices[:,[0,2]],break_actual))
        raw_offsets=(vertices[:,[0,2]]-left)@across
        deck=np.r_[vertices[:,1],break_y]
        terrain=np.array([_terrain_interpolation(world,x,z,encoded_height)[0] for x,z in points])
        source_terrain=np.array([_terrain_interpolation(world,x,z)[0] for x,z in points])
        target_gap=float(contract['joinTargetGapMetres'])
        solve_band=np.asarray(contract['joinSolveGapBandMetres'],float)
        constraint_mode=contract['joinConstraintMode']
        actual_gap=deck-terrain
        identity_start=len(vertices)
        identity_deck=deck[identity_start:]
        identity_terrain=terrain[identity_start:]
        identity_source_terrain=source_terrain[identity_start:]
        identity_source_deck=profile.at(_arch_vertex_stations(
            break_actual,left,axis,(station,)))
        identity_gap=identity_deck-identity_terrain
        if constraint_mode=='uniform-equality':
            residual=np.abs(identity_gap-target_gap)
        elif constraint_mode=='bounded-gap':
            residual=np.maximum.reduce((solve_band[0]-identity_gap,
                                        identity_gap-solve_band[1],
                                        np.zeros_like(identity_gap)))
        else:raise BP.ProfileError(f'unknown join constraint mode {constraint_mode!r}')
        # The bound contains only actual XZ displacement from float32 encoding,
        # observed Y encoding error and arithmetic roundoff.  It is not a
        # geometric join tolerance.
        numeric=(np.abs(identity_deck-identity_source_deck)+
                 np.abs(identity_terrain-identity_source_terrain)+
                 64*np.finfo(float).eps*np.maximum(
                     1.,np.abs(identity_deck)+np.abs(identity_terrain)))
        _validate_join_postcheck_gaps(actual_gap,lift_limit,residual,numeric,side)
        water=L.water_fields(points[:,0],points[:,1],height=terrain,plan=world.plan)
        if np.asarray(water['mask'],bool).any():
            raise BP.ProfileError(f'{side} final full-width join intersects water')
        join_report[side]={'analyticIntervals':expected,'unclippedServingIntervals':raw,
                           'excludedServingIntervals':excluded,
                           'unclaimedDisconnectedServingIntervals':
                               geometry['unclaimedDisconnectedJoinIntervals'][side],
                            'encodedIntervals':actual,
                           'excludedServingIntervalClassification':[
                               {'interval':interval,'status':'unresolved-needs-bounded-2d-road-and-water-trace'}
                               for interval in excluded],
                            'emittedVertices':len(vertices),'terrainBreaklinePoints':len(break_points),
                            'supportConstraints':len(points),
                            'constraintMode':constraint_mode,
                            'carriedEqualityRows':(len(break_actual)
                                                   if constraint_mode=='uniform-equality' else 0),
                            'carriedBoundedGapRows':(len(break_actual)
                                                    if constraint_mode=='bounded-gap' else 0),
                            'physicalOnlyEmittedVertices':len(vertices),
                            'canonicalContactRowProvenanceMatched':True,
                            'minimumGroundGapMetres':float(actual_gap.min()),
                            'maximumGroundGapMetres':float(actual_gap.max()),
                            'maximumGroundGapLimitMetres':lift_limit,
                            'maximumContactConstraintResidualMetres':float(residual.max()),
                            'maximumEncodingBoundMetres':float(numeric.max()),
                            'maximumPhysicalPointDifferenceFromSolveGapMetres':(
                                float(np.max(np.abs(actual_gap-target_gap)))
                                if constraint_mode=='uniform-equality' else None),
                            'solveGapMetres':(target_gap
                                             if constraint_mode=='uniform-equality' else None),
                            'solveGapBandMetres':solve_band.tolist(),
                             'unusedMinimumContactMarginMetres':float(actual_gap.min()-BP.DRY_CLEARANCE_METRES)}
    _bridge_progress(world,'postcheck-joins-complete',site=int(site['id']))

    side_contacts=_side_junction_contact_samples(world,site,faces,geometry)
    side_gaps=[]
    for face_index,(x,z) in side_contacts:
        deck=_triangle_height(faces[face_index],np.array([x,z]))
        terrain=_terrain_interpolation(world,x,z,encoded_height)[0]
        gap=float(deck-terrain);side_gaps.append(gap)
        if gap<BP.DRY_CLEARANCE_METRES or gap>lift_limit:
            raise BP.ProfileError('actual dry side-junction contact escapes physical ground-gap bounds')
        water=L.water_fields(np.array([x]),np.array([z]),height=np.array([terrain]),plan=world.plan)
        if bool(np.asarray(water['mask'])[0]):
            raise BP.ProfileError('actual dry side-junction contact intersects water')
    side_junction_report={
        'contactPoints':len(side_contacts),
        'minimumGroundGapMetres':(float(min(side_gaps)) if side_gaps else None),
        'maximumGroundGapMetres':(float(max(side_gaps)) if side_gaps else None),
        'maximumGroundGapLimitMetres':lift_limit,
        'excludedDryBranchSegments':geometry['servingComponentAuthority']['dryBankParallelSegments']}

    overlay_vertices=[];ground_gap=[]
    solid_overlaps=0
    for face_number,face in enumerate(faces,1):
        for nodes,terrain_triangle,polygon in _face_overlays(world,face):
            if _solid_overlap(world,np.c_[polygon[:,0],np.zeros(len(polygon)),polygon[:,1]],
                              released_margin_nodes,face):
                solid_overlaps+=1
            points=np.vstack((polygon,polygon.mean(axis=0)))
            deck=np.array([_triangle_height(face,point) for point in points])
            terrain=np.array([_triangle_height(np.c_[terrain_triangle[:,0],
                [encoded_height[node] for node in nodes],terrain_triangle[:,2]],point) for point in points])
            gap=deck-terrain;ground_gap.extend(gap[:-1]);overlay_vertices.extend(points[:-1])
        if face_number%512==0:
            _bridge_progress(world,'postcheck-terrain-overlays',site=int(site['id']),
                             completed=face_number,total=len(faces))
    water_authority=getattr(world,'claimed_bridge_final_water_authority',{}).get(site['id'])
    if water_authority is None:raise BP.ProfileError('missing regenerated final encoded water authority')
    continuous_water=_continuous_emitted_water_check(faces,water_authority['faces'],clearance)
    final_join_water=_join_misses_water(world,site,faces,water_authority['faces'],geometry)
    _bridge_progress(world,'postcheck-water-complete',site=int(site['id']))
    if solid_overlaps:
        raise BP.ProfileError('claimed deck overlaps retained-solid terrain cells')
    if not ground_gap or min(ground_gap)<0.:
        raise BP.ProfileError('actual encoded deck penetrates final terrain')

    # Reuse the exact actor-centre outer approaches and dry side-junction
    # approaches that supplied the LP rows.  The full road-width footprint is
    # still required at the deck join, but terrain hidden behind the fixed
    # balustrade margin is not an exposed actor approach.
    _,_,approach,_,_,_,_,bounds=_site_terrain_selection(world,site,landing)
    approach_water_samples=0
    for _,terrain_triangle in _terrain_triangles(world,bounds):
        points=[]
        for part in approach:
            for polygon in part.clip(terrain_triangle):points.extend(polygon[:,[0,2]])
        if not points:continue
        points=np.asarray(points,float);points=np.vstack((points,points.mean(axis=0)))
        terrain=np.array([_terrain_interpolation(world,x,z,encoded_height)[0] for x,z in points])
        water=L.water_fields(points[:,0],points[:,1],height=terrain,plan=world.plan)
        approach_water_samples+=len(points)
        if np.asarray(water['mask'],bool).any():
            raise BP.ProfileError('final promised ground approach ring intersects water')
    affected=[];influenced=[]
    for nodes,terrain_triangle in _terrain_triangles(world,bounds):
        on_approach=any(_clip_area(part,terrain_triangle)>NEGLIGIBLE_FLOOR_AREA for part in approach)
        changed=any(node in deltas and deltas[node]!=0. for node in nodes)
        if not on_approach and not changed:continue
        xyz=terrain_triangle.copy();xyz[:,1]=[encoded_height[node] for node in nodes]
        xyz=xyz[[0,2,1]]
        grade=_encoded_grade(xyz)
        if changed:influenced.append(grade)
        if on_approach:
            affected.append(grade)
            if grade>GRADE:raise BP.ProfileError('actual encoded ground approach exceeds the .65 grade limit')
    nominal_coverage=_nominal_floor_certificate_inputs(world,site,faces,geometry)
    return {'joinCoverage':join_report,'sideJunctionContact':side_junction_report,
            'nominalFloorCertificateInputs':nominal_coverage,'deckTriangles':len(faces),
            'maximumEncodedDeckGrade':float(deck_grades.max(initial=0.)),
            'terrainOverlayVertices':len(overlay_vertices),
            'continuousEncodedWater':continuous_water,'finalJoinWater':final_join_water,
            'waterClearanceIsSampledNotContinuous':False,
            'minimumDeepWaterClearanceMetres':continuous_water['minimumClearanceMetres'],
            'minimumGroundClearanceMetres':float(min(ground_gap)),
            'maximumInteriorDryGapMetres':float(max(ground_gap,default=0.)),
            'affectedApproachTriangles':len(affected),
            'maximumEncodedApproachGrade':float(max(affected,default=0.)),
            'approachDrySamples':approach_water_samples,
            'allIncidentInfluenceTriangles':len(influenced),
            'maximumIncidentInfluenceGrade':float(max(influenced,default=0.))}


def _joint_site_fit(world,site,road,landing,lift_limit,clearance,reference):
    """Jointly solve one claimed PL deck and only its dry support/approach terrain."""
    left,_,axis,across,length=_site_frame(site);roads=_serving_roads(world,site,strict=True)
    geometry,span,approach,terrain,deck_triangles,approach_triangles,mutable_nodes,bounds=(
        _site_terrain_selection(world,site,landing))
    _bridge_progress(world,'lp-selection-complete',site=int(site['id']),
                     terrainTriangles=len(terrain),deckTriangles=len(deck_triangles),
                     approachTriangles=len(approach_triangles),mutableNodes=len(mutable_nodes))
    half=float(geometry['nominalHalf'])
    approach_samples=[]
    for _,triangle in approach_triangles:
        points=[]
        for part in approach:
            for polygon in part.clip(triangle):points.extend(polygon[:,[0,2]])
        if not points:continue
        points=np.asarray(points,float);points=np.vstack((points,points.mean(axis=0)))
        approach_samples.extend(points)
        bed=np.array([_terrain_interpolation(world,x,z,reference)[0] for x,z in points])
        if np.asarray(L.water_fields(points[:,0],points[:,1],height=bed,plan=world.plan)['mask'],bool).any():
            raise BP.ProfileError('promised ground approach ring intersects water')
    # Pin every vertex of every source terrain cell contributing positive
    # actual encoded water in this complete local envelope. This is stronger
    # than sampling wet vertices and preserves shoreline triangles exactly.
    water_authority=getattr(world,'claimed_bridge_water_authority',{}).get(site['id'],{})
    nx=world.height.shape[1];water_nodes=set()
    for cell in np.asarray(water_authority.get('sourceCells',()),int):
        iz,ix=divmod(int(cell),nx-1)
        water_nodes.update(((iz,ix),(iz,ix+1),(iz+1,ix),(iz+1,ix+1)))
    protected_nodes=set()
    support_boxes=getattr(world,'claimed_bridge_support_boxes',())
    for nodes,triangle in terrain:
        if any(_footprint_intersects_triangle(footprint,triangle)
               for footprint in support_boxes):protected_nodes.update(nodes)
    solid_margin_release=_site_solid_margin_release_nodes(
        world,site,support_boxes,water_nodes,reference)
    authored=np.asarray(getattr(world,'authored_terrain_authority',np.zeros_like(reference,bool)),bool)
    if authored.shape!=reference.shape:
        raise BP.ProfileError('authored terrain authority does not match the claimed-bridge terrain grid')
    mutable=[]
    for iz,ix in sorted(mutable_nodes):
        x=world.x0+ix*TERRAIN_CELL;z=world.z0+iz*TERRAIN_CELL
        wf=L.water_fields(np.array([x]),np.array([z]),height=np.array([reference[iz,ix]]),plan=world.plan)
        if (not authored[iz,ix]
                and (iz,ix) not in water_nodes and (iz,ix) not in protected_nodes
                and not bool(np.asarray(wf['mask'])[0])
                and (not bool(world.solids[iz,ix]) or (iz,ix) in solid_margin_release)):
            mutable.append((iz,ix))
    stations=BP.canonical_stations(geometry['constructionStart'],0.,length,geometry['constructionEnd'])
    middle=length*.5
    # A half-metre lattice point can fall within one derived float32
    # displacement guard of an authored/certificate plane and create a band
    # that cannot survive XZ encoding. Keep authored profile planes, remove
    # nearby lattice copies, and leave nominal planes as certificate queries.
    anchors=np.array([geometry['constructionStart'],0.,middle,length,geometry['constructionEnd']])
    guards=np.r_[anchors,geometry['nominalStart'],geometry['nominalEnd']]
    arithmetic=64*np.finfo(float).eps*max(1.,float(np.max(np.abs(guards))))
    essential=np.isin(stations,anchors)
    near_guard=np.min(np.abs(stations[:,None]-guards),axis=1)<=geometry['axisGuardMetres']+arithmetic
    stations=np.unique(np.r_[stations[essential|~near_guard],anchors])
    profile_count=len(stations);basis=np.eye(profile_count)
    node_vars={node:profile_count+i for i,node in enumerate(mutable)}
    absolute=profile_count+len(mutable)
    smooth_start=absolute+len(mutable);smooth_count=max(0,profile_count-2)
    size=smooth_start+smooth_count
    zero=BP.ArchProfile(stations,np.zeros(len(stations)),0.,middle,length)
    meshes,components=_candidate_components(world,site,road,landing,zero,strict=True)
    faces=np.concatenate([mesh.positions[mesh.indices.reshape(-1,3)] for mesh in meshes])
    faces_xz=faces[:,:,[0,2]]
    _bridge_progress(world,'lp-mesh-built',site=int(site['id']),faces=len(faces))
    rows=[];limits=[];equal=[];equal_values=[];row_groups={};equal_groups={}
    def mark_rows(name,start):
        row_groups[name]=[int(start),len(rows)]
    def mark_equal(name,start):
        equal_groups[name]=[int(start),len(equal)]
    guard=_world_y_guard(world)
    join_stations=(geometry['constructionStart'],geometry['constructionEnd'])
    def profile_row(distance):
        row=np.zeros(size);row[:profile_count]=BP.interpolated_basis(
            distance,stations,basis);return row
    # The emitted float32 water authority is unchanged by this fit.  Clip each
    # actual encoded deck face against it and carry every affine-overlap vertex
    # directly into the LP; the postcheck repeats the same continuous proof.
    water_faces=np.asarray(water_authority.get('faces',()),float).reshape(-1,3,3)
    water_bins=_water_face_bins(water_faces)
    encoded_water_rows=0;group_start=len(rows)
    for face,face_xz in zip(faces,faces_xz):
        low=np.floor(face_xz.min(axis=0)/8.).astype(int)
        high=np.floor(face_xz.max(axis=0)/8.).astype(int)
        candidates=sorted({index for ix in range(low[0],high[0]+1)
                            for iz in range(low[1],high[1]+1)
                            for index in water_bins.get((ix,iz),())})
        for index in candidates:
            polygon=_convex_xz_overlap(face,water_faces[index])
            if not len(polygon) or abs(_area_xz(polygon))<=0.:continue
            points=polygon[:,[0,2]]
            coefficients=_encoded_face_profile_rows(
                face_xz,points,left,axis,stations,basis,join_stations=join_stations)
            for point,profile_values in zip(points,coefficients):
                row=np.zeros(size);row[:profile_count]=-profile_values
                rows.append(row);limits.append(-(_triangle_height(water_faces[index],point)+clearance+guard))
                encoded_water_rows+=1
    mark_rows('encoded-water-clearance',group_start)
    _bridge_progress(world,'lp-water-rows-built',site=int(site['id']),rows=encoded_water_rows)
    # The promised outside approach stays ground.  Prevent its own grading
    # from turning any currently dry sampled part into water.
    group_start=len(rows)
    for x,z in np.unique(np.asarray(approach_samples,float).reshape(-1,2),axis=0):
        baseline,trow=_terrain_row(world,x,z,node_vars,size)
        water=L.water_fields(np.array([x]),np.array([z]),height=np.array([baseline]),plan=world.plan)
        _append_mutable_dry_constraint(rows,limits,trow,baseline,np.asarray(water['surface'])[0],guard)
    mark_rows('approach-remains-dry',group_start)
    # Actual float32 join edges must cover the independent analytic capsules.
    joins=[];join_report={};join_rows=[];join_row_details=[];join_margin=0.;join_identity={}
    for side,station in zip(('left','right'),join_stations):
        vertices,actual,error=_emitted_join(faces,left,axis,across,station)
        expected=_contract_join_intervals(world,site,station,geometry)
        raw=_contract_join_intervals(world,site,station,geometry,clip_to_nominal=False)
        excluded=_excluded_join_intervals(raw,half)
        maximum_expansion=max(float(geometry['allowedRoadCapsuleGuardMetres']),
                              float(geometry['allowedCrossHalf'])-half)
        _require_join_coverage(expected,actual,max(error*2.,np.finfo(np.float32).eps),side,
                               maximum_expansion=maximum_expansion)
        if not len(vertices):raise BP.ProfileError(f'{side} join emitted no vertices')
        break_points,break_offsets=_terrain_join_points(world,left,axis,across,station,expected)
        # The solve uses the same actual float32 face basis that deck_mesh will
        # emit.  Canonical points remain solely the source-displacement
        # authority used to derive the construction margin.
        _,points,_,_,provenance=_emitted_join_heights(
            faces,left,axis,across,station,break_offsets,return_provenance=True)
        bed=np.array([_terrain_interpolation(world,x,z,reference)[0] for x,z in points])
        water=L.water_fields(points[:,0],points[:,1],height=bed,plan=world.plan)
        if np.asarray(water['mask'],bool).any():raise BP.ProfileError(f'{side} full-width join intersects water')
        coefficient_rows=_join_profile_rows_from_provenance(
            faces_xz,provenance,left,axis,stations,basis,join_stations)
        join_identity[side]={'terrainBreakOffsetsMetres':break_offsets.tolist(),
                             'encodedContactPoints':points.tolist(),
                             'canonicalFaceVertexProvenance':_canonical_join_provenance(
                                 faces_xz,provenance)}
        margin,margin_rows=_join_margin_v4(world,reference,node_vars,break_points,points,axis)
        join_margin=max(join_margin,margin)
        for (x,z),coefficients in zip(points,coefficient_rows):
            baseline,trow=_terrain_row(world,x,z,node_vars,size)
            prow=np.zeros(size);prow[:profile_count]=coefficients
            join_rows.append((prow-trow,baseline))
            join_row_details.append({'side':side,'point':[float(x),float(z)],
                                     'baseline':float(baseline)})
        joins.extend(points)
        join_report[side]={'analyticIntervals':expected,'unclippedServingIntervals':raw,
                           'excludedServingIntervals':excluded,
                           'unclaimedDisconnectedServingIntervals':
                               geometry['unclaimedDisconnectedJoinIntervals'][side],
                           'encodedIntervals':actual,
                           'excludedServingIntervalClassification':[
                               {'interval':interval,'status':'unresolved-needs-bounded-2d-road-and-water-trace'}
                               for interval in excluded],
                           'emittedVertices':len(vertices),'terrainBreaklinePoints':len(break_points),
                           'supportConstraints':len(points),'canonicalStationMetres':station,
                           'encodedContactPoints':points.tolist(),'carriedFaceEdgeProvenance':provenance,
                           'encodingMarginTerms':margin_rows}
    _bridge_progress(world,'lp-joins-built',site=int(site['id']),joinRows=len(join_rows))
    join_target=BP.DRY_CLEARANCE_METRES+join_margin
    if join_target>lift_limit:
        raise BP.ProfileError('derived outer-join encoding margin exceeds the bank-lift policy')
    group_start=len(equal)
    for row,baseline in join_rows:
        equal.append(row);equal_values.append(baseline+join_target)
    mark_equal('encoded-full-width-join-contact',group_start)
    for report in join_report.values():
        report['uniformSolveGapMetres']=join_target
        report['uniformEncodingMarginMetres']=join_margin
    # A dry attributed branch excluded from the wet crossing remains terrain,
    # but an actor must cross its real intersection with the selected deck.
    # Constrain every affine terrain-piece endpoint on that actual encoded
    # lateral boundary during the solve; final postcheck reuses the same edge
    # authority.
    side_contacts=_side_junction_contact_samples(world,site,faces,geometry)
    group_start=len(rows)
    for face_index,(x,z) in side_contacts:
        profile_values=_encoded_face_profile_rows(
            faces_xz[face_index],np.array([[x,z]]),left,axis,stations,basis,
            join_stations=join_stations)[0]
        baseline,trow=_terrain_row(world,x,z,node_vars,size)
        prow=np.zeros(size);prow[:profile_count]=profile_values
        rows.append(prow-trow);limits.append(baseline+lift_limit-guard)
        rows.append(-prow+trow);limits.append(-(baseline+BP.DRY_CLEARANCE_METRES+guard))
        water=L.water_fields(np.array([x]),np.array([z]),height=np.array([baseline]),plan=world.plan)
        if bool(np.asarray(water['mask'])[0]):
            raise BP.ProfileError('dry side-junction deck contact intersects water')
    mark_rows('side-junction-contact',group_start)
    _bridge_progress(world,'lp-side-junction-rows-built',site=int(site['id']),
                     contacts=len(side_contacts),rows=len(rows)-group_start)
    # Subdivide every deck face by only the terrain cells under that face.
    # Both surfaces are affine on each overlap, so their difference reaches
    # every extremum at these exact polygon vertices; interior samples cannot
    # add a ground-support or mutable-dryness constraint.
    samples=[];sample_profile_rows=[]
    for face,face_xz in zip(faces,faces_xz):
        face_points=[]
        for _,_,polygon in _face_overlays(world,face):face_points.extend(polygon)
        if not face_points:raise BP.ProfileError('encoded deck face has no terrain overlay')
        face_points=np.asarray(face_points,float)
        samples.extend(face_points)
        sample_profile_rows.extend(_encoded_face_profile_rows(
            face_xz,face_points,left,axis,stations,basis,join_stations=join_stations))
    # A shared XZ can lie on faces from opposite sides of a PL station kink.
    # Keep distinct face-plane coefficient rows while removing only exact
    # duplicate constraints.
    combined=np.c_[np.asarray(samples,float),np.asarray(sample_profile_rows,float)]
    combined=np.unique(combined,axis=0)
    sample_xz=combined[:,:2];sample_profile_rows=combined[:,2:]
    sample_bed=np.array([_terrain_interpolation(world,x,z,reference)[0] for x,z in sample_xz])
    water=L.water_fields(sample_xz[:,0],sample_xz[:,1],height=sample_bed,plan=world.plan)
    group_start=len(rows)
    for index,(x,z) in enumerate(sample_xz):
        baseline,trow=_terrain_row(world,x,z,node_vars,size)
        p=np.zeros(size);p[:profile_count]=sample_profile_rows[index]
        # A named arch may rise above dry bank terrain inside its exact deck.
        # It must not penetrate that terrain after float32 encoding.  The
        # authored 25 mm contact target is reserved for both outer join planes.
        rows.append(-p+trow);limits.append(
            -(baseline+_claimed_ground_support_offset(world,outer_join=False)))
        wet=bool(np.asarray(water['mask'])[index])
        if not wet:
            # Keep a dry named-deck sample dry after grading, so the fixed
            # ground-support constraint and final water classification agree.
            _append_mutable_dry_constraint(
                rows,limits,trow,baseline,np.asarray(water['surface'])[index],guard)
    mark_rows('deck-ground-nonpenetration-and-dryness',group_start)
    _bridge_progress(world,'lp-ground-rows-built',site=int(site['id']),
                     overlayVertices=len(sample_xz),rows=len(rows)-group_start)
    rise=BP.arch_rise(length,clearance,SOLVE_GRADE)
    shape_rows,shape_limits,curvature_rows,middle_index=_per_station_profile_constraints(
        stations,middle,rise)
    group_start=len(rows)
    for profile_values,bound in zip(shape_rows,shape_limits):
        row=np.zeros(size);row[:profile_count]=profile_values
        rows.append(row);limits.append(float(bound))
    mark_rows('profile-single-crest-and-slope',group_start)
    curvature_limits=PROFILE_SLOPE_CHANGE_PER_METRE*.5*(
        np.diff(stations)[:-1]+np.diff(stations)[1:])
    # Bound every adjacent slope change as an authored gentle-arch shape rule.
    # The absolute auxiliary remains only a deterministic smoothness
    # tie-breaker inside that physical representation family.
    group_start=len(rows)
    for index,profile_values in enumerate(curvature_rows):
        curvature=np.zeros(size);curvature[:profile_count]=profile_values
        rows.append(curvature);limits.append(float(curvature_limits[index]))
        rows.append(-curvature);limits.append(float(curvature_limits[index]))
        auxiliary=smooth_start+index
        row=curvature.copy();row[auxiliary]-=1.;rows.append(row);limits.append(0.)
        row=-curvature;row[auxiliary]-=1.;rows.append(row);limits.append(0.)
    mark_rows('profile-curvature-and-smoothness',group_start)
    # Only the promised dry ground outside the named deck is walking terrain.
    directions=np.linspace(0.,2*math.pi,32,endpoint=False)
    # Each encoded vertex can move by one world-scale float32 Y guard.  A
    # two-metre right terrain triangle therefore gains at most this Euclidean
    # gradient magnitude after encoding.  Build the margin into the solve;
    # final .65 comparison remains strict.
    approach_grade_encoding_margin=2.*math.sqrt(2.)*guard/TERRAIN_CELL
    cap=(GRADE-approach_grade_encoding_margin)*math.cos(math.pi/32.)
    group_start=len(rows)
    for nodes,triangle in approach_triangles:
        xz=triangle[:,[0,2]];matrix=xz[1:]-xz[0]
        inverse=np.linalg.inv(matrix)
        heights=np.array([reference[node] for node in nodes])
        gx0,gz0=inverse@np.array([heights[1]-heights[0],heights[2]-heights[0]])
        gx=np.zeros(size);gz=np.zeros(size)
        for number,node in enumerate(nodes):
            unit=np.zeros(3);unit[number]=1.
            coefficient=inverse@np.array([unit[1]-unit[0],unit[2]-unit[0]])
            if node in node_vars:
                gx[node_vars[node]]+=coefficient[0];gz[node_vars[node]]+=coefficient[1]
        if not np.any(gx) and not np.any(gz):continue
        for angle in directions:
            dx,dz=math.cos(angle),math.sin(angle);rows.append(dx*gx+dz*gz);limits.append(cap-dx*gx0-dz*gz0)
    mark_rows('actual-approach-grade',group_start)
    group_start=len(rows)
    for number,node in enumerate(mutable):
        delta_index=profile_count+number;absolute_index=absolute+number
        row=np.zeros(size);row[delta_index]=1;row[absolute_index]=-1;rows.append(row);limits.append(0.)
        row=np.zeros(size);row[delta_index]=-1;row[absolute_index]=-1;rows.append(row);limits.append(0.)
    mark_rows('terrain-cut-fill-absolute-value',group_start)
    objective=np.zeros(size)
    objective[:profile_count]=1e-9
    objective[absolute:absolute+len(mutable)]=1.
    objective[smooth_start:]=1e-6
    bounds=([(None,None)]*profile_count+
            [(-ROAD_CUT_METRES,ROAD_FILL_METRES)]*len(mutable)+
            [(0,None)]*len(mutable)+[(0,None)]*smooth_count)
    variable_provenance=([
        {'kind':'profile-height','stationMetres':float(station)} for station in stations]+[
        {'kind':'terrain-delta','node':[int(node[0]),int(node[1])]} for node in mutable]+[
        {'kind':'terrain-absolute-delta','node':[int(node[0]),int(node[1])]} for node in mutable]+[
        {'kind':'profile-absolute-curvature','stationMetres':float(stations[index+1])}
        for index in range(smooth_count)])
    model={'A_ub':csr_matrix(np.asarray(rows,float)),
        'b_ub':np.asarray(limits,float),'A_eq':csr_matrix(np.asarray(equal,float)),
        'b_eq':np.asarray(equal_values,float),'objective':objective.copy(),'bounds':tuple(bounds),
        'rowGroups':row_groups,'equalityGroups':equal_groups,
        'variables':variable_provenance,'site':int(site['id'])}
    capture=getattr(world,'claimed_bridge_lp_capture',None)
    diagnostic=capture is not None or bool(getattr(world,'claimed_bridge_diagnostics',False))
    if diagnostic:
        lp_models=getattr(world,'claimed_bridge_lp_models',{});lp_models[site['id']]=model
        world.claimed_bridge_lp_models=lp_models
    if capture is not None:capture(site['id'],model)
    _bridge_progress(world,'lp-model-built',site=int(site['id']),variables=size,
                      inequalities=len(rows),equalities=len(equal))
    solve_options={'primal_feasibility_tolerance':1e-9,'dual_feasibility_tolerance':1e-9}
    result=linprog(objective,A_ub=model['A_ub'],b_ub=model['b_ub'],
                   A_eq=model['A_eq'],b_eq=model['b_eq'],bounds=bounds,
                   method='highs',options=solve_options)
    join_constraint_mode='uniform-equality'
    curvature_mode='preferred-hard-cap';required_curvature_rate=None
    join_lower=join_target;join_upper=lift_limit-join_margin
    if not result.success and int(result.status)==2:
        # A flat deck does not require every terrain break point across its
        # width to share one exact terrain elevation. Prefer that authored
        # uniform contact, then fall back to the already-authored physical gap
        # band with the same derived encoding guard on both boundaries.
        if join_upper<join_lower:
            raise BP.ProfileError('derived join guards leave no physical ground-gap band')
        band_rows=list(rows);band_limits=list(limits);group_start=len(band_rows)
        for row,baseline in join_rows:
            band_rows.append(-row);band_limits.append(-(baseline+join_lower))
            band_rows.append(row);band_limits.append(baseline+join_upper)
        band_groups=dict(row_groups)
        band_groups['encoded-full-width-join-gap-band']=(group_start,len(band_rows))
        model={'A_ub':csr_matrix(np.asarray(band_rows,float)),
            'b_ub':np.asarray(band_limits,float),'A_eq':csr_matrix((0,size)),
            'b_eq':np.empty(0,float),'objective':objective.copy(),'bounds':tuple(bounds),
            'rowGroups':band_groups,'equalityGroups':{},
            'variables':variable_provenance,'site':int(site['id'])}
        if diagnostic:model['joinContacts']=join_row_details
        if diagnostic:
            lp_models=getattr(world,'claimed_bridge_lp_models',{});lp_models[site['id']]=model
            world.claimed_bridge_lp_models=lp_models
        if capture is not None:capture(site['id'],model)
        _bridge_progress(world,'lp-join-gap-fallback-built',site=int(site['id']),
                         lowerGapMetres=join_lower,upperGapMetres=join_upper,
                         inequalities=len(band_rows))
        result=linprog(objective,A_ub=model['A_ub'],b_ub=model['b_ub'],
                       A_eq=model['A_eq'],b_eq=model['b_eq'],bounds=bounds,
                       method='highs',options=solve_options)
        join_constraint_mode='bounded-gap'
    if not result.success and int(result.status)==2:
        # The .08/m curvature cap is the preferred visual family, not an owner
        # physical limit.  Find the gentlest physically feasible profile, then
        # retain that optimum while applying the original earthwork/smoothness
        # objective.  The reviewed .09/m ceiling prevents a sharp-ramp escape.
        start,stop=model['rowGroups']['profile-curvature-and-smoothness']
        count=(stop-start)//4
        if stop-start!=4*count:raise BP.ProfileError('unexpected curvature constraint layout')
        extended=hstack((model['A_ub'],lil_matrix((model['A_ub'].shape[0],1)))).tolil()
        extended_limits=model['b_ub'].copy()
        for index in range(count):
            spacing=float(extended_limits[start+4*index]/PROFILE_SLOPE_CHANGE_PER_METRE)
            for offset in (0,1):
                row=start+4*index+offset;extended[row,-1]=-spacing;extended_limits[row]=0.
        extended=extended.tocsr()
        extended_equal=hstack((model['A_eq'],lil_matrix((model['A_eq'].shape[0],1)))).tocsr()
        minimax=np.zeros(size+1);minimax[-1]=1.
        phase1=linprog(minimax,A_ub=extended,b_ub=extended_limits,
            A_eq=extended_equal,b_eq=model['b_eq'],bounds=[*bounds,(0.,None)],
            method='highs',options=solve_options)
        if not phase1.success:
            raise BP.ProfileError(f'curvature-minimax bridge fit is infeasible: {phase1.message}')
        required_curvature_rate=float(phase1.x[-1])
        if required_curvature_rate>CURVATURE_FALLBACK_CEILING_PER_METRE:
            raise BP.ProfileError('minimum feasible bridge curvature exceeds the reviewed .09/m ceiling')
        curvature_headroom=1e-9
        curvature_bound=float(np.nextafter(required_curvature_rate+curvature_headroom,np.inf))
        phase2=linprog(np.r_[objective,0.],A_ub=extended,b_ub=extended_limits,
            A_eq=extended_equal,b_eq=model['b_eq'],bounds=[*bounds,(0.,curvature_bound)],
            method='highs',options=solve_options)
        if not phase2.success:
            raise BP.ProfileError(f'curvature-minimax objective tie-break is infeasible: {phase2.message}')
        result=phase2;curvature_mode='reviewed-minimax-fallback'
        model={**model,'A_ub':extended,'b_ub':extended_limits,'A_eq':extended_equal,
            'objective':np.r_[objective,0.],'bounds':tuple([*bounds,(0.,curvature_bound)]),
            'variables':[*variable_provenance,{'kind':'maximum-slope-change-per-metre'}]}
        if diagnostic:
            lp_models=getattr(world,'claimed_bridge_lp_models',{});lp_models[site['id']]=model
            world.claimed_bridge_lp_models=lp_models
        if capture is not None:capture(site['id'],model)
        _bridge_progress(world,'lp-curvature-minimax-fallback-finished',site=int(site['id']),
            requiredSlopeChangePerMetre=required_curvature_rate,
            ceilingSlopeChangePerMetre=CURVATURE_FALLBACK_CEILING_PER_METRE)
    if diagnostic and result.success:
        solutions=getattr(world,'claimed_bridge_lp_solutions',{})
        solutions[site['id']]=np.asarray(result.x,float).copy();world.claimed_bridge_lp_solutions=solutions
    _bridge_progress(world,'lp-solve-finished',site=int(site['id']),success=bool(result.success),
                     status=int(result.status))
    if not result.success:raise BP.ProfileError(f'joint bridge/approach fit is infeasible: {result.message}')
    profile=BP.ArchProfile(stations,result.x[:profile_count],0.,middle,length)
    profile_slopes=np.diff(profile.heights)/np.diff(profile.stations)
    profile_slope_change=np.diff(profile_slopes)
    profile_slope_spacing=.5*(np.diff(profile.stations)[:-1]+np.diff(profile.stations)[1:])
    actual_curvature_rate=float(np.max(np.abs(profile_slope_change)/profile_slope_spacing,initial=0.))
    if (curvature_mode=='reviewed-minimax-fallback'
            and actual_curvature_rate>CURVATURE_FALLBACK_CEILING_PER_METRE):
        raise BP.ProfileError('actual minimax bridge curvature exceeds the reviewed .09/m ceiling')
    contracts=getattr(world,'claimed_bridge_v7_contracts',{})
    contracts[site['id']]={'geometry':geometry,'joinTargetGapMetres':join_target,
                            'joinEncodingMarginMetres':join_margin,
                            'joinConstraintMode':join_constraint_mode,
                            'joinSolveGapBandMetres':[join_lower,join_upper],
                            'joinContactRows':join_identity,
                           'profileFamily':{'kind':'per-station-piecewise-linear-single-crest',
                                            'profileVariables':profile_count,
                                            'smoothnessVariables':smooth_count,
                                            'maximumAdjacentSlopeChangePerMetre':
                                                 PROFILE_SLOPE_CHANGE_PER_METRE,
                                            'curvatureMode':curvature_mode,
                                            'minimumRequiredSlopeChangePerMetre':required_curvature_rate,
                                            'actualMaximumSlopeChangePerMetre':actual_curvature_rate,
                                            'fallbackSafetyCeilingPerMetre':
                                                CURVATURE_FALLBACK_CEILING_PER_METRE,
                                            'middleStationMetres':middle}}
    world.claimed_bridge_v7_contracts=contracts
    for report in join_report.values():
        report['constraintMode']=join_constraint_mode
        report['solveGapBandMetres']=[join_lower,join_upper]
        if join_constraint_mode=='bounded-gap':report.pop('uniformSolveGapMetres',None)
    deltas={node:float(result.x[index]) for node,index in node_vars.items()}
    node_xz=np.array([[world.x0+ix*TERRAIN_CELL,world.z0+iz*TERRAIN_CELL] for iz,ix in mutable])
    influence_station=(node_xz-left)@axis if len(node_xz) else np.empty(0)
    influence_side=(node_xz-left)@across if len(node_xz) else np.empty(0)
    changed_nodes=[node for node in mutable if deltas[node]!=0.]
    changed_xz=np.array([[world.x0+ix*TERRAIN_CELL,world.z0+iz*TERRAIN_CELL]
                         for iz,ix in changed_nodes])
    changed_station=(changed_xz-left)@axis if len(changed_xz) else np.empty(0)
    changed_side=(changed_xz-left)@across if len(changed_xz) else np.empty(0)
    incident={}
    changed_set=set(changed_nodes)
    for iz,ix in changed_nodes:
        bounds=(max(0,ix-1),min(world.height.shape[1]-1,ix+1),
                max(0,iz-1),min(world.height.shape[0]-1,iz+1))
        for nodes,triangle in _terrain_triangles(world,bounds):
            if any(node in changed_set for node in nodes):incident[nodes]=triangle
    incident_xz=(np.concatenate([triangle[:,[0,2]] for triangle in incident.values()])
                 if incident else np.empty((0,2)))
    incident_station=(incident_xz-left)@axis if len(incident_xz) else np.empty(0)
    incident_side=(incident_xz-left)@across if len(incident_xz) else np.empty(0)
    changed_rows=[{'node':[int(iz),int(ix)],
                   'xyzBefore':[float(world.x0+ix*TERRAIN_CELL),float(reference[iz,ix]),
                                float(world.z0+iz*TERRAIN_CELL)],
                   'xyzAfter':[float(world.x0+ix*TERRAIN_CELL),float(reference[iz,ix]+deltas[(iz,ix)]),
                               float(world.z0+iz*TERRAIN_CELL)],
                   'deltaMetres':deltas[(iz,ix)]} for iz,ix in changed_nodes]
    return profile,deltas,{'site':site['id'],'key':site.get('key'),'landingMetres':landing,
                           'representationV7':contracts[site['id']],
                           'authority':{'wetEdges':np.asarray(site['wetEdges'],float).tolist(),
                                        'servingRoads':[{'id':item.get('id'),'width':float(item['width']),
                                                         'points':np.asarray(item['points'],float).tolist()}
                                                        for item in roads]},
                            'mutableTerrainVertices':len(mutable),
                            'releasedSolidMarginVertices':[list(node) for node in sorted(solid_margin_release)],
                           'profileVariables':profile_count,
                           'profileSmoothnessVariables':smooth_count,
                           'continuousEncodedWaterRows':encoded_water_rows,
                           'profileStationsMetres':profile.stations.tolist(),
                           'profileHeightsMetres':profile.heights.tolist(),
                           'maximumProfileGrade':float(np.max(np.abs(profile_slopes),initial=0.)),
                            'maximumAdjacentProfileSlopeChange':float(
                                np.max(np.abs(profile_slope_change),initial=0.)),
                            'profileCurvatureMode':curvature_mode,
                            'preferredMaximumSlopeChangePerMetre':PROFILE_SLOPE_CHANGE_PER_METRE,
                            'minimumRequiredSlopeChangePerMetre':required_curvature_rate,
                            'actualMaximumSlopeChangePerMetre':actual_curvature_rate,
                            'curvatureFallbackSafetyCeilingPerMetre':
                                CURVATURE_FALLBACK_CEILING_PER_METRE,
                           'changedTerrainVertices':len(changed_nodes),'changedTerrain':changed_rows,
                           'approachTriangles':len(approach_triangles),
                           'underDeckTriangles':len(deck_triangles),'joinCoverage':join_report,
                           'mutableTerrainStationRangeMetres':([float(influence_station.min()),float(influence_station.max())]
                                                              if len(influence_station) else None),
                           'mutableTerrainCrossRangeMetres':([float(influence_side.min()),float(influence_side.max())]
                                                            if len(influence_side) else None),
                           'changedTerrainStationRangeMetres':([float(changed_station.min()),float(changed_station.max())]
                                                              if len(changed_station) else None),
                            'changedTerrainCrossRangeMetres':([float(changed_side.min()),float(changed_side.max())]
                                                             if len(changed_side) else None),
                            'changedIncidentTriangleCount':len(incident),
                            'changedIncidentStationRangeMetres':([float(incident_station.min()),float(incident_station.max())]
                                                                if len(incident_station) else None),
                            'changedIncidentCrossRangeMetres':([float(incident_side.min()),float(incident_side.max())]
                                                              if len(incident_side) else None),
                           'maximumCutMetres':max([0.,*[-value for value in deltas.values()]]),
                           'maximumFillMetres':max([0.,*deltas.values()])}


def fit_claimed_sites(world,site_ids=None,content=None):
    """Explicitly fit selected claimed decks and atomically preserve hydrology."""
    all_sites=list(getattr(world,'crossing_sites',()))
    if site_ids is None:sites=all_sites
    else:
        requested=list(dict.fromkeys(map(int,site_ids)))
        by_id={site['id']:site for site in all_sites}
        missing=[site_id for site_id in requested if site_id not in by_id]
        if missing:raise BP.ProfileError(f'claimed bridge ids are absent: {missing}')
        sites=[by_id[site_id] for site_id in requested]
    if not sites:
        # Once every territory owns its saved crossings, route replacement removes
        # every procedural river site. There is then no native deck or terrain
        # stencil to fit; saved deck geometry is exported from its scene assembly.
        # Preserve the old failure for a missing/empty selection in a mixed world.
        authored=set(getattr(content, 'authored_regions', ())) if content is not None else set()
        if site_ids is not None or set(getattr(world, 'ids', ())) != authored or not authored:
            raise BP.ProfileError('no claimed bridge sites were explicitly selected')
        if not hasattr(world, 'water'):
            raise BP.ProfileError('claimed bridge fitting requires the current hydrology authority')
        world.claimed_bridge_profiles={}
        world.claimed_bridge_v7_contracts={}
        world.claimed_bridge_water_authority={}
        world.claimed_bridge_final_water_authority={}
        world.claimed_bridge_protected_nodes=np.empty((0,2),np.int32)
        world.claimed_bridge_fit={
            'sites':[], 'selectedSiteIds':[], 'mutableTerrainVertices':0,
            'changedTerrainVertices':0, 'protectedTerrainVertices':0,
            'authoredTerrainVertices':int(np.count_nonzero(getattr(world, 'authored_terrain_authority', ()))),
            'outsideDeclaredStencilChangedVertices':0, 'waterAuthority':{},
            'maximumCutMetres':0., 'maximumFillMetres':0.}
        return world.claimed_bridge_fit
    if not hasattr(world,'water'):
        raise BP.ProfileError('claimed bridge fitting requires the current hydrology authority')
    landing,lift,clearance=deck_policy(world);reference=np.asarray(world.height,float).copy()
    original_water=world.water;road=road_footprint(world);profiles={};changes={};reports=[]
    support_boxes,colliding_boxes=_retained_footprints(content)
    colliding_objects=[]
    for item in getattr(content,'objects',()) if content is not None else ():
        if not item.get('collides') or item.get('walk'):continue
        low=np.asarray(item.get('low',()),float);high=np.asarray(item.get('high',()),float)
        if (low.shape==(3,) and high.shape==(3,) and np.all(np.isfinite(low[[0,2]]))
                and np.all(np.isfinite(high[[0,2]])) and np.all(high[[0,2]]>low[[0,2]])):
            if not (np.isfinite(low[1]) and np.isfinite(high[1]) and high[1]>=low[1]):
                low=low.copy();high=high.copy();low[1]=-np.inf;high[1]=np.inf
            colliding_objects.append((item.get('node'),low.copy(),high.copy()))
    previous={name:getattr(world,name,None) for name in (
        'claimed_bridge_profiles','claimed_bridge_v7_contracts','claimed_bridge_fit',
        'claimed_bridge_water_authority','claimed_bridge_final_water_authority',
        'claimed_bridge_support_boxes','claimed_bridge_colliding_boxes',
            'claimed_bridge_colliding_objects','claimed_bridge_solid_clearance_sources',
            'claimed_bridge_protected_nodes','claimed_bridge_solid_margin_source_nodes')}
    selections={site['id']:_site_terrain_selection(world,site,landing) for site in sites}
    declared={site_id:selection[-2] for site_id,selection in selections.items()}
    bounds_rows=[selection[-1] for selection in selections.values()]
    support_boxes=_crop_footprints(world,support_boxes,bounds_rows)
    colliding_boxes=_crop_footprints(world,colliding_boxes,bounds_rows)
    colliding_objects=[item for item in colliding_objects if _crop_footprints(
        world,[(item[1][[0,2]],item[2][[0,2]])],bounds_rows)]
    before={site['id']:_encoded_water_authority(world,selections[site['id']][-1]) for site in sites}
    world.claimed_bridge_y_guard=_world_y_guard(world)
    world.claimed_bridge_v7_contracts={}
    world.claimed_bridge_water_authority=before
    world.claimed_bridge_support_boxes=support_boxes
    world.claimed_bridge_colliding_boxes=colliding_boxes
    world.claimed_bridge_colliding_objects=colliding_objects
    world.claimed_bridge_solid_clearance_sources=_site8_solid_clearance_sources(world,content)
    world.claimed_bridge_solid_margin_source_nodes=_site8_known_solid_margin_nodes(world,content)
    source_solids=np.asarray(world.solids,bool).copy()
    try:
        for site in sites:
            roads=sorted(getattr(world,'crossing_site_roads',{}).get(site['id'],()))
            _bridge_progress(world,'fit-site-start',site=int(site['id']),routes=roads)
            try:
                if not _serving_roads(world,site,strict=True):
                    raise BP.ProfileError(f'claimed bridge {site["id"]} has no serving road')
                profile,deltas,report=_joint_site_fit(world,site,road,landing,lift,clearance,reference)
            except Exception as error:
                context=f'claimed bridge site {site["id"]} routes {roads}'
                if hasattr(error,'add_note'):error.add_note(context)
                _bridge_progress(world,'fit-site-failed',site=int(site['id']),routes=roads,
                                 error=f'{type(error).__name__}: {error}')
                raise
            _bridge_progress(world,'fit-site-solved',site=int(site['id']),routes=roads)
            overlap=set(changes)&set(deltas)
            if overlap:raise ValueError(f'claimed bridge {site["id"]} shares graded terrain vertices with another site')
            changes.update(deltas);profiles[site['id']]=profile;reports.append(report)
        changed=reference.copy()
        for node,value in changes.items():changed[node]=reference[node]+value
        authored=np.asarray(getattr(world,'authored_terrain_authority',np.zeros_like(reference,bool)),bool)
        if authored.shape!=reference.shape:
            raise BP.ProfileError('authored terrain authority does not match the claimed-bridge terrain grid')
        if not np.array_equal(changed[authored],reference[authored]):
            raise BP.ProfileError('claimed bridge fitting changed authored terrain authority')
        delta=changed-reference
        if np.any(delta<-ROAD_CUT_METRES) or np.any(delta>ROAD_FILL_METRES):
            raise ValueError('claimed bridge terrain escaped cut/fill bounds')
        permitted=set().union(*declared.values())
        changed_nodes=set(map(tuple,np.argwhere(delta!=0.)))
        if not changed_nodes<=permitted:
            raise BP.ProfileError('claimed bridge grading changed terrain outside its declared stencil')
        world.height=changed;world.claimed_bridge_profiles=profiles
        world.water=L.water_fields(world.gx,world.gz,height=world.height,plan=world.plan)
        _bridge_progress(world,'final-hydrology-regenerated',sites=len(sites))
        after={site['id']:_encoded_water_authority(world,_site_local_bounds(world,site,landing))
               for site in sites}
        water_comparison={}
        for site in sites:
            same,fields=_same_water_authority(before[site['id']],after[site['id']])
            water_comparison[site['id']]={'unchanged':same,'fields':fields,
                'sourceCells':len(after[site['id']]['sourceCells']),
                'encodedWaterTriangles':len(after[site['id']]['faces'])}
            if not same:
                raise BP.ProfileError(f'claimed bridge {site["id"]} grading changed source or encoded water geometry')
        world.claimed_bridge_final_water_authority=after
        for site,report in zip(sites,reports):
            report['waterAuthority']=water_comparison[site['id']]
            report['declaredTerrainStencil']={'bounds':_site_local_bounds(world,site,landing),
                                               'vertices':len(declared[site['id']])}
            _bridge_progress(world,'postcheck-start',site=int(site['id']))
            report['actualGeometry']=_fit_postcheck(world,site,road,landing,lift,clearance,
                                                     profiles[site['id']],changes,
                                                     report['releasedSolidMarginVertices'])
            _bridge_progress(world,'postcheck-finished',site=int(site['id']))
        world.claimed_bridge_protected_nodes=np.asarray(sorted(permitted),np.int32).reshape(-1,2)
        if not np.array_equal(world.solids,source_solids):
            raise BP.ProfileError('claimed bridge fitting changed the routing solid mask')
    except Exception:
        world.height=reference;world.water=original_water
        for name,value in previous.items():
            if value is None:world.__dict__.pop(name,None)
            else:setattr(world,name,value)
        raise
    world.claimed_bridge_fit={'sites':reports,'selectedSiteIds':[site['id'] for site in sites],
                              'mutableTerrainVertices':len(changes),
                               'changedTerrainVertices':int(np.count_nonzero(delta)),
                              'protectedTerrainVertices':len(world.claimed_bridge_protected_nodes),
                              'authoredTerrainVertices':int(np.count_nonzero(authored)),
                              'outsideDeclaredStencilChangedVertices':0,
                              'waterAuthority':water_comparison,
                              'maximumCutMetres':float(np.max(-delta,initial=0.)),
                              'maximumFillMetres':float(np.max(delta,initial=0.))}
    return world.claimed_bridge_fit


def site_arch(world,site,gx,gz,bed,wf,active,landing,lift_limit,clearance,water_fields):
    """One smooth longitudinal arch, constant across a claimed site's width."""
    left,right=np.asarray(site['wetEdges'][0],float),np.asarray(site['wetEdges'][1],float)
    axis=right-left;length=float(np.linalg.norm(axis))
    if length<1e-9:raise BP.ProfileError('claimed bridge has an empty wet span')
    axis/=length;across=np.array([-axis[1],axis[0]])
    distances=(gx-left[0])*axis[0]+(gz-left[1])*axis[1]
    fitted=site['id'] in getattr(world,'claimed_bridge_profiles',{})
    serving=_serving_roads(world,site,strict=fitted)
    contract=getattr(world,'claimed_bridge_v7_contracts',{}).get(site['id'])
    geometry=contract['geometry'] if contract is not None else _claimed_geometry_v7(
        world,site,landing,serving)
    half=float(geometry['nominalHalf'])
    offsets=np.arange(-half,half+1e-9,.5)
    bank_points=np.concatenate((left+axis*geometry['constructionStart']+offsets[:,None]*across,
                                left+axis*geometry['constructionEnd']+offsets[:,None]*across))
    bank_bed=np.asarray(world.height_at(bank_points[:,0],bank_points[:,1]),float).reshape(2,-1)
    bank_water=water_fields(bank_points[:,0],bank_points[:,1],height=bank_bed.reshape(-1),plan=world.plan)
    if np.asarray(bank_water['mask'],bool).any():
        raise BP.ProfileError('bridge does not have a complete dry full-width bank join on both sides')
    deep=np.asarray(wf['mask'],bool)&(np.asarray(wf['depth'])>.35)
    lower=np.where(deep,np.maximum(bed+BP.DRY_CLEARANCE_METRES,np.asarray(wf['surface'])+clearance),
                   bed+BP.DRY_CLEARANCE_METRES)
    dry=active&~np.asarray(wf['mask'],bool)
    # A claimed, named arch may stand above terrain inside its exact span.
    # deck_lift_metres remains a full-width outer-join rule; bank_bounds below
    # enforces it while the interior retains ground nonpenetration.
    upper=np.full_like(bed,np.inf)
    profile=getattr(world,'claimed_bridge_profiles',{}).get(site['id'])
    if profile is None:
        profile=BP.solve_arch(distances[active],lower[active],upper[active],
            start=geometry['constructionStart'],wet_start=0.,wet_end=length,
            end=geometry['constructionEnd'],left_bounds=BP.bank_bounds(bank_bed[0],lift_limit),
            right_bounds=BP.bank_bounds(bank_bed[1],lift_limit),maximum_grade=SOLVE_GRADE,
            crown_metres=BP.arch_rise(length,clearance,SOLVE_GRADE))
    span=_selected_span_outline(serving,geometry,left,axis)
    relevant=active&span.contains(gx,gz)
    height=profile.at(distances[relevant])
    if not fitted and np.any(height<lower[relevant]-1e-8):
        raise BP.ProfileError('stored joint profile no longer fits final terrain/water')
    deck=np.full_like(bed,-np.inf);deck[active]=profile.at(distances[active])
    arch={'profile':profile,'origin':left,'axis':axis,'prepared':fitted,
          'joinStations':[geometry['constructionStart'],geometry['constructionEnd']]}
    return deck,{'shape':'smooth longitudinal arch; flat cross-section','axis':axis.tolist(),
        'bankHeights':[profile.left,profile.right],'crownHeight':profile.crown,
        'crownRiseMetres':profile.crown-max(profile.left,profile.right)},arch


def landing_cut(mask,cut,dry_cells):
    """The cells one landing trim removes from a deck: its lifted cells and every cell they part from the water.

    A landing ends at its first lifted cell. Cells beyond it that no longer share a cell edge, through the rest of
    the deck, with a cell over the water (one with a vertex that is not dry) would stand as a floor of their own,
    joined to the span through a cell corner at most, which nobody walks: they go with the cut, so a trim never
    leaves a deck in pieces. ``mask``, ``cut`` and ``dry_cells`` are the component's cell grids.
    """
    kept=mask&~cut
    parts,_=label(kept,structure=CROSS)
    wet=np.unique(parts[kept&~dry_cells])
    return mask&~np.isin(parts,wet[wet>0])


def _bridge_cell_authority(world,water_fields):
    """One mask authority shared by loose inventory and final surface export."""
    landing,_,_=deck_policy(world)
    outline=RoadOutline(world);road=road_footprint(world);rows,cols=np.nonzero(road)
    x=world.x0+(cols+.5)*CELL;z=world.z0+(rows+.5)*CELL
    ground=world.height_at(x,z);water=water_fields(x,z,height=ground,plan=world.plan)
    # Conservative shoulder cells must not invent a bridge on a dry road
    # merely because nearby water reaches an invisible grid-cell centre.
    inside=outline.contains(x,z)
    wet=np.zeros_like(road);wet[rows,cols]=water['mask']&(water['depth']>.35)&inside
    river=np.zeros_like(road)
    if 'river_mask' in water:river[rows,cols]=np.asarray(water['river_mask'],bool)&inside
    sites=list(getattr(world,'crossing_sites',[]));site_cells={};spanned=np.zeros_like(road)
    for site in sites:
        fitted=site['id'] in getattr(world,'claimed_bridge_profiles',{})
        if fitted:
            roads=_serving_roads(world,site,strict=True)
            if not roads:raise BP.ProfileError(f'claimed bridge {site["id"]} has no serving road')
            geometry=getattr(world,'claimed_bridge_v7_contracts',{})[site['id']]['geometry']
            for side,station in zip(('left','right'),
                                    (geometry['constructionStart'],geometry['constructionEnd'])):
                expected=_contract_join_intervals(world,site,station,geometry)
                _require_join_coverage(expected,expected,0.,side)
            serving_world=SimpleNamespace(roads=_guarded_serving_roads(roads,geometry),
                                          x0=world.x0,z0=world.z0,x1=world.x1,z1=world.z1)
            site_left,_,site_axis,_,_=_site_frame(site)
            span=_selected_span_outline(roads,geometry,site_left,site_axis)
            cells=_selected_span_cells(serving_world,site,geometry,span)
        else:cells=site_span_cells(world,site,road,landing)
        if cells.any():site_cells[site['id']]=cells;spanned|=cells
    return {'outline':outline,'road':road,'wet':wet,'river':river,'sites':sites,
            'siteCells':site_cells,'spanned':spanned,'loose':wet&~spanned}


def loose_crossing_inventory(world, *, water_fields=None):
    """Read-only complete loose-wet components and their stable road bindings.

    Cell indices are flattened against the current road-cell grid.  A road is
    bound only where its complete authored-width capsule contains a wet cell
    centre, using the same exact outline test as ``common_surface``.
    """
    authority=_bridge_cell_authority(world,water_fields or L.water_fields)
    loose=authority['loose'];labels,count=label(loose,structure=np.ones((3,3)))
    width=loose.shape[1];components=[]
    road_outlines=[]
    for road in world.roads:
        road_id=road.get('id')
        if not road_id:raise BP.ProfileError('loose crossing inventory requires stable road ids')
        road_outlines.append((str(road_id),RoadOutline(SimpleNamespace(roads=[road]))))
    for number in range(1,count+1):
        rows,cols=np.nonzero(labels==number)
        if not len(rows):continue
        flat=np.sort(rows*width+cols).astype(np.int64)
        x=world.x0+(cols+.5)*CELL;z=world.z0+(rows+.5)*CELL
        bindings=[]
        for road_id,outline in road_outlines:
            selected=np.asarray(outline.contains(x,z),bool)
            if selected.any():
                bindings.append({'roadId':road_id,
                                 'looseWetCells':tuple(map(int,np.sort(flat[selected])))})
        bindings.sort(key=lambda item:item['roadId'])
        if not bindings:
            raise BP.ProfileError('loose wet component has no exact full-width road binding')
        components.append({'componentSeed':int(flat[0]),
                           'looseWetCells':tuple(map(int,flat)),
                           'roadIds':tuple(item['roadId'] for item in bindings),
                           'fullWidthWaterRoadIds':tuple(item['roadId'] for item in bindings),
                           'fullWidthWaterCells':tuple(bindings),
                           'bounds':[int(rows.min()),int(rows.max()+1),
                                     int(cols.min()),int(cols.max()+1)]})
    components.sort(key=lambda item:item['componentSeed'])
    indices=tuple(map(int,np.flatnonzero(loose)))
    covered={cell for component in components for cell in component['looseWetCells']}
    if covered!=set(indices):raise BP.ProfileError('loose component inventory is incomplete')
    return {'looseWetCellIndices':indices,'components':tuple(components),
            'shape':tuple(map(int,loose.shape))}


def common_surface(world, *, water_fields=None, maximum_extension=None):
    """One deck field over every bridge the roads need, clipped later to the road capsule union.

    A bridge deck is a crossing site's span (river_crossings: the wet width at a claimed site) plus landings of at
    most ``crossing_policy.deck_landing_metres`` on each bank, over the road cells there; deep water a road crosses
    anywhere else (a sea channel between islands) gets the same deck: its wet cells plus that landing. Nothing else
    is decked: the approach aprons, the connection aprons, the bank growth and the floating-run spans of earlier
    publications are retired (``maximum_extension`` is accepted and ignored). A deck stands on the water clearance,
    on one smooth longitudinal arch with a flat cross-section. Both complete dry-bank joins must fit the existing
    grade policy and the outer joins' lift policy; an infeasible claimed site fails instead of losing a landing.
    Inside its exact named span an arch may rise over dry bank terrain. Loose sea-channel decks keep the earlier
    per-dry-vertex common-floor solver until their road-tangent runs are represented explicitly.
    """
    water_fields=water_fields or L.water_fields
    landing,lift_limit,clearance=deck_policy(world)
    authority=_bridge_cell_authority(world,water_fields)
    outline=authority['outline'];road=authority['road'];wet=authority['wet'];river=authority['river']
    sites=authority['sites'];site_cells=authority['siteCells'];spanned=authority['spanned']
    # Deep water a road crosses away from every site: its own wet cells plus the landing.
    loose=authority['loose']
    prepared_coast=hasattr(world,'claimed_coastal_records')
    selected_mask=np.zeros_like(loose);prepared_cells=();fallback_cells=tuple(map(int,np.flatnonzero(loose)))
    if prepared_coast:
        selected_mask,prepared_cells,fallback_cells=C.prepared_footprint_mask(
            world,tuple(map(int,np.flatnonzero(loose))),loose.shape,world.x0,world.z0,CELL)
        fallback=loose.copy();fallback.flat[list(prepared_cells)]=False
        if np.any(fallback&selected_mask):
            raise ValueError('prepared coastal floor intersects an unselected loose wet cell')
        cells=fallback
    else:cells=loose.copy()
    for _ in range(int(math.ceil(landing/CELL))):
        cells=binary_dilation(cells,structure=CROSS)&road&~selected_mask
    cells|=spanned
    stray_river=river&wet&~spanned
    final=np.full((road.shape[0]+1,road.shape[1]+1),np.nan)
    # A deck lifts at most deck_lift_metres over dry ground: a landing cell the solved deck would carry higher over
    # its bank is left to the graded road, and the deck is solved again without it (a steep bank ends the landing,
    # and the landing cells beyond it go too: landing_cut).
    trimmed=0;cut_off=0;cut_banks=[]
    for attempt in range(TRIM_PASSES+1):
        final.fill(np.nan)
        labels,count=label(cells,structure=np.ones((3,3)))
        frontier=frontier_vertices(cells,road)
        components=[];maximum_bank_error=0.;worst_bank=None;lift_reports=[];next_loose=500;trim=np.zeros_like(cells)
        for component,sl in enumerate(find_objects(labels),1):
            if sl is None:continue
            iz0,iz1=sl[0].start,sl[0].stop;ix0,ix1=sl[1].start,sl[1].stop
            mask=labels[sl]==component;active=vertices_for_cells(mask)
            gx,gz=np.meshgrid(world.x0+np.arange(ix0,ix1+1)*CELL,world.z0+np.arange(iz0,iz1+1)*CELL)
            bed=world.height_at(gx,gz)
            wf=water_fields(gx,gz,height=bed,plan=world.plan)
            water_vertices=wf['mask']&(wf['depth']>.35)
            members=sorted(site_id for site_id,site_mask in site_cells.items() if (site_mask[sl]&mask).any())
            profile_report={};arch=None
            if len(members)>1:
                raise ValueError(f'Bridge component joins claimed sites {members}; a shared junction profile is required')
            prepared=bool(members and members[0] in getattr(world,'claimed_bridge_profiles',{}))
            if prepared:
                site=next(site for site in sites if site['id']==members[0])
                try:deck,profile_report,arch=site_arch(world,site,gx,gz,bed,wf,active,landing,lift_limit,clearance,water_fields)
                except BP.ProfileError as error:raise ValueError(f"Bridge site {site['id']} ({site.get('key','unnamed')}) cannot meet both banks: {error}") from error
            else:
                lower=np.where(water_vertices,np.maximum(bed+.025,wf['surface']+.85),bed+.025)
                deck=bounded_floor(bank_profile(lower,active,water_vertices),active)
            dry=active&~wf['mask'];component_outline=outline;component_geometry=None
            if prepared:
                left,_,axis,_,length=_site_frame(site)
                component_roads=_serving_roads(world,site,strict=site['id'] in getattr(world,'claimed_bridge_profiles',{}))
                component_half=max(float(road['width']) for road in component_roads)
                contract=getattr(world,'claimed_bridge_v7_contracts',{}).get(site['id'])
                geometry=contract['geometry'] if contract is not None else _claimed_geometry_v7(
                    world,site,landing,component_roads)
                component_geometry=geometry
                component_outline=_selected_span_outline(component_roads,geometry,left,axis)
                dry&=component_outline.contains(gx,gz)
            lifted=dry&(deck-bed>lift_limit+1e-9)
            if not prepared and lifted.any() and attempt<TRIM_PASSES:
                corners=dry[:-1,:-1]&dry[1:,:-1]&dry[:-1,1:]&dry[1:,1:]
                touching=lifted[:-1,:-1]|lifted[1:,:-1]|lifted[:-1,1:]|lifted[1:,1:]
                cut=mask&corners&touching
                if cut.any() and (mask&~cut&~corners).any():
                    removed=landing_cut(mask,cut,corners)
                    view=trim[sl];view|=removed
                    beyond=removed&~cut
                    if beyond.any():
                        cut_off+=int(beyond.sum())
                        rr,cc=np.nonzero(cut&binary_dilation(beyond,structure=CROSS))
                        if len(rr):cut_banks.append([round(float(world.x0+(ix0+cc.mean()+.5)*CELL),1),round(float(world.z0+(iz0+rr.mean()+.5)*CELL),1)])
            bank=frontier[iz0:iz1+1,ix0:ix1+1]&active
            error=float(np.max(deck[bank]-bed[bank],initial=0))
            if bank.any() and error>=maximum_bank_error:
                worst=int(np.argmax(np.where(bank,deck-bed,-np.inf)))
                worst_bank=(float(gx.ravel()[worst]),float(gz.ravel()[worst]))
            maximum_bank_error=max(maximum_bank_error,error)
            identity=members[0]+1 if members else next_loose
            if not members:next_loose+=1
            maximum_dry_gap=round(float(np.max((deck-bed)[dry],initial=0)),3)
            report={'component':identity,'sites':members,'cells':int(mask.sum()),'bankErrorMetres':round(error,3),
                    **profile_report}
            if prepared:
                report.update(maximumInteriorDryGapMetres=maximum_dry_gap,
                              interiorDryGapAboveOuterJoinLimitVertices=int(lifted.sum()),
                              deckLiftPolicyAppliesAtOuterJoins=True)
            else:
                report.update(dryLiftOverLimitVertices=int(lifted.sum()),maximumDryLiftMetres=maximum_dry_gap)
            if lifted.any():
                where=int(np.argmax(np.where(lifted,deck-bed,-np.inf)))
                report['worstDryLift']=[round(float(gx.ravel()[where]),1),round(float(gz.ravel()[where]),1)]
            lift_reports.append(report)
            view=final[iz0:iz1+1,ix0:ix1+1];view[active]=deck[active]
            components.append({'id':identity,'sites':members,'slice':sl,'cells':mask,'height':deck,'bankError':error,
                               'water':water_vertices,'arch':arch,'outline':component_outline,
                               'geometry':component_geometry})
        if not trim.any():break
        cells=cells&~trim;trimmed+=int(trim.sum())
    for component in components:component.setdefault('outline',outline)
    stray=[]
    if stray_river.any():
        zs,xs=np.nonzero(stray_river)
        stray=[[round(float(world.x0+(c+.5)*CELL),1),round(float(world.z0+(r+.5)*CELL),1)] for r,c in list(zip(zs,xs))[::25]]
    field={'x0':world.x0,'z0':world.z0,'cell':CELL,'mask':cells,'height':final,'components':components,'outline':outline,
            'wetCells':int(wet.sum()),'siteCells':int(spanned.sum()),'looseWetCells':int(loose.sum()),
            'looseWetCellIndices':tuple(map(int,np.flatnonzero(loose))),
            'preparedLooseWetCellIndices':tuple(prepared_cells),
            'legacyLooseWetCellIndices':tuple(fallback_cells),
            'riverWaterOutsideSites':{'cells':int(stray_river.sum()),'at':stray},
            'maximumBankError':maximum_bank_error,'worstBank':worst_bank,'deckLandingMetres':landing,'deckLiftMetres':lift_limit,
            'deckClearanceMetres':clearance,
            'trimmedLandingCells':trimmed,'cutOffLandingCells':cut_off,'cutOffLandingBanks':cut_banks,'decks':lift_reports}
    if hasattr(world,'claimed_coastal_records'):
        field=C.replace_legacy_loose_components(world,field)
    return field



def _prepared_surface_at(world,component,x,z):
    """Look up the exact emitted float32 floor triangles for a prepared deck."""
    mesh,_=_prepared_deck_mesh(world,component)
    cached=component.get('_preparedQueryCache')
    if cached is None:
        faces=np.asarray(mesh.positions[mesh.indices.reshape(-1,3)],float)
        polygons=SH.polygons(faces[:,:,[0,2]])
        bins={}
        for index,face in enumerate(faces):
            xz=face[:,[0,2]];low=np.floor(xz.min(axis=0)/8.).astype(int);high=np.floor(xz.max(axis=0)/8.).astype(int)
            for ix in range(low[0],high[0]+1):
                for iz in range(low[1],high[1]+1):bins.setdefault((ix,iz),[]).append(index)
        cached=(faces,polygons,{key:tuple(value) for key,value in bins.items()})
        component['_preparedQueryCache']=cached
    faces,polygons,bins=cached
    x,z=np.broadcast_arrays(np.asarray(x,float),np.asarray(z,float));shape=x.shape
    points=np.c_[x.ravel(),z.ravel()];covered=np.zeros(len(points),bool);height=np.full(len(points),-np.inf)
    for point_index,point in enumerate(points):
        key=tuple(np.floor(point/8.).astype(int))
        for face_index in bins.get(key,()):
            face=faces[face_index];xz=face[:,[0,2]]
            if np.any(point<xz.min(axis=0)) or np.any(point>xz.max(axis=0)):continue
            # GEOS' robust predicate includes the exact encoded triangle boundary.
            # Divided barycentric comparisons can reject a shared vertex when an
            # otherwise exact solution rounds to 1+1 ULP or -1 ULP.
            if not SH.intersects_xy(polygons[face_index],point[0],point[1]):continue
            height[point_index]=_triangle_height(face,point);covered[point_index]=True;break
    return covered.reshape(shape),height.reshape(shape)


def surface_at(world,x,z,field=None):
    """Exact same grid diagonal as emitted decks, including shared edges."""
    field=field if field is not None else world.bridge_field
    x,z=np.broadcast_arrays(np.asarray(x,float),np.asarray(z,float))
    terrain=np.asarray(world.height_at(x,z),float)
    result=terrain.copy()
    fx=(x-field['x0'])/CELL;fz=(z-field['z0'])/CELL
    base_x=np.floor(fx).astype(int);base_z=np.floor(fz).astype(int)
    mask=field['mask'];h=field['height']
    arch_cells=np.zeros_like(mask)
    for component in field.get('components',()):
        if component.get('arch') is not None:
            view=arch_cells[component['slice']];view|=component['cells']
    # A visible GLB contour vertex can round a few ten-thousandths of a metre
    # across its analytic boundary. Keep lookup on that same encoded floor.
    inside=field['outline'].contains(x,z,tolerance=2e-4) if 'outline' in field else True
    for dx,dz in ((0,0),(-1,0),(0,-1),(-1,-1)):
        ix,iz=base_x+dx,base_z+dz;u,v=fx-ix,fz-iz
        valid=(ix>=0)&(iz>=0)&(ix<mask.shape[1])&(iz<mask.shape[0])&(u>=0)&(u<=1)&(v>=0)&(v<=1)
        cx=np.clip(ix,0,mask.shape[1]-1);cz=np.clip(iz,0,mask.shape[0]-1)
        valid&=mask[cz,cx]&~arch_cells[cz,cx]&inside
        a,b,c,d=h[cz,cx],h[cz,cx+1],h[cz+1,cx],h[cz+1,cx+1]
        y=np.where(u+v<=1,a+(b-a)*u+(c-a)*v,d+(c-d)*(1-u)+(b-d)*(1-v))
        result=np.where(valid,np.maximum(result,y),result)
    # Prepared claimed decks query the same actual float32 triangles emitted by
    # deck_mesh. The conservative grid below remains only for legacy arches.
    for component in field.get('components',()):
        arch=component.get('arch')
        if arch is None:continue
        if arch.get('prepared',False):
            covered,height=_prepared_surface_at(world,component,x,z)
            result=np.where(covered,np.maximum(terrain,height),result)
            continue
        sl=component['slice'];component_mask=component['cells'];covered=np.zeros(x.shape,bool)
        component_outline=component.get('outline') or field['outline']
        component_inside=component_outline.contains(x,z,tolerance=2e-4)
        local_x=fx-sl[1].start;local_z=fz-sl[0].start
        bx,bz=np.floor(local_x).astype(int),np.floor(local_z).astype(int)
        for dx,dz in ((0,0),(-1,0),(0,-1),(-1,-1)):
            ix,iz=bx+dx,bz+dz;u,v=local_x-ix,local_z-iz
            valid=(ix>=0)&(iz>=0)&(ix<component_mask.shape[1])&(iz<component_mask.shape[0])&(
                u>=0)&(u<=1)&(v>=0)&(v<=1)
            cx=np.clip(ix,0,component_mask.shape[1]-1);cz=np.clip(iz,0,component_mask.shape[0]-1)
            covered|=valid&component_mask[cz,cx]&component_inside
        distance=(x-arch['origin'][0])*arch['axis'][0]+(z-arch['origin'][1])*arch['axis'][1]
        analytic=arch_height(arch,distance)
        result=np.where(covered,np.maximum(terrain,analytic),result)
    return result


def encoded_floor_vertices(world,component,xz):
    """Encode XZ first, then lift that exact point onto the common floor.

    Independent XYZ rounding changes the grade of a thin clipped face. One
    shared height for every encoded XZ also keeps neighbouring source planes
    joined when rounding moves an outline intersection across their diagonal.
    """
    xz=np.asarray(xz,dtype=np.float32).astype(float)
    sl=component['slice'];mask=component['cells'];h=component['height']
    fx=(xz[:,0]-world.x0)/CELL-sl[1].start
    fz=(xz[:,1]-world.z0)/CELL-sl[0].start
    bx,bz=np.floor(fx).astype(int),np.floor(fz).astype(int)
    y=np.full(len(xz),np.nan)
    for dx,dz in ((0,0),(-1,0),(0,-1),(-1,-1)):
        ix,iz=bx+dx,bz+dz;u,v=fx-ix,fz-iz
        valid=(ix>=0)&(iz>=0)&(ix<mask.shape[1])&(iz<mask.shape[0])&(u>=0)&(u<=1)&(v>=0)&(v<=1)
        cx=np.clip(ix,0,mask.shape[1]-1);cz=np.clip(iz,0,mask.shape[0]-1)
        valid&=mask[cz,cx]&~np.isfinite(y)
        selected=np.flatnonzero(valid)
        cx,cz,u,v=cx[selected],cz[selected],u[selected],v[selected]
        a,b,c,d=h[cz,cx],h[cz,cx+1],h[cz+1,cx],h[cz+1,cx+1]
        y[selected]=np.where(u+v<=1,a+(b-a)*u+(c-a)*v,d+(c-d)*(1-u)+(b-d)*(1-v))
    if not np.isfinite(y).all():raise ValueError('Encoded bridge outline left its common support floor')
    return np.c_[xz[:,0],y.astype(np.float32).astype(float),xz[:,1]]


def arch_height(arch,distance):
    """The one component-wide piecewise-linear longitudinal floor."""
    return arch['profile'].at(distance)


def arch_station_slices(polygon,arch):
    """Cut every outline polygon at the same component-wide breaklines."""
    axis=np.asarray(arch['axis'],float);origin=np.asarray(arch['origin'],float)
    across=np.array([-axis[1],axis[0]])
    station=(polygon[:,[0,2]]-origin)@axis
    low_polygon,high_polygon=float(station.min()),float(station.max())
    interior=np.asarray(arch['profile'].stations)
    interior=interior[(interior>low_polygon+1e-8)&(interior<high_polygon-1e-8)]
    values=np.r_[low_polygon,interior,high_polygon]
    pieces=[]
    for low,high in zip(values,values[1:]):
        a=origin+axis*low;b=origin+axis*high
        piece=_clip_halfplane(polygon,a,a-across)
        if len(piece):piece=_clip_halfplane(piece,b,b+across)
        if not len(piece):continue
        distance=(piece[:,[0,2]]-origin)@axis
        piece[:,1]=arch_height(arch,distance)
        pieces.append(piece)
    return pieces


def _encoded_loop(loop):
    """One exact float32 boundary loop without redundant encoded vertices."""
    points=np.asarray(loop,float)[:,[0,2]].astype(np.float32).astype(float)
    changed=True
    while changed and len(points)>=3:
        changed=False;keep=[]
        for index in range(len(points)):
            a,b,c=points[index-1],points[index],points[(index+1)%len(points)]
            if np.array_equal(a,b):changed=True;continue
            cross=(b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0])
            if cross==0. and np.dot(b-a,c-b)>=0.:changed=True;continue
            keep.append(index)
        points=points[keep]
    if len(points)<3:return np.empty((0,2))
    return points


def _split_index_polygon(indices,vertices,origin,axis,station,cache,station_index,overrides):
    """Split a convex indexed polygon once, sharing every edge intersection."""
    indices=list(indices);distance=(np.asarray(vertices)[indices]-origin)@axis-float(station)
    low=[];high=[]
    for position,current in enumerate(indices):
        previous=indices[position-1];before=distance[position-1];after=distance[position]
        if before*after<0.:
            edge=tuple(sorted((previous,current)));key=(int(station_index),*edge)
            if key not in cache:
                a,b=edge;da=float((vertices[a]-origin)@axis-station)
                db=float((vertices[b]-origin)@axis-station)
                point=vertices[a]+da/(da-db)*(vertices[b]-vertices[a])
                cache[key]=len(vertices);vertices.append(point);overrides.append(float(station))
            intersection=cache[key];low.append(intersection);high.append(intersection)
        if after<=0.:low.append(current)
        if after>=0.:high.append(current)
    def clean(values):
        result=[]
        for value in values:
            if not result or value!=result[-1]:result.append(value)
        if len(result)>1 and result[0]==result[-1]:result.pop()
        return result
    return clean(low),clean(high)


def _encoded_collinear_forward(a,b,c):
    a,b,c=np.asarray((a,b,c),dtype=np.float64)
    ab=b-a;bc=c-b
    return ab[0]*bc[1]-ab[1]*bc[0]==0. and np.dot(ab,bc)>=0.


def _shapely_selected_union_uv(roads,geometry,origin,axis,width_guard,start,end,half):
    """Selected capsule union in intrinsic coordinates, clipped by one exact box."""
    expanded=[{**road,'width':float(road['width'])+float(width_guard)} for road in roads]
    outline=RoadOutline(SimpleNamespace(roads=expanded))
    selected=_selected_outline(outline,geometry['servingSegmentIndices'],geometry['servingSegmentXZ'])
    origin=np.asarray(origin,float);axis=np.asarray(axis,float);across=np.array([-axis[1],axis[0]])
    polygons=[]
    for polygon in selected.polygons:
        delta=np.asarray(polygon,float)-origin
        candidate=SH.Polygon(np.c_[delta@axis,delta@across])
        if not candidate.is_empty and candidate.area>0.:polygons.append(candidate)
    if not polygons:raise BP.ProfileError('selected serving-road union is empty')
    union=SH.union_all(polygons)
    clipped=union.intersection(SH.box(float(start),-float(half),float(end),float(half)))
    if clipped.is_empty or clipped.area<=0. or not clipped.is_valid:
        raise BP.ProfileError('selected serving-road union is not a valid positive polygon')
    return clipped


def _positive_shapely_polygons(geometry):
    return [part for part in SH.get_parts(geometry)
            if part.geom_type=='Polygon' and not part.is_empty and part.area>0.]


def _prepared_floor_set_certificate(world,site,faces,geometry):
    """Require nominal road set subset actual encoded floor subset allowed guard."""
    origin,_,axis,_,_=_site_frame(site);across=np.array([-axis[1],axis[0]])
    roads=_serving_roads(world,site,strict=True)
    nominal=_shapely_selected_union_uv(
        roads,geometry,origin,axis,0.,geometry['nominalStart'],geometry['nominalEnd'],
        geometry['nominalHalf'])
    allowed=_shapely_selected_union_uv(
        roads,geometry,origin,axis,geometry['allowedRoadCapsuleGuardMetres'],
        geometry['policyStart'],geometry['policyEnd'],geometry['allowedCrossHalf'])
    faces=np.asarray(faces,float);actual_triangles=[]
    for face in faces:
        delta=face[:,[0,2]]-origin
        triangle=SH.Polygon(np.c_[delta@axis,delta@across])
        if triangle.is_empty or triangle.area<=0. or not triangle.is_valid:
            raise BP.ProfileError('actual encoded floor contains a nonpositive polygon')
        actual_triangles.append(triangle)
    actual=SH.union_all(actual_triangles)
    missing=nominal.difference(actual);extra=actual.difference(allowed)
    tree=SH.STRtree(actual_triangles);overlaps=[]
    for first,triangle in enumerate(actual_triangles):
        for second in tree.query(triangle,predicate='intersects'):
            second=int(second)
            if second<=first:continue
            area=float(triangle.intersection(actual_triangles[second]).area)
            if area>0.:overlaps.append({'faces':[first,second],'areaSquareMetres':area})
    if not missing.is_empty:
        raise BP.ProfileError(f'actual encoded floor misses nominal road union: {missing.wkt}')
    if not extra.is_empty:
        raise BP.ProfileError(f'actual encoded floor escapes allowed road guard: {extra.wkt}')
    if overlaps:
        raise BP.ProfileError(f'actual encoded floor has positive triangle overlaps: {overlaps}')
    return {'complete':True,'nominalAreaSquareMetres':float(nominal.area),
            'actualAreaSquareMetres':float(actual.area),'allowedAreaSquareMetres':float(allowed.area),
            'positiveFaceOverlaps':0,'nominalUncovered':False,'actualOutsideAllowedGuard':False}


def _prepared_deck_mesh(world,component):
    """Build one shared encoded road-union mesh, then split it at profile stations."""
    cached=component.get('_preparedMeshCache')
    if cached is not None:return cached
    arch=component['arch'];profile=arch['profile'];outline=component['outline']
    origin=np.asarray(arch['origin'],float);axis=np.asarray(arch['axis'],float)
    across=np.array([-axis[1],axis[0]])
    half=float(getattr(outline,'half',None) or max(segment[4] for segment in outline.base.segments))
    low,high=float(profile.stations[0]),float(profile.stations[-1])
    geometry=component['geometry']
    # ``outline.base`` is already the exact selected, guarded capsule set.
    # Give its stable segment order a local identity so the shared GEOS helper
    # can build one union without reintroducing disconnected serving roads.
    selected_roads=[{'id':f'prepared-{index}','width':float(segment[4]),
                     'points':[[segment[0],0.,segment[1]],[segment[2],0.,segment[3]]]}
                    for index,segment in enumerate(outline.base.segments)]
    selected_geometry={**geometry,'servingSegmentIndices':list(range(len(selected_roads))),
                       'servingSegmentXZ':outline.base.segments[:,:4].tolist()}
    span_uv=_shapely_selected_union_uv(
        selected_roads,selected_geometry,origin,axis,0.,low,high,half)
    source_xz=[];source_triangles=[];encoded_uv_to_xz={};collapsed_source_triangles=0
    def encoded_ring(coordinates):
        coordinates=np.asarray(coordinates,float)
        xz=(origin+coordinates[:,0,None]*axis+coordinates[:,1,None]*across).astype(np.float32)
        keep=np.any(xz!=np.roll(xz,1,axis=0),axis=1);xz=xz[keep]
        if len(xz)<3:return None
        uv=np.c_[(xz.astype(float)-origin)@axis,(xz.astype(float)-origin)@across]
        for point,encoded in zip(uv,xz):encoded_uv_to_xz[tuple(point)]=encoded
        return uv
    for band_low,band_high in zip(profile.stations,profile.stations[1:]):
        band=span_uv.intersection(SH.box(float(band_low),-half,float(band_high),half))
        for polygon in _positive_shapely_polygons(band):
            exterior=encoded_ring(np.asarray(polygon.exterior.coords[:-1],float))
            holes=[ring for interior in polygon.interiors
                   if (ring:=encoded_ring(np.asarray(interior.coords[:-1],float))) is not None]
            if exterior is None:continue
            encoded_polygon=SH.Polygon(exterior,holes)
            if not encoded_polygon.is_valid:encoded_polygon=SH.make_valid(encoded_polygon)
            for positive in _positive_shapely_polygons(encoded_polygon):
                triangles=SH.constrained_delaunay_triangles(positive)
                for triangle in SH.get_parts(triangles):
                    if triangle.geom_type!='Polygon' or triangle.is_empty or triangle.area<=0.:continue
                    coordinates=np.asarray(triangle.exterior.coords[:-1],float)
                    if len(coordinates)!=3:
                        raise BP.ProfileError('constrained road triangulation emitted a nontriangle')
                    encoded=[]
                    for point in coordinates:
                        value=encoded_uv_to_xz.get(tuple(point))
                        if value is None:
                            value=(origin+point[0]*axis+point[1]*across).astype(np.float32)
                            actual=np.array([(value.astype(float)-origin)@axis,
                                             (value.astype(float)-origin)@across])
                            encoded_uv_to_xz[tuple(actual)]=value
                        encoded.append(value)
                    encoded=np.asarray(encoded,np.float32)
                    if len(np.unique(encoded,axis=0))<3:
                        collapsed_source_triangles+=1;continue
                    actual_uv=np.c_[(encoded.astype(float)-origin)@axis,
                                    (encoded.astype(float)-origin)@across]
                    signed=np.sum(actual_uv[:,0]*np.roll(actual_uv[:,1],-1)-
                                  actual_uv[:,1]*np.roll(actual_uv[:,0],-1))
                    if signed==0.:collapsed_source_triangles+=1;continue
                    if signed>0.:encoded=encoded[::-1].copy()
                    start=len(source_xz);source_xz.extend(encoded)
                    source_triangles.append([start,start+1,start+2])
    if not source_triangles:
        raise BP.ProfileError('prepared claimed bridge emitted no constrained floor triangles')
    source_xz=np.asarray(source_xz,np.float32)
    encoded_xz,vertex_remap=np.unique(source_xz,axis=0,return_inverse=True)
    source_station=(source_xz.astype(float)-origin)@axis
    encoded_station=_arch_vertex_stations(encoded_xz,origin,axis,arch.get('joinStations',(low,high)))
    encoded_y=profile.at(encoded_station).astype(np.float32)
    remap=vertex_remap[np.asarray(source_triangles,np.int32)]
    if np.any((remap[:,0]==remap[:,1])|(remap[:,1]==remap[:,2])|(remap[:,2]==remap[:,0])):
        raise BP.ProfileError('prepared constrained floor collapsed during float32 encoding')
    positions=np.c_[encoded_xz[:,0],encoded_y.astype(float),encoded_xz[:,1]]
    faces=positions[remap]
    normal=np.cross(faces[:,1]-faces[:,0],faces[:,2]-faces[:,0])
    if np.any(normal[:,1]<=0):raise BP.ProfileError('reconstructed encoded road union has nonpositive floor')
    if np.any(np.hypot(normal[:,0],normal[:,2])>GRADE*normal[:,1]):
        raise BP.ProfileError('prepared intrinsic floor exceeds encoded grade')
    site_id=int(component['sites'][0])
    site=next(row for row in world.crossing_sites if int(row['id'])==site_id)
    component['spatialSetCertificate']=_prepared_floor_set_certificate(world,site,faces,geometry)
    owners=np.asarray(world.owner_at(faces[:,:,0].mean(axis=1),faces[:,:,2].mean(axis=1)),int)
    mesh=M.Mesh(positions=positions,normals=np.tile([0.,1.,0.],(len(positions),1)),
        uvs=positions[:,[0,2]]*.25,indices=remap.ravel(),material='bridge_timber')
    mesh.recompute_normals(180);component['precisionCleanupArea']=0.
    component['topology']='shared-encoded-road-union-station-bands'
    component['encodedDegenerateBoundaryVerticesReconstructed']=collapsed_source_triangles
    component['sourceStationProvenance']=source_station.tolist()
    component['encodedVertexStations']=encoded_station.tolist()
    component['_preparedMeshCache']=(mesh,owners)
    return component['_preparedMeshCache']


def _component_source_triangles(world,component):
    """Return grid triangles and their inherited territory owners.

    ``deck_mesh`` deliberately attributes every clipped descendant to the
    source cell centre.  Keeping that rule in one helper lets saved-territory
    authority prove that an entire loose component is replaceable before the
    expensive road-union clipping pass.
    """
    sl=component['slice'];mask=component['cells'];heights=component['height']
    gx,gz=np.meshgrid(world.x0+np.arange(sl[1].start,sl[1].stop+1)*CELL,
                      world.z0+np.arange(sl[0].start,sl[0].stop+1)*CELL)
    row,col=np.nonzero(mask);a=row*gx.shape[1]+col;b=a+1;c=a+gx.shape[1];d=c+1
    indices=np.c_[a,c,b,b,c,d].reshape(-1,3)
    vertices=np.c_[gx.ravel(),heights.ravel(),gz.ravel()]
    centers=np.c_[world.x0+(sl[1].start+col+.5)*CELL,world.z0+(sl[0].start+row+.5)*CELL]
    owners=np.repeat(world.owner_at(centers[:,0],centers[:,1]).astype(int),2)
    return vertices,indices,owners


def _component_has_road_width_face(world,component,vertices,indices):
    """Cheaply preserve the existing empty-deck failure before suppression."""
    outline=component.get('outline') or RoadOutline(world)
    arch=component.get('arch')
    for triangle in vertices[indices]:
        for polygon in outline.clip(triangle):
            pieces=arch_station_slices(polygon,arch) if arch is not None else [polygon]
            for piece in pieces:
                for face in triangulate_floor(piece,minimum_area=(
                        0. if arch is not None and arch.get('prepared',False)
                        else NEGLIGIBLE_FLOOR_AREA),
                        normalize=not (arch is not None and arch.get('prepared',False))):
                    if abs(_area_xz(face))>=1e-8:return True
    return False


def _suppresses_generated_authored_component_before_mesh(world,component,authored_owners):
    """Prove the existing loose-component suppression without building it."""
    if component.get('sites'):return False
    vertices,indices,owners=_component_source_triangles(world,component)
    if not _suppresses_generated_authored_component(component,owners,authored_owners):return False
    # An empty clip currently fails in deck_mesh.  Only skip after finding one
    # face accepted by the same clip and triangulation rules; otherwise retain
    # that validation by falling through to the full mesh path.
    return _component_has_road_width_face(world,component,vertices,indices)


def deck_mesh(world,component):
    if component.get('arch') is not None and component['arch'].get('prepared',False):
        return _prepared_deck_mesh(world,component)
    vertices,indices,owners=_component_source_triangles(world,component)
    outline=component.get('outline') or RoadOutline(world)
    arch=component.get('arch')
    clipped=[]
    for triangle,owner in zip(vertices[indices],owners):
        for polygon in outline.clip(triangle):
            clipped.append((polygon,owner))
    triangles=[];clipped_owners=[];areas=[]
    for polygon,owner in clipped:
        pieces=arch_station_slices(polygon,arch) if arch is not None else [polygon]
        for piece in pieces:
            for face in triangulate_floor(piece,minimum_area=(0. if arch is not None and arch.get('prepared',False)
                                                              else NEGLIGIBLE_FLOOR_AREA),
                                          normalize=not (arch is not None and arch.get('prepared',False))):
                area=abs(_area_xz(face))
                if area<1e-8:continue
                triangles.append(face);clipped_owners.append(owner);areas.append(area)
    if not triangles:raise ValueError('Bridge component has no road-width deck')
    triangle_array=np.asarray(triangles)
    xz,remap=np.unique(triangle_array[:,:,[0,2]].reshape(-1,2).astype(np.float32),axis=0,return_inverse=True)
    if arch is None:
        positions=encoded_floor_vertices(world,component,xz)
    else:
        distance=_arch_vertex_stations(xz,arch['origin'],arch['axis'],arch.get('joinStations',()))
        y=arch_height(arch,distance).astype(np.float32).astype(float)
        positions=np.c_[xz[:,0],y,xz[:,1]]
    faces=positions[remap.reshape(-1,3)]
    normal=np.cross(faces[:,1]-faces[:,0],faces[:,2]-faces[:,0])
    invalid=(normal[:,1]<=0)|(np.hypot(normal[:,0],normal[:,2])>GRADE*normal[:,1])
    # Only remnants can fail as encoded floor faces: a face under a square
    # centimetre, or one thinner than a centimetre across its longest edge (a
    # clipped sliver a metre long and a quarter of a millimetre wide lying
    # across the crease between two bounded grid triangles takes the crease's
    # grade). Nothing walks either and the served grid never samples them.
    # This is no exemption for a narrow ordinary face: every retained encoded
    # face still receives the strict grade, winding and non-degeneracy check
    # in build_bridges.
    # A claimed bridge has exact positive-area coverage authority.  Removing
    # even a thin encoded piece would open a real hole; let the strict emitted
    # grade check fail instead. Legacy loose decks retain their old cleanup.
    cleanup=(invalid&precision_remnants(faces,np.asarray(areas)) if arch is None or not arch.get('prepared',False)
             else np.zeros(len(faces),bool))
    component['precisionCleanupArea']=float(np.sum(np.asarray(areas)[cleanup]))
    remap=remap.reshape(-1,3)[~cleanup]
    clipped_owners=np.asarray(clipped_owners)[~cleanup]
    used,reindexed=np.unique(remap,return_inverse=True)
    positions=positions[used];remap=reindexed.reshape(-1,3)
    mesh=M.Mesh(positions=positions,normals=np.tile([0.,1.,0.],(len(positions),1)),
        uvs=positions[:,[0,2]]*.25,indices=remap.ravel(),material='bridge_timber')
    mesh.recompute_normals(180)
    return mesh,clipped_owners


def edge_fascia(mesh,owners,outline):
    """Shallow outside timber faces below the floor, never across a bank join.

    Test the capsule exterior instead of counting unmatched edges: union clips
    can have harmless collinear T-junctions inside a common surface.
    """
    faces=mesh.indices.reshape(-1,3)
    edges=np.concatenate([faces[:,[i,(i+1)%3]] for i in range(3)])
    edge_owners=np.tile(owners,3)
    unique,index,count=np.unique(np.sort(edges,axis=1),axis=0,return_index=True,return_counts=True)
    boundary=edges[index[count==1]];edge_owners=edge_owners[index[count==1]]
    a,b=mesh.positions[boundary[:,0]],mesh.positions[boundary[:,1]]
    dxz=(b-a)[:,[0,2]];length=np.linalg.norm(dxz,axis=1)
    normal=np.c_[-dxz[:,1],dxz[:,0]]/np.maximum(length[:,None],1e-12)
    middle=(a+b)[:,[0,2]]*.5;outside=middle+normal*1e-5;inside=middle-normal*1e-5
    keep=(length>1e-4)&~outline.contains(outside[:,0],outside[:,1])&outline.contains(inside[:,0],inside[:,1])
    a,b=a[keep],b[keep];edge_owners=edge_owners[keep]
    if not len(a):return None,np.empty(0,int)
    bottom_a=a-np.array([0,DECK_FASCIA_DEPTH_METRES,0]);bottom_b=b-np.array([0,DECK_FASCIA_DEPTH_METRES,0])
    positions=np.stack((a,b,bottom_a,bottom_b),axis=1).reshape(-1,3)
    indices=(np.arange(len(a))[:,None]*4+np.array([0,2,1,1,2,3])).ravel()
    fascia=M.Mesh(positions=positions,normals=np.zeros_like(positions),uvs=positions[:,[0,2]]*.25,
                  indices=indices,material='bridge_edge_timber')
    fascia.recompute_normals(180)
    return fascia,np.repeat(edge_owners,2)


def timber_texture():
    """A small, deliberately broad plank pattern readable from the camera."""
    from PIL import Image
    x,y=np.meshgrid(np.arange(128),np.arange(128));plank=y//16
    tones=np.array([0,-5,3,-2,4,-3,2,-4])[plank]
    grain=2*np.sin(x*.19+plank*1.7)+np.sin(x*.53+y*.22)
    seam=(y%16<1)|((x+(plank%2)*64)%128<1)
    rgb=np.stack([103+tones+grain,83+tones+grain,61+tones+grain],axis=-1)
    rgb[seam]=[56,44,32]
    output=io.BytesIO();Image.fromarray(np.uint8(np.clip(rgb,0,255))).save(output,format='PNG')
    return output.getvalue()


def merge_meshes(meshes):
    """One mesh of several of one material (a site's disconnected deck pieces, their fascias)."""
    if len(meshes)==1:return meshes[0]
    offsets=np.cumsum([0]+[len(m.positions) for m in meshes[:-1]])
    return M.Mesh(positions=np.concatenate([m.positions for m in meshes]),normals=np.concatenate([m.normals for m in meshes]),
                  uvs=np.concatenate([m.uvs for m in meshes]),indices=np.concatenate([m.indices+o for m,o in zip(meshes,offsets)]),
                  material=meshes[0].material)


def subset_mesh(mesh,triangles):
    indices=mesh.indices.reshape(-1,3)[triangles]
    used,remap=np.unique(indices,return_inverse=True)
    return M.Mesh(positions=mesh.positions[used],normals=mesh.normals[used],uvs=mesh.uvs[used],
                  indices=remap.ravel(),material=mesh.material)


def pier_floor_minimum(faces,x,z,width=.8):
    """Minimum actual encoded deck over the complete encoded pier footprint.

    Clip every intersecting emitted floor triangle, preserving its plane. The
    minimum may occur at a triangle/grid boundary inside the footprint rather
    than its corners. A partial shoulder cannot support a full-width pier.
    """
    low=np.asarray([x-width*.5,z-width*.5],dtype=np.float32).astype(float)
    high=np.asarray([x+width*.5,z+width*.5],dtype=np.float32).astype(float)
    rectangle=np.array([low,[high[0],low[1]],high,[low[0],high[1]]])
    xz=faces[:,:,[0,2]]
    candidates=faces[np.all(xz.max(axis=1)>=low,axis=1)&np.all(xz.min(axis=1)<=high,axis=1)]
    area=0.;minimum=np.inf
    for triangle in candidates:
        polygon=triangle
        for a,b in zip(rectangle,np.roll(rectangle,-1,axis=0)):
            polygon=_clip_halfplane(polygon,a,b)
            if not len(polygon):break
        if len(polygon):
            area+=abs(_area_xz(polygon));minimum=min(minimum,float(polygon[:,1].min()))
    footprint=float(np.prod(high-low))
    if not np.isfinite(minimum) or abs(area-footprint)>max(1e-6,footprint*1e-6):return None
    return minimum


def pier_mesh(world,faces,x,z):
    minimum=pier_floor_minimum(faces,x,z)
    if minimum is None:return None
    # Downward float32 rounding bounds the encoded cap as well as its centre.
    top=float(np.nextafter(np.float32(minimum-.12),np.float32(-np.inf)))
    bed=float(world.height_at(x,z))
    if top-bed<.4:return None
    height=top-bed+.06
    return M.box((.8,height,.8),center=(x,bed-.06+height*.5,z),material='bridge_stone')


def fit_pier(world,faces,x,z):
    """Fit an edge support inward without changing its planned bridge span."""
    offsets=[(0.,0.)]+sorted(((dx*.2,dz*.2) for dx in range(-6,7) for dz in range(-6,7)
        if 0<dx*dx+dz*dz<=36),key=lambda q:(q[0]*q[0]+q[1]*q[1],q[0],q[1]))
    for dx,dz in offsets:
        minimum=pier_floor_minimum(faces,x+dx,z+dz)
        if minimum is None:continue
        mesh=pier_mesh(world,faces,x+dx,z+dz)
        return mesh,{'planned':[x,z],'position':[x+dx,z+dz],'shiftMetres':math.hypot(dx,dz),
            'minimumDeck':minimum,'status':'supported' if mesh is not None else 'grounded bank stub'}
    raise ValueError(f'Bridge pier at {x},{z} has no complete .8m deck footprint within1.2m')


def support_spacing(world,faces,planned,placed):
    """Comparable geometric span estimate over emitted floor samples.

    Grounded deck points act as bank supports. Twice the largest nearest-anchor
    distance estimates unsupported spacing; it is not a structural beam model.
    """
    from scipy.spatial import cKDTree
    samples=np.unique(np.r_[faces.reshape(-1,3),faces.mean(axis=1)],axis=0)
    ground=np.asarray(world.height_at(samples[:,0],samples[:,2]))
    banks=samples[samples[:,1]-ground<=.4][:,[0,2]]
    suspended=samples[samples[:,1]-ground>.4][:,[0,2]]
    def span(points):
        if not len(suspended):return 0.
        anchors=np.r_[np.asarray(points).reshape(-1,2),banks]
        return float(cKDTree(anchors).query(suspended)[0].max()*2) if len(anchors) else None
    return {'supportsBefore':len(planned),'supportsAfter':len(placed),
        'oldMaximumUnsupportedSpanEstimateMetres':span(planned),
        'maximumUnsupportedSpanEstimateMetres':span(placed),
        'spanMetric':'Twice maximum nearest-support/bank distance at emitted vertices and triangle centres; geometric spacing estimate'}


def _authored_bridge_geometry(world,builder):
    """Build saved bridge controls with the same simple preview equation.

    Endpoints are exact bank landings.  ``arch`` is parabolic crown rise and a
    single vertical lift preserves that shape when water clearance requires it.
    The top strip is the walk collision authority; fascia and piers are visual.
    """
    snapshots=getattr(world,'authoring_snapshots',None)
    if snapshots is None:
        snapshot=getattr(world,'authoring_snapshot',None)
        if snapshot is None:return [],[],[]
        snapshots={snapshot.document.get('regionId','sunmane_steppe'):snapshot}
    from terrain_export import authored_surface_material,_rotated_uv
    records=[];parts=[];walk_triangles=[]
    bridges=[]
    for source_region,snapshot in sorted(snapshots.items()):
        if source_region not in world.ids:
            raise ValueError(f'authored bridge region {source_region!r} is absent from the continent')
        bridges.extend((source_region,snapshot,bridge)
                       for bridge in snapshot.document.get('bridges',()))
    for source_region,snapshot,bridge in bridges:
        start=snapshot.continent_point(bridge['start']);end=snapshot.continent_point(bridge['end'])
        delta=end[[0,2]]-start[[0,2]];length=float(np.linalg.norm(delta))
        if length<=1e-6:raise ValueError(f"authored bridge {bridge['id']} has coincident endpoints")
        segments=max(1,int(math.ceil(length)));t=np.linspace(0.,1.,segments+1)
        centres=start[None,:]*(1-t[:,None])+end[None,:]*t[:,None]
        centres[:,1]+=4*float(bridge['arch'])*t*(1-t)
        water=[]
        for river in world.plan.get('rivers',()):
            distance,profile,width=L.river_field(centres[:,0],centres[:,2],river)
            eligible=distance<=width+1e-8
            water.append(np.where(eligible,profile,-np.inf))
        visible=np.max(water,axis=0) if water else np.full(len(t),-np.inf)
        lift=float(np.max(np.where(np.isfinite(visible),
            visible+float(bridge['waterClearance'])-centres[:,1],0.),initial=0.))
        lift=max(0.,lift);centres[:,1]+=lift
        axis=delta/length;side=np.array([-axis[1],axis[0]])
        half=float(bridge['width'])*.5
        left=centres.copy();right=centres.copy()
        left[:,[0,2]]+=side*half;right[:,[0,2]]-=side*half
        vertices=np.empty((2*len(centres),3));vertices[0::2]=left;vertices[1::2]=right
        faces=[]
        for index in range(segments):
            a=2*index;faces.extend(([a,a+2,a+1],[a+1,a+2,a+3]))
        faces=np.asarray(faces,np.int32)
        along=t*length
        raw_uv=np.empty((2*len(centres),2));raw_uv[0::2]=np.c_[np.zeros(len(t)),along]
        raw_uv[1::2]=np.c_[np.full(len(t),float(bridge['width'])),along]
        deck_surface=dict(bridge['deckSurface'])
        deck_surface['rotationDegrees']=float(deck_surface.get('rotationDegrees',0.))+float(
            bridge.get('deckTextureRotationDegrees',0.))
        name=bridge['id']
        identity=name if source_region=='sunmane_steppe' else source_region+'__'+name
        deck_material,density=authored_surface_material(builder,deck_surface,identity+'_deck')
        mesh=M.Mesh(positions=vertices,normals=np.tile([0.,1.,0.],(len(vertices),1)),
                    uvs=_rotated_uv(raw_uv/.24,deck_surface,density),indices=faces.ravel(),
                    material=deck_material)
        mesh.recompute_normals(180)
        top=mesh.positions[mesh.indices.reshape(-1,3)];walk_triangles.append(top)
        # A saved bridge belongs to the scene that declares it. Midpoint
        # ownership can change at a seam and must not silently reattribute an
        # editable control to its neighbour. Preserve Sunmane's published node
        # and record ids; qualify later territories so local ids may repeat.
        region=(world.ids[int(world.owner_at(*centres[len(centres)//2,[0,2]]))]
                if source_region=='sunmane_steppe' else source_region)
        node=f'Walk_AuthoredBridge_{identity}_{region}'
        parts.append((region,node,mesh,True,identity))
        # A shallow fascia makes the span readable from the water without
        # changing its collision surface.
        fascia_vertices=[];fascia_faces=[];fascia_uv=[];depth=.22
        for edge in (left,right):
            for index in range(segments):
                base=len(fascia_vertices);a=edge[index];b=edge[index+1]
                fascia_vertices.extend((a,b,b-[0,depth,0],a-[0,depth,0]))
                distance0=along[index];distance1=along[index+1]
                fascia_uv.extend(([distance0/.24,0],[distance1/.24,0],
                                   [distance1/.24,depth/.24],[distance0/.24,depth/.24]))
                fascia_faces.extend((base,base+1,base+2,base,base+2,base+3))
        fascia=M.Mesh(positions=np.asarray(fascia_vertices),normals=np.zeros((len(fascia_vertices),3)),
                      uvs=_rotated_uv(fascia_uv,deck_surface,density),indices=np.asarray(fascia_faces),
                      material=deck_material);fascia.recompute_normals(180)
        parts.append((region,f'AuthoredBridgeEdge_{identity}_{region}',fascia,False,identity))
        support_material,_=authored_surface_material(
            builder,bridge['supportSurface'],identity+'_support')
        support_count=max(0,int(math.ceil(length/5.))-1);supports=[]
        for number in range(1,support_count+1):
            station=number/(support_count+1);centre=start*(1-station)+end*station
            centre[1]+=4*float(bridge['arch'])*station*(1-station)+lift-.22
            bottom=float(world.height_at(centre[0],centre[2]));height=float(centre[1]-bottom)
            if height<=.3:continue
            support=M.box((.55,height,.55),center=(centre[0],bottom+height*.5,centre[2]),
                          uv_scale=1.,material=support_material)
            support_node=f'AuthoredBridgeSupport_{identity}_{number:02d}_{region}'
            parts.append((region,support_node,support,False,identity));supports.append({
                'station':station,'position':[float(centre[0]),float(centre[2])],
                'bottom':bottom,'top':float(centre[1])})
        records.append({'id':identity,'length':length,'segments':segments,'width':float(bridge['width']),
                        'arch':float(bridge['arch']),'waterClearance':float(bridge['waterClearance']),
                        'uniformClearanceLift':lift,'supports':supports})
    return parts,walk_triangles,records


def _suppresses_generated_authored_component(component,owners,authored_owners):
    """Whether bridge authority replaces this complete procedural component.

    Claimed crossings belong to their stable crossing site even when a landing
    overlaps Sunmane. Loose components are suppressed only when every emitted
    floor face belongs to a saved territory. Mixed saved/procedural coverage
    remains intact; adjacent saved territories replace their respective slices.
    """
    return (not component.get('sites') and len(owners)>0 and
            set(map(int,owners)).issubset(authored_owners))


def _authored_crossing_claims(world):
    """Stable claimed crossing keys owned by exact saved asset assemblies."""
    claims={}
    snapshots=dict(getattr(world,'authoring_snapshots',{}) or {})
    legacy=getattr(world,'authoring_snapshot',None)
    if legacy is not None:
        snapshots.setdefault(legacy.document.get('regionId','sunmane_steppe'),legacy)
    for region,snapshot in sorted(snapshots.items()):
        for asset in snapshot.document.get('objects',()):
            crossing=asset.get('metadata',{}).get('authoredCrossing')
            if not isinstance(crossing,dict):continue
            identity=str(crossing.get('id','')).strip()
            if not identity:raise ValueError(
                f"{region}/{asset.get('id')}: authoredCrossing needs a stable id")
            previous=claims.get(identity)
            owner=(region,str(asset.get('id','')))
            if previous is not None and previous!=owner:
                raise ValueError(
                    f"authored crossing {identity!r} is claimed by both "
                    f"{previous[0]}/{previous[1]} and {owner[0]}/{owner[1]}")
            claims[identity]=owner
    return claims


def _claimed_component_crossings(world,component,claims):
    """Return stable keys when every claimed site in a component is saved."""
    if not component.get('sites'):return ()
    sites={int(site['id']):str(site.get('key',''))
           for site in getattr(world,'crossing_sites',())}
    keys=[]
    for raw in component['sites']:
        site_id=int(raw)
        if site_id not in sites or not sites[site_id]:
            raise ValueError(f'bridge component references unknown crossing site {site_id}')
        keys.append(sites[site_id])
    selected=tuple(sorted({key for key in keys if key in claims}))
    if selected and len(selected)!=len(set(keys)):
        raise ValueError(
            f'bridge component mixes saved and procedural crossing claims: {sorted(set(keys))}')
    return selected


def build_bridges(world,path, *, water_fields=None):
    """Return bridge parts matching build_continent.bridge_scene's contract."""
    water_fields=water_fields or L.water_fields
    field=common_surface(world,water_fields=water_fields)
    builder=G.GltfBuilder('Eloria unified continental bridge deck')
    builder.add_material(G.Material('bridge_stone',base_color=(.44,.43,.37,1),roughness=.92))
    builder.add_image('continental_bridge_planks',timber_texture())
    builder.add_material(G.Material('bridge_timber',base_color_texture='continental_bridge_planks',roughness=.93))
    builder.add_material(G.Material('bridge_edge_timber',base_color=(.085,.061,.04,1),roughness=.95,double_sided=True))
    builder.add_material(G.Material('threshold_invisible',base_color=(0,0,0,0),alpha_mode='BLEND'))
    result=[];triangles=[];support_reports=[];suppressed_components=[]
    authored_owners={world.ids.index(region) for region in
                     getattr(world,'authoring_snapshots',{}) if region in world.ids}
    if not authored_owners and getattr(world,'authoring_snapshot',None) is not None \
            and 'sunmane_steppe' in world.ids:
        authored_owners.add(world.ids.index('sunmane_steppe'))
    authored_crossings=_authored_crossing_claims(world)
    def add(region,name,mesh, *, collides=False,record_id=None):
        builder.add_mesh(name,mesh,with_tangents=False)
        root=builder.add_node(G.Node(name,mesh=name))
        part={'region':region,'roots':[root],'bounds':mesh.bounds(),'node':name,'segment':[]}
        if collides:part['collides']=True
        if record_id is not None:part['recordId']=record_id
        result.append(part)
    # A site whose deck fell into disconnected components names every piece by the site: its floors and fascias are
    # gathered and emitted as one node per territory after the loop, so no two nodes share a name.
    numbers=[component['id'] for component in field['components']]
    shared={number for number in numbers if numbers.count(number)>1};gathered={}
    def floor(region,name,mesh,number):
        if number in shared:gathered.setdefault(name,(region,[]))[1].append(mesh)
        else:add(region,name,mesh)
    for component in field['components']:
        token=C.component_token(component)
        claimed_crossings=_claimed_component_crossings(
            world,component,authored_crossings)
        if claimed_crossings:
            suppressed_components.append(component['id'])
            continue
        if _suppresses_generated_authored_component_before_mesh(
                world,component,authored_owners):
            suppressed_components.append(component['id'])
            continue
        mesh,owners=deck_mesh(world,component)
        if _suppresses_generated_authored_component(component,owners,authored_owners):
            suppressed_components.append(component['id'])
            continue
        faces=mesh.positions[mesh.indices.reshape(-1,3)]
        encoded=faces.astype(np.float32).astype(float)
        normal=np.cross(encoded[:,1]-encoded[:,0],encoded[:,2]-encoded[:,0])
        invalid=(normal[:,1]<=0)|(np.hypot(normal[:,0],normal[:,2])>GRADE*normal[:,1]+1e-10)
        if invalid.any():
            first=np.flatnonzero(invalid)[0];where=encoded[first].mean(axis=0)
            slope=np.hypot(normal[first,0],normal[first,2])/max(normal[first,1],1e-20)
            raise ValueError(f'Quantized bridge floor is not a valid <=.65 slope at {where.tolist()}: grade {slope:.8f}, projected area {normal[first,1]*.5:.9f}m2')
        triangles.append(faces)
        for index,region in enumerate(world.ids):
            selected=np.flatnonzero(owners==index)
            if len(selected):floor(region,f"Walk_ContinentalBridgeUnion_{token}_{region}",subset_mesh(mesh,selected),component['id'])
        fascia,fascia_owners=edge_fascia(mesh,owners,component.get('outline') or field['outline'])
        if fascia is not None:
            for index,region in enumerate(world.ids):
                selected=np.flatnonzero(fascia_owners==index)
                if len(selected):floor(region,f"BridgeUnionTimberEdge_{token}_{region}",subset_mesh(fascia,selected),component['id'])
        row,col=np.nonzero(component['cells']);sl=component['slice'];planned=[];placed=[];fitted=[]
        if not component.get('coastalRecordId'):
            for r,c in zip(row,col):
                iz,ix=sl[0].start+int(r),sl[1].start+int(c)
                if ix%8!=4 or iz%8!=4:continue
                x,z=world.x0+(ix+.5)*CELL,world.z0+(iz+.5)*CELL
                if not (component.get('outline') or field['outline']).contains(x,z):continue
                if float(surface_at(world,x,z,field))-.12-float(world.height_at(x,z))<.4:continue
                # Piers stand only under the span, over the water; a landing rests on its bank.
                bed=np.array([float(world.height_at(x,z))])
                if not bool(np.asarray(water_fields(np.array([x]),np.array([z]),height=bed,plan=world.plan)['mask']).reshape(-1)[0]):continue
                planned.append([x,z]);support,fit=fit_pier(world,encoded,x,z);fitted.append(fit)
                if support is None:continue
                placed.append(fit['position']);region=world.ids[int(world.owner_at(*fit['position']))]
                add(region,f"BridgeUnionPier_{token}_{ix}_{iz}",support)
        if component.get('coastalRecordId'):
            claim=component['claim'];support_names={support.name for support in claim.supports}
            support_names.update(support.name for stair in claim.stairs for support in stair.supports)
            support_reports.append({'component':component['id'],'authority':'prepared-coastal-claim',
                'genericPiersSkipped':True,'preparedSupports':len(support_names),
                'supportContact':dict(claim.evidence.get('supportContact',{}))})
        else:
            support_reports.append(dict(component=component['id'],
                **support_spacing(world,encoded,planned,placed),piers=fitted))
    authored_parts,authored_triangles,authored_records=_authored_bridge_geometry(world,builder)
    for region,name,mesh,collides,record_id in authored_parts:
        add(region,name,mesh,collides=collides,record_id=record_id)
    triangles.extend(authored_triangles)
    for name,(region,meshes) in gathered.items():add(region,name,merge_meshes(meshes))
    for part in C.coastal_auxiliary_parts(world):
        add(part['region'],part['name'],part['mesh'],collides=bool(part['collides']),
            record_id=part.get('recordId'))
    names=[part['node'] for part in result]
    if len(names)!=len(set(names)):raise ValueError('Bridge parts share a node name: '+', '.join(sorted({n for n in names if names.count(n)>1})))
    world.bridge_triangles=np.concatenate(triangles) if triangles else np.empty((0,3,3))
    # Queries after export must retain the exact prepared profile/component
    # authority used by the emitted floor and support checks.
    world.bridge_field=field
    for connection in world.connections:
        if connection['type']!='walk':continue
        anchor=np.asarray(connection['anchor']);normal=np.asarray(connection['normal'])
        for side,region in enumerate(connection['regions']):
            outward=normal*(1 if side==0 else -1);tangent=np.array([-outward[1],outward[0]])
            corners=np.array([anchor+outward*d+tangent*t for d in (-4,2) for t in (-4,4)])
            lo=corners.min(axis=0);hi=corners.max(axis=0)
            x,z=np.meshgrid(np.arange(lo[0],hi[0]+.5,CELL),np.arange(lo[1],hi[1]+.5,CELL))
            vertices=np.c_[x.ravel(),surface_at(world,x.ravel(),z.ravel(),field),z.ravel()]
            row,col=np.indices((x.shape[0]-1,x.shape[1]-1));a=(row*x.shape[1]+col).ravel();b=a+1;c=a+x.shape[1];d=c+1
            mesh=M.Mesh(positions=vertices,normals=np.tile([0.,1.,0.],(len(vertices),1)),uvs=vertices[:,[0,2]],
                        indices=np.c_[a,c,b,b,c,d].ravel(),material='threshold_invisible')
            mesh.recompute_normals(180)
            add(region,'Walk__StreamThreshold_'+connection['id']+'_'+region,mesh)
    Path(path).parent.mkdir(parents=True,exist_ok=True);builder.write_glb(str(path))
    world.bridge_report={'components':len(field['components']),'visibleCells':int(field['mask'].sum()),
        'visibleTriangles':len(world.bridge_triangles),'wetCells':field['wetCells'],'siteCells':field['siteCells'],'looseWetCells':field['looseWetCells'],
        'riverWaterOutsideSites':field['riverWaterOutsideSites'],'decks':field['decks'],
        'deckLandingMetres':field['deckLandingMetres'],'deckLiftMetres':field['deckLiftMetres'],'trimmedLandingCells':field['trimmedLandingCells'],
        'cutOffLandingCells':field['cutOffLandingCells'],'cutOffLandingBanks':field['cutOffLandingBanks'],
        'maximumBankErrorMetres':field['maximumBankError'],'worstBank':field['worstBank'],'maximumGrade':GRADE,
        'outlineMaximumInsetFraction':1-math.cos(math.pi/(2*CAP_ARC_STEPS)),
        'precisionCleanupAreaSquareMetres':sum(c.get('precisionCleanupArea',0) for c in field['components']),
        'supports':support_reports,
        'authored':authored_records,
        'suppressedGeneratedComponents':suppressed_components,
        'policy':'Decks only at claimed crossing sites (span plus landings) and over deep water crossed away from a site; disjoint road capsule union clipped onto one common floor; unchanged terrain; exact ownership by cell; piers only over water; timber fascia below the floor.'}
    return result
