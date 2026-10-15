"""Grey-box dressing for a trail road, from its layout's `dressing` block.

A route's `source/dressing.py` (which build_trail.py loads) is a shim over this
module: the road's kits, woods, set pieces and labels live in its layout.json,
so one dresser serves every road that has no fort of its own to build. The
Harrowcrag Road keeps its own dresser.

Plan coordinates (x east, y south). A kit's front is its glTF +Z, which is plan
+y (bearing 90), so a piece faces bearing b at rot = b - 90. Solid pieces close
the ground their body stands on (kits.KitLibrary), trees only at the trunk,
ground cover nowhere; a solid piece never stands in a creature mouth's way in,
and the builder re-opens every interactive object's tile.

The `dressing` block:
    kits          {key: "region/kit-stem" | "@kit/file.glb"}
    tint          {key: [r, g, b]}           darken or recolour a kit's textures
    woods         {count, mix: [[key, weight]...], scale: [lo, hi], near: m, minElev, maxElev, solid}
    cover         {count, mix, band: [near, far]}       walk-through ground cover by the road
    rocks         {count, mix, band, scale}             boulders off the road
    frame         {count, mix, scale, sink}             crags along the map's edge
    camp          {tents: key, fire: key, shelter: key, crates: [keys]}
    checkpoint    {fire: key, shelter: key}
    lantern       {key, every: m}
    objects       {waystone: key, cache: key, plaque: key}
    city          {count, mix, gap: m}                  houses packed off the road (a drowned quarter)
    landmarks     [item...]: {"kit": key, "at": [x, y], "rot": deg | "face": [x, y], "scale" | "fitLength",
                  "solid" ("footprint" | "trunk" | null | {"disc": r}), "z" | "dz", "group", "deck" (sit
                  the kit's deck on the road: "deckMax", "deckLift"), "alongLength" (turn a model long
                  in z so its length follows rot)} or a primitive {"shape": box|cyl|cone|ball, "at", "size"|"r","h",
                  "mat", "rot", "z" | "dz", "solid"}; {"ring": {...item, "around": [x, y], "radius": [rx, ry],
                  "rotDeg", "n", "phase"}} and {"line": {...item, "from", "to", "step"}} repeat an item
    labels        {plaque: [title, text], cache, side: [title, text]}
"""
from __future__ import annotations

import math

import numpy as np

from landforms import seeded

REGIONS = "godot-client/world_authoring/regions"


def kit_paths(checkout, route_dir, kits):
    out = {}
    for key, ref in kits.items():
        if ref.startswith("@"):
            out[key] = route_dir / "source" / ref[1:]
        else:
            region, stem = ref.split("/")
            out[key] = checkout / REGIONS / region / "assets" / "prototypes" / f"{stem}.glb"
    return out


def facing(bearing):
    return bearing - 90.0


def bearing_to(ax, ay, bx, by):
    return math.degrees(math.atan2(by - ay, bx - ax))


def layout_d(lattice, x, y, key="d"):
    a = lattice[key]
    i = min(max(int(round(y * 2)), 0), a.shape[0] - 1)
    j = min(max(int(round(x * 2)), 0), a.shape[1] - 1)
    return a[i, j]


def _repeat(item, kits=None):
    """A ring or a line of one item, as plain items. A line of a kit with `"step": "auto"` lays
    its modules end to end along the kit's own length (x), a metre's overlap hiding the joins."""
    if "ring" in item:
        spec = dict(item["ring"])
        cx, cy = spec.pop("around")
        rx, ry = spec.pop("radius")
        rot = math.radians(spec.pop("rotDeg", 0.0))
        n = spec.pop("n")
        phase = spec.pop("phase", 0.0)
        out = []
        for k in range(n):
            a = phase + 2 * math.pi * k / n
            u, v = rx * math.cos(a), ry * math.sin(a)
            x, y = cx + u * math.cos(rot) - v * math.sin(rot), cy + u * math.sin(rot) + v * math.cos(rot)
            one = dict(spec, at=[x, y])
            if "rot" not in one and "face" not in one:
                one["rot"] = facing(math.degrees(math.atan2(y - cy, x - cx)) + 180)
            out.append(one)
        return out
    if "line" in item:
        spec = dict(item["line"])
        (ax, ay), (bx, by) = spec.pop("from"), spec.pop("to")
        step = spec.pop("step")
        if step == "auto":
            ext = kits.extent(spec["kit"])
            step = max(ext[0], ext[2]) * float(spec.get("scale", 1.0)) - spec.pop("overlap", 1.0)
        n = max(1, int(round(math.hypot(bx - ax, by - ay) / step)))
        ang = facing(bearing_to(ax, ay, bx, by)) + 90
        return [dict(spec, at=[ax + (bx - ax) * (k + 0.5) / n, ay + (by - ay) * (k + 0.5) / n],
                     rot=spec.get("rot", ang)) for k in range(n)]
    return [item]


