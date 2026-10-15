"""Coastal art pass for Lantern Reach. Authored geometry, existing Eloria textures.

This module changes presentation only. The quest targets, walk grid and gated
route remain owned by build_map.py. Large dressing stays off the walk surface.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import struct

CLIENT = Path(__file__).resolve().parents[2]
TEXTURES = CLIENT / "eloria-assets/maps/nymara-regions/sunmane_steppe/textures"


def mix(a, b, t):
    return tuple(x+(y-x)*t for x,y in zip(a,b))


def cross(a,b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def unit(v):
    n=math.sqrt(sum(t*t for t in v)) or 1
    return tuple(t/n for t in v)


def rod(g,name,a,b,r,mat,sides=8):
    direction=unit(tuple(y-x for x,y in zip(a,b)))
    u=unit(cross(direction,(0,1,0) if abs(direction[1]) < .9 else (1,0,0)))
    v=cross(direction,u)
    points=[tuple(c[j]+r*(math.cos(i*math.tau/sides)*u[j]+math.sin(i*math.tau/sides)*v[j])
                  for j in range(3)) for c in (a,b) for i in range(sides)]
    faces=[]
    for i in range(sides):
        k=(i+1)%sides
        faces += [(i,k,sides+k),(i,sides+k,sides+i)]
    g.mesh(name,points,faces,mat)


def pebble(g,name,at,size,mat,rng,rings=5,sides=9):
    points=[]
    for j in range(rings+1):
        phi=math.pi*j/rings
        for i in range(sides):
            theta=i*math.tau/sides
            jitter=rng.uniform(.88,1.12)
            points.append((at[0]+math.sin(phi)*math.cos(theta)*size[0]*jitter,
                           at[1]+math.cos(phi)*size[1]*jitter,
                           at[2]+math.sin(phi)*math.sin(theta)*size[2]*jitter))
    faces=[]
    for j in range(rings):
        for i in range(sides):
            a=j*sides+i;b=j*sides+(i+1)%sides;c=b+sides;d=a+sides
            faces += [(a,c,b),(a,d,c)]
    g.mesh(name,points,faces,mat)


def torus(g,name,at,r,tube,mat,sides=24,tube_sides=5):
    points=[(at[0]+(r+math.cos(j*math.tau/tube_sides)*tube)*math.cos(i*math.tau/sides),
             at[1]+math.sin(j*math.tau/tube_sides)*tube,
             at[2]+(r+math.cos(j*math.tau/tube_sides)*tube)*math.sin(i*math.tau/sides))
            for i in range(sides) for j in range(tube_sides)]
    faces=[]
    for i in range(sides):
        for j in range(tube_sides):
            a=i*tube_sides+j;b=((i+1)%sides)*tube_sides+j
            c=((i+1)%sides)*tube_sides+(j+1)%tube_sides;d=i*tube_sides+(j+1)%tube_sides
            faces += [(a,b,c),(a,c,d)]
    g.mesh(name,points,faces,mat)


def palette(g):
    def texture(name,tint=(1,1,1),scale=.6):
        return g.material(name,tint,texture=TEXTURES/f"{name}-basecolor.png",
                          normal=TEXTURES/f"{name}-normal.png",uv_scale=scale)
    return {
        "earth":texture("ground",scale=.24),
        "wood":texture("timber",(.65,.64,.59),.5),
        "stone":texture("stone",(.48,.56,.56),.8),
        "canvas":texture("canvas",(.78,.77,.65),1.2),
        "rope":texture("textile",(.58,.45,.25),2),
        "bark":texture("leather",(.28,.25,.19),1),
        "brass":g.material("aged_brass",(.43,.28,.10),metallic=.6,roughness=.47),
        "iron":g.material("oxidised_iron",(.075,.10,.105),metallic=.7,roughness=.62),
        "slate":g.material("wet_blue_slate",(.095,.17,.20),roughness=.55),
        "slate_light":g.material("slate_edges",(.14,.23,.26),roughness=.5),
        "leaf":g.material("coastal_grass",(.14,.25,.12)),
        "leaf_tip":g.material("grass_seedheads",(.29,.35,.17)),
        "needles":g.material("wind_pine",(.055,.16,.105)),
        "glow":g.material("amber_glass",(1,.49,.10),True),
        "water":g.material("sea",(.05,.14,.18),roughness=.25),
        "foam":g.material("sea_foam",(.33,.53,.52)),
        "parchment":g.material("keeper_parchment",(.71,.60,.40)),
    }


def curved_boat(g,m,name,x=0,y=0,z=0,sail=True):
    """Planked hull, gunwale, ribs, thwarts, mast, rigging and a bowed sail."""
    g.group=name
    sections=[(-4.4,.12),(-3.7,1.15),(-2.5,1.85),(-.7,2.05),(1.3,1.95),(3,1.3),(4.2,.12)]
    for side in [-1,1]:
        for band in range(6):
            lower=band/6;upper=(band+1)/6
            points=[]
            for zz,width in sections:
                for t in [lower,upper]:
                    points.append((x+side*width*(.55+.45*t),y+.08+t*1.35+.18*(abs(zz)/4.4)**2,z+zz))
            faces=[]
            for i in range(len(sections)-1):
                a=i*2
                faces += [(a,a+2,a+3),(a,a+3,a+1)]
            g.mesh(name+"_hull_plank",points,faces,m["wood"])
        rim=[(x+side*w,y+1.5+.18*(abs(zz)/4.4)**2,z+zz) for zz,w in sections]
        for a,b in zip(rim,rim[1:]):
            rod(g,"gunwale",a,b,.10,m["wood"])
        for zz,width in sections[1:-1]:
            rod(g,"ribs",(x+side*width*.55,y+.16,z+zz),(x+side*width,y+1.47,z+zz),.065,m["wood"])
    for i in range(24):
        zz=-3.7+i*.31
        width=next((wa+(wb-wa)*(zz-za)/(zb-za) for (za,wa),(zb,wb) in zip(sections,sections[1:]) if za<=zz<=zb),.3)
        g.box("deck_board",x,y+.4,z+zz,width*1.7,.13,.29,m["wood"])
    for zz in [-2.3,.2,2.1]:
        g.box("seat",x,y+.97,z+zz,3.2,.15,.42,m["wood"])
    rod(g,"mast",(x,y+.4,z),(x,y+7.1,z),.12,m["wood"],12)
    for side in [-1,1]:
        rod(g,"stay",(x,y+6.9,z),(x+side*1.7,y+1.6,z+2.5),.025,m["rope"],5)
    rod(g,"forestay",(x,y+6.9,z),(x,y+1.7,z-4.2),.024,m["rope"],5)
    rod(g,"yard",(x-2.2,y+6.2,z),(x+2.2,y+6.2,z),.08,m["wood"])
    if sail:
        points=[]
        for row in range(9):
            t=row/8
            for col in range(9):
                u=col/8
                points.append((x+(u-.5)*(4.25-.75*t), y+6.12-3.85*t,
                               z+.65*math.sin(math.pi*u)*math.sin(math.pi*t)))
        faces=[]
        for row in range(8):
            for col in range(8):
                a=row*9+col
                faces += [(a,a+1,a+10),(a,a+10,a+9)]
        g.mesh("canvas_sail",points,faces,m["canvas"])
        for col in [0,2,4,6,8]:
            u=col/8
            rod(g,"sail_seam",(x+(u-.5)*4.25,y+6.1,z+.012),
                (x+(u-.5)*3.5,y+2.28,z+.012),.013,m["rope"],4)
    else:
        for j in range(7):
            rod(g,"furled_sail",(x-1.9,y+6.25+j*.035,z),(x+1.9,y+6.25+j*.035,z),.13,m["canvas"])
        rod(g,"broken_oar",(x-2,y+1.7,z-1),(x+.6,y+1.55,z+1.6),.045,m["wood"])
    for side in [-1,1]:
        rod(g,"oar",(x+side*.5,y+1.1,z+2.2),(x+side*2.8,y+1.7,z-1.8),.045,m["wood"])
    torus(g,"deck_rope",(x+.75,y+.57,z+2.6),.37,.05,m["rope"])


def barrel(g,m,x,y,z):
    for j in range(14):
        a=j*math.tau/14;b=(j+.94)*math.tau/14
        vertices=[(x+math.cos(t)*r,y+h,z+math.sin(t)*r) for h,r in [(0,.35),(.55,.43),(1.1,.35)] for t in [a,b]]
        g.mesh("barrel_stave",vertices,[(0,1,3),(0,3,2),(2,3,5),(2,5,4)],m["wood"])
    for h,r in [(.12,.38),(.54,.445),(.97,.39)]:
        torus(g,"barrel_hoop",(x,y+h,z),r,.035,m["iron"])
    g.cylinder("barrel_lid",x,y+1.07,z,.35,.055,m["wood"],14)


def chest(g,m,x,y,z):
    for row in range(4):
        g.box("chest_plank",x,y+.13+row*.19,z,1.75,.18,1.05,m["wood"])
    # Arched lid assembled as staves, with two matching iron straps.
    for i in range(10):
        a=i*math.pi/10;b=(i+1)*math.pi/10
        points=[(xx,y+.7+math.sin(t)*.38,z+math.cos(t)*.53)
                for xx in [x-.88,x+.88] for t in [a,b]]
        g.mesh("chest_lid",points,[(0,2,3),(0,3,1)],m["wood"])
        for xx in [x-.6,x+.6]:
            strip=[(xxx,y+.71+math.sin(t)*.39,z+math.cos(t)*.54)
                   for xxx in [xx-.045,xx+.045] for t in [a,b]]
            g.mesh("chest_strap",strip,[(0,2,3),(0,3,1)],m["iron"])
    g.box("lock_plate",x,y+.67,z+.55,.22,.33,.06,m["brass"])
    for side in [-1,1]:
        for zz in [-.49,.49]:
            g.box("chest_corner",x+side*.84,y+.35,z+zz,.09,.7,.09,m["iron"])
    # The same turquoise seal makes the shared-storage connection visible.
    g.cylinder("cache_seal",x,y+1.1,z,.19,.055,m["foam"],8)


def shelter(g,m,name,x,ty,ground):
    z=-ty;h=ground(x,ty)
    g.group="Build_"+name
    for side in [-1,1]:
        for row in range(3):
            for col in range(4):
                g.box("stone_footing",x+side*3.6+(col-1.5)*.95,h+.12+row*.23,z-3.6,.91,.21,.58,m["stone"])
        for col in range(11):
            xx=x+side*3.5+(col-5)*.35
            g.box("wall_board",xx,h+1.85,z-3.6,.33,2.3,.16,m["wood"])
        for xx in [x+side*1.65,x+side*5.5]:
            g.box("wall_post",xx,h+1.9,z-3.6,.23,3.8,.27,m["wood"])
        rod(g,"wall_brace",(x+side*1.8,h+1,z-3.43),(x+side*5.35,h+3.1,z-3.43),.10,m["wood"],4)
    g.box("door_lintel",x,h+3.25,z-3.6,3.5,.25,.42,m["wood"])
    # Left wall stays within the existing blocked strip; an open front and
    # rear doorway preserve both the approach sightlines and route collision.
    for col in range(19):
        g.box("side_board",x-5.5,h+1.6,z-3.2+col*.35,.18,3.2,.33,m["wood"])
    for zz in [z-3.5,z-.25,z+3.3]:
        g.box("side_post",x-5.5,h+1.8,zz,.27,3.6,.27,m["wood"])
    # Retained back roof strip, with overlapping pitched slate courses.
    g.group="Roof_"+name
    for row in range(5):
        zz=z-4.35+row*.37
        hh=h+3.15+row*.16
        for col in range(25):
            xx=x-5.9+col*.48+(row%2)*.16
            pts=[(xx,hh,zz),(xx+.46,hh,zz),(xx+.46,hh+.18,zz+.43),(xx,hh+.18,zz+.43)]
            g.mesh("slate_tile",pts,[(0,2,1),(0,3,2)],m["slate_light"] if (col+row)%5==0 else m["slate"])
    rod(g,"roof_ridge",(x-5.9,h+4.02,z-2.5),(x+6,h+4.02,z-2.5),.12,m["iron"])
    g.group="Build_"+name
    # Corner furniture is tucked into existing solid wall footprints.
    barrel(g,m,x-5.2,h,z-3.55)
    barrel(g,m,x+4.8,h,z-3.7)


def lighthouse(g,m,ground):
    x,z=99,-101;h=ground(x,101)
    g.group="Build_BeaconTower"
    for row in range(14):
        lower=row*.5;upper=(row+1)*.5
        r=2.5-row*.026
        for col in range(24):
            a=(col+(row%2)*.5)*math.tau/24;b=a+math.tau/24-.018
            pts=[(x+math.cos(t)*rr,h+yy,z+math.sin(t)*rr)
                 for yy,rr in [(lower+.016,r),(upper-.016,r-.024)] for t in [a,b]]
            colors=[(.80+((col*13+row*3)%9)*.025, .89, .84, 1)]*4
            g.mesh("stone_course",pts,[(0,3,1),(0,2,3)],m["stone"],colors)
    for hh,rr in [(0,2.53),(.5,2.5),(6.9,2.2),(7.1,3.0),(7.5,3.08)]:
        g.cylinder("stone_moulding",x,h+hh,z,rr,.18,m["stone"],32)
    g.group="Build_LanternRoom"
    g.cylinder("balcony_floor",x,h+7.38,z,3.05,.16,m["wood"],32)
    for i in range(24):
        a=i*math.tau/24;xx=x+math.cos(a)*3;zz=z+math.sin(a)*3
        rod(g,"balcony_baluster",(xx,h+7.5,zz),(xx,h+8.45,zz),.035,m["iron"],6)
    torus(g,"balcony_rail",(x,h+8.45,z),3,.055,m["iron"],48)
    for i in range(8):
        a=i*math.tau/8;xx=x+math.cos(a)*2.15;zz=z+math.sin(a)*2.15
        rod(g,"lantern_mullion",(xx,h+7.55,zz),(xx,h+10.7,zz),.085,m["brass"])
    for hh in [7.65,8.35,10.55]:
        torus(g,"lantern_frame",(x,h+hh,z),2.17,.065,m["brass"],40)
    # A Fresnel-style stack gives the light a recognizable optical housing.
    for row in range(12):
        r=.7+.25*math.sin(row/11*math.pi)
        g.cylinder("optic_ring",x,h+8.2+row*.16,z,r,.06,m["brass"],32)
    g.group="Roof_Beacon"
    # A closed backing prevents light leaks through the slate joints.
    g.cylinder("roof_backing",x,h+10.82,z,3.13,1.82,m["iron"],64,0)
    for row in range(7):
        bottom=3.15*(1-row/7);top=3.15*(1-(row+1)/7)
        for col in range(32):
            a=(col+(row%2)*.5)*math.tau/32;b=a+.98*math.tau/32
            pts=[(x+math.cos(t)*r,h+10.85+up,z+math.sin(t)*r)
                 for r,up in [(bottom,row*.26+.06),(top,(row+1)*.26+.02)] for t in [a,b]]
            g.mesh("roof_scale",pts,[(0,3,1),(0,2,3)],m["slate_light"] if (col+row*3)%7==0 else m["slate"])
    rod(g,"finial",(x,h+12.6,z),(x,h+13.5,z),.055,m["brass"])
    rod(g,"weather_vane",(x-.65,h+13.1,z),(x+.65,h+13.1,z),.035,m["brass"])
    g.group="Prop_BeaconHousing"
    g.cylinder("housing_pedestal",97,ground(97,98),-98,.48,1.1,m["stone"],16)
    for hh,rr in [(1.1,.55),(1.18,.49),(1.55,.49)]:
        g.cylinder("housing_ring",97,ground(97,98)+hh,-98,rr,.10,m["brass"],16)


def shoreline(g,m,land,ground):
    edges={}
    for x,y in land:
        for dx,dy,a,b in [(0,-1,(x-.5,y-.5),(x+.5,y-.5)),(1,0,(x+.5,y-.5),(x+.5,y+.5)),
                          (0,1,(x+.5,y+.5),(x-.5,y+.5)),(-1,0,(x-.5,y+.5),(x-.5,y-.5))]:
            if (x+dx,y+dy) not in land:
                edges[a]=b
    g.group="Scenery_ShoreCliffs"
    while edges:
        first=next(iter(edges));at=first;loop=[]
        while at in edges:
            loop.append(at);at=edges.pop(at)
            if at==first: break
        if len(loop)<3: continue
        # Smooth the outline only outside the collision footprint. Three rock
        # courses and a shallow apron hide the prototype's square tile edge.
        for _ in range(2):
            loop=[p for a,b in zip(loop,loop[1:]+loop[:1]) for p in [mix(a,b,.25),mix(a,b,.75)]]
        points=[];colors=[]
        for i,a in enumerate(loop):
            prev=loop[i-1];nxt=loop[(i+1)%len(loop)]
            dx,dy=nxt[0]-prev[0],nxt[1]-prev[1];l=math.hypot(dx,dy) or 1
            outward=(dy/l,-dx/l)
            jag=.15*math.sin(i*1.8)+.12*math.cos(i*.7)
            for width,height in [(0,ground(*a)-.02),(.65+jag,ground(*a)-.3),(1.1+jag,-.7),(1.65+jag,-1.65),(2.7+jag,-2.6)]:
                points.append((a[0]+outward[0]*width,height,-a[1]-outward[1]*width))
                colors.append((.78,.89,.82,1) if width<1 else (.53,.66,.64,1))
        faces=[]
        for i in range(len(loop)):
            for j in range(4):
                a=i*5+j;b=((i+1)%len(loop))*5+j
                faces.extend([(a,a+1,b+1),(a,b+1,b)])
        g.mesh("cliff_courses",points,faces,m["stone"],colors)


def gate_placements(p):
    """Fit the complete gate footing inside the land at each crossing.

    The reusable gate is 8.1 m wide including its stone feet. The upper
    connectors are narrower, and the return connector is off-centre. These
    are presentation transforms only; the server still owns the gate bounds.
    """
    def surface(x, y):
        # Same shared corners and diagonal as Walk_Terrain below.
        xx, yy = math.floor(x + .5) - .5, math.floor(y + .5) - .5
        u, v = x - xx, y - yy
        def corner(a, b):
            return sum(p.ground(a + dx, b + dy)
                       for dx in (-.5, .5) for dy in (-.5, .5)) / 4
        a, b, c, d = (corner(xx, yy), corner(xx + 1, yy),
                      corner(xx + 1, yy + 1), corner(xx, yy + 1))
        return a * (1-u) + b * (u-v) + c * v if u >= v else a * (1-v) + c * u + d * (v-u)

    result = {}
    for gate in p.GATES:
        x, y = gate["at"]
        left = right = x
        if not p.is_land(x, y):
            raise ValueError(f"Gate {gate['id']} has no land at its crossing")
        while left > 0 and p.is_land(left - 1, y):
            left -= 1
        while right < p.SIZE - 1 and p.is_land(right + 1, y):
            right += 1
        # Clip the original footprint to the shore, leaving 10 cm of bank.
        lo, hi = max(x - 4.05, left - .4), min(x + 4.05, right + .4)
        scale = (hi - lo) / 8.1
        centre = (lo + hi) / 2
        samples = [surface(centre + side * offset * scale, y + dz)
                   for side in (-1, 1) for offset in (3.45, 4.05)
                   for dz in (-.3, .3)]
        result[gate["id"]] = {"position": [round(centre, 6), round(min(samples) - .02, 6), -y],
                               "scale": [round(scale, 6), 1, 1]}
    return result


def author_world(g,p):
    rng=random.Random(90261)
    m=palette(g)
    land={(x,y) for y in range(p.SIZE) for x in range(p.SIZE) if p.is_land(x,y)}
    grid=bytearray(p.SIZE*p.SIZE)
    for x,y in land:
        grid[y*p.SIZE+x]=round((p.ground(x,y)+2.2)/.2)
    g.group="Walk_Terrain"
    points=[];faces=[];colors=[]
    for x,y in sorted(land):
        start=len(points)
        for xx,yy in [(x-.5,y-.5),(x+.5,y-.5),(x+.5,y+.5),(x-.5,y+.5)]:
            # Shared corner elevations stitch the old steps into a continuous
            # surface. Difference from a server tile's centre is at most 0.1 m.
            h=sum(p.ground(xx+dx,yy+dy) for dx in [-.5,.5] for dy in [-.5,.5])/4
            points.append((xx,h,-yy))
            distance=min(p.road_distance((xx,yy)),p.road_distance((xx,yy),p.SHORTCUT))
            blend=max(0,min(1,(distance-1.1)/1.45))
            tint=mix((.91,.84,.65,1),(.24,.48,.31,1),blend)
            variation=.94+.04*math.sin(xx*.7+yy*.41)
            colors.append(tuple(c*variation for c in tint[:3])+(1,))
        faces += [(start,start+1,start+2),(start,start+2,start+3)]
    g.mesh("continuous_ground",points,faces,m["earth"],colors)
    shoreline(g,m,land,p.ground)
    g.group="Scenery_Water"
    g.box("water",60,-1.7,-60,500,.2,500,m["water"])
    blockers=[]
    for name,x,y in [("Boathouse",34,35),("Workshop",46,73)]:
        shelter(g,m,name,x,y,p.ground)
        blockers += [[x-6,y+3,x-2,y+4],[x+2,y+3,x+6,y+4],[x-6,y-3,x-5,y+3]]
    lighthouse(g,m,p.ground)
    blockers.append([97,99,101,103])
    curved_boat(g,m,"Build_GroundedFerry",12,p.ground(12,15),-15,False)
    blockers.append([10,11,14,19])
    for x1,y1,x2,y2 in blockers:
        for y in range(y1,y2+1):
            for x in range(x1,x2+1): grid[y*p.SIZE+x]=0
    for target in p.TARGETS:
        x,y=target["tile"];h=p.ground(x,y);z=-y
        g.group="Prop_"+target["id"]
        if target["kind"]=="storage": chest(g,m,x,h,z)
        if target["kind"] in ("manufacturing","merchant"):
            for col in range(5):
                g.box("bench_plank",x,h+1,z-.5+col*.23,2.25,.16,.21,m["wood"])
            for dx in [-.85,.85]:
                for dz in [-.4,.4]:
                    g.box("bench_leg",x+dx,h+.5,z+dz,.14,1,.14,m["wood"])
            g.box("cloth_roll",x-.55,h+1.16,z,.65,.18,.34,m["canvas"])
            rod(g,"hatchet_handle",(x+.3,h+1.14,z+.3),(x+.7,h+1.14,z-.28),.035,m["wood"])
            g.box("hatchet_blade",x+.68,h+1.19,z-.26,.30,.10,.20,m["iron"])
        if target["id"]=="chart":
            g.box("chart_frame",x,h+1.6,z,1.4,1.65,.13,m["wood"])
            g.box("parchment",x,h+1.6,z+.08,1.17,1.43,.04,m["parchment"])
            for j in range(6):
                rod(g,"chart_route",(x-.37+j*.12,h+1.1+j*.17,z+.11),(x-.25+j*.12,h+1.27+j*.17,z+.11),.013,m["iron"],4)
    lanterns=[]
    g.group="Prop_PathLanterns"
    for x,y in p.ROUTE[::2]+p.SHORTCUT[::2]:
        x+=2.5
        # Tall posts must not obscure an interaction at the gameplay camera.
        if any(math.hypot(x-t[key][0],y-t[key][1])<3.5
               for t in p.TARGETS for key in ("tile","approach")): continue
        h=p.ground(x,y)
        rod(g,"lantern_post",(x,h,-y),(x,h+2.8,-y),.075,m["wood"])
        rod(g,"lantern_arm",(x,h+2.7,-y),(x-.55,h+2.7,-y),.045,m["iron"])
        xx=x-.5
        g.box("lantern_base",xx,h+2,-y,.36,.09,.36,m["iron"])
        g.box("lantern_glass",xx,h+2.25,-y,.28,.43,.28,m["glow"])
        g.cylinder("lantern_cap",xx,h+2.5,-y,.28,.20,m["iron"],4,0)
        for dx in [-.16,.16]:
            for dz in [-.16,.16]: rod(g,"lantern_frame",(xx+dx,h+2,-y+dz),(xx+dx,h+2.5,-y+dz),.02,m["iron"],5)
        lanterns.append([xx,h+2.25,-y])
    # Low, non-blocking tufts outside the worn path and target approach circles.
    g.group="Scenery_ShoreGrass"
    grass_count=0
    for _ in range(1600):
        x,y=rng.uniform(6,115),rng.uniform(8,110)
        if (round(x),round(y)) not in land: continue
        if min(p.road_distance((x,y)),p.road_distance((x,y),p.SHORTCUT))<2.6: continue
        if any(math.hypot(x-t["tile"][0],y-t["tile"][1])<3.2 for t in p.TARGETS): continue
        if not grid[round(y)*120+round(x)]: continue
        h=p.ground(x,y)
        for j in range(7):
            a=rng.random()*math.tau;w=rng.uniform(.04,.08);height=rng.uniform(.25,.65)
            dx,dz=math.cos(a),math.sin(a)
            pts=[(x-dx*w,h,-y-dz*w),(x+dx*w,h,-y+dz*w),
                 (x+dx*.12,h+height*.65,-y+dz*.12),(x+dx*.3,h+height,-y+dz*.3)]
            g.mesh("grass_blade",pts,[(0,1,2),(0,2,3)],m["leaf"] if j%3 else m["leaf_tip"])
        grass_count+=1
    solids=[]
    g.group="Scenery_ShoreRocks"
    for _ in range(2200):
        x,y=rng.uniform(5,117),rng.uniform(6,113);r=rng.uniform(.55,1.5)
        if any((xx,yy) in land for xx in range(math.floor(x-r-.5),math.ceil(x+r+.5)+1)
               for yy in range(math.floor(y-r-.5),math.ceil(y+r+.5)+1)): continue
        if not any((round(x+dx),round(y+dy)) in land for dx,dy in [(0,4),(0,-4),(4,0),(-4,0)]): continue
        if any(math.hypot(x-t["tile"][0],y-t["tile"][1])<5 for t in p.TARGETS): continue
        if any(math.hypot(x-s["tile"][0],y-s["tile"][1])<r+s["radius"]+.5 for s in solids): continue
        pebble(g,"sea_rock",(x,-1,-y),(r,r*.95,r*.85),m["stone"],rng)
        solids.append({"tile":[x,y],"radius":r})
        if len(solids)>=70: break
    g.group="Scenery_WindPines"
    # Pines grow on unwalkable rocky outcrops; none stands between a target
    # and its approach tile. Asymmetric tiers give them a prevailing wind.
    for index in [3,11,19,27,35,43,51]:
        if index>=len(solids): continue
        x,y=solids[index]["tile"];base=-.2
        rod(g,"pine_trunk",(x,base,-y),(x+.25,base+4.8,-y),.13,m["bark"])
        for row in range(4):
            g.cylinder("wind_pine",x+row*.17,base+1.6+row*.7,-y,.95-row*.16,1.8,m["needles"],7,0)
    # A real planked arrival deck and dock furniture establish a harbor scale.
    g.group="Prop_Dock"
    for j in range(9):
        g.box("dock_plank",106.5,p.ground(106,22)+.025,-22+j*.22,3,.05,.20,m["wood"])
    for x,y in [(108,22),(105,23)]:
        rod(g,"bollard",(x,-1.5,-y),(x,p.ground(x,y)+.5,-y),.14,m["wood"],10)
        torus(g,"mooring_rope",(x,p.ground(x,y)+.3,-y),.22,.045,m["rope"])
    g.group=""
    return grid,blockers,{"artVersion":"0.2.0","lanterns":lanterns,"solidDressing":solids,
                          "gatePlacements":gate_placements(p),
                          "grassClumps":grass_count,"terrain":"continuous vertex-blended textured surface"}


def read_glb(path):
    content=path.read_bytes();length=struct.unpack_from("<I",content,12)[0]
    doc=json.loads(content[20:20+length]);start=20+length
    n=struct.unpack_from("<I",content,start)[0]
    return doc,bytearray(content[start+8:start+8+n])


def write_glb(path,doc,blob):
    doc["buffers"]=[{"byteLength":len(blob)}]
    encoded=json.dumps(doc,separators=(",",":")).encode()
    encoded+=b" "*(-len(encoded)%4);blob+=b"\0"*(-len(blob)%4)
    path.write_bytes(struct.pack("<4sII",b"glTF",2,28+len(encoded)+len(blob))+
                     struct.pack("<I4s",len(encoded),b"JSON")+encoded+
                     struct.pack("<I4s",len(blob),b"BIN\0")+blob)


def runtime_assets(out,glb_type):
    """Self-contained copies of existing models, with selected native clips.

    Animation tracks are matched by joint name, just as the production native
    importer does. Textures and meshes stay byte-for-byte within the source GLB.
    """
    models=out/"models";models.mkdir(exist_ok=True)
    sources={"reed.glb":"godot-client/assets/world/harvestables/mirror_reed.glb",
             "quartz.glb":"godot-client/assets/world/harvestables/quartz.glb",
             "boar.glb":"godot-client/assets/actors/native/creatures/wild_boar.glb"}
    provenance=[]
    for name,rel in sources.items():
        src=CLIENT/rel;shutil.copyfile(src,models/name)
        provenance.append({"output":"models/"+name,"source":rel,"sha256":hashlib.sha256(src.read_bytes()).hexdigest(),"changes":"none"})
    source=CLIENT/"godot-client/assets/actors/native/races/luminous_male.glb"
    animation=CLIENT/"godot-client/assets/actors/native/shared/Universal_Animation_Library.glb"
    doc,blob=read_glb(source);clips,clip_blob=read_glb(animation)
    nodes={n.get("name"):i for i,n in enumerate(doc["nodes"])}
    accessors={};views={}
    def transfer(index):
        if index in accessors:return accessors[index]
        acc=copy.deepcopy(clips["accessors"][index]);vi=acc["bufferView"]
        if vi not in views:
            v=copy.deepcopy(clips["bufferViews"][vi]);start=v.get("byteOffset",0)
            while len(blob)%4:blob.append(0)
            v["buffer"]=0;v["byteOffset"]=len(blob)
            blob.extend(clip_blob[start:start+v["byteLength"]])
            views[vi]=len(doc["bufferViews"]);doc["bufferViews"].append(v)
        acc["bufferView"]=views[vi]
        accessors[index]=len(doc["accessors"]);doc["accessors"].append(acc)
        return accessors[index]
    doc["animations"]=[]
    wanted={"Idle_A","Walk","Fighting_Idle","Sword_Attack","Hit_Chest"}
    for clip in clips["animations"]:
        if clip.get("name") not in wanted:continue
        result={"name":clip["name"],"samplers":[],"channels":[]}
        for channel in clip["channels"]:
            name=clips["nodes"][channel["target"]["node"]].get("name")
            name="Head" if name=="head" else name
            if name not in nodes:continue
            sampler=copy.deepcopy(clip["samplers"][channel["sampler"]])
            sampler["input"]=transfer(sampler["input"]);sampler["output"]=transfer(sampler["output"])
            result["channels"].append({"sampler":len(result["samplers"]),"target":{"node":nodes[name],"path":channel["target"]["path"]}})
            result["samplers"].append(sampler)
        if result["channels"]:doc["animations"].append(result)
    assert {a["name"] for a in doc["animations"]} >= {"Idle_A","Walk"}
    write_glb(models/"traveler.glb",doc,blob)
    provenance.append({"output":"models/traveler.glb","source":str(source.relative_to(CLIENT)),
                       "sha256":hashlib.sha256(source.read_bytes()).hexdigest(),
                       "animationSource":str(animation.relative_to(CLIENT)),
                       "animationSHA256":hashlib.sha256(animation.read_bytes()).hexdigest(),
                       "changes":"Selected animation channels mapped to existing joints; source meshes and images retained."})
    boat=glb_type();m=palette(boat);curved_boat(boat,m,"SavedBoat")
    boat.write(models/"boat.glb")
    provenance.append({"output":"models/boat.glb","source":"art_authoring.py","changes":"Original curved hull, planking, sail and rigging."})
    gate=glb_type();m=palette(gate)
    gate.group="GatePosts"
    for x in [-3.75,3.75]:
        gate.box("footing",x,.2,0,.6,.4,.6,m["stone"])
        gate.box("post",x,1.6,0,.32,3.2,.32,m["wood"])
        gate.cylinder("cap",x,3.15,0,.31,.25,m["iron"],4,0)
    gate.group="GateLeaf"
    for x in [i*.45-3.4 for i in range(16)]:
        gate.box("picket",x,1.45,0,.23,2.15,.18,m["wood"])
    for y in [.65,2.25]:
        gate.box("rail",0,y,.05,7.3,.18,.2,m["wood"])
    for side in [-1,1]:
        rod(gate,"brace",(side*.1,.7,.2),(side*3.5,2.2,.2),.075,m["iron"],4)
        for y in [.8,2.1]: gate.box("hinge",side*3.5,y,.22,.42,.13,.08,m["iron"])
    gate.write(models/"gate.glb")
    provenance.append({"output":"models/gate.glb","source":"art_authoring.py","changes":"Original timber pickets, iron braces and hinges."})
    return {"reusedAssets":provenance,"textureSource":str(TEXTURES.relative_to(CLIENT)),
            "textureAttribution":"Original Eloria project work, CC-BY-4.0; Sunmane Steppe texture set.",
            "animationAttribution":"Existing Eloria Universal Animation Library; retain repository's source attribution.",
            "geometry":"Original Lantern Reach procedural geometry by art_authoring.py."}
