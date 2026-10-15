"""The Red Canyon: a herd wash through open sandstone cuts."""
from __future__ import annotations
import math
from amberwood import canyoncraft as C, mesh as M, props as P
from amberwood.stonework import MeshGroup

def dress(it,pal,seed):
    def put(g,x,y,z):it.group.add(g.translate(x,y,z))
    def room(key):
        s=it.spaces[key];return s["x0"],s["z0"],s["x1"],s["z1"],s["floor"]
    def remnant(x,y,z,r=2,h=8,k=0,depth=None):
        put(C.butte(r,h,depth,seed+k),x,y-.18,z)
    def banner(x,y,z,k=0):
        g=MeshGroup()
        g.add(M.tube([(0,0,0),(0,5,0)],[.11,.07],segments=8,cap_start=True,cap_end=True,material=pal["timber"]))
        g.add(M.tube([(-.7,4.6,0),(.7,4.6,0)],[.065,.065],segments=6,material=pal["timber"]))
        g.add(P.banner(1.25,2.2,seed+k,material=pal["cloth"]).translate(0,4.55,0))
        put(g,x,y,z)
    def shelter(x,y,z,w=7,d=4,h=4,angle=0):
        put(C.shelter(w,d,h).rotate_y(angle),x,y,z)
    def tuft(x,y,z,k=0):
        put(C.dry_tuft(seed+k),x,y,z)
    def bed(x,y,z,k=0):
        for i in range(9):tuft(x+math.sin(i*2.4)*1.4,y,z+math.cos(i*2.4),k+i)

    # Only the preparation bay, sheltered caves and vault need hanging lamps.
    it.lamps[:]=[]
    shelter(-5.3,0,5.5,w=7,d=4,h=4,angle=-math.pi/2)
    for k,(x,z) in enumerate(((-5,6),(-4.2,7))):
        put(P.barrel(radius=.42,height=.9,seed=seed+k,material=pal["timber"]),x,0,z)
    banner(5,0,5,k=2)
    it.lamps.append([-4,3.2,7])

    x0,z0,x1,z1,y=room("wind-cut")
    remnant(x0+2.4,y,z0+7,2.2,9,10,depth=3.6)
    remnant(x1-2.2,y,z1-6,1.8,7,11,depth=3.5)
    banner(x1-3,y,z0+4,12)
    bed(x0+3,y,z1-4,20)

    x0,z0,x1,z1,y=room("horse-cave")
    shelter(x0+3,y,z0+12,12,6,4.4,-math.pi/2)
    shelter(x1-2.5,y,z1-5,7,4,4.1,math.pi/2)
    bed(x0+4.5,y,z0+12,40);bed(x1-3.7,y,z1-5,55)
    it.lamps.extend([[x0+4.5,y+3.4,z0+10],[x1-4,y+3,z1-6]])

    x0,z0,x1,z1,y=room("ridge-path")
    cx=(x0+x1)/2
    for k,z in enumerate((z0+4,z1-4)):
        remnant(x0+1.8,y,z,1.6,5.6,60+k)
        banner(cx+2.0,y+3,z,65+k)
    for z in (z0+9,z1-8):
        # Low talus at the bed of the ravine, clear of the walking rib.
        remnant(x1-2,y,z,1.6,1.8,70+int(z),depth=2.7)

    x0,z0,x1,z1,y=room("scree-stair")
    remnant(x1-2.6,y,z0+7,2.2,10,80,depth=3.4)
    bed(x0+3,y,z1-4,85)
    banner(x0+3,y,z0+4,88)

    x0,z0,x1,z1,y=room("forked-wash-hub");cx=(x0+x1)/2
    remnant(cx,y,z1-1,2.8,10,90,depth=1.8)
    banner(cx-7,y,z1-3,91);banner(cx+7,y,z1-3,92)

    x0,z0,x1,z1,y=room("forked-wash-shade-fork")
    shelter(x0+3,y,z0+10,13,6,4,-math.pi/2)
    shelter(x1-2.5,y,z1-5,7,4,4.3,math.pi/2)
    bed(x0+4.2,y,z0+10,110)
    it.lamps.extend([[x0+4.4,y+3.1,z0+8],[x1-3.5,y+3.2,z1-5]])
    x0,z0,x1,z1,y=room("forked-wash-sun-fork")
    remnant(x1-2,y,z0+7,1.7,8.8,130,depth=3)
    remnant(x0+1.8,y,z1-5,1.4,4.8,131)
    for k in range(7):tuft(x1-3,y,z0+3+k*2,140+k)

    x0,z0,x1,z1,y=room("forked-wash-merge")
    for side,x in enumerate((x0+3,x1-3)):bed(x,y,z0+5,160+side*10)

    x0,z0,x1,z1,y=room("long-wash")
    # Staggered remnants turn the eye across the wash without narrowing its core.
    for k,z in enumerate((z0+5,z0+16,z0+27)):
        x=x0+1.9 if k%2==0 else x1-1.9
        remnant(x,y,z,1.55,5.5+k,180+k,depth=2.4)
    for k in (0,1,2):
        ax0,az0,ax1,az1,ay=room(f"long-wash-alcove-{k}")
        if k!=1:shelter((ax0+ax1)/2,ay,(az0+az1)/2+1,w=5,d=2.8,h=3.4)
        bed((ax0+ax1)/2,ay,(az0+az1)/2,200+k*10)

    x0,z0,x1,z1,y=room("sun-court");cx=(x0+x1)/2
    # Two wind-worn towers frame the final gap; their broken crowns read above the cuts.
    remnant(cx-5.2,y,z1-1,3,20,240,depth=3.8)
    remnant(cx+5.2,y,z1-.5,2.6,24,241,depth=3.3)
    for side in (-1,1):
        shelter(cx+side*12.5,y,z0+11,7,4,4.1,side*math.pi/2)
        for k in range(3):
            # Bleached long bones are a restrained sign of the pride's feeding bays.
            x,z=cx+side*11.8+k*.38,z0+9+k*.7
            g=M.tube([(-.65,.12,0),(0,.17,.05),(.7,.11,-.06)],[.09,.13,.08],
                     segments=7,cap_start=True,cap_end=True,material="grey_bone")
            put(g.rotate_y(k*.6),x,y,z)

    x0,z0,x1,z1,y=room("vault");cx=(x0+x1)/2
    shelter(cx,y,z1-1,w=10,d=4,h=4.8)
    banner(x0+2,y,z0+3,260)
    it.lamps.append([cx,y+3.6,z1-3])
