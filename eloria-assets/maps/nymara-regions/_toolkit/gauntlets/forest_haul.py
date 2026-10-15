"""A forestry haul route assembled from shared, parameterised asset recipes."""
from __future__ import annotations

from amberwood import forestcraft as F
from amberwood import mesh as M
from amberwood import props as P


def dress(it, pal, seed):
    def put(piece, x, y, z):
        it.group.add(piece.translate(x, y, z))

    def room(key):
        s = it.spaces[key]
        return (s["x0"], s["z0"], s["x1"], s["z1"], s["floor"])

    def lamp(x, y, z):
        it.lamps.append([round(x, 2), round(y, 2), round(z, 2)])

    def bent(x, y, z, span=7.0):
        put(F.timber_bent(span=span, timber=pal["timber"]), x, y, z)
        lamp(x - span * .5 + .5, y + 3.15, z)

    # The safe hall is a supply bay. The central arrival and the home stone
    # stay clear; stored timber and the cart point towards the first gate.
    put(P.cart(seed=seed), -4.6, 0, 5.6)
    put(P.log_pile(length=3.2, rows=3, per_row=4, seed=seed), -4.8, 0, 10.0)
    for z in (4.5, 6.3):
        put(P.barrel(radius=.48, height=1.1), 5.2, 0, z)
    bent(0, 0, 9.0, span=7.0)

    x0, z0, x1, z1, y = room("undercut")
    cx = (x0 + x1) * .5
    for z in (z0 + 4, z1 - 4):
        bent(cx, y, z, span=8.0)
    for z in (z0 + 6, z0 + 12):
        put(P.log_pile(length=3.2, seed=seed + int(z)), x0 + 2.6, y, z)
    put(P.cart(seed=seed + 1), x1 - 2.8, y, z1 - 5)
    put(F.root_arch(span=9, height=5.0, radius=.6), cx, y, z1 - 2.6)

    # Vats occupy the seep side of the cellar; roots make the exit a landmark.
    x0, z0, x1, z1, y = room("root-cellar")
    cx = (x0 + x1) * .5
    for z in (z0 + 6.0, z0 + 13.0):
        put(F.resin_vat(), x1 - 3, y, z)
        lamp(x1 - 3, y + 3.2, z)
    put(F.root_arch(span=12, height=6.4, radius=1.0), cx, y, z1 - 5)
    lamp(cx, y + 4.5, z1 - 6)
    put(P.log_pile(length=4, seed=seed + 2), x0 + 3, y, z0 + 9)

    # Low rails frame the exposed span; the deck is the only walkable surface.
    s = it.spaces["sap-bridge"]
    cx = (s["x0"] + s["x1"]) * .5
    y = s["floor"] + 3
    for point in it.lamps:
        if s["z0"] < point[2] < s["z1"] and abs(point[0] - (cx - 2.2)) < .01:
            point[1] = y + 3.1
            put(M.box((.16, 2.8, .16), center=(0, 1.4, 0), material=pal["metal"]),
                point[0], y, point[2])
    for side in (-1, 1):
        put(M.box((.13, .16, s["z1"] - s["z0"] - 1.6),
                  center=(0, .92, 0), material=pal["timber"]),
            cx + side * 2.2, y, (s["z0"] + s["z1"]) * .5)
    for z in (s["z0"] + 6, s["z1"] - 6):
        put(F.root_arch(span=12, height=7, radius=.8), cx, y - 3, z)

    x0, z0, x1, z1, y = room("stump-stair")
    cx = (x0 + x1) * .5
    bent(cx, y, z0 + 2.6, span=7)
    put(F.haul_winch(), cx - 5.3, y, z0 + 3.8)
    put(P.cart(seed=seed + 3), x1 - 3, y, z0 + 8)
    put(F.root_arch(span=10, height=5.2, radius=.7), cx, y, z1 - 3)

    # The hub exposes two different economies before the party commits:
    # waterlogged collection vats on the left, dry stacked timber on the right.
    x0, z0, x1, z1, y = room("twin-hollows-hub")
    cx = (x0 + x1) * .5
    put(F.root_arch(span=8, height=5.3, radius=.85), cx, y, z1 - 4)
    for side in (-1, 1):
        lamp(cx + side * 10, y + 3.0, z1 - 2.5)
    put(F.resin_vat(radius=1.1, contents=pal["water"]), x0 + 3.6, y, z0 + 5)
    put(P.log_pile(length=3.2, seed=seed + 4), x1 - 3.6, y, z0 + 5)

    x0, z0, x1, z1, y = room("twin-hollows-wet-hollow")
    cx = (x0 + x1) * .5
    # A contained seep has a raised stone lip. It does not paint water on the
    # walk floor or claim dry ground below a pool as navigable.
    put(F.resin_vat(radius=2.05, height=.85, timber=pal["rock"],
                    contents=pal["water"]), x0 + 2.8, y, z0 + 8)
    put(F.root_arch(span=8, height=5.0, radius=.8), cx, y, z1 - 5)
    for z in (z0 + 5, z1 - 4):
        lamp(cx + 3.6, y + 2.8, z)

    x0, z0, x1, z1, y = room("twin-hollows-dry-hollow")
    cx = (x0 + x1) * .5
    for z in (z0 + 5, z1 - 5):
        bent(cx, y, z, span=6)
        put(P.log_pile(length=3, rows=4, per_row=5, seed=seed + int(z)),
            x1 - 2.5, y, z + 1)
    put(F.haul_winch(), x0 + 2.7, y, z1 - 4)

    x0, z0, x1, z1, y = room("twin-hollows-merge")
    cx = (x0 + x1) * .5
    for side in (-1, 1):
        put(P.barrel(radius=.65, height=1.4), cx + side * 5.5, y, z1 - 3.5)
        lamp(cx + side * 6, y + 2.8, z0 + 5)

    # Frames and lit storage bays break the long view into ten-metre beats.
    x0, z0, x1, z1, y = room("lantern-walk")
    cx = (x0 + x1) * .5
    for z in (z0 + 3, z0 + 13, z0 + 23):
        bent(cx, y, z, span=7)
    for k in (0, 2):
        ax0, az0, ax1, az1, ay = room(f"lantern-walk-alcove-{k}")
        put(F.resin_vat(radius=1.15), (ax0 + ax1) * .5, ay, az1 - 1.45)
        lamp((ax0 + ax1) * .5, ay + 2.8, (az0 + az1) * .5)
    s = it.spaces["lantern-walk-alcove-1"]
    lamp((s["x0"] + s["x1"]) * .5, y + 2.8, (s["z0"] + s["z1"]) * .5)

    # Roots have overwhelmed the final loading court. Their crown frames the
    # boss dais from the doorway; the eight add positions and rear door stay clear.
    x0, z0, x1, z1, y = room("boar-court")
    cx = (x0 + x1) * .5
    put(F.root_arch(span=14, height=8.0, radius=1.45), cx, y, z1 - 4)
    for side in (-1, 1):
        put(F.root_arch(span=6.5, height=5.7, radius=.9).rotate_y(side * .25),
            cx + side * 11, y, z0 + 10)
        lamp(cx + side * 5, y + 4, z1 - 8)
    lamp(cx, y + 5.0, z0 + 8)

    x0, z0, x1, z1, y = room("vault")
    cx = (x0 + x1) * .5
    for side in (-1, 1):
        put(P.barrel(radius=.48, height=1.05), cx + side * 2.8, y, z1 - 2.6)
    lamp(cx, y + 3.0, z1 - 4)
