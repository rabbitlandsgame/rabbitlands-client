"""retarget_underground.py: follow a partition change at the interior doors without rebuilding the interiors.

  python -B eloria-assets/maps/continent-v2/_continent_v2/retarget_underground.py [--check] [--server <checkout>] \
         [--map <interior map id>]

The interior sources are underground.py SOURCES: content/underground.json (the caves, landfall_insides, built by
build_underground.py) and content/landfall_town.json (the town's rooms, landfall_town, built by
build_town_interiors.py). A source that is absent is skipped, and so is a source whose package is not built yet (its
objects.json records are still written; it is listed under "unbuilt"). build_underground.py is retired (procedural
generators were archived on 2026-10-16; the owner re-enables a rebuild per run), but each interior's package must still
name its exits' exterior map and tile, and underground.py refuses a package whose recorded source hash is not its
source's. A partition change (a map renamed or its server frame grown) moves only the door ends, so this tool rewrites
only those:
  * every cave door's entrance tile (a section's old single `entrance`, or each of its `entrances`;
    underground_source.py) is its marker position read in the exterior map's current frame (frames.py); the return
    tile keeps its offset from the entrance. Each door is rewritten on its own line, found by its marker;
  * a building door (kind "building", content/landfall_town.json) has no scene marker: its tile and return tile are
    the source's, and are checked against the exterior map's served grid (--server, or ELORIA_SERVER_ROOT, names the
    server checkout whose codec reads it): both walkable, reached from the map's arrival by the server's step rule,
    with four walkable neighbours, and apart; its painted point (`position`) lies within underground.DOOR_REACH tiles
    of its tile. A door that fails is refused, never moved;
  * the interior package's exit portals and interactives with that door's object id name the entrance's map and the
    new return tile;
  * a section renamed in the source renames only labels: its spawn point and chambers, its exits' "Leave <name>" (a
    building door's exit is labelled by its `exitLabel`), the passage portals into it ("On into <name>") and its
    entrance art's label in objects.json (ids, geometry and collision keep the built section's);
  * objects.json holds a record per passage end (pass 2): {passage: true, height 3.6, radius 1.6, label: the end's
    own `label` (the town's stairs: "Upstairs: the guest rooms", as the package and the server name it), else the
    section the end leads into (the caves)}, so the client gives the way on a full-height pick, no stand-in model and
    its hover name (map_object_3d.gd destination()); and a record per building door: {entrance: true, building: true,
    exteriorTile, modelOffset, label, exitLabel, exitOffset?, category?, height 3.0, radius 1.2}, no `scene` (the door
    is painted on the facade; export_collision.py stands no art for it). `modelOffset` [dx, 0, dz] is the painted door
    point (`position`) minus the door tile's centre in the exterior map's metres (its frame, frames.py), so the
    client's pick and label stand on the painted door rather than on the step in front of it. The same id serves the
    door's interior exit, whose street door build_town_interiors.py sets in the wall one tile beyond the exit tile,
    the way `exitFacing` points: `exitOffset` [fx, 0, -fy] (tile +y is world -Z) moves that end's pick and label
    into the doorway. A drawn stair's passage record also carries the `modelOffset` build_town_interiors.py writes on
    its portal (the flight's centre minus the end tile's centre), so its pick and label stand on the stair. An interior
    interactive (the town's lore objects and stations, 59251-59299) gets a pick-only record {interactive: true,
    pickOnly: true, label (the source's short `label`, else its text's first clause), modelOffset (the source's `at`,
    the prop's point, minus the tile's centre), height, radius (the source's, else the packaged size of the prop at
    `at`, reused-scenery.json)}: no ring, no stand-in model. Records of passage ends, building doors and interior
    interactives that no source has any longer are dropped; a record another source owns is never touched;
  * each package's provenance.sourceSha256 becomes its source's hash. Nothing else in a package changes, and its
    builder hash must still be the builder its provenance names (the source's builder in underground.SOURCES).
--map <id> retargets one interior only (landfall_insides, the caves; landfall_town, the town): its source, its package
and its doors' and passage ends' records in objects.json. Every other source is still read, for its object ids (a
clash is refused, and its records are never taken for stale), but its source, package and records stay as they are;
a stale record no source owns any longer is listed under "orphans" and left for a run over every interior. Use it
when another interior's package must not be rewritten here (the caves' recorded source hash drifts while their
geometry does not: the publication decides when to rewrite it).
--check writes nothing and exits 1 when any file would change.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

import frames as F
import underground as U
import underground_source as S

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "content/underground.json"
TOWN_SOURCE = HERE / "content/landfall_town.json"
BUILDER = HERE / "build_underground.py"
# A building door's record: the door is painted on the facade, so the pick is a little smaller than a cave mouth's.
BUILDING_DOOR = {"height": 3.0, "radius": 1.2}
PASSAGE = {"height": 3.6, "radius": 1.6}
# An interior interactive's pick (no ring, no model) when its source gives no size and no prop stands at its `at`;
# a prop's pick is its packaged size (reused-scenery.json bounds, scaled), its radius held to INTERACTIVE_RADIUS.
INTERACTIVE_PICK = {"height": 1.8, "radius": 0.8}
INTERACTIVE_RADIUS = (0.4, 1.6)
SCENERY = "eloria-assets/source/world_objects/underground/reused-scenery.json"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def source_path(spec) -> Path:
    return HERE / "content" / Path(spec.source).name


def door_lines(text, design, checkout, default_kind="underground"):
    """The cave doors retargeted on the source text: each door's tile from its marker position in its map's current
    frame, its return tile at the same offset (a door without a `kind` is `default_kind`: the caves' doors are cave
    doors, the town's building doors, which keep their tiles). Returns the new text; `design` is updated to match."""
    lines = text.split("\n")
    for section in design["sections"]:
        listed = section["entrances"] if "entrances" in section else [section["entrance"]] if "entrance" in section else []
        for door in listed:
            if door.get("kind", default_kind) != "underground":
                continue
            frame = F.load_source(door["map"], checkout)
            x, _, z = door["position"]
            tile = list(frame.tile(x, z))
            offset = [door["returnTile"][0] - door["tile"][0], door["returnTile"][1] - door["tile"][1]]
            back = [tile[0] + offset[0], tile[1] + offset[1]]
            # the source is hand-laid-out: rewrite only this door's two arrays on its own line
            found = [i for i, line in enumerate(lines) if f'"marker": "{door["marker"]}"' in line]
            if len(found) != 1:
                raise SystemExit(f"{section['id']}: door {door['marker']} must stand on one line of its own")
            index = found[0]
            for key, old, new in (("tile", door["tile"], tile), ("returnTile", door["returnTile"], back)):
                before = f'"{key}": [{old[0]},{old[1]}]'
                if before not in lines[index]:
                    raise SystemExit(f"{section['id']}: cannot find {before} on its entrance line")
                lines[index] = lines[index].replace(before, f'"{key}": [{new[0]},{new[1]}]', 1)
            door["tile"], door["returnTile"] = tile, back
    return "\n".join(lines)



class Grids:
    """The exterior maps' served grids and their reach from each map's arrival (the server's step rule), read once."""

    def __init__(self, checkout: Path, server):
        self.checkout, self.server, self.maps, self.codec = checkout, server, {}, None

    def __call__(self, region):
        if region not in self.maps:
            import numpy as np
            import export_collision as X
            if self.codec is None:
                if not self.server:
                    raise SystemExit("a building door is checked on its exterior map's served grid: pass --server "
                                     "<server checkout> (or set ELORIA_SERVER_ROOT)")
                self.codec = X.server_codec(self.server)
            package = self.checkout / "eloria-assets/maps/continent-v2" / region / "client"
            grid = self.codec.served_grid.decode_file((package / "served-grid.escg.gz").read_bytes())
            codes = np.frombuffer(grid.codes, dtype=np.uint16).reshape(grid.height, grid.width)
            manifest = json.loads((package / "world.json").read_text(encoding="utf-8"))
            defaults = [p for p in manifest.get("spawnPoints", []) if p.get("default")]
            if len(defaults) != 1:
                raise SystemExit(f"{region}: its package names no single default arrival")
            ax, ay = defaults[0]["serverTile"]
            reached = X.reach_from(X.legal_steps(codes, self.codec.climb_units), codes.shape, [(ay, ax)])
            self.maps[region] = (codes, reached)
        return self.maps[region]


def check_building_door(section, door, grids, checkout):
    """A building door's tile and return tile on its exterior map's served grid; SystemExit names what fails."""
    tag = f"{section['id']} building door {door['object']}"
    codes, reached = grids(door["map"])
    height, width = codes.shape
    tile, back = list(door["tile"]), list(door["returnTile"])
    if tile == back:
        raise SystemExit(f"{tag}: its return tile is its own tile")
    for name, (x, y) in (("tile", tile), ("returnTile", back)):
        if not (1 <= x < width - 1 and 1 <= y < height - 1):
            raise SystemExit(f"{tag}: {name} {[x, y]} lies outside {door['map']}")
        if not codes[y, x]:
            raise SystemExit(f"{tag}: {name} {[x, y]} is not walkable on the {door['map']} served grid")
        if not reached[y, x]:
            raise SystemExit(f"{tag}: {name} {[x, y]} is not reached from {door['map']}'s arrival")
        closed = [[x + dx, y + dy] for dx, dy in U.FOUR if not codes[y + dy, x + dx]]
        if closed:
            raise SystemExit(f"{tag}: {name} {[x, y]} has blocked neighbours {closed}")
    frame = F.load_source(door["map"], checkout)
    px, _, pz = door["position"]
    painted = frame.tile(px, pz)
    if max(abs(painted[0] - tile[0]), abs(painted[1] - tile[1])) > U.DOOR_REACH:
        raise SystemExit(f"{tag}: its painted point {list(painted)} is more than {U.DOOR_REACH} tiles from its tile "
                         f"{tile}")


def _metres(value):
    """A record's offset component: millimetres, and never -0.0."""
    return round(float(value), 3) + 0.0


def door_offset(door, checkout):
    """A building door's `modelOffset` [dx, 0, dz]: its painted point (`position`, exterior metres) minus its tile's
    centre in the exterior map's frame (frames.py, the frame check_building_door reads the tile rule in)."""
    frame = F.load_source(door["map"], checkout)
    cx, cz = frame.local(*door["tile"])
    px, _, pz = door["position"]
    return [_metres(px - cx), 0.0, _metres(pz - cz)]


def exit_offset(door):
    """A building door's `exitOffset` [fx, 0, -fy] at its interior exit: the street door stands in the wall one tile
    beyond the exit tile, the way `exitFacing` points (build_town_interiors.door_geometry; tile +y is world -Z).
    None for a door without an exitFacing."""
    facing = door.get("exitFacing")
    if not facing:
        return None
    return [_metres(facing[0]), 0.0, _metres(-facing[1])]


def building_record(door, checkout):
    """objects.json's record of a building door (both ends: one id serves the street door and the interior exit)."""
    record = {"entrance": True, "building": True, "exteriorTile": list(door["tile"]),
              "modelOffset": door_offset(door, checkout), "label": door["label"], "exitLabel": door["exitLabel"]}
    inside = exit_offset(door)
    if inside is not None:
        record["exitOffset"] = inside
    if door.get("category"):
        record["category"] = door["category"]
    return {**record, **BUILDING_DOOR}


def prop_sizes(checkout):
    """The packaged scenery's sizes {asset: (width, depth, height)} in metres at scale 1 (reused-scenery.json's
    bounds), or {} while it is absent."""
    path = checkout / SCENERY
    if not path.is_file():
        return {}
    sizes = {}
    for asset in json.loads(path.read_text(encoding="utf-8")).get("assets", []):
        (x0, y0, z0), (x1, y1, z1) = asset["bounds"]
        sizes[asset["id"]] = (x1 - x0, z1 - z0, y1 - y0)
    return sizes


def interactive_label(reader, entry):
    """An interior interactive's short name: its reader's interactive_label (town_source), else its `label` or text."""
    module = getattr(reader, "module", reader)
    found = getattr(module, "interactive_label", None)
    return found(entry) if found else entry.get("label") or entry["text"]


def interactive_record(reader, section, entry, sizes):
    """objects.json's pick-only record of an interior interactive: no ring and no stand-in model, a pick shape standing
    on the prop or picture it describes. `modelOffset` [dx, 0, dz] is the source's `at` (the prop's point, tile units)
    minus the tile's centre in metres (tile +y is world -Z); `height` and `radius` are the source's, else the prop's
    standing at `at` (its packaged size, scaled, raised by its `height`), else INTERACTIVE_PICK."""
    tx, ty = entry["tile"]
    at = entry.get("at")
    offset = [0.0, 0.0, 0.0]
    height, radius = INTERACTIVE_PICK["height"], INTERACTIVE_PICK["radius"]
    if at is not None:
        offset = [_metres(at[0] - (tx + .5)), 0.0, _metres(-(at[1] - (ty + .5)))]
        props = [p for p in section.get("props", []) if p["asset"] in sizes
                 and max(abs(p["at"][0] - at[0]), abs(p["at"][1] - at[1])) < .05]
        if props:
            prop = props[0]
            width, depth, tall = sizes[prop["asset"]]
            scale = prop.get("scale", 1)
            height = tall * scale + prop.get("height", 0)
            low, high = INTERACTIVE_RADIUS
            radius = min(high, max(low, max(width, depth) * scale / 2))
    height = entry.get("height", height)
    radius = entry.get("radius", radius)
    return {"interactive": True, "pickOnly": True, "label": interactive_label(reader, entry), "modelOffset": offset,
            "height": round(float(height), 2), "radius": round(float(radius), 2)}


def exit_label(section, door):
    """A door's way out, as its builder labels it: a building door's exitLabel, a cave door's "Leave <section>"."""
    return door.get("exitLabel") or f'Leave {section["name"]}'


def end_label(end, names):
    """A passage end's portal label: its own `label` (the town's stairs), else "On into <the other section>"."""
    return end.get("label") or f'On into {names[end["to"]]}'


def room_spaces(design):
    """The town package's `spaces` keys, as build_town_interiors.py names them: each room's name, a repeat numbered."""
    keys = []
    for section in design["sections"]:
        for name in section.get("roomNames", []):
            key, n = name, 2
            while key in keys:
                key, n = f"{name} {n}", n + 1
            keys.append(key)
    return keys


def retarget(checkout: Path, server=None, only=None, notes=None):
    """The rewritten files {path: bytes} (only those that change are written), the exits retargeted and the interiors
    whose package is not built. `only` (an interior map id, --map) limits the rewrite to that interior; `notes` (a
    dict, when given) receives "orphans": the stale records a run limited by `only` left in place."""
    outputs, changed, unbuilt = {}, 0, []
    grids = Grids(checkout, server)
    objects_path = checkout / "godot-client/data/world/objects.json"
    objects = json.loads(objects_path.read_bytes())
    authored = objects["authoredObjects"]
    all_doors, all_ends, buildings, picks, end_offsets = {}, {}, {}, {}, {}
    sizes = prop_sizes(checkout)
    # every source's ids, read even when --map leaves the source alone: a clash between interiors is refused, and a
    # record another interior owns is never stale
    owners, building_ids, end_ids, interactive_ids, interiors = {}, set(), set(), set(), []
    for spec in U.SOURCES:
        path = source_path(spec)
        if not path.is_file():
            continue
        reader = U.reader_of(spec)
        text = path.read_text(encoding="utf-8")
        design = json.loads(text)
        region = design["map"]["id"]
        interiors.append(region)
        listed = [door for s in design["sections"] for door in reader.doors(s)]
        passage_ends = [end for passage in reader.passages(design) for end in passage["ends"]]
        lore = [(s, entry) for s in design["sections"] for entry in U.section_interactives(reader, s)]
        for object_id in ([door["object"] for door in listed] + [end["object"] for end in passage_ends]
                          + [entry["object"] for _, entry in lore]):
            if object_id in owners:
                raise SystemExit(f"{spec.source}: object id {object_id} is another interior's too")
            owners[object_id] = region
        building_ids.update(door["object"] for door in listed if door.get("kind", spec.kind) == "building")
        end_ids.update(end["object"] for end in passage_ends)
        interactive_ids.update(entry["object"] for _, entry in lore)
        if only is not None and region != only:
            continue
        picks.update({entry["object"]: interactive_record(reader, s, entry, sizes) for s, entry in lore})
        source = door_lines(text, design, checkout, spec.kind).encode("utf-8")
        if json.loads(source) != design:
            raise SystemExit("the textual edit does not match the intended source")
        outputs[path] = source
        doors = {door["object"]: door for s in design["sections"] for door in reader.doors(s)}
        owner = {door["object"]: s for s in design["sections"] for door in reader.doors(s)}
        for object_id, door in doors.items():
            if door.get("kind") == "building":
                check_building_door(owner[object_id], door, grids, checkout)
                buildings[object_id] = door
        names = {s["id"]: s["name"] for s in design["sections"]}
        ends = {end["object"]: end for passage in reader.passages(design) for end in passage["ends"]}
        all_doors.update({oid: (door, owner[oid]) for oid, door in doors.items()})
        # the record's label: the end's own (the town's stairs), else the section it leads into (the caves)
        all_ends.update({oid: (end, end.get("label") or names[end["to"]]) for oid, end in ends.items()})
        package_path = checkout / "eloria-assets/maps/continent-v2" / region / "client/world.json"
        if not package_path.is_file():
            unbuilt.append(region)
            continue
        raw = package_path.read_bytes()
        package = json.loads(raw)
        provenance = package.get("provenance", {})
        builder = HERE / Path(str(provenance.get("builder", ""))).name
        if builder.name != spec.builder:
            raise SystemExit(f"the {region} package was built by another builder than {spec.builder}; "
                             "refusing to retarget it")
        if not builder.is_file() or provenance.get("builderSha256") != sha(builder.read_bytes()):
            raise SystemExit(f"{spec.builder} changed since the {region} build: rebuild it with "
                             f"{spec.builder}; retargeting cannot")
        for name, digest in (provenance.get("imports") or {}).items():
            helper = HERE / Path(name).name
            if not helper.is_file() or sha(helper.read_bytes()) != digest:
                raise SystemExit(f"{helper.name}, which {spec.builder} imports, changed since the {region} "
                                 f"build: rebuild it with {spec.builder}; retargeting cannot")
        for key in ("portals", "interactives"):
            for item in package.get(key, []):
                door = doors.get(item.get("objectId"))
                if door is None or "destinationMap" not in item:
                    continue
                if item["destinationMap"] != door["map"] or item["destinationTile"] != door["returnTile"]:
                    item["destinationMap"], item["destinationTile"] = door["map"], list(door["returnTile"])
                    changed += 1
        # names are labels only: the builder wrote each section's name on these records (build_underground.build;
        # build_town_interiors.build names a chamber <section>-<room> after its room, roomNames)
        exits = {oid: exit_label(owner[oid], door) for oid, door in doors.items()}
        exits.update({oid: end_label(end, names) for oid, end in ends.items()})
        rooms = {s["id"]: s.get("roomNames") for s in design["sections"]}
        for item in package.get("spawnPoints", []):
            if item.get("section") in names:
                item["name"] = names[item["section"]]
        for item in package.get("chambers", []):
            if item.get("section") not in names:
                continue
            if rooms[item["section"]] is None:
                item["name"] = names[item["section"]]
            else:
                item["name"] = rooms[item["section"]][int(str(item["id"]).rsplit("-", 1)[1])]
        if "spaces" in package and sorted(package["spaces"]) != sorted(room_spaces(design)):
            raise SystemExit(f"the {region} package's rooms are not the source's roomNames (its music "
                             f"spaces are keyed by them): rebuild it with {spec.builder}")
        for key in ("portals", "interactives"):
            for item in package.get(key, []):
                if item.get("objectId") in exits and "label" in item:
                    item["label"] = exits[item["objectId"]]
        # a drawn stair's pick stands on the flight (build_town_interiors.py writes the stair's offset from its end
        # tile on the passage portal)
        end_offsets.update({item["objectId"]: item["modelOffset"] for item in package.get("portals", [])
                            if item.get("objectId") in ends and "modelOffset" in item})
        package["provenance"]["sourceSha256"] = sha(source)
        indent = 1 if raw.startswith(b'{\n "') else (2 if raw.startswith(b'{\n  "') else None)
        outputs[package_path] = (json.dumps(package, indent=indent, ensure_ascii=False)
                                 + ("\n" if raw.endswith(b"\n") else "")).encode("utf-8")
    if only is not None and only not in interiors:
        raise SystemExit(f"--map {only}: no interior source authors it (the interiors: {', '.join(interiors)})")
    # the client's entrance art stands on each cave door's exterior tile (export_collision.py reads it there)
    for object_id, (door, section) in all_doors.items():
        record = authored.get(str(object_id))
        if door.get("kind") == "building":
            continue
        if record is not None and record.get("entrance"):
            if record.get("building"):
                raise SystemExit(f"objects.json {object_id} is a building door's record; the cave door {object_id} "
                                 "cannot share it")
            record["exteriorTile"] = list(door["tile"])
            record["label"] = section["name"]
    # stale records: a building door's or a passage end's that no source has any longer. A run over every interior
    # drops them; a --map run drops only those whose id its own interior now uses otherwise, and lists the rest
    stale = [key for key, record in authored.items()
             if (record.get("building") and int(key) not in building_ids)
             or (record.get("passage") and int(key) not in end_ids)
             or (record.get("pickOnly") and record.get("interactive") and int(key) not in interactive_ids)]
    kept = [key for key in stale if only is not None and owners.get(int(key)) != only]
    for key in stale:
        if key not in kept:
            del authored[key]
    if notes is not None:
        notes["orphans"] = sorted(kept, key=int)
    # a building door stands no model: the door is the facade's, picked by the record (map_object_3d.gd) where the
    # record's modelOffset puts the painted door; one id serves both ends, so the record also carries the way out
    for object_id, door in sorted(buildings.items()):
        record = authored.get(str(object_id))
        if record is not None and not record.get("building"):
            raise SystemExit(f"objects.json {object_id} already holds another object's record")
        authored[str(object_id)] = building_record(door, checkout)
    # a passage end stands no model: the way on is the builder's mouth, picked at full height (map_object_3d.gd)
    for object_id, (end, label) in sorted(all_ends.items()):
        record = authored.get(str(object_id))
        if record is not None and not record.get("passage"):
            raise SystemExit(f"objects.json {object_id} already holds another object's record")
        authored[str(object_id)] = {"passage": True, **PASSAGE, "label": label}
        if object_id in end_offsets:
            authored[str(object_id)]["modelOffset"] = [_metres(v) for v in end_offsets[object_id]]
    # an interior interactive stands no model and draws no ring: the pick-only record puts its click shape and hover
    # label on the prop or picture it describes (map_object_3d.gd)
    for object_id, pick in sorted(picks.items()):
        record = authored.get(str(object_id))
        if record is not None and not (record.get("pickOnly") and record.get("interactive")):
            raise SystemExit(f"objects.json {object_id} already holds another object's record")
        authored[str(object_id)] = pick
    objects_raw = (json.dumps(objects, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    outputs[objects_path] = objects_raw
    return outputs, changed, unbuilt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--checkout", type=Path, default=F.DEFAULT_CHECKOUT)
    parser.add_argument("--server", type=Path, default=os.environ.get("ELORIA_SERVER_ROOT"),
                        help="the server checkout whose served-grid codec reads the exterior grids (building doors)")
    parser.add_argument("--map", dest="only", metavar="MAP_ID",
                        help="retarget this interior only (its source, package and objects.json records); every "
                             "other source is read for its ids and left as it is")
    args = parser.parse_args()
    notes = {}
    outputs, changed, unbuilt = retarget(args.checkout.resolve(), args.server, args.only, notes)
    stale = [str(p) for p, raw in outputs.items() if not p.is_file() or p.read_bytes() != raw]
    extra = {"orphans": notes["orphans"]} if notes.get("orphans") else {}
    if args.check:
        print(json.dumps({"stale": stale, "unbuilt": unbuilt, **extra}, indent=1))
        return 1 if stale else 0
    for path, raw in outputs.items():
        if not path.is_file() or path.read_bytes() != raw:
            path.write_bytes(raw)
    print(json.dumps({"written": stale, "exitsRetargeted": changed, "unbuilt": unbuilt, **extra}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
