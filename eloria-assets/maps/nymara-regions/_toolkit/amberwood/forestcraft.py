"""Reusable underground forestry structures in the continent's existing palette.

All dimensions are metres. Props stand at y=0 and face -Z. Root arches keep
their centre open; vats have a real rim and a recessed liquid surface.
"""
from __future__ import annotations

from . import mesh as M
from .stonework import MeshGroup


def timber_bent(span=7.0, height=4.0, timber="timber_warm"):
    """A braced haul-road frame with a clear cart opening."""
    g = MeshGroup()
    for side in (-1, 1):
        x = side * span * .5
        g.add(M.box((.38, height, .42), center=(x, height * .5, 0), material=timber))
        g.add(M.tube([(x, height - 1.4, 0), (x - side * 1.1, height - .23, 0)],
                     [.16, .16], segments=4, cap_start=True, cap_end=True, material=timber))
    g.add(M.box((span + .8, .4, .48), center=(0, height + .12, 0), material=timber))
    return g


def root_arch(span=9.0, height=6.0, radius=.75, bark="bark_dark"):
    """One crooked living arch; a tapered root at either foot seats it in soil."""
    g = MeshGroup()
    half = span * .5
    path = [(-half - 1.1, .04, -.9), (-half, 1.2, 0),
            (-half + .2, height * .6, .2), (-half * .55, height * .95, .35),
            (.25, height, .1), (half * .6, height * .85, -.1),
            (half, height * .4, 0), (half + .5, .12, .8)]
    g.add(M.tube(path, [radius * .35, radius, radius * .85, radius * .65,
                        radius * .53, radius * .75, radius, radius * .35],
                 segments=9, cap_start=True, cap_end=True, uv_scale=.65, material=bark))
    return g


def resin_vat(radius=1.55, height=1.35, timber="timber_warm",
              metal="dark_iron", contents="amber_resin"):
    """Open coopered vat, inset liquid and raised hoops, without a hidden lid."""
    g = MeshGroup()
    g.add(M.lathe([(radius * .85, 0), (radius, height),
                   (radius - .16, height + .02), (radius * .82, .15)],
                  segments=18, uv_scale=1.1, material=timber))
    for fraction in (.2, .75):
        y = height * fraction
        r = radius * (.85 + .15 * fraction) + .025
        g.add(M.cylinder(r, r + .012, .08, 18, cap_bottom=False,
                         cap_top=False, material=metal).translate(0, y, 0))
    g.add(M.lathe([(0, height * .69), (radius * .9, height * .69)], 18,
                  uv_scale=.5, material=contents))
    return g


def haul_winch(timber="timber_warm", metal="dark_iron"):
    """A hand winch at the upper landing of a former cart incline."""
    g = MeshGroup()
    for x in (-1.05, 1.05):
        g.add(M.box((.32, 1.7, .6), center=(x, .85, 0), material=timber))
    g.add(M.tube([(-1.3, 1.25, 0), (1.5, 1.25, 0)], [.12, .12],
                 cap_start=True, cap_end=True, material=metal))
    g.add(M.tube([(-.78, 1.25, 0), (.78, 1.25, 0)], [.47, .47],
                 segments=14, cap_start=True, cap_end=True, material=timber))
    g.add(M.tube([(1.5, 1.25, 0), (1.5, 1.25, -.62), (1.85, 1.25, -.62)],
                 [.07, .07, .07], cap_start=True, cap_end=True, material=metal))
    return g
