"""Reusable arcades, bells and sluice mechanisms for civic waterworks.

Dimensions are metres; fronts face -Z and pieces stand at y=0. Material
names are supplied by the caller. Bells have a real inner shell and lip.
"""
from __future__ import annotations
import math
import numpy as np
from . import mesh as M
from .stonework import MeshGroup


def arcade_frame(span=6.0, spring=2.8, rise=2.0,
                  stone="ashlar", trim="pale_ashlar", depth=.8):
    """Paired piers carrying a continuous arch, with no sill across the route."""
    g = MeshGroup()
    thick = .45
    for side in (-1, 1):
        x = side * (span / 2 + thick / 2)
        g.add(M.box((.85, .22, depth + .36), center=(x, .11, 0), material=stone))
        g.add(M.box((thick, spring - .22, depth), center=(x, (spring + .22) / 2, 0),
                    uv_scale=.55, material=stone))
        g.add(M.box((.76, .16, depth + .18), center=(x, spring - .12, 0), material=trim))
    g.add(M.arch(span, rise, thick, depth, 24, uv_scale=.55, material=stone).translate(0, spring, 0))
    g.add(M.arch(span + thick * 2, rise * (1 + thick * 2 / span), .10, depth + .10,
                 24, uv_scale=.5, material=trim).translate(0, spring, 0))
    return g


def hanging_bell(radius=1.2, height=1.7, bronze="dark_iron", lip="gilt_brass"):
    """A hollow flared bell whose mouth is at y=0; hang it by its crown."""
    if min(radius, height) <= 0:
        raise ValueError("bell dimensions must be positive")
    profile=[(radius, .06 * height), (radius * 1.02, .16 * height),
             (radius * .84, .25 * height), (radius * .60, .65 * height),
             (radius * .48, .87 * height), (radius * .24, height),
             (radius * .12, height), (radius * .16, .85 * height),
             (radius * .36, .74 * height), (radius * .48, .57 * height),
             (radius * .70, .24 * height), (radius * .89, .15 * height),
             (radius * .86, .08 * height), (radius, .06 * height)]
    g = MeshGroup()
    # The legacy lathe winds inward relative to its declared normals.
    g.add(M.lathe(profile, 32, uv_scale=.65, material=bronze).flip_winding())
    ring=[(radius * 1.025 * math.cos(a), height * .15, radius * 1.025 * math.sin(a))
          for a in np.linspace(0, math.tau, 49)]
    g.add(M.tube(ring,[radius * .055] * len(ring),segments=8,material=lip))
    g.add(M.tube([(0, height * .88, 0), (0, height * .1, 0)], [.055, .08],
                 segments=8,cap_start=True,cap_end=True,material=lip))
    g.add(M.icosphere(radius * .18, 2, material=lip).translate(0, height * .10, 0))
    return g


def sluice_lift(width=4.0, height=3.4, raised=.65,
                 stone="ashlar", timber="timber_dark", metal="dark_iron", water=None):
    """A gate in vertical guides with a screw lift and a six-spoke handwheel."""
    if width <= 1 or height <= 1 or not 0 <= raised < height:
        raise ValueError("sluice needs a positive frame and a contained gate")
    g = MeshGroup()
    for side in (-1, 1):
        x=side*(width/2+.25)
        g.add(M.box((.65,height,.8),center=(x,height/2,0),material=stone))
        g.add(M.box((.13,height,.20),center=(side*(width/2+.04),height/2,-.43),material=metal))
    g.add(M.box((width+1.4,.30,.94),center=(0,height+.15,0),material=stone))
    g.add(M.box((width,height-raised,.23),center=(0,(height+raised)/2,0),material=timber))
    # A recessed dark throat remains behind the raised gate.
    g.add(M.box((width,raised,.12),center=(0,raised/2,.20),material="dark_iron"))
    if water is not None and raised > .2:
        sheet=[(-width*.37,raised*.62,-.15),(-width*.37,-.40,-1.3),
               (width*.37,-.40,-1.3),(width*.37,raised*.62,-.15)]
        g.add(M.quad(sheet[::-1],uv_scale=.4,material=water))
    for y in (raised+.25,height-.25):
        g.add(M.box((width,.15,.10),center=(0,y,-.17),material=metal))
    g.add(M.tube([(0,height-.3,-.25),(0,height+1.2,-.25)],[.085,.085],
                 segments=8,cap_start=True,cap_end=True,material=metal))
    # A helical rib exposes the drive's purpose at eye level.
    helix=[(.12*math.cos(a),height-.15+a/math.tau*.22,-.25+.12*math.sin(a))
           for a in np.linspace(0,math.tau*4.5,91)]
    g.add(M.tube(helix,[.028]*len(helix),segments=5,material=metal))
    cy,cz=height+.67,-.56
    circle=[(.58*math.cos(a),cy+.58*math.sin(a),cz) for a in np.linspace(0,math.tau,37)]
    g.add(M.tube(circle,[.065]*len(circle),segments=8,material=metal))
    for a in np.linspace(0,math.tau,6,endpoint=False):
        g.add(M.tube([(0,cy,cz),(.58*math.cos(a),cy+.58*math.sin(a),cz)],
                     [.04,.04],segments=6,material=metal))
    return g


def cargo_bay(width=4.5, depth=5.2, stone="ashlar", timber="timber_grey", seed=0):
    """Cargo on a raised bonded-store plinth, with a clear inspection counter."""
    from . import props as P
    g = MeshGroup()
    g.add(M.box((width,.7,depth),center=(0,.35,0),uv_scale=.5,material=stone))
    for x,z,size in ((-.9,.7,1.15),(.6,1.25,.95),(.2,-.2,.85)):
        g.add(P.crate(size=size,seed=seed,material=timber).translate(x,.7,z))
    for x in (-width/2+.3,width/2-.3):
        g.add(M.box((.22,1.15,.65),center=(x,.575,-depth/2-.55),material=timber))
    g.add(M.box((width,.13,.95),center=(0,1.22,-depth/2-.55),uv_scale=.8,material=timber))
    return g
