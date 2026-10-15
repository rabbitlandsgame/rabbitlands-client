"""A flooded customs road: bonded stores, cisterns, sluices and a bell court."""
from __future__ import annotations
import math
from amberwood import arcadecraft as A
from amberwood import templecraft as T
from amberwood import mesh as M
from amberwood import props as P
from amberwood import crownmaterials as CM


def dress(it, pal, seed):
    def put(piece,x,y,z):
        it.group.add(piece.translate(x,y,z))
    def room(key):
        s=it.spaces[key]
        return s["x0"],s["z0"],s["x1"],s["z1"],s["floor"]
    def lamp(x,y,z):
        it.lamps.append([round(x,2),round(y,2),round(z,2)])
    def frame(x,y,z,span=6.0,spring=2.5,rise=1.8):
        put(A.arcade_frame(span,spring,rise,stone=CM.MARBLE,trim=CM.VERDIGRIS),x,y,z)
        lamp(x-span/2+.65,y+spring+rise-.4,z-.45)
    pool_holes=[]
    wet_rooms=[]
    def pool(x,y,z,width,length):
        put(T.ritual_basin(width,length,height=.85,stone=CM.MARBLE,water=pal["water"]),x,y,z)
        pool_holes.append((x-width/2,z-length/2,x+width/2,z+length/2,y))
    def sluice(x,y,z,side=0,raised=.65):
        put(A.sluice_lift(3.5,3.3,raised,CM.MARBLE,CM.VERDIGRIS,CM.GILT,
                                water=pal["water"] if y > 0 else None).rotate_y(side),x,y,z)
        lamp(x-math.sin(side)*1.2,y+3.8,z-math.cos(side)*1.2)
    def cargo(x,y,z,k=0,angle=0):
        put(A.cargo_bay(stone=pal["wall"],timber=pal["timber"],seed=seed+k).rotate_y(angle),x,y,z)
        lamp(x,y+3.5,z-1.8)
    def wade(key):
        wet_rooms.append(key)
    for key in pal["flood_rooms"]:
        wade(key)

    frame(0,0,8.4,span=7,spring=2.3,rise=1.6)
    cargo(-5.2,0,5,k=1)
    put(A.hanging_bell(.45,.65,CM.VERDIGRIS,CM.GILT),4.8,3.2,5.0)
    lamp(4.8,3.7,4.2)

    x0,z0,x1,z1,y=room("customs-arcade")
    cx=(x0+x1)/2
    for side in (-1,1):
        cargo(cx+side*7.7,y,z0+8,10+side)
        cargo(cx+side*7.7,y,z1-4.5,13+side)
    frame(cx,y,z0+3.2,span=7.4)
    frame(cx,y,z1-3,span=7.4)

    # Three arches take the bridge load to the flooded hall's bed.
    x0,z0,x1,z1,pit=room("bell-walk")
    cx=(x0+x1)/2;deck=pit+3
    it.lamps[:]=[p for p in it.lamps if not z0<=p[2]<=z1]
    for z in (z0+3,(z0+z1)/2,z1-3):
        for side in (-1,1):
            put(M.box((.9,3.0,1.0),center=(0,1.5,0),material=CM.MARBLE),cx+side*3,pit,z)
        frame(cx,deck,z,span=5.3,spring=2.5,rise=1.4)

    # Cistern supply reaches visible wall gates and troughs; its centre is a wade.
    x0,z0,x1,z1,y=room("cistern")
    cx=(x0+x1)/2
    for side in (-1,1):
        pool(cx+side*9.8,y,z0+12,4.2,16)
        sluice(cx+side*12.25,y+.85,z0+12,side*math.pi/2)
    for z in (z0+4,z1-4):
        frame(cx,y,z,span=9.4,spring=3.1,rise=2.2)

    x0,z0,x1,z1,y=room("long-arcade")
    cx=(x0+x1)/2
    for z in (z0+4,z0+14,z0+24):
        frame(cx,y,z,span=8,spring=2.3,rise=1.8)
    for k in (0,2):
        ax0,az0,ax1,az1,ay=room(f"long-arcade-alcove-{k}")
        cargo((ax0+ax1)/2,ay,(az0+az1)/2,20+k)
    # The middle Kelp alcove remains accessible, with water on its old floor.

    x0,z0,x1,z1,y=room("two-sluices-hub")
    cx=(x0+x1)/2
    for side in (-1,1):
        frame(cx+side*11,y,z1-2,span=5.3,spring=2.3,rise=1.5)
    sluice(cx,y,z1-.75,raised=.35)
    # North is a maintained valve aisle with bonded stores; south is silted.
    x0,z0,x1,z1,y=room("two-sluices-north-sluice")
    cx=(x0+x1)/2
    for side in (-1,1):
        sluice(cx+side*7.2,y,z0+10,side*math.pi/2,raised=.4)
        cargo(cx+side*5.6,y,z1-4,30+side)
    frame(cx,y,z0+3,span=6.3)
    x0,z0,x1,z1,y=room("two-sluices-south-sluice")
    cx=(x0+x1)/2
    sluice(x1-.7,y,z0+10,math.pi/2,raised=1.5)
    for k,z in enumerate((z0+5,z1-4)):
        put(P.boulder(radius=1.8,seed=seed+40+k,material=CM.SAND),x0+1.9,y-.9,z)
        put(M.box((.42,3.7,.48),center=(0,1.85,0),material=CM.MARBLE)
            .rotate_z(.9),x0+2.5,y,z)
        lamp(cx+1.5,y+3.6,z)
    frame(cx,y,z1-3,span=6.3)

    x0,z0,x1,z1,y=room("two-sluices-merge")
    cx=(x0+x1)/2
    for side in (-1,1):
        pool(cx+side*7.5,y,z0+6,3.5,5)
        lamp(cx+side*5.5,y+3.8,z0+6)
    x0,z0,x1,z1,y=room("campanile-stair")
    cx=(x0+x1)/2
    frame(cx,y,z0+3,span=7.8,spring=2.5,rise=1.9)
    for side in (-1,1):
        put(A.hanging_bell(.8,1.2,CM.VERDIGRIS,CM.GILT),cx+side*7.5,y+1.0,z0+11)
        put(M.box((2.3,1.0,2.3),center=(0,.5,0),material=CM.MARBLE),cx+side*7.5,y,z0+11)
        lamp(cx+side*6,y+3.8,z0+11)

    # The great bell clears the reward doorway; its yoke is seated on twin piers.
    x0,z0,x1,z1,y=room("bell-court")
    cx=(x0+x1)/2
    frame(cx,y,z1-1.6,span=8.8,spring=4.8,rise=2.9)
    put(M.box((8.5,.5,1.05),center=(0,.25,0),material=CM.VERDIGRIS),cx,y+7.3,z1-2.2)
    put(A.hanging_bell(2.0,2.7,CM.VERDIGRIS,CM.GILT),cx,y+4.8,z1-2.2)
    for side in (-1,1):
        pool(cx+side*12.7,y,z0+11,3.6,14)
        sluice(cx+side*14.8,y+.85,z0+11,side*math.pi/2)
        lamp(cx+side*4,y+6.8,z1-5)
    x0,z0,x1,z1,y=room("vault")
    cx=(x0+x1)/2
    frame(cx,y,z1-1,span=7,spring=2.4,rise=1.5)
    for side in (-1,1):
        put(P.barrel(radius=.55,height=1.25,seed=seed+60+side,material=pal["timber"]),
            cx+side*4.5,y,z0+7)

    # Clip the shallow flood around cistern walls. Two transparent water skins
    # must not overlap at almost the same height inside a basin.
    for key in wet_rooms:
        x0,z0,x1,z1,y=room(key)
        x0+=.15; z0+=.15; x1-=.15; z1-=.15
        holes=[h for h in pool_holes if abs(h[4]-y)<.01 and h[2]>x0 and h[0]<x1 and h[3]>z0 and h[1]<z1]
        xs=sorted({x0,x1,*[max(x0,min(x1,h[i])) for h in holes for i in (0,2)]})
        zs=sorted({z0,z1,*[max(z0,min(z1,h[i])) for h in holes for i in (1,3)]})
        for a,b in zip(xs,xs[1:]):
            for c,d in zip(zs,zs[1:]):
                if any(h[0]<(a+b)/2<h[2] and h[1]<(c+d)/2<h[3] for h in holes):
                    continue
                it.group.add(M.quad([(a,y+.32,c),(a,y+.32,d),(b,y+.32,d),(b,y+.32,c)],
                                    uv_scale=.18,material=pal["water"]))
