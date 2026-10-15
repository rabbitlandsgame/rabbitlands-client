"""Dressing for the Harrowcrag Road (build_trail.py loads this).

Plan coordinates (x east, y south). The fort is the route's own Meshy kit
(source/kit/kit-hc-*.glb, MESHY_BATCH.md); the woods, rocks and camp come
from the regions' kit prototypes. A kit's front is its glTF +Z, which is plan
+y (bearing 90), so a piece faces bearing b at rot = b - 90.

Solid pieces close the ground their body stands on (kits.KitLibrary), trees
only at the trunk, ground cover nowhere. Interactive objects keep their own
tiles open whatever stands near them (the builder re-opens them).
"""
from __future__ import annotations

import math

import numpy as np

REGIONS = "godot-client/world_authoring/regions"
KITS = {
    # the fort: this route's own Meshy pieces
    "wall": "@kit/kit-hc-curtain-wall-ruined.glb", "breach": "@kit/kit-hc-curtain-wall-breach.glb",
    "tower": "@kit/kit-hc-round-tower-ruined.glb", "gatehouse": "@kit/kit-hc-gatehouse-burst.glb",
    "keep": "@kit/kit-hc-keep-ruined.glb", "rubble": "@kit/kit-hc-rubble-low.glb",
    "collapse": "@kit/kit-hc-rubble-collapse.glb", "barn": "@kit/kit-hc-barn-burnt.glb",
    "altar": "@kit/kit-hc-ring-altar.glb", "standard": "@kit/kit-hc-war-standard.glb",
    "siege": "@kit/kit-hc-siege-engine-wreck.glb", "tomb": "@kit/kit-hc-rock-tomb-door.glb",
    # woods
    "oak": "amberwood/kit-russet-oak-tree-1", "maple1": "amberwood/kit-autumn-maple-tree-1",
    "maple2": "amberwood/kit-autumn-maple-tree-2", "fir": "amberwood/kit-dark-fir-1",
    "chestnut": "amberwood/kit-sweet-chestnut-1", "alpfir1": "mirrorhold/kit-alpine-fir-tree-1",
    "alpfir2": "mirrorhold/kit-alpine-fir-tree-2", "pine": "grey_moors/kit-mountain-pine-tree-1",
    "snag": "grey_moors/kit-raven-snag-1", "broadleafa": "sw_isle/kit-sw-broadleaf-tree-a",
    "broadleafb": "sw_isle/kit-sw-broadleaf-tree-b", "resinpine": "amberwood/kit-resin-tapped-pine-1",
    "larch": "amberwood/kit-golden-larch-1",
    "under1": "amberwood/kit-undergrowth-1", "under2": "amberwood/kit-undergrowth-2",
    "under3": "amberwood/kit-undergrowth-3", "under4": "amberwood/kit-undergrowth-4",
    "under5": "amberwood/kit-undergrowth-5", "bracken": "amberwood/kit-bracken-patch-1",
    "bramble": "amberwood/kit-bramble-1", "fern": "amberwood/kit-autumn-fern-1",
    "gorse": "grey_moors/kit-gorse-bush-1",
    # rock
    "boulder1": "amberwood/kit-mossy-boulder-1", "boulder2": "amberwood/kit-mossy-boulder-2",
    "boulder3": "amberwood/kit-mossy-boulder-3", "boulder4": "amberwood/kit-mossy-boulder-4",
    "boulder5": "amberwood/kit-mossy-boulder-5",
    "crag1": "grey_moors/kit-mossy-crag-1", "crag2": "grey_moors/kit-mossy-crag-2",
    "crag3": "grey_moors/kit-mossy-crag-3", "crag4": "grey_moors/kit-mossy-crag-4",
    "crag5": "grey_moors/kit-mossy-crag-5",
    "stones1": "amberwood/kit-river-stones-1", "stones2": "amberwood/kit-river-stones-2",
    "fallsrock1": "amberwood/kit-waterfall-rocks-1", "fallsrock2": "amberwood/kit-waterfall-rocks-2",
    "log1": "amberwood/kit-mossy-log-1", "log2": "amberwood/kit-mossy-log-2",
    "hollowlog": "amberwood/kit-hollow-log-1", "stump1": "amberwood/kit-mossy-stump-1",
    "stump2": "amberwood/kit-mossy-stump-2",
    "standing1": "grey_moors/kit-moor-standing-stone-1", "standing2": "grey_moors/kit-moor-standing-stone-2",
    "standing3": "grey_moors/kit-moor-standing-stone-3",
    # people's things
    "tent": "whitehorn_range/kit-expedition-tent-1", "woodshelter": "whitehorn_range/kit-firewood-shelter-1",
    "crate1": "whitehorn_range/kit-supply-crate-1", "crate2": "whitehorn_range/kit-supply-crate-2",
    "crates": "four_gates/kit-crate-stack-1", "barrels": "four_gates/kit-barrel-stack-1",
    "cart": "sunmane_steppe/kit-cart", "firepit": "sunmane_steppe/kit-fire-pit",
    "notice": "amberwood/kit-notice-board-1", "lantern": "grey_moors/kit-trail-lantern-post-1",
    "waystone": "whitehorn_range/kit-horn-waystone-1", "haystack": "amberwood/kit-hay-stack-1",
    "fence": "amberwood/kit-split-rail-fence-1", "well": "crownwater/kit-stone-well-1",
    "cottage": "amberwood/kit-amber-cottage-1", "graves": "grey_moors/kit-grave-markers-1",
    "bones": "sunmane_steppe/kit-bleached-bones-0",
}
TREES = [("broadleafb", 0.16), ("broadleafa", 0.05), ("fir", 0.10), ("alpfir1", 0.20), ("alpfir2", 0.17),
         ("pine", 0.14), ("resinpine", 0.04), ("oak", 0.04), ("maple1", 0.04), ("larch", 0.03),
         ("chestnut", 0.03), ("snag", 0.0)]
