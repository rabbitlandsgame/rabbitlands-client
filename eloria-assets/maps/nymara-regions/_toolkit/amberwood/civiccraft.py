"""Civic waterfront pieces with material choices supplied by each region."""
from __future__ import annotations
import math
import numpy as np
from . import mesh as M
from . import stonework as SW


def arcaded_causeway(length, near, far, width=5.4, arches=3, foot=-16.0,
                     stone="ashlar", paving="cobble_paving", trim="pale_ashlar"):
    """A surveyed sloping deck on real arches, aligned along local +X.

    The deck top is exactly near/far at its ends. Arch slices share edges
    rather than overlapping boxes, and all masonry finishes below the deck.
    Piers are vertical after shearing and extend below the lagoon bed.
    """
    if length <= 0 or width <= 1 or arches < 1 or foot >= min(near, far) - 1:
        raise ValueError("causeway needs positive dimensions and a foot below its deck")
    out = SW.MeshGroup()
    level = (near + far) / 2
    top, bottom = level, level - 0.5
    x0, x1, z0, z1 = -length/2, length/2, -width/2, width/2
    out.add_walk(M.quad([(x0,top,z0),(x0,top,z1),(x1,top,z1),(x1,top,z0)],
                         uv_scale=0.5, material=paving))
    for face in [
        [(x0,bottom,z0),(x0,top,z0),(x1,top,z0),(x1,bottom,z0)],
        [(x1,bottom,z1),(x1,top,z1),(x0,top,z1),(x0,bottom,z1)],
        [(x0,bottom,z1),(x0,top,z1),(x0,top,z0),(x0,bottom,z0)],
        [(x1,bottom,z0),(x1,top,z0),(x1,top,z1),(x1,bottom,z1)],
        [(x0,bottom,z1),(x0,bottom,z0),(x1,bottom,z0),(x1,bottom,z1)]]:
        out.add(M.quad(face, uv_scale=0.6, material=stone))
    span = length / arches
    pier_width = min(1.5, span * 0.18)
    for i in range(arches + 1):
        x = x0 + span*i
        # End piers stay inside the deck footprint, leaving a flush landing.
        w = pier_width if 0 < i < arches else pier_width/2
        cx = x if 0 < i < arches else x + (w/2 if i == 0 else -w/2)
        out.add(M.box((w, bottom-foot-0.04, width),
                      center=(cx,(bottom+foot-0.04)/2,0), material=stone))
    for i in range(arches):
        left = x0 + span*i + pier_width/2
        right = x0 + span*(i+1) - pier_width/2
        xs = np.linspace(left, right, 25)
        u = np.linspace(-1, 1, 25)
        underside = bottom - 0.6 - min(4.0, span*0.34) * (1-np.sqrt(1-u*u))
        for a,b,ya,yb in zip(xs,xs[1:],underside,underside[1:]):
            for sign in (-1,1):
                face = [(a,ya,sign*width/2),(b,yb,sign*width/2),
                        (b,bottom-0.04,sign*width/2),(a,bottom-0.04,sign*width/2)]
                out.add(M.quad(face if sign > 0 else list(reversed(face)),
                               uv_scale=0.6, material=stone))
            out.add(M.quad([(a,ya,-width/2),(b,yb,-width/2),
                            (b,yb,width/2),(a,ya,width/2)],
                           uv_scale=0.6, material=stone))
    for sign in (-1,1):
        out.add(SW.balustrade(length, 0.85, material=trim)
                .translate(0,top,sign*(width/2+0.29)))
    shear = np.eye(4)
    shear[1,0] = (far-near)/length
    return out.transformed(shear)


def market_shelter(width=14.0, depth=5.0, stone="pale_ashlar",
                   timber="timber_dark", roof="slate_roof"):
    """Open civic market roof; the region supplies its single ground surface."""
    out = SW.MeshGroup()
    for x in (-width/2,0,width/2):
        for z in (-depth/2,depth/2):
            out.add(SW.column(3.2, radius=0.19, material=stone).translate(x,0,z))
    for z in (-depth/2,depth/2):
        out.add(M.box((width+0.8,0.24,0.24),center=(0,4.05,z),material=timber))
    out.add(pitched_canopy(width+1.6,depth+1.4,4.08,5.05,roof,timber))
    return out


def pitched_canopy(width, depth, eave, ridge, roof, lining="timber_dark", thickness=0.12):
    """Closed thin roof with distinct upper and underside skins."""
    if min(width,depth,thickness) <= 0 or ridge <= eave:
        raise ValueError("pitched roof needs positive dimensions and a raised ridge")
    out = SW.MeshGroup()
    for sign in (-1,1):
        top = np.array([[-width/2,eave,sign*depth/2],
                        [width/2,eave,sign*depth/2],
                        [width/2,ridge,0],[-width/2,ridge,0]],dtype=float)
        if sign < 0:
            top = top[::-1]
        lower = top - (0,thickness,0)
        out.add(M.quad(top,uv_scale=0.7,material=roof))
        out.add(M.quad(lower[::-1],uv_scale=0.7,material=lining))
        for i,j in ((0,1),(1,2),(3,0)):
            out.add(M.quad([top[i],lower[i],lower[j],top[j]],
                           uv_scale=0.7,material=roof))
    return out