def dress(spec, props, layout, lattice, kits, groups, paths):
    data = layout.data
    sec = layout.sections
    rng = np.random.default_rng(seeded(data.get("id", "trail") + ":dress"))
    tints = spec.get("tint", {})
    for key, path in paths.items():
        kits.load(key, path, tint=tuple(tints[key]) if key in tints else None)
    h = props.height_at
    W, H = layout.W, layout.H
    d = lattice["d"]
    height = lattice["height"]
    wet = lattice["wet"]
    feats = lattice.get("features", {})
    deep = feats.get("deep", np.zeros(d.shape, bool))
    keep = feats.get("keep", np.zeros(d.shape, bool))
    water_level = lattice["land"].water_level if lattice.get("land") is not None and lattice["land"].water_mode else None

    links = [(m["rimPoint"], m["at"], m["width"] / 2 + 3.5) for m in layout.mouths if m["kind"] != "floor"]
    pockets = [(m["at"][0], m["at"][1], m["radius"]) for m in layout.mouths if m["kind"] != "floor"]

    def blocks_a_mouth(x, y, pad=0.0):
        for (ax, ay), (bx, by), reach in links:
            dx, dy = bx - ax, by - ay
            t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / max(dx * dx + dy * dy, 1e-9)))
            if math.hypot(x - (ax + t * dx), y - (ay + t * dy)) < reach + pad:
                return True
        return any(math.hypot(x - px, y - py) < r + 1.0 + pad for px, py, r in pockets)

    spots = [(x, y) for x, y, _ in object_spots(layout)]

    def crowds_an_object(x, y, reach):
        """A solid body this wide here would wall in an interactive object's tile."""
        return any(math.hypot(x - sx, y - sy) < reach + 1.5 for sx, sy in spots)

    owner, kinds = lattice["owner"], lattice["kinds"]
    path_kind = np.array([k == "path" for k in kinds])

    def blocks_the_road(x, y, reach):
        """A solid body this wide here would stand on a path between sections: the road's own
        corridor (inside an arena the floor is wide enough to go round)."""
        for k in range(13):
            if k == 12:
                px, py = x, y
            else:
                a = 2 * math.pi * k / 12
                px, py = x + math.cos(a) * reach * 0.85, y + math.sin(a) * reach * 0.85
            i, j = cell(px, py)
            if d[i, j] <= 0.5 and path_kind[owner[i, j]]:
                return True
        return False

    def kit_reach(key, scale, solid):
        if solid == "trunk":
            return 0.8 * scale
        lo, hi = kits.kits[key].bounds
        return 0.5 * max(hi[0] - lo[0], hi[2] - lo[2]) * scale

    def cell(x, y):
        return min(max(int(y * 2), 0), d.shape[0] - 1), min(max(int(x * 2), 0), d.shape[1] - 1)

    def on_water(x, y):
        i, j = cell(x, y)
        if wet[i, j] or (deep[i, j] and not keep[i, j]):
            return True
        return water_level is not None and height[i, j] < water_level + 0.15

    def put(group, key, x, y, rot=0.0, scale=1.0, solid="footprint", z=None, sink=0.15, encloses=False):
        if key not in kits.kits:
            raise SystemExit(f"dressing names no kit {key!r}")
        # a solid piece never stands in a creature mouth's way in: the mouth is how a pulse arrives
        if solid in ("footprint", "trunk"):
            reach = kit_reach(key, scale, solid)
            # a vault's own shell (`encloses`) stands round its objects: props.clear reopens the vault
            # and over the way into it (props.clear reopens both)
            if (blocks_a_mouth(x, y, 0.7 * reach)
                    or (not encloses and (crowds_an_object(x, y, reach) or blocks_the_road(x, y, reach)))):
                props.notes.add(f"refused {key} at ({x:.0f}, {y:.0f})")
                return False
        kits.place(groups[group], key, x, y, (h(x, y) if z is None else z) - sink, rot, scale, solid)
        return True

    def pick(mix):
        keys = [k for k, _ in mix]
        weights = np.array([w for _, w in mix], dtype=np.float64)
        return keys[int(rng.choice(len(keys), p=weights / weights.sum()))]

    def base_z(item, x, y):
        if item.get("z") is not None:
            return float(item["z"])
        return h(x, y) + float(item.get("dz", 0.0))

    # ------------------------------------------------------------ set pieces
    placed_landmarks = 0
    for raw in spec.get("landmarks", []):
        for item in _repeat(raw, kits):
            x, y = item["at"]
            group = item.get("group", "arena")
            if "face" in item:
                rot = facing(bearing_to(x, y, *item["face"]))
            else:
                rot = float(item.get("rot", 0.0))
            if "kit" in item:
                key = item["kit"]
                scale = float(item.get("scale", 1.0))
                ext = kits.extent(key)
                long_side = max(ext[0], ext[2])
                if item.get("deck") or "fitLength" in item or item.get("alongLength"):
                    # a run lies along its long side: a model that is long in z is turned so its z
                    # follows the bearing `rot` gives its x
                    if ext[2] > ext[0]:
                        rot -= 90.0
                if "fitLength" in item:                      # sized to a crossing or a run
                    scale = float(item["fitLength"]) / long_side
                if item.get("deck"):
                    # a bridge, causeway or stair the road crosses on: its deck sits on the walk
                    # height (the ground under a crossing is the road), and it closes nothing
                    top = kits.deck_top(key, float(item.get("deckMax", 1.0))) * scale
                    z = h(x, y) - top + float(item.get("deckLift", 0.04))
                    solid = None                              # a deck never closes the road it carries
                    sink = 0.0
                else:
                    solid = item.get("solid", "footprint")
                    z = base_z(item, x, y) if ("z" in item or "dz" in item) else None
                    sink = float(item.get("sink", 0.15))
                disc = None
                if isinstance(solid, dict):                  # {"disc": r}: a trunk of its own size
                    disc, solid = float(solid["disc"]) * scale, None
                    if blocks_a_mouth(x, y, disc) or blocks_the_road(x, y, disc):
                        props.notes.add(f"refused {key} at ({x:.0f}, {y:.0f})")
                        continue
                if put(group, key, x, y, rot, scale, solid, z, sink, bool(item.get("encloses"))):
                    placed_landmarks += 1
                    if disc:
                        props.solids.append(("disc", x, y, disc))
                continue
            mat = item.get("mat", "ashlar")
            z0 = base_z(item, x, y)
            overhead = z0 - h(x, y) > 2.2
            reach = item.get("r") or 0.5 * max(item.get("size", [1, 1])[:2])
            solid = bool(item.get("solid", not overhead)) and not (
                (blocks_a_mouth(x, y) or crowds_an_object(x, y, reach)) and not item.get("force"))
            shape = item["shape"]
            if shape == "box":
                sx, sy, sz = item["size"]
                props.box(x, y, sx, sy, sz, rot=rot, mat=mat, solid=solid, z=z0, bucket="Props")
            elif shape == "cyl":
                props.cyl(x, y, item["r"], item["h"], mat=mat, solid=solid, z=z0, top=item.get("top"),
                          segments=item.get("segments", 12))
            elif shape == "cone":
                props.cone(x, y, item["r"], item["h"], mat=mat, z=z0, bucket="Props", segments=item.get("segments", 9),
                           solid=solid)
            elif shape == "ball":
                props.rock(x, y, item["r"], mat=mat, solid=solid, squash=item.get("squash", 1.0), seed=placed_landmarks)
            placed_landmarks += 1

    # ------------------------------------------------------------ the camp, the fires, the lanterns
    camp_spec = spec.get("camp", {})
    th = sec[layout.order[0]]
    cx, cy = th["at"]
    if camp_spec:
        for k, b in enumerate((150.0, 230.0, 310.0)):
            r = math.radians(b)
            x, y = cx + math.cos(r) * th["rx"] * 0.62, cy + math.sin(r) * th["ry"] * 0.62
            put("camp", camp_spec["tents"], x, y, facing(bearing_to(x, y, cx, cy)), camp_spec.get("tentScale", 1.0))
        put("camp", camp_spec["fire"], cx - 3.0, cy + 1.0, 0.0, 1.0)
        props.cyl(cx - 3.0, cy + 1.0, 0.5, 0.5, mat="gb_fire", solid=False, z=h(cx - 3.0, cy + 1.0) + 0.15)
        props.light(cx - 3.0, cy + 1.0, h(cx - 3.0, cy + 1.0) + 1.4, ident="camp-fire")
        if camp_spec.get("shelter"):
            x, y = cx + th["rx"] * 0.55, cy + th["ry"] * 0.45
            put("camp", camp_spec["shelter"], x, y, facing(bearing_to(x, y, cx, cy)), 1.0)
        for k, key in enumerate(camp_spec.get("crates", [])):
            x, y = cx - th["rx"] * 0.55 + k * 1.6, cy + th["ry"] * 0.5
            put("camp", key, x, y, rng.uniform(0, 360), 1.0)
    cp_spec = spec.get("checkpoint", camp_spec)
    for cp in data.get("checkpoints", []):
        x, y = cp["at"]
        if cp_spec.get("fire"):
            put("camp", cp_spec["fire"], x, y, 0.0, 1.0)
        if cp_spec.get("shelter"):
            put("camp", cp_spec["shelter"], x + 3.5, y - 2.5, rng.uniform(0, 360), 0.9)
        props.cyl(x, y, 0.5, 0.5, mat="gb_fire", solid=False, z=h(x, y) + 0.15)
        props.light(x, y, h(x, y) + 1.4, ident=f"{cp['id']}-fire")
    lantern = spec.get("lantern")
    if lantern:
        every = lantern.get("every", 48.0)
        for p in layout.paths:
            pts = p["points"]
            dist = 0.0
            for (ax, ay, _), (bx, by, _) in zip(pts, pts[1:]):
                n = math.hypot(bx - ax, by - ay)
                ux, uy = (bx - ax) / max(n, 1e-6), (by - ay) / max(n, 1e-6)
                s = 0.0
                while s < n:
                    if (dist + s) % every < 1.0 and dist + s > 20:
                        side = 1 if int((dist + s) / every) % 2 else -1
                        off = p["width"] / 2 + 1.4
                        x, y = ax + ux * s - uy * off * side, ay + uy * s + ux * off * side
                        if layout_d(lattice, x, y) > 0.6 and (lantern.get("wet") or not on_water(x, y)):
                            put("road", lantern["key"], x, y, facing(bearing_to(x, y, ax + ux * s, ay + uy * s)), 1.0,
                                solid=None)
                    s += 1.0
                dist += n

    # ------------------------------------------------------------ a drowned quarter's houses
    city = spec.get("city")
    houses = 0
    if city:
        gap = city.get("gap", 3.5)
        taken = []
        for _ in range(city["count"] * 40):
            if houses >= city["count"]:
                break
            x, y = rng.uniform(8, W - 8), rng.uniform(8, H - 8)
            key = pick(city["mix"])
            lo, hi = kits.kits[key].bounds
            radius = 0.5 * math.hypot(hi[0] - lo[0], hi[2] - lo[2]) * city.get("scale", 1.0)
            if layout_d(lattice, x, y) < radius + gap:
                continue
            i, j = cell(x, y)
            if feats.get("canal") is not None and feats["canal"][i, j]:
                continue
            if any(math.hypot(x - a, y - b) < radius + r + 1.0 for a, b, r in taken):
                continue
            if blocks_a_mouth(x, y, radius):
                continue
            # the nearest road is where the front faces
            best = None
            for p in layout.paths:
                for q in p["points"]:
                    dq = math.hypot(q[0] - x, q[1] - y)
                    if best is None or dq < best[0]:
                        best = (dq, q[0], q[1])
            rot = facing(bearing_to(x, y, best[1], best[2])) if best else rng.uniform(0, 360)
            kits.place(groups["scenery"], key, x, y, h(x, y) - 0.3, round(rot / 90) * 90, city.get("scale", 1.0), None)
            taken.append((x, y, radius))
            houses += 1

    # ------------------------------------------------------------ the frame's crags
    frame = spec.get("frame")
    if frame:
        for k in range(frame["count"]):
            edge = k % 4
            t = rng.uniform(0.04, 0.96)
            x, y = [(t * W, 6.0), (W - 6.0, t * H), (t * W, H - 6.0), (6.0, t * H)][edge]
            if layout_d(lattice, x, y) < 10 or on_water(x, y):
                continue
            put("scenery", pick(frame["mix"]), x, y, rng.uniform(0, 360), rng.uniform(*frame.get("scale", (0.9, 1.4))),
                solid=None, sink=frame.get("sink", 3.0))

    # ------------------------------------------------------------ woods, cover and rocks
    counts = {"landmarks": placed_landmarks, "houses": houses}
    woods = spec.get("woods")
    if woods:
        placed = 0
        lo_e, hi_e = woods.get("minElev", -1e9), woods.get("maxElev", 1e9)
        near = woods.get("near", 3.0)
        for _ in range(woods["count"] * 60):
            x, y = rng.uniform(3, W - 3), rng.uniform(3, H - 3)
            i, j = cell(x, y)
            dist = d[i, j]
            if dist < near or on_water(x, y) or not lo_e <= height[i, j] <= hi_e:
                continue
            gy = height[min(i + 4, height.shape[0] - 1), j] - height[max(i - 4, 0), j]
            gx = height[i, min(j + 4, height.shape[1] - 1)] - height[i, max(j - 4, 0)]
            if math.hypot(gx, gy) / 4.0 > woods.get("maxSlope", 1.1):
                continue
            near_pocket = any(math.hypot(x - px, y - py) < r + 7 for px, py, r in pockets)
            if rng.random() > (0.9 if (near_pocket or dist < 9) else woods.get("far", 0.3)):
                continue
            put("woods", pick(woods["mix"]), x, y, rng.uniform(0, 360), rng.uniform(*woods.get("scale", (0.9, 1.4))),
                solid=woods.get("solid", "trunk"))
            placed += 1
            if placed >= woods["count"]:
                break
        counts["trees"] = placed
    cover = spec.get("cover")
    if cover:
        placed = 0
        band = cover.get("band", (0.6, 7.0))
        for _ in range(cover["count"] * 40):
            x, y = rng.uniform(3, W - 3), rng.uniform(3, H - 3)
            if not (band[0] < layout_d(lattice, x, y) < band[1]) or on_water(x, y):
                continue
            put("cover", pick(cover["mix"]), x, y, rng.uniform(0, 360), rng.uniform(*cover.get("scale", (0.8, 1.3))),
                solid=None, sink=0.05)
            placed += 1
            if placed >= cover["count"]:
                break
        counts["cover"] = placed
    rocks = spec.get("rocks")
    if rocks:
        placed = 0
        band = rocks.get("band", (1.0, 12.0))
        for _ in range(rocks["count"] * 40):
            x, y = rng.uniform(3, W - 3), rng.uniform(3, H - 3)
            if not (band[0] < layout_d(lattice, x, y) < band[1]) or on_water(x, y):
                continue
            put("cover", pick(rocks["mix"]), x, y, rng.uniform(0, 360), rng.uniform(*rocks.get("scale", (0.6, 1.3))),
                solid=None, sink=rocks.get("sink", 0.4))
            placed += 1
            if placed >= rocks["count"]:
                break
        counts["rocks"] = placed

    # ------------------------------------------------------------ the interactive objects
    objs = spec.get("objects", {})
    for x, y, kind in object_spots(layout):
        if kind == "waystone" and objs.get("waystone"):
            put("objects", objs["waystone"], x, y, facing(180), 1.0, solid=None)
        elif kind == "cache" and objs.get("cache"):
            put("objects", objs["cache"], x, y, facing(180), 0.8, solid=None)
        elif kind == "plaque" and objs.get("plaque"):
            put("objects", objs["plaque"], x, y, facing(90), 1.0, solid=None)
        elif kind == "node":
            props.cyl(x, y, 0.5, 0.8, mat="gb_canopy_broad", solid=False)
    counts["refused"] = sorted(n[len("refused "):] for n in props.notes if n.startswith("refused "))
    props.counts = counts
    # designed space that must stay open whatever a kit's body says: the vault and its way in
    vault = sec["vault"]
    court = next(s for s in layout.order if sec[s]["kind"] == "court")
    props.clear = [("ellipse", vault["at"][0], vault["at"][1], vault["rx"] - 0.5, vault["ry"] - 0.5),
                   ("path", tuple(sec[court]["at"]), tuple(vault["at"]), 3.0)]


