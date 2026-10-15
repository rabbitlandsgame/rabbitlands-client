"""Continuous timber floors and piled, mitred routes shared by water regions."""
from __future__ import annotations
import math
import numpy as np
from . import mesh as M, architecture as A
from .stonework import MeshGroup

def deck_panel(half_x, half_z, y=0.0, thickness=0.11, material="timber_dark"):
    """Joined boards: grain repeats at plank width, with no holes for a ground ray."""
    if min(half_x, half_z, thickness) <= 0:
        raise ValueError("deck dimensions must be positive")
    parts=[]
    edges=np.linspace(-half_z,half_z,max(2,math.ceil(half_z*2/.38)+1))
    for a,b in zip(edges,edges[1:]):
        parts.append(M.quad([(-half_x,y,a),(-half_x,y,b),(half_x,y,b),(half_x,y,a)],
                            uv_scale=.8,material=material))
    bottom=y-thickness
    for a,b in [((-half_x,-half_z),(half_x,-half_z)),
                ((half_x,-half_z),(half_x,half_z)),
                ((half_x,half_z),(-half_x,half_z)),
                ((-half_x,half_z),(-half_x,-half_z))]:
        parts.append(M.quad([(a[0],bottom,a[1]),(b[0],bottom,b[1]),
                             (b[0],y,b[1]),(a[0],y,a[1])],material=material))
    parts.append(M.quad([(-half_x,bottom,-half_z),(half_x,bottom,-half_z),
                         (half_x,bottom,half_z),(-half_x,bottom,half_z)],material=material))
    return M.merge(parts,material)

def junction(centre, ports, radius=4.5, material="timber_dark", foot=-8):
    """A convex landing whose port chords are the exact ends of its routes.

    Ports contain two (x,y,z) edge points on the landing circle. The remaining
    circular rim is sampled between ports; a single fan owns the walking top.
    """
    c=np.asarray(centre,dtype=float)
    points=[np.asarray(p) for port in ports for p in port]
    angles=[math.atan2(p[2]-c[2],p[0]-c[0]) for p in points]
    for angle in np.linspace(-math.pi,math.pi,25)[:-1]:
        p=c+np.array([math.cos(angle)*radius,0,math.sin(angle)*radius])
        # Do not insert a rim vertex outside an entrance chord.
        if any(np.dot((p-c)[[0,2]],(np.mean(port,axis=0)-c)[[0,2]]) >
               np.linalg.norm((np.mean(port,axis=0)-c)[[0,2]])**2+1e-7 for port in ports):
            continue
        points.append(p);angles.append(angle)
    ordered=np.array(points)[np.argsort(angles)]
    out=MeshGroup()
    for a,b in zip(ordered,np.roll(ordered,-1,axis=0)):
        # Increasing polar angle in XZ faces down, hence reversed winding.
        out.add_walk(M._make([c,b,a],[[0,1,0]]*3,
                            [[v[0]*.7,v[2]*.7] for v in (c,b,a)],[[0,1,2]],material))
    for a in ordered[::3]:
        height=max(.3,a[1]-.14-foot)
        out.add(M.cylinder(.15,.17,height,6,material=material,
                          cap_top=False,cap_bottom=False).translate(a[0],foot,a[2]))
    return out

def piled_route(stations, width=3.8, material="timber_dark", rope="timber_dark",
                bed=None, ends=None, rails=True):
    """A sloping timber ribbon with mitred bends and independently cut ends.

    Endpoint sections may be skewed to meet an existing rectangular quay.
    Walking faces share edges only. Piles reach the surveyed bed; railings
    remain outside the floor and stop short of junctions.
    """
    points=np.asarray(stations,dtype=float)
    if points.ndim!=2 or points.shape[1]!=3 or len(points)<2 or width<=0:
        raise ValueError("route needs 3D stations and a positive width")
    runs=np.diff(points[:,[0,2]],axis=0);lengths=np.linalg.norm(runs,axis=1)
    if np.any(lengths<.01):raise ValueError("route stations must differ in plan")
    tangent=runs/lengths[:,None];normals=np.c_[-tangent[:,1],tangent[:,0]]
    mitres=np.empty((len(points),2));mitres[0]=normals[0];mitres[-1]=normals[-1]
    for i in range(1,len(points)-1):
        bisector=normals[i-1]+normals[i];divisor=float(np.dot(bisector,normals[i]))
        if divisor<.5:raise ValueError("route bend is too sharp")
        mitres[i]=bisector/divisor
    left=points.copy();right=points.copy()
    left[:,[0,2]]-=mitres*width/2;right[:,[0,2]]+=mitres*width/2
    if ends:
        for i,section in ((0,ends[0]),(-1,ends[1])):
            if section is not None:left[i],right[i]=section
    out=MeshGroup()
    for i,length in enumerate(lengths):
        j=i+1
        count=max(1,math.ceil(length/.38))
        for k in range(count):
            u,v=k/count,(k+1)/count
            a=left[i]+(left[j]-left[i])*u;b=left[i]+(left[j]-left[i])*v
            c=right[i]+(right[j]-right[i])*v;d=right[i]+(right[j]-right[i])*u
            out.add_walk(M.quad([d,c,b,a],uv_scale=.8,material=material))
        for a,b in ((left[j],left[i]),(right[i],right[j])):
            drop=np.array([0,.11,0])
            out.add(M.quad([a,b,b-drop,a-drop],material=material))
        n=max(1,math.ceil(length/5))
        for k in range(n):
            u=(k+.5)/n;p=points[i]+(points[j]-points[i])*u
            for sign in (-1,1):
                x,z=p[[0,2]]+normals[i]*sign*(width/2+.2)
                floor=float(bed(x,z))-.5 if bed else -8.
                height=max(.3,p[1]+(.95 if rails else -.14)-floor)
                out.add(M.cylinder(.105,.15,height,6,material=material,
                                  cap_top=False,cap_bottom=False).translate(x,floor,z))
        if rails and length>3:
            for sign in (-1,1):
                a=points[i]+(points[j]-points[i])*min(.7/length,.2)
                b=points[j]-(points[j]-points[i])*min(.7/length,.2)
                offset=np.array([normals[i,0]*sign*(width/2+.2),.75,normals[i,1]*sign*(width/2+.2)])
                out.add(A.beam(a+offset,b+offset,.045,material=rope))
    return out

def lateen_rig(height=7.0, timber="timber_dark", cloth="canvas_awning"):
    """A mast, diagonal yard and a thick triangular sail, local bow on +Z."""
    out=MeshGroup()
    out.add(A.beam((0,0,0),(0,height,0),.12,material=timber))
    a=np.array([-.10,height*.32,-2.4]);b=np.array([.10,height,2.8])
    out.add(A.beam(a,b,.085,material=timber))
    points=np.array([a+[.06,-.12,0],b+[.06,-.12,0],[.12,height*.24,2.7]])
    normal=np.cross(points[1]-points[0],points[2]-points[0]);normal/=np.linalg.norm(normal)
    for sign in (-1,1):
        p=points+normal*sign*.015;order=[0,1,2] if sign>0 else [2,1,0]
        out.add(M._make(p,[normal*sign]*3,[[0,0],[1,1],[1,0]],[order],cloth))
    return out
