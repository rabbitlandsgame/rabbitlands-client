"""The Barrow Run: a family visitation road under peat, breached by roots."""
from __future__ import annotations
import math
from amberwood import barrowcraft as B
from amberwood import moorcraft as G
from amberwood import forestcraft as F
from amberwood import mesh as M
from amberwood import props as P


def dress(it, pal, seed):
    def put(piece, x, y, z):
        it.group.add(piece.translate(x, y, z))
    def room(key):
        s = it.spaces[key]
        return s["x0"], s["z0"], s["x1"], s["z1"], s["floor"]
    def lamp(x, y, z):
        it.lamps.append([round(x, 2), round(y, 2), round(z, 2)])
    def frame(x, y, z, span=6, height=3.3, k=0):
        put(B.dolmen_frame(span, height, seed + k), x, y, z)
        lamp(x - span / 2 + 1, y + height + .1, z - .7)
    def cist(x, y, z, k=0, opened=False, angle=0):
        put(B.burial_cist(opened=opened, seed=seed + k).rotate_y(angle), x, y, z)
        put(G.candle_cluster(5, .4, seed + k), x - (1.35 if opened else 0),
            y + (.02 if opened else 1.08), z - .8)
    def niches(x, y, z, angle=0, k=0):
        put(B.burial_niches(seed=seed + k).rotate_y(angle), x, y, z)
        # Light stands clear of the front of the bank and illuminates its recesses.
        lamp(x - math.sin(angle) * 1.1, y + 2.8, z - math.cos(angle) * 1.1)
    def roots(x, y, z, span=7, height=4.8):
        put(F.root_arch(span, height, .42, bark="grey_dead_bark"), x, y, z)

    # Candles and the first low capstone mark the sheltered visitation entrance.
    frame(0, 0, 8.3, span=7.2, height=3.2)
    niches(-5.7, 0, 7, angle=-math.pi / 2, k=1)
    put(G.candle_cluster(9, .8, seed), 4.5, .02, 5.5)

    x0, z0, x1, z1, y = room("peat-cut")
    cx = (x0 + x1) / 2
    for k, z in enumerate((z0 + 5, z0 + 15, z0 + 25)):
        frame(cx, y, z, span=7.8, height=3.3, k=10 + k)
    for k in (0, 2):
        ax0, az0, ax1, az1, ay = room(f"peat-cut-alcove-{k}")
        cist((ax0 + ax1) / 2, ay, (az0 + az1) / 2, 20 + k)
        lamp((ax0 + ax1) / 2, ay + 3.3, az0 + 1)
    # The Moss alcove is still a useful detour, with damp roots beside its node.
    ax0, az0, ax1, az1, ay = room("peat-cut-alcove-1")
    roots((ax0 + ax1) / 2, ay, az1 - .8, span=3.1, height=3.0)

    x0, z0, x1, z1, y = room("first-barrow")
    cx = (x0 + x1) / 2
    for side in (-1, 1):
        for k, z in enumerate((z0 + 6, z0 + 14)):
            cist(cx + side * 8.8, y, z, 30 + k + side, opened=(side == 1 and k == 1))
        niches(cx + side * 11.8, y, z0 + 10, angle=side * math.pi / 2, k=40 + side)
    frame(cx, y, z0 + 4, span=8.8, height=4.2, k=41)
    frame(cx, y, z1 - 4, span=8.8, height=4.2, k=42)

    # Roots emerge from the bank, and trestles reach the waterbed below.
    x0, z0, x1, z1, pit = room("bog-board")
    cx, deck = (x0 + x1) / 2, pit + 3
    it.lamps[:] = [p for p in it.lamps if not z0 <= p[2] <= z1]
    for k, z in enumerate((z0 + 2, (z0 + z1) / 2, z1 - 2)):
        put(F.timber_bent(span=5.0, height=3.0, timber=pal["timber"]), cx, deck, z)
        lamp(cx - 1.5, deck + 3.0, z - .4)
    for sign in (-1, 1):
        for k, z in enumerate((z0 + 6, z0 + 19)):
            put(P.boulder(radius=2.4, seed=seed + 50 + k, material="grey_barrow_turf"),
                cx + sign * 7.4, pit - .9, z)
            put(F.root_arch(span=4.2, height=4.0, radius=.5, bark="grey_dead_bark"),
                cx + sign * 6.6, pit, z)

    x0, z0, x1, z1, y = room("fifth-chamber")
    cx = (x0 + x1) / 2
    for side in (-1, 1):
        for k, z in enumerate((z0 + 5, z0 + 14)):
            niches(cx + side * 9.9, y, z, side * math.pi / 2, 60 + k + side)
    frame(cx, y, z1 - 3, span=7.7, height=3.5, k=64)

    x0, z0, x1, z1, y = room("split-barrow-hub")
    cx = (x0 + x1) / 2
    frame(cx - 11, y, z1 - 2.1, span=5.2, height=3.3, k=70)
    roots(cx + 11, y, z1 - 2.1, span=5.2, height=3.9)
    niches(cx, y, z1 - .8, k=71)
    # The east branch keeps its carved family graves; the west is peat and roots.
    x0, z0, x1, z1, y = room("split-barrow-east-passage")
    cx = (x0 + x1) / 2
    for side in (-1, 1):
        cist(cx + side * 5.8, y, z0 + 5.5, 80 + side)
        cist(cx + side * 5.8, y, z1 - 5.5, 83 + side)
    frame(cx, y, z1 - 3, span=6.3, height=3.4, k=85)
    x0, z0, x1, z1, y = room("split-barrow-west-passage")
    cx = (x0 + x1) / 2
    for k, z in enumerate((z0 + 4, z1 - 4)):
        roots(cx, y, z, span=9.8, height=5.0)
        cist(x0 + 2.3, y, z + 1, 90 + k, opened=True, angle=-.25)
        lamp(cx + 2.5, y + 3.8, z)
    # Small pools sit inside raised peat lips, outside the centre combat lane.
    for z in (z0 + 7, z1 - 6):
        put(M.box((2.9, .15, 3.8), center=(0, .075, 0), material="grey_barrow_turf"),
            x1 - 1.6, y, z)
        put(M.box((2.5, .025, 3.3), center=(0, .163, 0), material=pal["water"]),
            x1 - 1.6, y, z)

    x0, z0, x1, z1, y = room("split-barrow-merge")
    cx = (x0 + x1) / 2
    for side in (-1, 1):
        cist(cx + side * 7.4, y, z0 + 6, 100 + side)
        lamp(cx + side * 6, y + 3.8, z0 + 6)

    x0, z0, x1, z1, y = room("reeve-stair")
    cx = (x0 + x1) / 2
    frame(cx, y, z0 + 3, span=7.8, height=3.5, k=110)
    for side in (-1, 1):
        niches(cx + side * 9.8, y, z0 + 10, side * math.pi / 2, 111 + side)

    # A crown of split slabs above the final doorway ends the long view.
    x0, z0, x1, z1, y = room("reeve-hall")
    cx = (x0 + x1) / 2
    frame(cx, y, z1 - 1.2, span=8.8, height=6.2, k=120)
    for k, x in enumerate((-4.1, -2.1, 0, 2.1, 4.1)):
        put(G.menhir(4.1 - abs(x) * .5, seed + 121 + k, material=pal["stone"]),
            cx + x, y + 6.8, z1 - 1.2)
    for side in (-1, 1):
        for k, z in enumerate((z0 + 7, z0 + 15)):
            cist(cx + side * 12.5, y, z, 130 + k + side)
        niches(cx + side * 11, y, z1 - 2.2, k=140 + side)
        lamp(cx + side * 5.2, y + 5.6, z1 - 5)
    x0, z0, x1, z1, y = room("vault")
    cx = (x0 + x1) / 2
    niches(x0 + 1, y, z0 + 7, -math.pi / 2, 150)
    lamp(cx, y + 3.5, z1 - 3)
