"""Whitehorn's worked silver stair being closed by the glacier."""
from __future__ import annotations
import math
from amberwood import crystalcraft as C
from amberwood import forestcraft as F
from amberwood import mountaincraft as H
from amberwood import mesh as M
from amberwood import props as P


def dress(it, pal, seed):
    it.accent_lights = []
    def put(piece, x, y, z):
        it.group.add(piece.translate(x, y, z))
    def room(key):
        s = it.spaces[key]
        return s["x0"], s["z0"], s["x1"], s["z1"], s["floor"]
    def lamp(x, y, z):
        it.lamps.append([round(x, 2), round(y, 2), round(z, 2)])
    def glow(x, y, z, energy=2.3):
        it.accent_lights.append({"id": f"ice-glow-{len(it.accent_lights)}", "kind": "point",
            "position": [round(x, 2), round(y, 2), round(z, 2)],
            "color": [.24, .52, .82], "range": 12.0, "energy": energy, "attenuation": 1.4})
    def bent(x, y, z, span=7.0):
        put(F.timber_bent(span=span, height=4.0, timber=pal["timber"]), x, y, z)
        lamp(x + span * .5 - .4, y + 3.3, z)
    def cascade(x, y, z, width, height, angle=0, k=0):
        put(H.frozen_cascade(width=width, height=height, seed=seed + k,
                            ice=pal["crystal"], rock=pal["rock"]).rotate_y(angle), x, y, z)

    # A sheltered loading floor: ore and sledges on the left, stores on the
    # right, and a clear centre between the arrival, briefing and waystone.
    put(H.ore_sledge(timber=pal["timber"], ore=pal["node"]), -4.8, 0, 6.0)
    put(F.haul_winch(timber=pal["timber"]), -4.8, 0, 10.3)
    for z in (4.5, 6.4):
        put(P.barrel(radius=.45, height=1.05, material=pal["timber"]), 5.0, 0, z)
    bent(0, 0, 9.0)

    x0, z0, x1, z1, y = room("cascade-cave")
    cx = (x0 + x1) * .5
    cascade(x1 - .9, y, z0 + 10, 9.0, 7.0, math.pi / 2, k=1)
    glow(x1 - 2.8, y + 3.8, z0 + 10)
    put(H.ore_face(seed=seed, rock=pal["rock"], ore=pal["node"]).rotate_y(-math.pi / 2),
        x0 + .7, y, z0 + 9)
    put(H.ore_sledge(timber=pal["timber"], ore=pal["node"]), x0 + 3, y, z0 + 14)
    bent(cx, y, z0 + 3.5, span=7.5)
    bent(cx, y, z1 - 4, span=8.0)

    # Hoists stand beside the upper landings, with space for a sled to turn.
    for index, key in enumerate(("first-riser", "last-riser")):
        x0, z0, x1, z1, y = room(key)
        cx = (x0 + x1) * .5
        bent(cx, y, z0 + 3, span=7)
        put(F.haul_winch(timber=pal["timber"]), cx - 5.0, y, z0 + 3)
        put(H.ore_sledge(timber=pal["timber"], ore=pal["node"]), x1 - 3, y, z0 + 7)
        cascade(x0 + 1.0, y, z1 - 5, 5.0, 5.4, -math.pi / 2, k=10 + index)
        glow(x0 + 2.8, y + 3, z1 - 5)
        lamp(cx + 3, y + 3.5, z1 - 4)

    # The bridge's rock anchors and the frozen fall explain the exposed gap.
    s = it.spaces["icefall-span"]
    cx = (s["x0"] + s["x1"]) * .5
    z = (s["z0"] + s["z1"]) * .5
    cascade(s["x1"] - .8, s["floor"], z, 13, 8.4, math.pi / 2, k=20)
    glow(s["x1"] - 2.5, s["floor"] + 4, z, energy=3.5)

    x0, z0, x1, z1, y = room("snowline-hall")
    cx = (x0 + x1) * .5
    for z in (z0 + 4, z1 - 4):
        bent(cx, y, z, span=7.5)
    put(H.ore_face(width=6.0, seed=seed + 30).rotate_y(-math.pi / 2), x0 + .6, y, z0 + 10)
    for z in (z0 + 6, z1 - 6):
        put(H.ore_sledge(timber=pal["timber"], ore=pal["node"]), x1 - 3, y, z)
    lamp(x0 + 2.5, y + 3.4, z0 + 10)

    # Blue is a natural crevasse; white is the shored haul adit. Their visual
    # cues begin in the hub, before the party chooses its irreversible branch.
    x0, z0, x1, z1, y = room("twin-crevasses-hub")
    cx = (x0 + x1) * .5
    cascade(cx - 6.5, y, z1 - 1.1, 5.0, 5.3, k=40)
    glow(cx - 10, y + 3, z1 - 3)
    bent(cx + 10.5, y, z1 - 3, span=5.3)
    put(H.ore_sledge(timber=pal["timber"], ore=pal["node"]), x1 - 3, y, z0 + 4.8)

    x0, z0, x1, z1, y = room("twin-crevasses-blue-crevasse")
    cx = (x0 + x1) * .5
    for k, z in enumerate((z0 + 6, z1 - 5)):
        cascade(x0 + .8, y, z, 6.0, 5.7, -math.pi / 2, k=50 + k)
        put(C.cluster(count=4, radius=1.2, height=3.2, seed=seed + 52 + k, material=pal["crystal"]),
            x1 - 2.2, y, z)
        glow(cx - 2.5, y + 3, z)
    lamp(cx, y + 3.8, z0 + 3.4)

    x0, z0, x1, z1, y = room("twin-crevasses-white-crevasse")
    cx = (x0 + x1) * .5
    for z in (z0 + 4, z1 - 4):
        bent(cx, y, z, span=6.0)
    put(H.ore_face(seed=seed + 60).rotate_y(math.pi / 2), x1 - .7, y, z0 + 10)
    put(H.ore_sledge(timber=pal["timber"], ore=pal["node"]), x0 + 2.6, y, z0 + 7)
    lamp(cx + 3.2, y + 3.4, z0 + 10)

    x0, z0, x1, z1, y = room("twin-crevasses-merge")
    cx = (x0 + x1) * .5
    for side in (-1, 1):
        put(P.barrel(radius=.6, height=1.3, material=pal["timber"]), cx + side * 6, y, z1 - 3)
        lamp(cx + side * 7, y + 3, z0 + 5)

    # The ice organ is the route's final silhouette: two frozen wings flank
    # the boss dais and leave the rear reward doorway open on its axis.
    x0, z0, x1, z1, y = room("rime-court")
    cx = (x0 + x1) * .5
    for side in (-1, 1):
        cascade(cx + side * 7.5, y, z1 - 1.2, 10, 9.2, k=70 + side)
        glow(cx + side * 6, y + 4.5, z1 - 5, energy=4)
        put(C.cluster(count=5, radius=1.5, height=5.2, seed=seed + 80 + side, material=pal["crystal"]),
            cx + side * 13, y, z0 + 9)
    lamp(cx, y + 4.8, z0 + 7)

    x0, z0, x1, z1, y = room("vault")
    cx = (x0 + x1) * .5
    put(H.ore_sledge(timber=pal["timber"], ore=pal["node"]), x0 + 2.8, y, z0 + 7)
    lamp(cx, y + 3.0, z1 - 4)
