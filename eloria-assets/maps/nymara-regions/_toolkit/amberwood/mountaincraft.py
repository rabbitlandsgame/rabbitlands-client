"""Mountain route equipment, using each region's pinned materials."""
from __future__ import annotations
import math
import numpy as np
from . import mesh as M
from . import stonework as SW

def suspension_bridge(length: float = 22.0, width: float = 1.9, sag: float = 1.5,
                seed: int = 0, deck_y: float = 0.0,
                rise: float = 0.0, stone="rubble_stone",
                timber="timber_grey", posts="timber_dark",
                rope="woven_cloth", iron="dark_iron") -> SW.MeshGroup:
    """Rope-and-plank suspension span, built along +X, deck centred on y=0.

    Panel 3 is the reference: two heavy anchor posts a side, four cables, and
    a plank deck that sags in the middle. `mesh.arch` is deliberately not used
    here - it builds in XY and extrudes along Z, so rotating it for a span
    shows the barrel end, which is the trap the production guide calls out.

    `rise` lifts the +X end that much above the -X one, the deck running
    straight between them under its own sag. A gorge cut across a mountainside
    has one shoulder above the other almost everywhere along it, and a level
    deck can only meet one of them: the other end either buries itself in the
    bank or stops in mid-air over the drop. The ends carry their own abutments
    and posts, so each one sits on its own ground.

    The deck planks are the only walk surface. The cables, posts and handrails
    are structural, so an actor can never be grounded on a rope. `walk_ends`
    records what the deck's two ends stand at, which is what the server walk
    grid needs to put the deck on the map at the height it is drawn.
    """
    if min(length, width) <= 0 or sag < 0:
        raise ValueError("bridge needs positive dimensions and nonnegative sag")
    group = SW.MeshGroup()
    half = length * 0.5
    steps = max(12, int(length / 1.1))

    def sag_at(t: float) -> float:
        # a catenary is overkill at this scale; a parabola reads identically
        return (deck_y + rise * (t - 0.5)
                - sag * (1.0 - (2.0 * t - 1.0) ** 2))

    group.walk_ends = (sag_at(0.0), sag_at(1.0))

    # -- anchor posts and abutments, one pair each end ---------------------
    for end in (-1.0, 1.0):
        base_x = end * half
        end_y = sag_at(0.0 if end < 0.0 else 1.0)
        abutment = M.box((1.7, 1.5, width + 1.5),
                         center=(base_x + end * 0.55, end_y - 0.75, 0.0),
                         uv_scale=1.1, material=stone)
        group.add(abutment)
        for side in (-1.0, 1.0):
            post = M.cylinder(0.20, 0.16, 2.5, segments=8, uv_scale=1.4,
                              material=posts)
            post.transform(M.translation(base_x, end_y, side * (width * 0.5 + 0.16)))
            group.add(post)
            cap = M.box((0.34, 0.14, 0.34),
                        center=(base_x, end_y + 2.55,
                                side * (width * 0.5 + 0.16)),
                        uv_scale=1.0, material=iron)
            group.add(cap)

    # -- cables: two decking cables carrying the planks, two handrails -----
    for side in (-1.0, 1.0):
        z = side * (width * 0.5 + 0.16)
        deck_path = np.array([[(-half + length * (i / steps)),
                               sag_at(i / steps) - 0.09, z]
                              for i in range(steps + 1)])
        group.add(M.tube(deck_path, [0.045] * (steps + 1), segments=5,
                         uv_scale=2.0, material=rope))
        rail_path = np.array([[(-half + length * (i / steps)),
                               sag_at(i / steps) + 1.02 - 0.35 *
                               (1.0 - (2.0 * (i / steps) - 1.0) ** 2), z]
                              for i in range(steps + 1)])
        group.add(M.tube(rail_path, [0.038] * (steps + 1), segments=5,
                         uv_scale=2.0, material=rope))
        # vertical hangers tying rail to deck
        for i in range(1, steps, 2):
            t = i / steps
            top = sag_at(t) + 1.02 - 0.35 * (1.0 - (2.0 * t - 1.0) ** 2)
            hanger = np.array([[-half + length * t, top, z],
                               [-half + length * t, sag_at(t) - 0.05, z]])
            group.add(M.tube(hanger, [0.016, 0.016], segments=4,
                             uv_scale=1.4, material=rope))

    # Contiguous profiled plank skins share edges. Boxes overlapped and their
    # horizontal tops approximated the slope as little steps.
    for i in range(steps):
        a,b=i/steps,(i+1)/steps
        xa,xb=-half+length*a,-half+length*b
        ya,yb=sag_at(a),sag_at(b)
        top=[(xa,ya,-width/2),(xa,ya,width/2),
             (xb,yb,width/2),(xb,yb,-width/2)]
        group.add_walk(M.quad(top,uv_scale=1.2,material=timber))
        lower=[(x,y-0.075,z) for x,y,z in top]
        group.add(M.quad(lower[::-1],uv_scale=1.2,material=timber))
        for j,k in ((0,3),(2,1)):
            group.add(M.quad([top[j],lower[j],lower[k],top[k]],
                             uv_scale=1.2,material=timber))
    return group