def sloped_boardwalk(length, near, far, width=2.8, foot=-2.0,
                     timber="timber_grey", rope="timber_grey"):
    """A continuous plank walk along +Z, surveyed at both shore ends.

    Plank tops meet at their edges without gaps or overlapping boxes. Posts
    and ropes stand outside the walking width. The region supplies the bed.
    """
    if length <= 0 or width <= 0:
        raise ValueError("boardwalk dimensions must be positive")
    out = SW.MeshGroup()
    count = max(2, math.ceil(length / 0.34))
    for i in range(count):
        a,b = i*length/count,(i+1)*length/count
        ya,yb = near+(far-near)*a/length,near+(far-near)*b/length
        out.add_walk(M.quad([(-width/2,ya,a),(-width/2,yb,b),
                             (width/2,yb,b),(width/2,ya,a)],
                            uv_scale=1.0,material=timber))
    for side in (-1,1):
        x = side*width/2
        face=[(x,near,0),(x,far,length),(x,far-0.12,length),(x,near-0.12,0)]
        out.add(M.quad(face if side < 0 else face[::-1],material=timber))
    out.add(M.quad([(-width/2,near-0.12,0),(width/2,near-0.12,0),
                    (width/2,far-0.12,length),(-width/2,far-0.12,length)],
                   material=timber))
    posts=max(2,math.ceil(length/3.0))
    for i in range(posts+1):
        z=i*length/posts;y=near+(far-near)*z/length
        out.add(M.box((width+0.55,0.14,0.22),
                      center=(0,y-0.19,z),material=timber))
    for side in (-1,1):
        x=side*(width/2+0.16)
        for i in range(posts+1):
            z=i*length/posts; y=near+(far-near)*z/length
            out.add(M.cylinder(0.10,0.09,y+0.95-foot,6,material=timber)
                    .translate(x,foot,z))
        for i in range(posts):
            a,b=i*length/posts,(i+1)*length/posts
            path=[]
            for u in np.linspace(0,1,7):
                z=a+(b-a)*u
                y=near+(far-near)*z/length+0.86-0.13*math.sin(math.pi*u)
                path.append([x,y,z])
            out.add(M.tube(np.asarray(path),[0.035]*len(path),segments=5,material=rope))
    return out


def roadside_shelter(width=12.0,depth=5.0,stone="rubble_stone",
                      timber="timber_grey",roof="slate_roof"):
    """Low working shelter open on +Z, with a lined roof and wind walls."""
    out=SW.MeshGroup()
    out.add(M.box((width,2.55,0.48),center=(0,1.275,-depth/2),material=stone))
    for side in (-1,1):
        out.add(M.box((0.48,2.55,depth-0.54),
                      center=(side*(width/2-0.24),1.275,0.03),material=stone))
        out.add(M.box((0.24,2.65,0.24),
                      center=(side*(width/2-0.8),1.325,depth/2-0.4),material=timber))
    out.add(M.box((width-1.0,0.20,0.22),
                  center=(0,2.55,depth/2-0.4),material=timber))
    out.add(pitched_canopy(width+1,depth+1,2.75,3.65,roof,timber))
    return out


def sounding_stage(width=12.0, depth=10.0, foot=-3.0,
                   stone="pale_ashlar", timber="timber_grey"):
    """A pile-supported cistern work floor, open shaft and sounding windlass.

    The floor is at Y=0 and the east edge accepts a boardwalk flush with it.
    A tessellated floor leaves a circular shaft open; the coping is solid
    scenery, so the grounding ray never mistakes its rim for a second floor.
    """
    if width < 7 or depth < 7 or foot >= -0.5:
        raise ValueError("sounding stage needs a work floor and submerged piles")
    out = SW.MeshGroup()
    x,z,hole=width/2,depth/2,1.84
    angles=sorted(set([i*math.tau/64 for i in range(64)]+
                      [math.atan2(sz*z,sx*x)%math.tau for sx in (-1,1) for sz in (-1,1)]))
    def rim(angle,radius=None):
        dx,dz=math.cos(angle),math.sin(angle)
        r=radius if radius is not None else 1/max(abs(dx)/x,abs(dz)/z)
        return (dx*r,0,dz*r)
    for i,a in enumerate(angles):
        b=angles[(i+1)%len(angles)]
        out.add_walk(M.quad([rim(a,hole),rim(b,hole),rim(b),rim(a)],
                            material=timber,uv_scale=0.85))
    for side in (-1,1):
        out.add(M.box((width,0.18,0.24),center=(0,-0.25,side*(z-0.3)),
                      material=timber))
        for px in (-x+0.4,0,x-0.4):
            out.add(M.cylinder(0.16,0.14,-foot-0.36,8,material=timber)
                    .translate(px,foot,side*(z-0.4)))
    # An uncapped ring, raised off the floor; no hidden seating face duplicates it.
    out.add(M.lathe([(2.12,0.06),(2.12,0.82),(1.84,0.82),(1.84,0.06)],
                    segments=32,material=stone))
    for side in (-1,1):
        out.add(M.cylinder(0.13,0.11,2.8,8,material=timber)
                .translate(side*2.5,0.05,0))
    out.add(M.box((5.5,0.22,0.25),center=(0,2.94,0),material=timber))
    out.add(M.cylinder(0.035,0.035,3.4,6,material=timber).translate(0,-0.45,0))
    out.add(M.lathe([(0.28,0),(0.38,0.45),(0.31,0.45),(0.23,0.07)],
                    segments=12,material=timber).translate(0,-0.65,0))
    return out
