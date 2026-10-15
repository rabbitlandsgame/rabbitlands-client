"""The Coil Causeway: a ceremonial water route maintained as a hatchery."""
from __future__ import annotations
import math
from amberwood import templecraft as T
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
    def frame(x, y, z, span=6.0, height=4.0, seal=.6):
        put(T.procession_frame(span, height, seal, pal["stone"], pal["wall"]), x, y, z)
        lamp(x - span * .5 + 1.0, y + height, z - .4)
    def basin(x, y, z, width=3.6, length=7.0, k=0):
        put(T.ritual_basin(width, length, stone=pal["stone"], water=pal["water"]), x, y, z)
        for sign in (-1, 1):
            put(T.lily_cluster(radius=min(width * .3, 1.1), seed=seed + k + sign), x, y + .34, z + sign * length * .24)
    def nest(x, y, z, k=0, radius=1.45):
        put(T.brood_nest(radius, seed + k, soil=pal["turf"]), x, y, z)
    def spill(x, y, z, side):
        put(T.wall_spillway(stone=pal["wall"], water=pal["water"]).rotate_y(side * math.pi / 2),
            x, y + .55 * .53, z)

    # Preparation and offerings flank the processional centre at the arrival.
    frame(0, 0, 8.5, span=7, height=3.8)
    for z in (4.0, 6.0):
        put(P.barrel(radius=.5, height=1.0, material=pal["timber"]), -5.5, 0, z)
    put(T.sun_disc(.8), 5.9, 3.3, 1.0)

    x0, z0, x1, z1, y = room("water-gate")
    cx = (x0 + x1) / 2
    for side in (-1, 1):
        basin(cx + side * 8.3, y, z0 + 10, width=3.4, length=9.0, k=10 + side)
        lamp(cx + side * 7.0, y + 3.7, z0 + 10)
        spill(cx + side * 10.2, y, z0 + 10, side)
    frame(cx, y, z0 + 3, span=7)
    frame(cx, y, z1 - 3, span=7)

    # Three supported gateways divide the span into short, legible reaches.
    # Pads sit on the channel water level below the causeway, never on its deck.
    x0, z0, x1, z1, pit = room("lily-causeway")
    cx, deck = (x0 + x1) / 2, pit + 3.0
    it.lamps[:] = [p for p in it.lamps if not z0 <= p[2] <= z1]
    for k, z in enumerate((z0 + 3, (z0 + z1) / 2, z1 - 3)):
        for side in (-1, 1):
            put(M.box((1.24, 3.0, 1.14), center=(0, 1.5, 0), material=pal["stone"]),
                cx + side * 3.0, pit, z)
            put(T.lily_cluster(1.7, seed + 20 + k * 2 + side), cx + side * 5.5, pit + .05, z + 1.5)
        frame(cx, deck, z, span=6, height=3.5, seal=.5)
    for side in (-1, 1):
        path = [(cx + side * 2.35, deck + 1.0, z0 + .8),
                (cx + side * 2.35, deck + 1.0, z1 - .8)]
        it.group.add(M.tube(path, [.12, .12], segments=6, material=pal["wall"]))

    # The working hatchery has a water trough and dry incubation beds.
    x0, z0, x1, z1, y = room("hatchery")
    cx = (x0 + x1) / 2
    basin(x1 - 3.0, y, (z0 + z1) / 2, width=4.7, length=15.0, k=30)
    spill(x1 - .2, y, (z0 + z1) / 2, 1)
    for k, z in enumerate((z0 + 5, z0 + 11.5, z1 - 5)):
        nest(x0 + 3.2, y, z, 34 + k)
        lamp(x0 + 4.2, y + 3.0, z)
    frame(cx, y, z1 - 3, span=7, height=4.2)
    put(F.root_arch(span=8, height=5.8, radius=.4, bark=pal["timber"]), cx, y, z0 + 3.5)

    # Repeated seals mark the gallery rhythm; the middle Lichen alcove stays open.
    x0, z0, x1, z1, y = room("serpent-gallery")
    cx = (x0 + x1) / 2
    for k, z in enumerate((z0 + 4, z0 + 14, z0 + 24)):
        frame(cx, y, z, span=8.0, height=3.6, seal=.5)
    for k in (0, 2):
        ax0, az0, ax1, az1, ay = room(f"serpent-gallery-alcove-{k}")
        ax, az = (ax0 + ax1) / 2, (az0 + az1) / 2
        put(T.sun_disc(.9), ax, ay + 2.2, az1 - .25)
        lamp(ax, ay + 3.3, az)

    x0, z0, x1, z1, y = room("two-mouths-hub")
    cx = (x0 + x1) / 2
    put(F.root_arch(span=5.2, height=4.3, radius=.35, bark=pal["timber"]), cx - 11, y, z1 - 2.5)
    frame(cx + 11, y, z1 - 2.5, span=5.3, height=3.9)
    basin(cx - 6.0, y, z0 + 6.0, width=3.0, length=5.0, k=40)

    x0, z0, x1, z1, y = room("two-mouths-wet-mouth")
    cx = (x0 + x1) / 2
    basin(x1 - 2.2, y, (z0 + z1) / 2, width=3.2, length=14.0, k=50)
    spill(x1 - .2, y, (z0 + z1) / 2, 1)
    nest(x0 + 2.2, y, z0 + 7, 51, radius=1.2)
    nest(x0 + 2.2, y, z1 - 5, 52, radius=1.2)
    put(F.root_arch(span=6.0, height=4.5, radius=.4, bark=pal["timber"]), cx, y, z1 - 3.0)
    for z in (z0 + 4, z1 - 4):
        lamp(cx - 2, y + 3.4, z)

    x0, z0, x1, z1, y = room("two-mouths-carved-mouth")
    cx = (x0 + x1) / 2
    for z in (z0 + 3.5, z1 - 3.5):
        frame(cx, y, z, span=6.2, height=4.1)
    for side in (-1, 1):
        put(T.sun_disc(1.0).rotate_y(side * math.pi / 2),
            cx + side * 7.4, y + 2.8, (z0 + z1) / 2)

    x0, z0, x1, z1, y = room("sun-stair")
    cx = (x0 + x1) / 2
    frame(cx, y, z0 + 3, span=7, height=4.4, seal=1.0)
    for side in (-1, 1):
        basin(cx + side * 7.2, y, z0 + 10, width=3.2, length=7, k=60 + side)
        lamp(cx + side * 5.2, y + 3.5, z0 + 10)

    # The largest sun seal crowns the reward door, visible across the court.
    x0, z0, x1, z1, y = room("coiled-court")
    cx = (x0 + x1) / 2
    frame(cx, y, z1 - 1.2, span=8.3, height=5.4, seal=2.25)
    for side in (-1, 1):
        basin(cx + side * 12.8, y, z0 + 10, width=3.0, length=11, k=70 + side)
        put(T.procession_frame(span=4.6, height=5.0, seal_radius=.8).rotate_y(side * math.pi / 2),
            cx + side * 14.5, y, z0 + 20)
        lamp(cx + side * 6.5, y + 5.8, z1 - 4)

    x0, z0, x1, z1, y = room("vault")
    cx = (x0 + x1) / 2
    put(T.sun_disc(.9), cx, y + 3, z1 - .3)
    lamp(cx, y + 3.6, z1 - 3)