def temple_pinnacle(height=14.0, radius=1.9, stone="pale_ashlar",
                     snow="snow_pack", crystal="blue_crystal"):
    """A tapered octagonal lantern and spire, with separated coping courses."""
    if height <= 5 or radius <= 0:
        raise ValueError("pinnacle needs room for its lantern")
    out=SW.MeshGroup()
    shaft=height*0.55
    out.add(M.cylinder(radius,radius*0.72,shaft,8,material=stone))
    out.add(M.cylinder(radius*0.84,radius*0.84,0.24,8,material=stone)
            .translate(0,shaft+0.025,0))
    for i in range(8):
        angle=i*math.tau/8
        out.add(M.cylinder(0.12,0.10,height*0.17,6,material=stone)
                .translate(math.cos(angle)*radius*0.66,shaft+0.29,
                           math.sin(angle)*radius*0.66))
    out.add(M.icosphere(radius*0.35,1,material=crystal)
            .translate(0,shaft+height*0.085,0))
    y=shaft+height*0.17+0.32
    out.add(M.cylinder(radius*0.83,radius*0.83,0.20,8,material=stone)
            .translate(0,y,0))
    out.add(M.cylinder(radius*0.86,0.025,height-y-0.23,8,material=snow)
            .translate(0,y+0.23,0))
    return out


def ore_sledge(length=3.1,width=1.5,timber="timber_grey",
                iron="dark_iron",ore="cliff_rock"):
    """Low haulage sled with iron runners, open timber bin and stone load."""
    out=SW.MeshGroup()
    for side in (-1,1):
        out.add(M.box((0.13,0.13,length+0.5),
                     center=(side*width*0.36,0.12,0),material=iron))
    out.add(M.box((width,0.16,length),center=(0,0.34,0),material=timber))
    for side in (-1,1):
        out.add(M.box((0.12,0.65,length),center=(side*(width/2-0.06),0.765,0),
                     material=timber))
        out.add(M.box((width-0.26,0.65,0.12),
                     center=(0,0.765,side*(length/2-0.06)),material=timber))
    for i in range(5):
        rock=M.icosphere(0.29+(i%2)*0.04,1,material=ore)
        out.add(rock.translate((-0.24 if i%2 else 0.21),0.67,(i-2)*0.43))
    return out


def frozen_cascade(width=6.0, height=6.5, depth=1.0, seed=0,
                   ice="glacier_ice", rock="cliff_rock"):
    """A frozen seep backed by rock, with irregular downward icicles.

    Faces -Z. The solid backing seats it against a cavern wall; the frozen
    curtain projects into the room, leaving its silhouette visible in cutaway.
    """
    if min(width, height, depth) <= 0:
        raise ValueError("a frozen cascade needs positive dimensions")
    rng = np.random.default_rng(seed)
    out = SW.MeshGroup()
    out.add(M.box((width, height * .85, depth * .45),
                  center=(0, height * .425, depth * .6), material=rock))
    count = max(5, int(width / .55))
    for i in range(count):
        x = -width * .5 + (i + .5) * width / count
        length = height * float(rng.uniform(.5, .97))
        radius = width / count * float(rng.uniform(.43, .68))
        top = height * float(rng.uniform(.91, 1.0))
        out.add(M.cylinder(.025, radius, length, 7, uv_scale=.8,
                           material=ice).translate(x, top - length,
                                                 float(rng.uniform(-depth * .3, depth * .15))))
        # Rounded accretion at the foot, where the seep has frozen against rock.
        toe = M.icosphere(radius * 1.1, 1, material=ice)
        out.add(toe.scale(1.0, .55, 1.0).translate(x, .18, -.2))
    return out


def ore_face(width=4.4, height=3.4, seed=0, rock="cliff_rock", ore="whitehorn_silver"):
    """A worked rock face with exposed seams; the accessible face points -Z."""
    from . import crystalcraft as C
    rng = np.random.default_rng(seed)
    out = SW.MeshGroup()
    out.add(M.box((width, height, .4), center=(0, height * .5, .2), material=rock))
    for i in range(5):
        x = (i - 2) * width * .17
        y = float(rng.uniform(.4, height * .6))
        out.add(C.shard(height=height * .42, radius=.13, seed=seed + i,
                        material=ore).rotate_z(float(rng.uniform(-.25, .25))).translate(x, y, -.15))
    return out
