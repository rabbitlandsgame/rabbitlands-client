"""Working woodland pieces using the game's existing timber and stone palette."""
from __future__ import annotations
import math
import numpy as np
from . import mesh as M, architecture as A, stonework as S

def mill_wheel(radius=2.3, width=1.0, timber="timber_dark", iron="dark_iron"):
    """Open paddle wheel around the X axis; rims and spokes have no filled disc."""
    out=S.MeshGroup()
    for x in (-width/2,width/2):
        rim=M.lathe([[radius-0.20,-0.10],[radius,-0.10],[radius,0.10],
                     [radius-0.20,0.10]],32,material=iron)
        out.add(rim.rotate_z(math.pi/2).translate(x,0,0))
        for i in range(8):
            a=i*math.pi/4
            out.add(A.beam((x,math.cos(a)*0.24,math.sin(a)*0.24),
                           (x,math.cos(a)*(radius-.2),math.sin(a)*(radius-.2)),
                           .13,.13,material=timber))
    for i in range(20):
        a=i*math.pi/10
        paddle=M.box((width+.12,.16,.45),material=timber)
        out.add(paddle.rotate_x(a).translate(0,math.cos(a)*radius,math.sin(a)*radius))
    out.add(M.cylinder(.18,.18,width+2.0,12,material=iron).rotate_z(math.pi/2)
            .translate((width+2)/2,0,0))
    return out

def watermill(seed=0, wheel_height=1.85):
    """Compact mill house with an exposed wheel on its eastern race."""
    out=A.forest_lodge(seed=seed,width=7.2,depth=8.0,storeys=1,
                       porch=True,balcony=False,workshop=False,preserve_materials=True)
    wheel=mill_wheel()
    for p in wheel.parts: out.add(p.translate(4.65,wheel_height,0))
    return out

def water_ribbon(stations,width=3.6,material="water_stream"):
    """One continuous upward-facing water skin through surveyed 3D stations."""
    p=np.asarray(stations,dtype=float)
    if len(p)<2 or width<=0: raise ValueError("water ribbon needs two stations and positive width")
    runs=np.diff(p[:,[0,2]],axis=0);lens=np.linalg.norm(runs,axis=1)
    if np.any(lens<.01):raise ValueError("water stations must be distinct")
    normals=np.c_[-runs[:,1],runs[:,0]]/lens[:,None]
    offsets=np.empty((len(p),2));offsets[0]=normals[0];offsets[-1]=normals[-1]
    for i in range(1,len(p)-1):
        v=normals[i-1]+normals[i];offsets[i]=v/max(.5,float(np.dot(v,normals[i])))
    left=p.copy();right=p.copy()
    left[:,[0,2]]-=offsets*width/2;right[:,[0,2]]+=offsets*width/2
    faces=[]
    for i in range(len(p)-1):
        # Split on the surveyed centreline. A single diagonal across a twisted
        # mitred quad interpolates away from that centreline's exact level.
        faces.append(M.quad([left[i],p[i],p[i+1],left[i+1]],uv_scale=.25,material=material))
        faces.append(M.quad([p[i],right[i],right[i+1],p[i+1]],uv_scale=.25,material=material))
    return M.merge(faces,material)
