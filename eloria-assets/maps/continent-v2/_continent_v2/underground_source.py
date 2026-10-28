"""underground_source.py: the ways into content/underground.json's sections, and its wall veins (pass 2, 2026-10-21).

Every reader of the underground source goes through these functions, so the old single-door form and the forms pass 2
adds read the same everywhere: build_underground.py (geometry, walk grid, manifest), underground.py (the publication
rules), retarget_underground.py, publish_cartography.py, tools/prepare_underground_scenery.py, the tests and the
review launcher. Pure JSON logic: no geometry, no third-party imports.

DOORS (a section's ways out to the overworld)
  "entrances": [{map, marker, object, tile, position, returnTile, arrival, exit, exitFacing?}, ...]
      Each door is a portal pair: the exterior object on `map` at `tile` (its marker `marker` must be in that map's bake
      as a runtime point with role underground_entrance, objectId and section) lands on the door's interior `arrival`;
      the same object id standing on the interior `exit` tile leads back to `returnTile` outside. `exitFacing` [dx, dy]
      is the wall the way out is set into (default [0, -1]). Write each door on ONE line: retarget_underground.py
      rewrites tile and returnTile by text, finding the line by its marker.
  The old form stays readable as one door: a single "entrance" {map, marker, object, tile, position, returnTile} with
  the section's own "arrival", "exit" and optional "exitFacing". A section has one form or the other, never both, and
  may have no door at all when a passage reaches it (a chain's deeper level).
  A door's optional `kind` is "underground" (the default: a cave mouth with its scene marker) or "building" (2026-10-27,
  content/landfall_town.json: a door painted on a building's facade; it has no `marker`, its `tile` and `returnTile`
  are the source's, and it carries `label`, `exitLabel` and an optional map `category`; underground.py checks them).

PASSAGES (the source's top-level list; same-map portal pairs between two sections)
  "passages": [{object, name?, art, ends: [{section, tile, arrival, facing?, object?, art?}, {...}]}, ...]
      Using the object standing on end i's `tile` takes the player to the OTHER end's `arrival`, on the same map.
      Every end is its own server object (interactives are keyed by map and object id): end i's id is its own
      `object`, else the passage's `object` + i (so a passage takes two consecutive ids by default). `art` (the
      passage's, or an end's own) is the mouth the builder draws at that end: 'stairs' (steps down into the dark),
      'crawl' (a low hole at the foot of the wall) or 'flooded' (the way goes on under water). `facing` [dx, dy]
      points from the end's tile into its mouth; by default it is the direction to the nearest rock face. `name` is
      only for people reading the source. Sections stay separate walk components: the passage is the only way across.

VEINS (a section's ore set into the rock face)
  "veins": [{resource, nodes: [object id, ...]}, ...]
      Names nodes already in the section's `nodes` (same resource) that are wall nodes: the node tile is the first
      rock tile behind the walkable edge (blocked, with a reached 4-neighbour, the server's 2-tile harvest reach is
      met from the floor tile in front). The builder keeps wall rocks off them (`veinClearance`, default 1.6 tiles)
      and refuses one whose tile stands farther than VEIN_FACE_MAX from its rock face; the packager presents them with
      their resource's wall seam art set into the face (`placement: wall`). underground_authoring.vein() picks the
      tiles for a new vein.

ARRIVALS: a section's arrivals are its doors' arrivals, then the arrivals of the passage ends in it. The first is the
section's primary arrival (its spawn point, the server metadata's `arrival`, the stranded-pocket check's start); every
arrival is a safe entry: encounters keep leash + 20 tiles from each of them.
"""
from __future__ import annotations

import copy
import json

DOOR_KEYS = ("map", "marker", "object", "tile", "position", "returnTile")
DOOR_KINDS = ("underground", "building")
# A building door (kind "building", town_source.py reads the town's) has no scene marker.
BUILDING_DOOR_KEYS = tuple(key for key in DOOR_KEYS if key != "marker")
MOUTH_ARTS = ("stairs", "crawl", "flooded")


class SourceError(ValueError):
    """The underground source names a way in or a vein this format cannot read."""