# mostly green with a few autumn crowns, as the concept: Amberwood's oaks and maples are all russet
COVER = ["under1", "under2", "under3", "under4", "under5", "under1", "under2", "under4", "gorse", "bracken"]
BOULDERS = ["boulder1", "boulder2", "boulder3", "boulder4", "boulder5"]
CRAGS = ["crag1", "crag2", "crag3", "crag4", "crag5"]
# The keep's Meshy model came out 41 m wide at its 28 m spec height; the court holds about 30 m.
KEEP_SCALE = 0.732
WALL_LENGTH = 16.3          # the H1 module at its 6.4 m height
WALL_STEP = 15.3            # modules overlap a metre: the ruin hides the join


def kit_paths(checkout, route_dir):
    out = {}
    for key, ref in KITS.items():
        if ref.startswith("@"):
            out[key] = route_dir / "source" / ref[1:]
        else:
            region, stem = ref.split("/")
            out[key] = checkout / REGIONS / region / "assets" / "prototypes" / f"{stem}.glb"
    return out


def facing(bearing):
    """rot_deg that turns a kit's front (+Z, plan bearing 90) to face plan bearing `bearing`."""
    return bearing - 90.0


def bearing_to(ax, ay, bx, by):
    return math.degrees(math.atan2(by - ay, bx - ax))


