"""retarget_underground.py: follow a partition change at the interior doors without rebuilding the interiors.

  python -B eloria-assets/maps/continent-v2/_continent_v2/retarget_underground.py [--check] [--server <checkout>]

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
  * objects.json holds a record per passage end (pass 2): {passage: true, height 3.6, radius 1.6, label: the section
    the end leads into}, so the client gives the way on a full-height pick and no stand-in model; and a record per
    building door: {entrance: true, building: true, exteriorTile, label, exitLabel, category?, height 3.0, radius
    1.2}, no `scene` (the door is painted on the facade; export_collision.py stands no art for it). The same id serves
    the door's interior exit. Records of passage ends and building doors that no source has any longer are dropped;
    a record another source owns is never touched;
  * each package's provenance.sourceSha256 becomes its source's hash. Nothing else in a package changes, and its
    builder hash must still be the builder its provenance names (the source's builder in underground.SOURCES).
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


def retarget(checkout: Path, server=None):
    outputs, changed, unbuilt = {}, 0, []
    grids = Grids(checkout, server)
    objects_path = checkout / "godot-client/data/world/objects.json"
    objects = json.loads(objects_path.read_bytes())
    authored = objects["authoredObjects"]
    all_doors, all_ends, buildings = {}, {}, {}
    for spec in U.SOURCES:
        path = source_path(spec)
        if not path.is_file():
            continue
        reader = U.reader_of(spec)
        text = path.read_text(encoding="utf-8")
        design = json.loads(text)
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
        for object_id in [*doors, *ends]:
            if object_id in all_doors or object_id in all_ends:
                raise SystemExit(f"{spec.source}: object id {object_id} is another interior's too")
        all_doors.update({oid: (door, owner[oid]) for oid, door in doors.items()})
        all_ends.update({oid: (end, names[end["to"]]) for oid, end in ends.items()})   # the record: where it leads
        package_path = checkout / "eloria-assets/maps/continent-v2" / design["map"]["id"] / "client/world.json"
        if not package_path.is_file():
            unbuilt.append(design["map"]["id"])
            continue
        raw = package_path.read_bytes()
        package = json.loads(raw)
        provenance = package.get("provenance", {})
        builder = HERE / Path(str(provenance.get("builder", ""))).name
        if builder.name != spec.builder:
            raise SystemExit(f"the {design['map']['id']} package was built by another builder than {spec.builder}; "
                             "refusing to retarget it")
        if not builder.is_file() or provenance.get("builderSha256") != sha(builder.read_bytes()):
            raise SystemExit(f"{spec.builder} changed since the {design['map']['id']} build: rebuild it with "
                             f"{spec.builder}; retargeting cannot")
        for name, digest in (provenance.get("imports") or {}).items():
            helper = HERE / Path(name).name
            if not helper.is_file() or sha(helper.read_bytes()) != digest:
                raise SystemExit(f"{helper.name}, which {spec.builder} imports, changed since the {design['map']['id']} "
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
            raise SystemExit(f"the {design['map']['id']} package's rooms are not the source's roomNames (its music "
                             f"spaces are keyed by them): rebuild it with {spec.builder}")
        for key in ("portals", "interactives"):
            for item in package.get(key, []):
                if item.get("objectId") in exits and "label" in item:
                    item["label"] = exits[item["objectId"]]
        package["provenance"]["sourceSha256"] = sha(source)
        indent = 1 if raw.startswith(b'{\n "') else (2 if raw.startswith(b'{\n  "') else None)
        outputs[package_path] = (json.dumps(package, indent=indent, ensure_ascii=False)
                                 + ("\n" if raw.endswith(b"\n") else "")).encode("utf-8")
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
    # a building door stands no model: the door is the facade's, picked by the record (map_object_3d.gd); one id
    # serves both ends, so the record also carries the label of the way out
    for key in [k for k, record in authored.items() if record.get("building") and int(k) not in buildings]:
        del authored[key]
    for object_id, door in sorted(buildings.items()):
        record = authored.get(str(object_id))
        if record is not None and not record.get("building"):
            raise SystemExit(f"objects.json {object_id} already holds another object's record")
        authored[str(object_id)] = {"entrance": True, "building": True, "exteriorTile": list(door["tile"]),
                                    "label": door["label"], "exitLabel": door["exitLabel"],
                                    **({"category": door["category"]} if door.get("category") else {}),
                                    **BUILDING_DOOR}
    # a passage end stands no model: the way on is the builder's mouth, picked at full height (map_object_3d.gd)
    for key in [k for k, record in authored.items() if record.get("passage") and int(k) not in all_ends]:
        del authored[key]
    for object_id, (end, label) in sorted(all_ends.items()):
        record = authored.get(str(object_id))
        if record is not None and not record.get("passage"):
            raise SystemExit(f"objects.json {object_id} already holds another object's record")
        authored[str(object_id)] = {"passage": True, **PASSAGE, "label": label}
    objects_raw = (json.dumps(objects, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    outputs[objects_path] = objects_raw
    return outputs, changed, unbuilt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--checkout", type=Path, default=F.DEFAULT_CHECKOUT)
    parser.add_argument("--server", type=Path, default=os.environ.get("ELORIA_SERVER_ROOT"),
                        help="the server checkout whose served-grid codec reads the exterior grids (building doors)")
    args = parser.parse_args()
    outputs, changed, unbuilt = retarget(args.checkout.resolve(), args.server)
    stale = [str(p) for p, raw in outputs.items() if not p.is_file() or p.read_bytes() != raw]
    if args.check:
        print(json.dumps({"stale": stale, "unbuilt": unbuilt}, indent=1))
        return 1 if stale else 0
    for path, raw in outputs.items():
        if not path.is_file() or path.read_bytes() != raw:
            path.write_bytes(raw)
    print(json.dumps({"written": stale, "exitsRetargeted": changed, "unbuilt": unbuilt}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
