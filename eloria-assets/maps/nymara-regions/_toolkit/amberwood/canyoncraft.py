"""Reusable open sandstone cuts, rock spines and eroded shelter forms.

Geometry uses metres, Y up. Only explicit floors enter the walking bucket.
Bedding UVs follow world height so adjacent wall bands share the same strata.
"""
from __future__ import annotations
import math
import numpy as np
from . import mesh as M, noise as N, materials as MAT, textures as T
from .stonework import MeshGroup

ROCK = "sunmane_red_sandstone"
SAND = "sunmane_wash_sand"

def sandstone(size=512, seed=809):
    coarse=N.tileable_fbm(size,5,4,seed=seed)
    grain=N.tileable_fbm(size,47,3,seed=seed+3)
    u=np.arange(size)/size
    x,y=np.meshgrid(u,u)
    beds=.5+.5*np.sin(math.tau*(y*5+.12*np.sin(math.tau*x)+coarse*.18))
    fine=.5+.5*np.sin(math.tau*(y*21+coarse*.09))
    value=np.clip(.25+coarse*.38+beds*.19+grain*.15,0,1)
    color=T._colorize(value,(0.,(.34,.19,.13)),(.5,(.57,.36,.23)),(1.,(.77,.57,.36)))
    rough=np.clip(.85+grain*.1,0,1)
    return T.TextureSet(ROCK,T._u8(color),T.pack_orm(.85+grain*.12,rough,np.zeros_like(rough)),
                        T.normal_from_height(grain*.22+fine*.045+beds*.04,1.1))

def register(sets):
    specs=(MAT.MaterialSpec(ROCK,ROCK,roughness=.96),
           MAT.MaterialSpec(SAND,"packed_earth",roughness=1,base_color=(.91,.85,.72,1)))
    for spec in specs:
        if spec.name not in MAT.BY_NAME:
            MAT.SPECS += (spec,)
            MAT.BY_NAME[spec.name]=spec
    if ROCK not in sets:
        sets[ROCK]=sandstone()

def _face(points,normal,material=ROCK,uv=None):
    p=np.array(points,dtype=float)
    if np.dot(np.cross(p[1]-p[0],p[2]-p[0]),normal)<0:
        p=p[::-1]
    q=M.quad(p,uv_scale=.3,material=material)
    if uv == "beds":
        # Horizontal distance along the panel, and absolute height.
        delta=p[1]-p[0]
        axis=0 if abs(delta[0])>abs(delta[2]) else 2
        q.uvs=np.array([[v[axis]*.25,v[1]*.35] for v in p])
    return q

def wall_run(a,b,y0,y1,height=8,depth=2.8,seed=0,material=ROCK,caps=True):
    """A closed eroded bank; its right-hand normal faces the usable floor."""
    a,b=np.array(a,float),np.array(b,float)
    length=float(np.linalg.norm(b-a))
    if length<.05:return MeshGroup()
    tangent=(b-a)/length
    inward=np.array([tangent[1],-tangent[0]])
    rng=np.random.default_rng(seed)
    stations=max(2,int(math.ceil(length/2)))
    levels=((0,.06),(.14,.16),(.29,-.28),(.37,.38),(.48,.13),
            (.58,-.50),(.72,-.12),(.82,-.90),(1,-.55))
    rings=[]
    for i in range(stations+1):
        t=i/stations; plan=a+(b-a)*t; ground=y0+(y1-y0)*t
        wave=0 if i in (0,stations) else float(.65*math.sin(math.tau*t)+rng.uniform(-.15,.15))
        crown=height*(1+.07*math.sin(i*1.8+seed))
        ring=[]
        for h,offset in levels:
            x,z=plan+inward*((0 if i in (0,stations) else offset)+wave)
            ring.append([x,ground-.3+(crown+.3)*h,z])
        x,z=plan-inward*depth
        ring += [[x,ground+crown,z],[x,ground-.3,z]]
        rings.append(ring)
    g=MeshGroup();n=[inward[0],0,inward[1]]
    for aa,bb in zip(rings,rings[1:]):
        for k in range(len(aa)):
            nxt=(k+1)%len(aa)
            normal=n if k<len(levels)-1 else ([0,1,0] if k==len(levels)-1 else
                     [-n[0],0,-n[2]] if k==len(levels) else [0,-1,0])
            g.add(_face([aa[k],bb[k],bb[nxt],aa[nxt]],normal,material,uv="beds"))
    # End caps are triangle fans; slight non-planarity follows the eroded face.
    for ring,sign in (((rings[0],-1),(rings[-1],1)) if caps else ()):
        center=np.mean(ring,axis=0)
        for k in range(len(ring)):
            pts=[center,ring[k],ring[(k+1)%len(ring)]]
            normal=np.array([tangent[0]*sign,0,tangent[1]*sign])
            if np.dot(np.cross(pts[1]-pts[0],pts[2]-pts[0]),normal)<0:pts=pts[::-1]
            mesh=M.Mesh(np.array(pts),np.zeros((3,3)),np.array([[v[0]*.25,v[1]*.35] for v in pts]),
                        None,np.array([0,1,2]),material)
            mesh.recompute_normals(0);g.add(mesh)
    return g