def object_spots(layout):
    """(x, y, kind) for every interactive and node spot, in plan coordinates."""
    sec = layout.sections
    th = sec[layout.order[0]]
    va = sec["vault"]
    spots = [(th["at"][0] + th["rx"] * 0.42, th["at"][1] - th["ry"] * 0.15, "waystone"),
             (th["at"][0] - th["rx"] * 0.25, th["at"][1] - th["ry"] * 0.45, "plaque"),
             (va["at"][0] + va["rx"] * 0.5, va["at"][1] + va["ry"] * 0.5, "waystone"),
             (va["at"][0] + va["rx"] * 0.5, va["at"][1] - va["ry"] * 0.45, "cache")]
    for side in layout.data.get("sides", []):
        x, y = side["at"]
        spots.append((x + 2.5, y - 2.5, "node"))
        spots.append((x - 3.0, y + 2.0, "plaque"))
    return spots


def objects(layout, height_at, labels):
    H = layout.H

    def tile(x, y):
        return [int(math.floor(x)), int(H - 1 - math.floor(y))]

    spots = object_spots(layout)
    staging, rules, vault_exit, cache = (tile(x, y) for x, y, _ in spots[:4])
    plaque_title, plaque_text = labels["plaque"]
    interactives = [
        {"id": "plaque-trailhead", "kind": "information", "target": "lore", "label": plaque_title,
         "text": plaque_text, "serverTile": rules, "objectId": 861},
        {"id": "exit-staging", "kind": "waystone", "target": "home", "label": "Waystone",
         "text": "The waystone home. Using it counts you out of the run.", "serverTile": staging, "objectId": 800},
        {"id": "cache", "kind": "cache", "target": "run", "label": labels["cache"],
         "text": "The road's cache. It opens once for each of you when the court is quiet.",
         "serverTile": cache, "objectId": 798},
        {"id": "exit-vault", "kind": "waystone", "target": "home", "label": "Waystone",
         "text": "The waystone home.", "serverTile": vault_exit, "objectId": 799},
    ]
    plaques = [{"objectId": 861, "tile": rules, "at": "trailhead"}]
    side_tiles = {}
    sides = layout.data.get("sides", [])
    if sides:
        side = sides[0]
        node = tile(side["at"][0] + 2.5, side["at"][1] - 2.5)
        side_plaque = tile(side["at"][0] - 3.0, side["at"][1] + 2.0)
        title, text = labels["side"]
        interactives.insert(2, {"id": f"plaque-{side['id']}", "kind": "information", "target": "lore", "label": title,
                                "text": text, "serverTile": side_plaque, "objectId": 862})
        plaques.append({"objectId": 862, "tile": side_plaque, "at": side["id"]})
        side_tiles[side["id"]] = {"node": node, "plaque": side_plaque}
    return {
        "stagingExit": {"objectId": 800, "tile": staging, "label": "Waystone"},
        "vaultExit": {"objectId": 799, "tile": vault_exit, "label": "Waystone"},
        "cache": {"objectId": 798, "tile": cache, "label": labels["cache"]},
        "plaques": plaques,
        "interactives": interactives,
        "sideTiles": side_tiles,
    }
