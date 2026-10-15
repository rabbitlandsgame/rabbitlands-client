"""Build one gauntlet package: `python _toolkit/gauntlets/build.py <region>`.

The route runs along +Z: the staging hall, then each leg behind its barred
way, the boss court, a plain way and the vault. Everything is one section
(there is nothing to black out - a gauntlet is walked end to end), exported
the way the secrets maps are so the client, the walk grid and the server
tools read it with the same code.

The manifest carries a `gauntlet` block: each leg's fight floor in server
tiles, its spawn tiles, its gate (the object a player uses, the tile they
stand on and the tile beyond), the court's boss and add tiles, the cache and
the two waystones. `tools/author_gauntlets.py` on the server turns that,
with the designs, into the instance file, the spawn groups, the objects and
the portals.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLKIT = HERE.parent
ROOT = TOOLKIT.parent
for entry in (str(TOOLKIT), str(HERE)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from amberwood import mesh as M                       # noqa: E402
from amberwood import materials as MAT                # noqa: E402
import preview                                         # noqa: E402
from amberwood.interiors import Interior, hanging_lamps  # noqa: E402
import export_insides_collision as EXPORT              # noqa: E402
import secrets_build as SB                             # noqa: E402
import validate_gltf                                   # noqa: E402
from gauntlets import designs as D                     # noqa: E402
from gauntlets import rooms as R                       # noqa: E402

TILES = 64                # server tiles; 384 m
WAY = 12.0                # a barred way between two rooms


def compose(theme: D.Theme, seed: int):
    pal = dict(theme.palette)
    pal.setdefault("bark", "bark_dark")
    pal["room_floors"] = theme.props.get("roomFloors", {})
    pal["flood_rooms"] = theme.props.get("floodRooms", ())
    pal["open_canyon"] = theme.props.get("openCanyon", False)
    pal["layout_seed"] = seed
    kit = theme.props.get("kit", "forest")
    way = float(theme.props.get("wayLength", WAY))
    it = Interior(theme.id, theme.name, "gauntlet", "", [0.0, 0.0, 0.0], "default")
    it.areas = []
    legs_out = []
    cursor_z = 0.0
    prev = R.staging(it, pal, kit, cursor_z, 0.0, seed, lore=theme.lore)
    staging = {"key": "staging", "bounds": prev.bounds}
    for index, leg in enumerate(theme.legs):
        leg_seed = seed + 31 * (index + 1)
        x = prev.x_out
        floor = prev.floor_out
        z_gate_start = prev.z_end
        z_room = z_gate_start + way
        gate_position, before, beyond = R.barred_way(it, leg.id, pal, leg.gate, (x, z_gate_start), (x, z_room),
                                                     floor, floor, leg_seed)
        record = {"id": leg.id, "name": leg.name, "kind": leg.kind, "advance": leg.advance,
                  "trigger": leg.trigger, "pressure": leg.pressure, "late": leg.late,
                  "gate": {"id": f"gate-{leg.id}", "kind": leg.gate, "label": R.GATE_LABELS[leg.gate],
                           "position": gate_position, "before": before, "beyond": beyond},
                  "bonus": leg.bonus}
        if leg.kind == "hall":
            built = R.hall(it, leg.id, pal, kit, z_room, x, floor, leg_seed, leg.pressure)
        elif leg.kind == "cavern":
            built = R.cavern(it, leg.id, pal, kit, z_room, x, floor, leg_seed, leg.pressure)
        elif leg.kind == "bridge":
            built = R.bridge(it, leg.id, pal, kit, z_room, x, floor, leg_seed, leg.pressure,
                             deck=theme.props.get("bridgeDeck", "stone"))
        elif leg.kind == "stair":
            built = R.stair(it, leg.id, pal, kit, z_room, x, floor, leg_seed, leg.pressure)
        elif leg.kind == "gallery":
            built = R.gallery(it, leg.id, pal, kit, z_room, x, floor, leg_seed, leg.pressure, bonus=leg.bonus)
        elif leg.kind == "fork":
            built, info = R.fork(it, leg.id, pal, kit, z_room, x, floor, leg_seed, leg.pressure, leg.branches, way=way)
            record["room"] = info["hub"]["key"]
            record["bounds"] = info["hub"]["bounds"]
            record["spawns"] = info["hub"]["spawns"]
            record["branches"] = []
            for branch in info["branches"]:
                g = branch["gate"]
                gate_position, b_before, b_beyond = R.barred_way(
                    it, f"{leg.id}-{branch['id']}", pal, leg.gate, (g["x"], g["z0"]), (g["x"], g["z1"]),
                    floor, floor, leg_seed + 7)
                record["branches"].append({
                    "id": branch["id"], "name": branch["name"], "kind": branch["kind"], "room": branch["key"],
                    "bounds": branch["bounds"], "spawns": branch["spawns"],
                    "gate": {"id": f"gate-{leg.id}-{branch['id']}", "kind": leg.gate,
                             "label": R.GATE_LABELS[leg.gate], "position": gate_position,
                             "before": b_before, "beyond": b_beyond}})
            record["merge"] = {"room": info["merge"]["key"], "bounds": info["merge"]["bounds"]}
            legs_out.append(record)
            prev = built
            continue
        elif leg.kind == "court":
            built = R.court(it, leg.id, pal, kit, z_room, x, floor, leg_seed, leg.pressure,
                            rear_step=theme.props.get("rearDaisStep", False))
            record["boss"] = built.boss
        else:
            raise ValueError(f"unknown leg kind {leg.kind!r} in {theme.id}")
        record["room"] = built.key
        record["bounds"] = built.bounds
        record["spawns"] = built.spawns
        if leg.plaque:
            title, text = leg.plaque
            bx0, bz0, bx1, bz1 = built.bounds
            R._plaque(it, f"plaque-{leg.id}", title, text, bx0 + 1.4, built.floor_out, bz0 + 2.0,
                      material=pal["timber"])
        legs_out.append(record)
        prev = built
    # the vault behind a plain way
    x = prev.x_out
    R.plain_way(it, "vault", pal, (x, prev.z_end), (x, prev.z_end + 8.0), prev.floor_out, prev.floor_out, seed)
    vault_built = R.vault(it, "vault", pal, kit, prev.z_end + 8.0, x, prev.floor_out, seed + 99)
    if kit == "forest_haul":
        from gauntlets import forest_haul
        forest_haul.dress(it, pal, seed)
    elif kit == "ice_mine":
        from gauntlets import ice_mine
        ice_mine.dress(it, pal, seed)
    elif kit == "temple_procession":
        from gauntlets import temple_procession
        temple_procession.dress(it, pal, seed)
    elif kit == "barrow_visitation":
        from gauntlets import barrow_visitation
        barrow_visitation.dress(it, pal, seed)
    elif kit == "drowned_customs":
        from gauntlets import drowned_customs
        drowned_customs.dress(it, pal, seed)
    elif kit == "canyon_wash":
        from gauntlets import red_canyon
        red_canyon.dress(it, pal, seed)
    lamps, placed = hanging_lamps(it.lamps, seed=seed)
    it.group.add(lamps)
    it.lamps = placed
    if theme.props.get("clipCoplanar", kit == "forest_haul"):
        from amberwood.coplanar import trim_coplanar
        trim_coplanar(it.group)
    it.spawn_space = "staging"
    it.landmark(f"{theme.id}-staging", theme.name, "staging", 1.6)
    it.environment = {"sky": "none", "ambient": {"colour": [0.10, 0.10, 0.12], "energy": 0.5},
                      "fog": {"enabled": True, "colour": [0.02, 0.02, 0.03], "begin": 16.0, "end": 60.0}}
    if kit == "forest_haul":
        it.environment = {
            "sky": "none", "backgroundColor": [0.035, 0.043, 0.038],
            "sun": {"enabled": False},
            "ambient": {"color": [0.44, 0.49, 0.43], "energy": 1.05},
            "fog": {"enabled": True, "color": [0.05, 0.065, 0.052], "density": 0.004},
            "tonemap": {"mode": "filmic", "exposure": 1.25, "white": 3.5}}
    if theme.props.get("environment"):
        it.environment = dict(theme.props["environment"])
    return it, legs_out, staging, {"key": "vault", "bounds": vault_built.bounds}


def prune_spawns(path: Path, grid) -> int:
    """Drop the spawn tiles the server's walk grid does not carry - under a
    boulder, against a pillar, in a wall's thickness - so a wave lands on the
    floor of its room. Returns how many went."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    dropped = 0

    def kept(tiles):
        nonlocal dropped
        out = [tile for tile in tiles if grid[tile[1], tile[0]]]
        dropped += len(tiles) - len(out)
        return out

    for leg in doc["gauntlet"]["legs"]:
        leg["spawnTiles"] = kept(leg["spawnTiles"])
        for branch in leg.get("branches", []):
            branch["spawnTiles"] = kept(branch["spawnTiles"])
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return dropped


