"""retarget_underground.py: follow a partition change at the underground doors without rebuilding the interior.

  python -B eloria-assets/maps/continent-v2/_continent_v2/retarget_underground.py [--check]

build_underground.py is retired (procedural generators were archived on 2026-10-16), but the shared interior's
package must still name its exits' exterior map and tile, and underground.py refuses a package whose recorded source
hash is not content/underground.json's. A partition change (a map renamed or its server frame grown) moves only the
door ends, so this tool rewrites only those:
  * every door's entrance tile (a section's old single `entrance`, or each of its `entrances`; underground_source.py)
    is its marker position read in the exterior map's current frame (frames.py); the return tile keeps its offset
    from the entrance. Each door is rewritten on its own line, found by its marker;
  * the interior package's exit portals and interactives with that door's object id name the entrance's map and the
    new return tile;
  * a section renamed in the source renames only labels: its spawn point and chambers, its exits' "Leave <name>",
    the passage portals into it ("On into <name>") and its entrance art's label in objects.json (ids, geometry and
    collision keep the built section's);
  * objects.json holds a record per passage end (pass 2): {passage: true, height 3.6, radius 1.6, label: the section
    the end leads into}, so the client gives the way on a full-height pick and no stand-in model; records of passage
    ends the source no longer has are dropped;
  * the package's provenance.sourceSha256 becomes the new source's hash. Nothing else in the package changes, and the
    builder hash must still be the retired builder's.
--check writes nothing and exits 1 when either file would change.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import frames as F
import underground_source as S

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "content/underground.json"
BUILDER = HERE / "build_underground.py"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def retarget(checkout: Path):
    text = SOURCE.read_text(encoding="utf-8")
    design = json.loads(text)
    lines = text.split("\n")
    for section in design["sections"]:
        listed = section["entrances"] if "entrances" in section else [section["entrance"]] if "entrance" in section else []
        for door in listed:
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
    source = "\n".join(lines).encode("utf-8")
    if json.loads(source) != design:
        raise SystemExit("the textual edit does not match the intended source")
    package_path = checkout / "eloria-assets/maps/continent-v2" / design["map"]["id"] / "client/world.json"
    raw = package_path.read_bytes()
    package = json.loads(raw)
    if package["provenance"]["builderSha256"] != sha(BUILDER.read_bytes()):
        raise SystemExit("the interior package was built by another builder; refusing to retarget it")
    doors = {door["object"]: door for s in design["sections"] for door in S.doors(s)}
    owner = {door["object"]: s for s in design["sections"] for door in S.doors(s)}
    changed = 0
    for key in ("portals", "interactives"):
        for item in package.get(key, []):
            door = doors.get(item.get("objectId"))
            if door is None or "destinationMap" not in item:
                continue
            if item["destinationMap"] != door["map"] or item["destinationTile"] != door["returnTile"]:
                item["destinationMap"], item["destinationTile"] = door["map"], list(door["returnTile"])
                changed += 1
    # names are labels only: the builder wrote each section's name on these records (build_underground.build)
    names = {s["id"]: s["name"] for s in design["sections"]}
    exits = {oid: f'Leave {s["name"]}' for oid, s in owner.items()}
    ends = {end["object"]: end for passage in S.passages(design) for end in passage["ends"]}
    exits.update({oid: f'On into {names[end["to"]]}' for oid, end in ends.items()})
    for key in ("spawnPoints", "chambers"):
        for item in package.get(key, []):
            if item.get("section") in names:
                item["name"] = names[item["section"]]
    for key in ("portals", "interactives"):
        for item in package.get(key, []):
            if item.get("objectId") in exits and "label" in item:
                item["label"] = exits[item["objectId"]]
    package["provenance"]["sourceSha256"] = sha(source)
    indent = 1 if raw.startswith(b'{\n "') else (2 if raw.startswith(b'{\n  "') else None)
    out = (json.dumps(package, indent=indent, ensure_ascii=False) + ("\n" if raw.endswith(b"\n") else "")).encode("utf-8")
    # the client's entrance art stands on each door's exterior tile (export_collision.py reads it there)
    objects_path = checkout / "godot-client/data/world/objects.json"
    objects = json.loads(objects_path.read_bytes())
    for object_id, door in doors.items():
        record = objects["authoredObjects"].get(str(object_id))
        if record is not None and record.get("entrance"):
            record["exteriorTile"] = list(door["tile"])
            record["label"] = owner[object_id]["name"]
    # a passage end stands no model: the way on is the builder's mouth, picked at full height (map_object_3d.gd)
    authored = objects["authoredObjects"]
    for key in [k for k, record in authored.items() if record.get("passage") and int(k) not in ends]:
        del authored[key]
    for object_id, end in sorted(ends.items()):
        authored[str(object_id)] = {"passage": True, "height": 3.6, "radius": 1.6, "label": names[end["to"]]}
    objects_raw = (json.dumps(objects, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    return {SOURCE: source, package_path: out, objects_path: objects_raw}, changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--checkout", type=Path, default=F.DEFAULT_CHECKOUT)
    args = parser.parse_args()
    outputs, changed = retarget(args.checkout)
    stale = [str(p) for p, raw in outputs.items() if not p.is_file() or p.read_bytes() != raw]
    if args.check:
        print(json.dumps({"stale": stale}, indent=1))
        return 1 if stale else 0
    for path, raw in outputs.items():
        if not path.is_file() or path.read_bytes() != raw:
            path.write_bytes(raw)
    print(json.dumps({"written": stale, "exitsRetargeted": changed}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
