"""Processional stonework and hatchery furnishings in the shared jungle palette.

Pieces stand at y=0; architectural fronts face -Z. Dimensions are metres.
Every material name is a parameter and every varied placement has an explicit seed.
"""
from __future__ import annotations
import math
import numpy as np
from . import mesh as M
from .stonework import MeshGroup


def sun_disc(radius=1.5, stone="verdant_carved_jade", trim="gilt_brass"):
    """A raised spiral sun seal; its front is z=0, with relief projecting -Z."""
    if radius <= 0:
        raise ValueError("a sun disc needs a positive radius")
    g = MeshGroup()
    # The legacy cylinder winds inward; opaque seals need outward faces.
    g.add(M.cylinder(radius, radius, .24, 32, material=stone).flip_winding().rotate_x(math.pi / 2))
    circle = [(radius * .86 * math.cos(a), radius * .86 * math.sin(a), -.08)
              for a in np.linspace(0, math.tau, 49)]
    g.add(M.tube(circle, [radius * .045] * len(circle), segments=6, material=trim))
    spiral = [(radius * (.08 + .58 * t) * math.cos(t * math.tau * 1.7),
               radius * (.08 + .58 * t) * math.sin(t * math.tau * 1.7), -.14)
              for t in np.linspace(0, 1, 60)]
    g.add(M.tube(spiral, [radius * .055] * len(spiral), segments=6, material=trim))
    for a in np.linspace(0, math.tau, 16, endpoint=False):
        path = [(radius * k * math.cos(a), radius * k * math.sin(a), .04) for k in (.99, 1.23)]
        g.add(M.tube(path, [radius * .07, radius * .025], segments=5, material=trim))
    return g


def procession_frame(span=6.0, height=4.2, seal_radius=.65,
                     stone="verdant_terrace_stone", carved="verdant_carved_jade", trim="gilt_brass"):
    """Paired stepped piers carrying a lintel and a small sun seal."""
    if span < 3 or height < 3:
        raise ValueError("a processional frame needs a clear human-sized opening")
    g = MeshGroup()
    for sign in (-1, 1):
        x = sign * span * .5
        g.add(M.box((1.2, .3, 1.1), center=(x, .15, 0), material=stone))
        g.add(M.box((.76, height - .3, .76), center=(x, (height + .3) * .5, 0), material=carved))
        g.add(M.box((1.08, .24, .98), center=(x, height - .35, 0), material=trim))
    g.add(M.box((span + 1.8, .45, .92), center=(0, height + .225, 0), material=carved))
    g.add(M.box((span + 2.1, .14, 1.1), center=(0, height + .52, 0), material=stone))
    if seal_radius:
        g.add(sun_disc(seal_radius, carved, trim).translate(0, height + .27, -.52))
    return g


def ritual_basin(width=4.0, length=7.0, height=.55,
                 stone="verdant_terrace_stone", water="water_lagoon"):
    """Open rectangular cistern: four joined rims and an inset water surface."""
    if min(width, length) <= 1 or height <= .2:
        raise ValueError("a basin needs room inside its rim")
    g = MeshGroup()
    rim = .32
    for sign in (-1, 1):
        g.add(M.box((rim, height, length), center=(sign * (width - rim) / 2, height / 2, 0),
                    material=stone))
        g.add(M.box((width - 2 * rim, height, rim),
                    center=(0, height / 2, sign * (length - rim) / 2), material=stone))
    x, z, y = width / 2 - rim, length / 2 - rim, height * .53
    g.add(M.quad([(-x, y, -z), (-x, y, z), (x, y, z), (x, y, -z)],
                 uv_scale=.4, material=water))
    return g


def lily_cluster(radius=1.4, seed=0, leaf="lily_pad", flower="hatchery_eggshell"):
    """Low pads and one pale bloom, placed just above a caller-owned waterline."""
    rng = np.random.default_rng(seed)
    g = MeshGroup()
    for i in range(5):
        a = float(rng.uniform(0, math.tau))
        x, z = math.cos(a) * radius * .65, math.sin(a) * radius * .65
        size = radius * float(rng.uniform(.2, .34))
        # Stagger the tops so neighbouring pads cannot share a rendering plane.
        y = .03 + i * .007
        pad = M.cylinder(size, size, .018, 11, cap_bottom=False, material=leaf).flip_winding()
        # Centre the radial leaf veins on the cap rather than at a UV corner.
        pad.uvs[:] = pad.positions[:, (0, 2)] / (2 * size) + .5
        g.add(pad.translate(x, y, z))
        if i == 0:
            for a in np.linspace(0, math.tau, 6, endpoint=False):
                petal = M.icosphere(size * .34, 1, material=flower).scale(1.0, .4, 1.8)
                g.add(petal.rotate_y(a).translate(x + math.cos(a) * size * .25,
                                                 y + .09, z + math.sin(a) * size * .25))
    return g


def brood_nest(radius=1.5, seed=0, soil="verdant_jungle_floor", egg="hatchery_eggshell"):
    """A shallow nesting mound carrying three recognisable eggs."""
    rng = np.random.default_rng(seed)
    g = MeshGroup()
    g.add(M.icosphere(radius, 2, material=soil).scale(1.0, .15, 1.0).translate(0, .14, 0))
    for i in range(3):
        a = i * math.tau / 3 + float(rng.uniform(-.18, .18))
        size = radius * float(rng.uniform(.24, .29))
        piece = M.icosphere(size, 2, material=egg).scale(.72, 1.15, .72)
        g.add(piece.translate(math.cos(a) * radius * .35, size * 1.15 + .15,
                              math.sin(a) * radius * .35))
    return g


def wall_spillway(width=.65, drop=1.1, reach=1.3,
                  stone="verdant_carved_jade", water="water_lagoon"):
    """Wall-fed outlet pouring toward -Z; y=0 is the receiving waterline."""
    if min(width, drop, reach) <= 0:
        raise ValueError("a spillway needs positive dimensions")
    g = MeshGroup()
    for sign in (-1, 1):
        g.add(M.box((.18, .52, .52), center=(sign * (width + .18) / 2, drop + .1, .12),
                    material=stone))
    g.add(M.box((width, .16, .52), center=(0, drop - .18, .12), material=stone))
    g.add(M.box((width + .36, .16, .52), center=(0, drop + .44, .12), material=stone))
    g.add(M.quad([(-width / 2, drop, -.04), (-width / 2, .015, -reach),
                  (width / 2, .015, -reach), (width / 2, drop, -.04)][::-1],
                 uv_scale=.8, material=water))
    return g