def enclosure(x0,z0,x1,z1,y,height,doors=(),floor=SAND,rock=ROCK,walk=True,seed=0):
    """An open cut whose full-height mouths exactly match the supplied doors."""
    g=MeshGroup()
    slab=_face([(x0,y,z0),(x1,y,z0),(x1,y,z1),(x0,y,z1)],[0,1,0],floor)
    (g.add_walk if walk else g.add)(slab)
    sides=(("west",(x0,z0),(x0,z1)),("north",(x0,z1),(x1,z1)),
           ("east",(x1,z1),(x1,z0)),("south",(x1,z0),(x0,z0)))
    for k,(side,a,b) in enumerate(sides):
        axis=1 if side in ("east","west") else 0
        lo,hi=sorted((a[axis],b[axis]))
        gaps=sorted((max(lo,c-w/2),min(hi,c+w/2)) for s,c,w,h in doors if s==side)
        intervals=[];cursor=lo
        for ga,gb in gaps:
            if ga>cursor:intervals.append((cursor,ga))
            cursor=max(cursor,gb)
        if cursor<hi:intervals.append((cursor,hi))
        for j,(aa,bb) in enumerate(intervals):
            pa=list(a);pb=list(b)
            pa[axis],pb[axis]=(aa,bb) if b[axis]>a[axis] else (bb,aa)
            g.add(wall_run(pa,pb,y,y,height,seed=seed+k*13+j,material=rock))
    # Flat end profiles close seams; small remnants soften the bank corners.
    # They also break the rectangular outline without narrowing the door centres.
    for k,(x,z) in enumerate(((x0,z0),(x0,z1),(x1,z0),(x1,z1))):
        g.add(butte(min(1.25,(x1-x0)/5,(z1-z0)/5),height*1.12,seed=seed+k*23,rock=rock).translate(x,y-.25,z))
    return g

def cut_passage(a,b,width,y0,y1,height=4.8,floor=SAND,rock=ROCK,seed=0):
    """Continuous surveyed ramp through an open rock slot, including its banks."""
    a,b=np.array(a,float),np.array(b,float)
    t=(b-a)/np.linalg.norm(b-a);n=np.array([t[1],-t[0]])*width/2
    g=MeshGroup()
    # The shared collision rasterizer takes each triangle's peak. Short strips
    # keep that conservative approximation within one 0.2 m server stage.
    steps=max(1,int(math.ceil(np.linalg.norm(b-a)/.4)))
    for k in range(steps):
        u,v=k/steps,(k+1)/steps
        aa,bb=a+(b-a)*u,a+(b-a)*v
        ya,yb=y0+(y1-y0)*u,y0+(y1-y0)*v
        corners=(aa-n,bb-n,bb+n,aa+n)
        pts=[[x,y,z] for (x,z),y in zip(corners,(ya,yb,yb,ya))]
        g.add_walk(_face(pts,[0,1,0],floor))
    # Passage ends join a room bank or sealed gate; buried end caps would
    # nearly share the adjoining bank plane after its erosion displacement.
    g.add(wall_run(a-n,b-n,y0,y1,height,depth=1.9,seed=seed,material=rock,caps=False))
    g.add(wall_run(b+n,a+n,y1,y0,height,depth=1.9,seed=seed+1,material=rock,caps=False))
    return g