def dress(props, layout, lattice, kits, groups, kit_paths_by_key):
    data = layout.data
    sec = layout.sections
    rng = np.random.default_rng(20261012)
    for key, path in kit_paths_by_key.items():
        # the moor crags are pale; darkened toward the painting's grey cliff stone
        kits.load(key, path, tint=(0.70, 0.71, 0.69) if key.startswith("crag") else None)
    h = props.height_at

    links = [(m["rimPoint"], m["at"], m["width"] / 2 + 3.5) for m in layout.mouths if m["kind"] != "floor"]

    def blocks_a_mouth(x, y):
        for (ax, ay), (bx, by), reach in links:
            dx, dy = bx - ax, by - ay
            t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / max(dx * dx + dy * dy, 1e-9)))
            if math.hypot(x - (ax + t * dx), y - (ay + t * dy)) < reach:
                return True
        return False

    def put(group, key, x, y, rot=0.0, scale=1.0, solid="footprint", z=None, sink=0.15):
        # a solid piece never stands in a creature mouth's way in: the mouth is how a pulse arrives
        if solid == "footprint" and group in ("arena", "camp", "cover") and blocks_a_mouth(x, y):
            return
        kits.place(groups[group], key, x, y, (h(x, y) if z is None else z) - sink, rot, scale, solid)

    # ------------------------------------------------------------ the fort
    crag = data["crag"]
    cx0, cy0 = crag["centre"]
    rx, ry = crag["rx"] * 0.93, crag["ry"] * 0.93
    top = crag["top"]
    road_in = next(p for p in layout.paths if p["to"] == "w5")["points"][-2]       # where the fort road arrives
    keep_at = (sec["vault"]["at"][0] + 1.0, sec["vault"]["at"][1])
    breach_mouth = next(m for m in layout.mouths if m["id"] == "w5-breach")
    # walk the curtain's ellipse by arc length and drop a module every WALL_STEP metres
    ts = np.linspace(0, 2 * math.pi, 4000, endpoint=False)
    ex, ey = cx0 + rx * np.cos(ts), cy0 + ry * np.sin(ts)
    seg = np.hypot(np.diff(np.r_[ex, ex[0]]), np.diff(np.r_[ey, ey[0]]))
    arc = np.r_[0, np.cumsum(seg)[:-1]]
    perimeter = float(seg.sum())
    gate_t = math.atan2((road_in[1] - cy0) / ry, (road_in[0] - cx0) / rx)
    gate_arc = float(arc[int(((gate_t % (2 * math.pi)) / (2 * math.pi)) * len(ts)) % len(ts)])
    n_modules = int(perimeter // WALL_STEP)
    placed_tower = 0
    for k in range(n_modules):
        a = (gate_arc + k * WALL_STEP) % perimeter
        i = int(np.searchsorted(arc, a)) % len(ts)
        x, y = float(ex[i]), float(ey[i])
        tangent = math.degrees(math.atan2(ey[(i + 5) % len(ts)] - ey[i - 5], ex[(i + 5) % len(ts)] - ex[i - 5]))
        outward = math.degrees(math.atan2((y - cy0) / ry ** 2, (x - cx0) / rx ** 2))
        if math.hypot(x - keep_at[0], y - keep_at[1]) < 20:
            continue                                     # the keep stands in the ring here
        if k == 0:
            # the fort road's gate: the passage runs along the road, out of the curtain
            put("fort", "gatehouse", x, y, facing(outward), 1.0, z=top - 0.4)
            continue
        if math.hypot(x - breach_mouth["at"][0], y - breach_mouth["at"][1]) < 14 and "breach" not in props.notes:
            put("fort", "breach", x, y, facing(outward), 1.0, z=top - 0.4)
            props.notes.add("breach")
            continue
        put("fort", "wall", x, y, facing(outward), 1.0, z=top - 0.4)
        if k % 3 == 2:
            j = int(np.searchsorted(arc, (a + WALL_STEP / 2) % perimeter)) % len(ts)
            put("fort", "tower", float(ex[j]), float(ey[j]), facing(outward) + 180, 0.85 + 0.1 * (placed_tower % 2),
                z=top - 0.6)
            placed_tower += 1
    # the inner wall and its burst gate between the bailey and the court
    gate_y = 161.0
    put("fort", "gatehouse", 182.0, gate_y, facing(0), 0.86, z=top - 0.2)
    for y in (gate_y - 18.5, gate_y + 18.5):
        put("fort", "wall", 182.0, y, facing(0), 0.95, z=top - 0.2)
    # the keep over the undercroft, its doorway facing the court
    put("fort", "keep", keep_at[0], keep_at[1], facing(180), KEEP_SCALE, z=sec["vault"]["elev"] - 0.25)
    # the court and the bailey: standards, graves, rubble, the siege engine, a well, stores
    for x, y in ((236.5, 150.5), (236.5, 173.5)):
        put("fort", "standard", x, y, facing(180) + rng.uniform(-10, 10), 1.0)
    put("fort", "graves", 205.0, 146.0, rng.uniform(0, 360), 1.0)
    put("fort", "graves", 226.0, 180.0, rng.uniform(0, 360), 1.0)
    for x, y, key in ((203.0, 172.0, "rubble"), (228.0, 146.5, "collapse"), (213.0, 182.0, "rubble"),
                      (198.0, 153.0, "rubble")):
        put("fort", key, x, y, rng.uniform(0, 360), 1.0)
    put("fort", "siege", 128.0, 170.0, 20.0, 1.0)
    put("fort", "well", 147.0, 152.0, 30.0, 1.0)
    put("fort", "crates", 160.0, 150.0, 60.0, 1.0)
    put("fort", "barrels", 163.0, 153.5, 10.0, 1.0)
    put("fort", "cart", 119.0, 158.0, -25.0, 1.0)
    for x, y, key in ((136.0, 156.0, "rubble"), (151.0, 177.0, "collapse"), (121.0, 176.0, "rubble"),
                      (167.0, 168.0, "rubble"), (142.0, 183.0, "rubble")):
        put("fort", key, x, y, rng.uniform(0, 360), 1.0)
    for x, y in ((125.0, 146.0), (158.0, 183.0)):
        put("fort", "standard", x, y, rng.uniform(0, 360), 0.9)

    # ------------------------------------------------------------ the trailhead camp
    th = sec["trailhead"]["at"]
    for x, y, b in ((33.0, 291.0, 30.0), (47.0, 310.0, -60.0), (29.0, 306.0, 10.0)):
        put("camp", "tent", x, y, facing(bearing_to(x, y, *th)) + b * 0.1, 1.25)
    put("camp", "firepit", 38.0, 300.0, 0.0, 1.0)
    put("camp", "woodshelter", 52.0, 307.0, facing(bearing_to(52, 307, *th)), 1.0)
    put("camp", "cart", 57.0, 291.0, 20.0, 1.0)
    for x, y, key in ((55.0, 304.0, "crate1"), (56.5, 302.5, "crate2"), (30.0, 297.0, "crates")):
        put("camp", key, x, y, rng.uniform(0, 360), 1.0)

    # ------------------------------------------------------------ 1 Hollow Meadow
    w1 = sec["w1"]["at"]
    put("arena", "barn", 152.0, 290.0, facing(bearing_to(152, 290, *w1)), 1.0)
    put("arena", "cottage", 118.0, 262.0, facing(bearing_to(118, 262, *w1)), 1.0)
    for x, y in ((138.0, 266.0), (144.0, 271.0), (130.0, 285.0), (147.0, 280.0), (124.0, 274.0)):
        put("arena", "haystack", x, y, rng.uniform(0, 360), 0.8)
    for x0, y0, x1, y1 in ((101, 268, 108, 259), (111, 256, 121, 252), (151, 258, 163, 265), (165, 268, 168, 276)):
        n = max(1, int(math.hypot(x1 - x0, y1 - y0) / 4.0))
        for i in range(n):
            t = (i + 0.5) / n
            put("arena", "fence", x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, facing(bearing_to(x0, y0, x1, y1)) + 90, 1.0)
    for i in range(3):
        for j in range(3):
            put("arena", "broadleafb", 112 + i * 6 + rng.uniform(-0.8, 0.8), 289 + j * 5 + rng.uniform(-0.8, 0.8),
                rng.uniform(0, 360), 0.45, solid="trunk")
    put("arena", "cart", 141.0, 277.0, 30.0, 1.0)
    put("arena", "boulder2", 127.0, 268.0, rng.uniform(0, 360), 0.8)
    put("arena", "boulder4", 158.0, 280.0, rng.uniform(0, 360), 0.8)

    # ------------------------------------------------------------ 2 The Old Ford
    for x, y, r in ((272, 286, 0.7), (279, 277, 0.6), (266, 292, 0.6), (283, 290, 0.75), (260, 280, 0.5)):
        put("arena", "stones1" if r > 0.6 else "stones2", x, y, rng.uniform(0, 360), r * 1.6)
    put("arena", "cart", 256.0, 300.0, -40.0, 1.0)
    for x, y in ((248.0, 268.0), (291.0, 296.0)):
        put("arena", "boulder" + str(rng.integers(1, 6)), x, y, rng.uniform(0, 360), 0.9)
    fx, fy = data["river"]["fall"]["at"]
    put("scenery", "fallsrock1", fx - 4, fy + 2, facing(120), 1.0, solid=None)
    put("scenery", "fallsrock2", fx + 6, fy - 1, facing(100), 0.9, solid=None)

    # ------------------------------------------------------------ 3 The Stone Ring
    cx, cy = sec["w3"]["at"]
    for k in range(12):
        a = 2 * math.pi * k / 12 + 0.13
        put("arena", f"standing{1 + k % 3}", cx + 16.5 * math.cos(a), cy + 16.5 * math.sin(a),
            facing(math.degrees(a) + 180), 1.9 if k % 3 == 1 else 1.6)
    put("arena", "altar", cx + 2, cy - 2, facing(90), 1.0)
    put("arena", "rubble", cx - 8, cy + 9, rng.uniform(0, 360), 0.8)

    # ------------------------------------------------------------ 4 Raven Gorge
    w4 = sec["w4"]
    for m in layout.mouths:
        if m["section"] == "w4" and m["kind"] == "pocket":
            bx, by = m["at"]
            b = bearing_to(*w4["at"], bx, by)
            dx, dy = math.cos(math.radians(b)), math.sin(math.radians(b))
            put("arena", "tomb", bx + dx * (m["radius"] + 1.5), by + dy * (m["radius"] + 1.5), facing(b + 180), 0.75)
    for x, y, key in ((212.0, 57.0, "collapse"), (226.0, 61.0, "rubble"), (200.0, 46.0, "rubble"),
                      (246.0, 56.0, "collapse"), (190.0, 56.0, "rubble"), (236.0, 44.0, "rubble")):
        put("arena", key, x, y, rng.uniform(0, 360), 1.0)
    for x, y in ((205.0, 49.0), (219.0, 53.0), (240.0, 50.0), (230.0, 58.0)):
        put("arena", "bones", x, y, rng.uniform(0, 360), 1.0, solid=None)

    # ------------------------------------------------------------ checkpoints, the watch post, Heron Pool
    for cp in data["checkpoints"]:
        x, y = cp["at"]
        put("camp", "firepit", x, y, 0.0, 1.0)
        put("camp", "woodshelter", x + 3.5, y - 2.5, rng.uniform(0, 360), 0.9)
    cp2 = next(c for c in data["checkpoints"] if c["id"] == "cp2")
    put("fort", "tower", cp2["at"][0] - 10, cp2["at"][1] + 1, facing(0), 0.6)
    for side in data.get("sides", []):
        x, y = side["at"]
        put("scenery", "stones1", x + 1, y + 3, 0, 1.2)
        put("scenery", "fern", x - 3, y - 3, rng.uniform(0, 360), 1.0, solid=None)
        put("scenery", "boulder3", x + 5, y + 4, rng.uniform(0, 360), 0.7)

    # ------------------------------------------------------------ road furniture
    for p in layout.paths:
        pts = p["points"]
        dist = 0.0
        for (ax, ay, _), (bx, by, _) in zip(pts, pts[1:]):
            n = math.hypot(bx - ax, by - ay)
            ux, uy = (bx - ax) / max(n, 1e-6), (by - ay) / max(n, 1e-6)
            s = 0.0
            while s < n:
                if (dist + s) % 48.0 < 1.0 and dist + s > 20:
                    side = 1 if int((dist + s) / 48) % 2 else -1
                    off = p["width"] / 2 + 1.4
                    x, y = ax + ux * s - uy * off * side, ay + uy * s + ux * off * side
                    if layout_d(lattice, x, y) > 0.6:
                        put("road", "lantern", x, y, facing(bearing_to(x, y, ax + ux * s, ay + uy * s)), 1.0, solid=None)
                s += 1.0
            dist += n

    # ------------------------------------------------------------ cliffs: crags round the crag and the frame
    for k in range(28):
        a = 2 * math.pi * k / 28 + rng.uniform(-0.04, 0.04)
        r = 1.04 + rng.uniform(0.0, 0.08)
        x, y = cx0 + crag["rx"] * r * math.cos(a), cy0 + crag["ry"] * r * math.sin(a)
        if layout_d(lattice, x, y) < 6:
            continue
        put("scenery", CRAGS[k % 5], x, y, math.degrees(a) + rng.uniform(-30, 30), rng.uniform(0.55, 0.8), solid=None,
            sink=4.0)
    for k in range(34):
        edge = k % 4
        t = rng.uniform(0.05, 0.95)
        x, y = [(t * layout.W, 6.0), (layout.W - 6.0, t * layout.H), (t * layout.W, layout.H - 6.0), (6.0, t * layout.H)][edge]
        if layout_d(lattice, x, y) < 10:
            continue
        put("scenery", CRAGS[int(rng.integers(0, 5))], x, y, rng.uniform(0, 360), rng.uniform(0.9, 1.4), solid=None,
            sink=3.0)

    # ------------------------------------------------------------ woods and the road's edges
    d = lattice["d"]
    kc = lattice["kc"]
    wet = lattice["wet"]
    height = lattice["height"]
    W, H = layout.W, layout.H
    pockets = [(m["at"][0], m["at"][1], m["radius"]) for m in layout.mouths if m["kind"] != "floor"]
    weights = np.array([w for _, w in TREES])
    weights /= weights.sum()
    placed = 0
    for _ in range(40000):
        x = rng.uniform(3, W - 3)
        y = rng.uniform(3, H - 3)
        i, j = int(y * 2), int(x * 2)
        dist = d[i, j]
        if dist < 3.0 or wet[i, j] or kc[i, j] < 1.1:
            continue
        gy = height[min(i + 4, height.shape[0] - 1), j] - height[max(i - 4, 0), j]
        gx = height[i, min(j + 4, height.shape[1] - 1)] - height[i, max(j - 4, 0)]
        if math.hypot(gx, gy) / 4.0 > 1.1:
            continue
        near_pocket = any(math.hypot(x - px, y - py) < r + 7 for px, py, r in pockets)
        keep = 0.9 if (near_pocket or dist < 9) else 0.3
        if rng.random() > keep:
            continue
        key = TREES[int(rng.choice(len(TREES), p=weights))][0]
        put("woods", key, x, y, rng.uniform(0, 360), rng.uniform(0.9, 1.45), solid="trunk")
        placed += 1
        if placed >= 560:
            break
    # gorge snags on the walls
    for k in range(10):
        x = rng.uniform(178, 262)
        y = rng.choice([rng.uniform(26, 32), rng.uniform(74, 82)])
        if layout_d(lattice, x, y) > 2.5:
            put("woods", "snag", x, y, rng.uniform(0, 360), rng.uniform(0.9, 1.3), solid=None)
    cover = 0
    for _ in range(30000):
        x = rng.uniform(3, W - 3)
        y = rng.uniform(3, H - 3)
        i, j = int(y * 2), int(x * 2)
        dist = d[i, j]
        if not (0.6 < dist < 7.0) or wet[i, j] or kc[i, j] < 1.05:
            continue
        put("cover", COVER[int(rng.integers(0, len(COVER)))], x, y, rng.uniform(0, 360), rng.uniform(0.8, 1.3),
            solid=None, sink=0.05)
        cover += 1
        if cover >= 650:
            break
    rocks = 0
    for _ in range(8000):
        x = rng.uniform(3, W - 3)
        y = rng.uniform(3, H - 3)
        i, j = int(y * 2), int(x * 2)
        if not (1.0 < d[i, j] < 12.0) or wet[i, j]:
            continue
        put("cover", BOULDERS[int(rng.integers(0, 5))], x, y, rng.uniform(0, 360), rng.uniform(0.6, 1.3), solid=None,
            sink=0.4)
        rocks += 1
        if rocks >= 140:
            break
    for _ in range(60):
        x = rng.uniform(10, W - 10)
        y = rng.uniform(10, H - 10)
        if 3.0 < layout_d(lattice, x, y) < 14.0:
            put("cover", ["log1", "log2", "hollowlog", "stump1", "stump2"][int(rng.integers(0, 5))], x, y,
                rng.uniform(0, 360), 1.0, solid=None)

    # ------------------------------------------------------------ procedural bits with no kit
    d35 = math.radians(35.0)
    ux, uy = math.cos(d35), math.sin(d35)
    bx, by = 262.0, 270.0
    deck = h(bx, by) + 2.2
    for k in (-2, -1, 1, 2):
        x, y = bx + ux * k * 4.4, by + uy * k * 4.4
        props.box(x, y, 4.6, 4.2, 0.9, rot=35, mat="ashlar", z=deck)
        props.cyl(x, y, 0.9, 2.4, mat="ashlar")
    props.box(fx, fy, 7.0, 1.0, 12.0, rot=-55, mat="water_stream", solid=False, z=data["river"]["fall"]["to"])
    for side in data.get("sides", []):
        x, y = side["at"]
        props.cyl(x + 1.0, y + 3.0, 2.6, 0.2, mat="water_stream", segments=16)
    for cp in data["checkpoints"]:
        x, y = cp["at"]
        props.cyl(x, y, 0.5, 0.5, mat="gb_fire", solid=False, z=h(x, y) + 0.15)
        props.light(x, y, h(x, y) + 1.4, ident=f"{cp['id']}-fire")
    props.cyl(38, 300, 0.5, 0.5, mat="gb_fire", solid=False, z=h(38, 300) + 0.15)
    props.light(38, 300, h(38, 300) + 1.4, ident="camp-fire")

    # ------------------------------------------------------------ the interactive objects
    for x, y, kind in _object_spots(layout):
        if kind == "waystone":
            put("objects", "waystone", x, y, facing(180), 1.0, solid=None)
        elif kind == "cache":
            put("objects", "crates", x, y, facing(180), 0.8, solid=None)
        elif kind == "plaque":
            put("objects", "notice", x, y, facing(90), 1.0, solid=None)
        elif kind == "node":
            props.cyl(x, y, 0.5, 0.8, mat="gb_canopy_broad", solid=False)
    props.counts = {"trees": placed, "cover": cover, "rocks": rocks}
    # designed space that must stay open whatever the kit's body says: the undercroft and its door
    vault = sec["vault"]
    props.clear = [("ellipse", vault["at"][0], vault["at"][1], vault["rx"] - 0.5, vault["ry"] - 0.5),
                   ("path", (sec["boss"]["at"][0] + 16.0, sec["boss"]["at"][1]), tuple(vault["at"]), 3.0)]


def layout_d(lattice, x, y):
    d = lattice["d"]
    i = min(max(int(round(y * 2)), 0), d.shape[0] - 1)
    j = min(max(int(round(x * 2)), 0), d.shape[1] - 1)
    return float(d[i, j])


def _object_spots(layout):
    """(x, y, kind) for every interactive and node spot, in plan coordinates."""
    sec = layout.sections
    th = sec["trailhead"]["at"]
    va = sec["vault"]["at"]
    spots = [(th[0] + 8, th[1] - 2, "waystone"), (th[0] - 5, th[1] - 7, "plaque"),
             (va[0] + 5, va[1] + 5, "waystone"), (va[0] + 5, va[1] - 4, "cache")]
    for side in layout.data.get("sides", []):
        x, y = side["at"]
        spots.append((x + 3, y - 3, "node"))
        spots.append((x - 4, y + 2, "plaque"))
    return spots


def objects(layout, height_at):
    H = layout.H

    def tile(x, y):
        return [int(math.floor(x)), int(H - 1 - math.floor(y))]

    sec = layout.sections
    th = sec["trailhead"]["at"]
    va = sec["vault"]["at"]
    staging = tile(th[0] + 8, th[1] - 2)
    rules = tile(th[0] - 5, th[1] - 7)
    vault_exit = tile(va[0] + 5, va[1] + 5)
    cache = tile(va[0] + 5, va[1] - 4)
    side = layout.data.get("sides", [])[0]
    node = tile(side["at"][0] + 3, side["at"][1] - 3)
    pool_plaque = tile(side["at"][0] - 4, side["at"][1] + 2)
    interactives = [
        {"id": "plaque-trailhead", "kind": "information", "target": "lore", "label": "Rules of the road",
         "text": "One party at a time. The waves come to you; the road behind stays quiet once you have cleared it. "
                 "Fall and you rise at the last fire you passed. The waystones count you out.",
         "serverTile": rules, "objectId": 861},
        {"id": "exit-staging", "kind": "waystone", "target": "home", "label": "Waystone",
         "text": "The waystone home. Using it counts you out of the run.", "serverTile": staging, "objectId": 800},
        {"id": "plaque-heron-pool", "kind": "information", "target": "lore", "label": "The pilgrims' pool",
         "text": "Pilgrims washed here before the last climb to Harrowcrag. The herons still fish it. "
                 "Nothing else of the pilgrims is left.", "serverTile": pool_plaque, "objectId": 862},
        {"id": "cache", "kind": "cache", "target": "run", "label": "The Castellan's strongbox",
         "text": "The road's cache. It opens once for each of you when the keep court is quiet.",
         "serverTile": cache, "objectId": 798},
        {"id": "exit-vault", "kind": "waystone", "target": "home", "label": "Waystone",
         "text": "The waystone home.", "serverTile": vault_exit, "objectId": 799},
    ]
    return {
        "stagingExit": {"objectId": 800, "tile": staging, "label": "Waystone"},
        "vaultExit": {"objectId": 799, "tile": vault_exit, "label": "Waystone"},
        "cache": {"objectId": 798, "tile": cache, "label": "The Castellan's strongbox"},
        "plaques": [{"objectId": 861, "tile": rules, "at": "trailhead"}, {"objectId": 862, "tile": pool_plaque, "at": "heron-pool"}],
        "interactives": interactives,
        "sideTiles": {side["id"]: {"node": node, "plaque": pool_plaque}},
    }