def doors(section):
    """The section's doors as dicts {map, marker, object, tile, position, returnTile, arrival, exit, exitFacing?,
    index}: its `entrances`, or its old single `entrance` with the section's arrival and exit; [] for none."""
    sid = section.get("id", "?")
    if "entrances" in section:
        if "entrance" in section:
            raise SourceError(f"{sid}: give `entrances` or the old `entrance`, not both")
        result = []
        for index, door in enumerate(section["entrances"]):
            kind = door.get("kind", "underground")
            if kind not in DOOR_KINDS:
                raise SourceError(f"{sid}: entrance {index} kind {kind!r} is not one of {DOOR_KINDS}")
            keys = DOOR_KEYS if kind == "underground" else BUILDING_DOOR_KEYS
            missing = [k for k in (*keys, "arrival", "exit") if k not in door]
            if missing:
                raise SourceError(f"{sid}: entrance {index} lacks {missing}")
            result.append({**copy.deepcopy(door), "index": index})
        return result
    if "entrance" in section:
        door = {**copy.deepcopy(section["entrance"]), "arrival": list(section["arrival"]),
                "exit": list(section["exit"]), "index": 0}
        if "exitFacing" in section:
            door["exitFacing"] = list(section["exitFacing"])
        return [door]
    return []


def passages(design):
    """The source's passages, each {object, name, art, ends: [end, end], index} where an end is {section, tile,
    arrival, facing (or None), object, art, passage (its passage's index), end (0 or 1), to (the other end's
    section)}."""
    result = []
    for index, passage in enumerate(design.get("passages", [])):
        ends = passage.get("ends", [])
        if len(ends) != 2:
            raise SourceError(f"passage {index}: give exactly two ends")
        art = passage.get("art", "stairs")
        normal = []
        for end_index, end in enumerate(ends):
            for key in ("section", "tile", "arrival"):
                if key not in end:
                    raise SourceError(f"passage {index} end {end_index} lacks {key}")
            object_id = end.get("object", passage.get("object", 0) + end_index if "object" in passage else None)
            if not isinstance(object_id, int) or object_id <= 0:
                raise SourceError(f"passage {index} end {end_index}: no object id (give the passage's `object`)")
            mouth = end.get("art", art)
            if mouth not in MOUTH_ARTS:
                raise SourceError(f"passage {index} end {end_index}: art {mouth!r} is not one of {MOUTH_ARTS}")
            normal.append({"section": end["section"], "tile": list(end["tile"]), "arrival": list(end["arrival"]),
                           "facing": list(end["facing"]) if "facing" in end else None, "object": object_id,
                           "art": mouth, "passage": index, "end": end_index})
        if normal[0]["section"] == normal[1]["section"]:
            raise SourceError(f"passage {index}: its ends must be in two different sections")
        normal[0]["to"], normal[1]["to"] = normal[1]["section"], normal[0]["section"]
        result.append({"object": passage.get("object"), "name": passage.get("name", ""), "art": art,
                       "ends": normal, "index": index})
    return result


def passage_ends(design, section_id):
    """The passage ends standing in one section, in passage order."""
    return [end for passage in passages(design) for end in passage["ends"] if end["section"] == section_id]


def arrivals(design, section):
    """Every arrival of a section as (kind, label, [x, y]): its doors' (kind 'door'), then its passage ends'
    (kind 'passage'); the first is the primary arrival."""
    result = [("door", f"door{door['index']}", list(door["arrival"])) for door in doors(section)]
    result += [("passage", f"passage{end['passage']}", list(end["arrival"]))
               for end in passage_ends(design, section["id"])]
    return result


def primary_arrival(design, section):
    """The section's primary arrival [x, y] (its first door's, else its first passage end's)."""
    found = arrivals(design, section)
    if not found:
        raise SourceError(f"{section.get('id', '?')}: no door and no passage end: nothing reaches it")
    return list(found[0][2])


def primary_exit(design, section):
    """The tile of the section's first way out: its first door's exit, else its first passage end's tile."""
    found = doors(section)
    if found:
        return list(found[0]["exit"])
    ends = passage_ends(design, section["id"])
    if not ends:
        raise SourceError(f"{section.get('id', '?')}: no door and no passage end")
    return list(ends[0]["tile"])


