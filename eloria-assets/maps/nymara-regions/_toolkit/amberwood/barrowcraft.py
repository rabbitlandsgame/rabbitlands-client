"""Reusable burial furniture and supported bog crossings in the moor palette.

Props stand at y=0 and architectural fronts face -Z. The walkway is centred
on the origin; its continuous substrate catches grounding rays at plank seams.
"""
from __future__ import annotations
import math
from . import mesh as M
from . import moorcraft as G
from .stonework import MeshGroup


def dolmen_frame(span=6.0, height=3.4, seed=0,
                  stone="grey_moor_granite", carved="grey_carved_stone"):
    """Split standing slabs carry one broad capstone over an unobstructed lane."""
    g = MeshGroup()
    for sign in (-1, 1):
        post = M.box((.95, height, 1.1), center=(sign * span / 2, height / 2, 0),
                     uv_scale=.6, material=carved)
        g.add(G._weather(post, .045, seed + sign + 2))
    cap = M.box((span + 1.6, .62, 1.45), center=(0, height + .3, 0),
                uv_scale=.65, material=stone)
    g.add(G._weather(cap, .055, seed + 4))
    return g


def burial_cist(width=1.65, length=3.0, height=.85, opened=False, seed=0,
                 stone="grey_drystone", carved="grey_carved_stone"):
    """A stone-lined grave, with a sealed lid or a lid slid aside by visitors."""
    g = MeshGroup()
    rim = .22
    g.add(M.box((width, .15, length), center=(0, .075, 0), material=stone))
    for side in (-1, 1):
        g.add(M.box((rim, height - .15, length),
                    center=(side * (width - rim) / 2, (height + .15) / 2, 0),
                    uv_scale=.22, material=stone))
        g.add(M.box((width - 2 * rim, height - .15, rim),
                    center=(0, (height + .15) / 2, side * (length - rim) / 2),
                    uv_scale=.22, material=stone))
    lid = M.box((width + .12, .18, length + .12), center=(0, height + .1, 0),
                uv_scale=.7, material=carved)
    if opened:
        lid.rotate_y(.14).translate(width * .65, .02, length * .16)
    g.add(G._weather(lid, .016, seed))
    # A raised headstone gives the grave a direction even at game-camera scale.
    g.add(G._weather(M.box((width * .72, 1.6, .25),
                          center=(0, .8, length / 2 + .3),
                          uv_scale=.6, material=carved), .025, seed + 1))
    return g


def burial_niches(width=4.8, seed=0, stone="grey_drystone", carved="grey_carved_stone"):
    """Six deep offering shelves in a freestanding stone bank, front facing -Z."""
    g = MeshGroup()
    height, depth, t = 3.25, 1.05, .22
    g.add(M.box((width, height, .2), center=(0, height / 2, depth / 2), uv_scale=.22, material=stone))
    for row in range(3):
        y = row * 1.5
        g.add(M.box((width, t, depth), center=(0, y + t / 2, 0), uv_scale=.22, material=stone))
    for i in range(4):
        x = -width / 2 + t / 2 + i * (width - t) / 3
        g.add(M.box((t, height - t, depth), center=(x, (height + t) / 2, 0),
                    uv_scale=.22, material=carved))
    for row in range(2):
        for i in range(3):
            x = (i - 1) * (width - t) / 3
            y = row * 1.5 + t
            g.add(M.box((.48, .8, .18), center=(x, y + .4, .25), material=carved))
            g.add(G.candle_cluster(3, .2, seed + row * 3 + i).translate(x, y, -.27))
    return g


def pile_walkway(length=28.0, width=4.4, deck_height=3.0, seed=0,
                  timber="grey_bog_timber", rope="timber_grey", posts="grey_dead_bark"):
    """Close-set cross planks on bearers, driven piles and braced trestles."""
    g = MeshGroup()
    # Top is precisely deck_height. Seams expose substrate only 4 cm below it.
    g.add_walk(M.box((width, .14, length), center=(0, deck_height - .11, 0),
                     uv_scale=.7, material=timber))
    count = max(2, math.ceil(length / .4))
    pitch = length / count
    for i in range(count):
        z = -length / 2 + (i + .5) * pitch
        g.add_walk(M.box((width, .075, pitch - .018),
                         center=(0, deck_height - .0375, z), uv_scale=.85, material=timber))
    for sign in (-1, 1):
        x = sign * (width / 2 - .25)
        g.add(M.box((.28, .36, length), center=(x, deck_height - .36, 0), material=timber))
    stations = max(2, math.ceil(length / 4))
    for k in range(stations + 1):
        z = -length / 2 + k * length / stations
        for sign in (-1, 1):
            x = sign * (width / 2 + .17)
            g.add(M.box((.28, deck_height + 1.1, .3),
                        center=(x, (deck_height + 1.1) / 2, z), material=posts))
            g.add(M.tube([(x, deck_height - 1.7, z), (-x, deck_height - .4, z)],
                         [.09, .09], segments=4, cap_start=True, cap_end=True, material=timber))
        g.add(M.box((width + .7, .25, .3), center=(0, deck_height - .53, z), material=timber))
        if k < stations:
            z1 = z + length / stations
            for sign in (-1, 1):
                x = sign * (width / 2 + .17)
                g.add(M.tube([(x, deck_height + .98, z), (x, deck_height + .78, (z + z1) / 2),
                              (x, deck_height + .98, z1)], [.045] * 3, segments=6, material=rope))
    return g