def write_manifest(theme: D.Theme, it: Interior, legs, staging, vault, stats, collision_stats, path: Path):
    lo, hi = it.group.bounds()
    walk_lo, walk_hi = it.group.walk_bounds()
    origin = [float(-collision_stats["originMetres"][0]), float(collision_stats["originMetres"][1])]
    tile = lambda position: SB.tile_of(position, origin)   # noqa: E731

    def box(bounds):
        x0, z0, x1, z1 = bounds
        a = tile([x0, 0, z1]); b = tile([x1, 0, z0])
        return {"min": [min(a[0], b[0]), min(a[1], b[1])], "max": [max(a[0], b[0]), max(a[1], b[1])]}

    for entry in it.harvestables + it.interactives:
        entry["serverTile"] = tile(entry["position"])
    gate_index = 0

    def gate_record(gate):
        nonlocal gate_index
        gate_index += 1
        return dict(gate, tile=tile(gate["before"]), beyondTile=tile(gate["beyond"]), objectId=800 + gate_index)

    for leg in legs:
        leg["boundsTiles"] = box(leg["bounds"])
        leg["spawnTiles"] = [tile(p) for p in leg["spawns"]]
        leg["gate"] = gate_record(leg["gate"])
        if "boss" in leg:
            leg["bossTile"] = tile(leg["boss"])
        for branch in leg.get("branches", []):
            branch["boundsTiles"] = box(branch["bounds"])
            branch["spawnTiles"] = [tile(p) for p in branch["spawns"]]
            branch["gate"] = gate_record(branch["gate"])
        if "merge" in leg:
            leg["merge"]["boundsTiles"] = box(leg["merge"]["bounds"])
    sx0, sz0, sx1, sz1 = staging["bounds"]
    arrival = [round((sx0 + sx1) * 0.5, 2), 0.05, round((sz0 + sz1) * 0.5, 2)]
    vx0, vz0, vx1, vz1 = vault["bounds"]
    vault_spot = [round((vx0 + vx1) * 0.5, 2), round(it.spaces["vault"]["floor"] + 0.05, 2), round((vz0 + vz1) * 0.5, 2)]
    objects = {"exit-staging": 800, "exit-vault": 799, "cache": 798}
    for entry in it.interactives:
        if entry["id"] in objects:
            entry["objectId"] = objects[entry["id"]]
    plaque_index = 0
    for entry in it.interactives:
        if entry["kind"] == "information":
            plaque_index += 1
            entry["objectId"] = 860 + plaque_index
    gauntlet = {
        "id": theme.id, "region": theme.region, "name": theme.name, "short": theme.short,
        "flavour": theme.flavour,
        "staging": {"room": "staging", "boundsTiles": box(staging["bounds"]), "arrival": arrival,
                    "arrivalTile": tile(arrival),
                    "exit": next(e for e in it.interactives if e["id"] == "exit-staging")},
        "legs": legs,
        "vault": {"room": "vault", "boundsTiles": box(vault["bounds"]), "spot": vault_spot,
                  "spotTile": tile(vault_spot),
                  "cache": next(e for e in it.interactives if e["id"] == "cache"),
                  "exit": next(e for e in it.interactives if e["id"] == "exit-vault")},
        "keeper": {"name": theme.keeper.name, "at": theme.keeper.at, "offset": list(theme.keeper.offset),
                   "actorType": theme.keeper.actor_type},
        "maxPlayers": theme.max_players,
        "bands": [{"id": b.id, "label": b.label, "minAd": b.min_ad, "maxAd": b.max_ad,
                   "timeLimit": b.time_limit, "cooldownHours": b.cooldown_hours} for b in theme.bands],
    }
    doc = {
        "schemaVersion": "1.0.0", "assetVersion": "1.0.0",
        "asset": {"id": theme.id, "name": theme.name, "glb": "world.glb", "units": "meters",
                  "coordinateSystem": {"handedness": "right", "upAxis": "Y", "northAxis": "-Z"},
                  "origin": [0, 0, 0],
                  "bounds": {"min": [round(float(v), 2) for v in lo], "max": [round(float(v), 2) for v in hi]},
                  "playableBounds": {"min": [round(float(v), 2) for v in walk_lo],
                                     "max": [round(float(v), 2) for v in walk_hi]},
                  "interiorClass": "gauntlet", "parentRegion": theme.region, "serverCells": TILES * 6},
        "coordinateTransform": {"metresPerTile": 1.0, "serverOrigin": origin, "origin": [0.0, 0.0, 0.0],
                                "walkingHeight": 0.0, "invertServerY": True},
        "spawnPoints": [{"id": "default", "position": arrival, "rotationDegrees": 0, "surface": "Walk"},
                        {"id": "vault", "position": vault_spot, "rotationDegrees": 180, "surface": "Walk"}],
        "collision": dict(collision_stats, nodeNames=[n for n in stats["nodeNames"] if not n.startswith("Walk_")]),
        "cutaway": {"hideNodes": [n for n in stats["nodeNames"] if n.startswith("Roof_")],
                    "reason": "interior lids; the isometric rig frames the floor, not the roof"},
        "navigation": {"surfaceNodePrefixes": ["Walk_"], "agentRadius": 0.4, "agentHeight": 1.9,
                       "maxSlopeDegrees": 45, "navmesh": {"format": "surface-prefix-v1", "polygons": []}},
        "portals": [],
        "landmarks": it.landmarks,
        "interactives": it.interactives,
        "npcMarkers": [],
        "harvestables": it.harvestables,
        "environment": dict(it.environment, openToSky=list(it.spaces) if theme.props.get("openCanyon") else [],
                            lights=[{"id": f"lamp-{i:03d}", "kind": "point", "position": p,
                                     "color": [1.0, 0.66, 0.32], "range": 14.0, "energy": 3.2,
                                     "attenuation": 1.2} for i, p in enumerate(it.lamps)] + getattr(it, "accent_lights", [])),
        "spaces": {k: {kk: round(float(vv), 2) for kk, vv in v.items()} for k, v in it.spaces.items()},
        "gauntlet": gauntlet,
        "performance": stats,
        "sources": [{"id": "generator", "file": "_toolkit/gauntlets/build.py", "role": "reproducible-build",
                     "design": "_toolkit/gauntlets/designs.py"}],
        "provenance": {"geometry": "authored with the gauntlet rooms over the shared toolkit",
                       "license": "CC-BY-4.0"},
        "productionStatus": "authored-geometry-materials-population",
        "notes": [f"{theme.name}: a linear instanced route of {len(legs)} legs under {theme.region}; the server "
                  "runs it as an instance and opens each gate when the leg before it is quiet."],
    }
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return doc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("region")
    ap.add_argument("--out", default=None)
    ap.add_argument("--server-collision", type=Path, default=None,
                    help="override the exported server grid for an isolated verification build")
    ap.add_argument("--seed", type=int, default=20260906)
    args = ap.parse_args()
    theme = D.theme(args.region)
    out = Path(args.out) if args.out else ROOT / "interiors" / theme.id
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    sets = preview.texture_sets()
    if theme.props.get("materialSet") == "crownwater":
        from amberwood import crownmaterials
        crownmaterials.register(sets)
    if theme.props.get("materialSet") == "sunmane_canyon":
        from amberwood import canyoncraft
        canyoncraft.register(sets)
    it, legs, staging, vault = compose(theme, args.seed)
    sections = [(theme.id, it.group)]
    if theme.props.get("localBatches", theme.props.get("kit") == "forest_haul"):
        from amberwood.spatial import sections as local_sections
        sections = local_sections(it.group, theme.id)
    stats = SB.export_glb(sections, sets, out / "world.glb", theme.id)
    payload, collision_stats = SB.build_collision(
        it.group, keep_open=[entry["position"] for entry in it.interactives + it.harvestables if "position" in entry],
        non_blocking_materials=theme.props.get("nonBlockingMaterials", ()))
    (out / "collision.bin").write_bytes(payload)
    doc = write_manifest(theme, it, legs, staging, vault, stats, collision_stats, out / "world.json")
    report = validate_gltf.validate(str(out / "world.glb"))
    (out / "world.glb.validator.json").write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
    errors = report.to_dict()["issues"]["numErrors"]
    # The server reads this grid: each tile the block of half-metre cells round
    # its centre (blocked if any is), heights in the server's 0.2 m steps. The
    # stride export it replaced let a tile reach half a metre into the wall
    # beside it and, passing the package's 0.1 m codes through, doubled every
    # riser so no stair could be climbed.
    collision_out = args.server_collision or (ROOT / "server-collision" / f"{theme.id}.bin")
    grid = EXPORT.export(out, collision_out, TILES, "footprint", heights="server")
    dropped = prune_spawns(out / "world.json", grid)
    blocked = []
    g = doc["gauntlet"]
    checks = [("arrival", g["staging"]["arrivalTile"]), ("vault", g["vault"]["spotTile"])]
    for leg in g["legs"]:
        checks.append((f"{leg['id']} gate before", leg["gate"]["tile"]))
        checks.append((f"{leg['id']} gate beyond", leg["gate"]["beyondTile"]))
        for branch in leg.get("branches", []):
            checks.append((f"{branch['id']} gate before", branch["gate"]["tile"]))
            checks.append((f"{branch['id']} gate beyond", branch["gate"]["beyondTile"]))
    for label, (tx, ty) in checks:
        if not (0 <= tx < grid.shape[1] and 0 <= ty < grid.shape[0]) or not grid[ty, tx]:
            blocked.append(label)
    span = doc["asset"]["bounds"]
    print(f"[{theme.id}] {len(legs)} legs, {stats['uniqueTriangles']} tris, {stats['glbBytes'] / 1e6:.2f} MB, "
          f"{collision_stats['walkableCells']} walkable cells, route {span['max'][2] - span['min'][2]:.0f} m, "
          f"glTF {'ok' if errors == 0 else 'ERRORS'} ({time.time() - t0:.1f}s)")
    if blocked:
        print(f"[{theme.id}] BLOCKED: {blocked}")
    return 0 if errors == 0 and not blocked else 1


if __name__ == "__main__":
    sys.exit(main())