def veins(section):
    """The section's veins [{resource, nodes: [object id, ...]}], checked against its nodes."""
    nodes = {oid: res for oid, res, _x, _y in section.get("nodes", [])}
    result, seen = [], set()
    for index, vein in enumerate(section.get("veins", [])):
        ids = list(vein.get("nodes", []))
        if not ids or "resource" not in vein:
            raise SourceError(f"{section.get('id', '?')}: vein {index} needs a resource and its node ids")
        for oid in ids:
            if nodes.get(oid) != vein["resource"]:
                raise SourceError(f"{section.get('id', '?')}: vein {index} names node {oid}, which is not one of the "
                                  f"section's {vein['resource']} nodes")
            if oid in seen:
                raise SourceError(f"{section.get('id', '?')}: node {oid} is in two veins")
            seen.add(oid)
        result.append({"resource": vein["resource"], "nodes": ids})
    return result


def wall_nodes(section):
    """The object ids of the section's vein (wall) nodes."""
    return {oid for vein in veins(section) for oid in vein["nodes"]}


def object_ids(design):
    """Every object id the source uses: (kind, id) for doors, passage ends and nodes, in source order."""
    result = []
    for section in design["sections"]:
        result += [("door", door["object"]) for door in doors(section)]
        result += [("node", oid) for oid, *_ in section.get("nodes", [])]
    result += [("passage", end["object"]) for passage in passages(design) for end in passage["ends"]]
    return result


def compact(value):
    """JSON on one line with ', ' between dict items and ',' inside arrays, as the source is laid out."""
    if isinstance(value, dict):
        return "{" + ", ".join(f"{json.dumps(k)}: {compact(v)}" for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ",".join(compact(v) for v in value) + "]"
    return json.dumps(value, ensure_ascii=False)


def _section_lines(section):
    keys = [k for k in section if not k.startswith("_")]
    head = [k for k in ("id", "name", "style", "danger") if k in section]
    lines = [", ".join(f"{json.dumps(k)}: {json.dumps(section[k], ensure_ascii=False)}" for k in head)]
    done = set(head)
    for key in keys:
        if key in done or key == "exit":
            continue
        if key == "arrival":
            lines.append(f'"arrival": {compact(section["arrival"])}, "exit": {compact(section["exit"])}')
            done |= {"arrival", "exit"}
        elif key in ("props", "entrances"):
            body = ",\n".join("        " + compact(item) for item in section[key])
            lines.append(f'"{key}": [\n' + body + "\n      ]")
        else:
            lines.append(f"{json.dumps(key)}: {compact(section[key])}")
        done.add(key)
    return "    {\n" + ",\n".join("      " + line for line in lines) + "\n    }"


def dump(design):
    """content/underground.json in its hand-laid-out style: one section key per line, one prop and one door per line
    (retarget_underground.py finds a door by its marker's line), one passage per line; keys starting with `_` (the
    builder's annotations) are left out. Write the result as bytes (LF)."""
    head = f'{{\n  "schema": {json.dumps(design["schema"])},\n  "map": {compact(design["map"])},\n  "sections": [\n'
    text = head + ",\n".join(_section_lines(s) for s in design["sections"]) + "\n  ]"
    if design.get("passages"):
        text += ',\n  "passages": [\n' + ",\n".join("    " + compact(p) for p in design["passages"]) + "\n  ]"
    return text + "\n}\n"


def check(design):
    """Structural checks of the ways in and the veins (no geometry): every passage end names a section, every section
    is reached by a door or a passage, door, passage and node ids are unique. Raises SourceError."""
    ids = [s["id"] for s in design["sections"]]
    if len(set(ids)) != len(ids):
        raise SourceError("section ids must be unique")
    for passage in passages(design):
        for end in passage["ends"]:
            if end["section"] not in ids:
                raise SourceError(f"passage {passage['index']}: no section {end['section']!r}")
    for section in design["sections"]:
        primary_arrival(design, section)
        veins(section)
    used = object_ids(design)
    counts = {}
    for _kind, oid in used:
        counts[oid] = counts.get(oid, 0) + 1
    repeated = sorted(oid for oid, n in counts.items() if n > 1)
    if repeated:
        raise SourceError(f"object ids used twice in the underground source: {repeated}")
    return True