def ridge_spine(length=28,width=4.4,height=3,rock=ROCK):
    """A narrow surviving rock rib, with a continuous top and flared lower banks."""
    g=MeshGroup();half=width/2
    g.add_walk(_face([(-half,height,0),(half,height,0),(half,height,length),(-half,height,length)],
                     [0,1,0],rock))
    for side in (-1,1):
        for k in range(14):
            a,b=length*k/14,length*(k+1)/14
            da,db=.8+.25*math.sin(k*1.8),.8+.25*math.sin((k+1)*1.8)
            g.add(_face([(side*half,height,a),(side*half,height,b),
                          (side*(half+db),-.2,b),(side*(half+da),-.2,a)],
                         [side,0,0],rock,uv="beds"))
    for z,n in ((0,[0,0,-1]),(length,[0,0,1])):
        g.add(_face([(-half,height,z),(half,height,z),(half+1,-.2,z),(-half-1,-.2,z)],n,rock))
    return g

def butte(radius=3,height=12,depth=None,seed=0,rock=ROCK):
    """A tapered, bedded sandstone remnant with a broken crown."""
    rng=np.random.default_rng(seed);g=MeshGroup()
    depth=depth or radius
    factors=(1.2,1.04,.95,1.02,.74,.85,.67,.57,.66,.40)
    az=np.arange(10)*math.tau/10
    jitter=rng.uniform(.88,1.12,10)
    rings=[]
    for k,scale in enumerate(factors):
        rings.append([[math.cos(a)*radius*scale*jitter[i],height*k/(len(factors)-1),
                       math.sin(a)*depth*scale*jitter[i]] for i,a in enumerate(az)])
    for aa,bb in zip(rings,rings[1:]):
        for i,a in enumerate(az):
            j=(i+1)%len(az)
            g.add(_face([aa[i],aa[j],bb[j],bb[i]],[math.cos(a+.3),0,math.sin(a+.3)],rock,uv="beds"))
    # A small flat crown closes the upper ring; the underside is buried in ground.
    ring=rings[-1]
    for i in range(len(ring)):
        p=np.array([[0,height,0],ring[i],ring[(i+1)%len(ring)]])
        if np.cross(p[1]-p[0],p[2]-p[0])[1]<0:p=p[::-1]
        q=M.Mesh(p,np.zeros((3,3)),p[:,[0,2]]*.3,None,np.array([0,1,2]),rock)
        q.recompute_normals(0);g.add(q)
    return g

def shelter(width=7,depth=4,height=4,rock=ROCK):
    """A visible undercut ledge with an attached back and sloping roof."""
    g=MeshGroup()
    # The back is at +Z, the open mouth at -Z.
    roof=[(-width/2,height+.5,depth/2),(width/2,height+.35,depth/2),
          (width*.46,height,-depth/2),(-width*.43,height+.15,-depth/2)]
    lower=[[x,y-.65,z] for x,y,z in roof]
    g.add(_face(roof,[0,1,0],rock))
    g.add(_face(lower,[0,-1,0],rock))
    for k in range(4):
        j=(k+1)%4
        desired=np.array(roof[k])+np.array(roof[j]);desired[1]=0
        g.add(_face([roof[k],roof[j],lower[j],lower[k]],desired,rock,uv="beds"))
    g.add(wall_run((-width/2,depth/2),(width/2,depth/2),0,0,height+.45,seed=77,material=rock))
    return g

def dry_tuft(seed=0,material="thatch_reed"):
    """Sparse dry grass with paired opposite-facing blades, without alpha cards."""
    rng=np.random.default_rng(seed);g=MeshGroup()
    for i in range(12):
        a=float(rng.uniform(0,math.tau));h=float(rng.uniform(.23,.65))
        x,z=float(rng.uniform(-.3,.3)),float(rng.uniform(-.3,.3))
        p=np.array([[x-.045*math.cos(a),.02,z-.045*math.sin(a)],
                    [x+.045*math.cos(a),.02,z+.045*math.sin(a)],
                    [x+.23*math.sin(a),h,z-.23*math.cos(a)]])
        m=M.Mesh(p,np.zeros((3,3)),np.array([[0,0],[1,0],[.5,1]]),None,np.array([0,1,2]),material)
        m.recompute_normals(0);g.add(m)
        back=m.copy().flip_winding();back.normals*=-1;g.add(back)
    return g
