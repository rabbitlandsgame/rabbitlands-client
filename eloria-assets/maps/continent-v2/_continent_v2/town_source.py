"""town_source.py: the reader, checker and writer of content/landfall_town.json (Landfall Town interiors, 2026-10-27).

The town interiors' source keeps underground.json's shape (schema, map, sections, passages) so the shared publication
helpers apply, and adds what a building needs. Every reader of landfall_town.json goes through this module:
build_town_interiors.py (shells, walk grid, manifest) and the publication tools. Pure JSON and rectangle arithmetic: no
geometry library, no third-party imports. underground_source.py stays the reader of underground.json; its compact()
and SourceError are reused here, so the two sources print and fail alike.

THE FRAME: server tile (x, y) is world (x, h, cells - y). Compass names in this source are the map's: south is -y (the
side the default camera stands on, world +Z: screen bottom), north +y, west -x, east +x. A side's wall is cut away
while the camera looks through it.

MAP: {id, name, alias, cells (a multiple of 6), builder: "build_town_interiors", environment {...}, camera {distance,
minDistance, maxDistance, pitchDegrees, zoomStep}}; environment and camera are written into the package as they stand.

A SECTION (one building, or one storey of one; at least BLACKSPACE tiles of unfloored blackspace from every other and
EDGE tiles from the map's edge):
  id, name, style (a STYLES key: the builder's theme), danger (short flavour, "Open to all"), about
  rooms [[cx, cy, rx, ry], ...]   sharp rectangles: centre and half extents (tiles). Every edge lies on a tile-row
                                  centre (x.5): a wall stands on one row of tiles. Rooms share walls and never overlap;
                                  together they make one connected floor. Room 0 holds the street door.
  roomNames [str, ...]            parallel to rooms: the chamber names (music keywords: tavern/inn -> inn; shop/store/
                                  forge/workshop -> shop; castle/hall -> castle; archive/library -> library; house/home/
                                  cottage -> home). A name without a keyword takes the section id's.
  links [[a, b, width], [a, b, width, [[x, y]]]]   a doorway in the wall rooms a and b share: a flat opening `width`
                                  metres wide (>= MIN_LINK_WIDTH), centred on the point given (on that wall) or else on
                                  the tile centre nearest the middle of the shared wall
  floors [surface, ...]           parallel to rooms: FLOORS ids
  walls surface | [surface, ...]  the section's wall surface or one per room (WALLS ids); a partition's faces each take
                                  their own room's
  windows [{room, side, at, width}]        a window in the room's outer wall on `side`, centred `at` (0..1, west to
                                  east or south to north) along it
  decals [{image, room, side, at, size, height?}]   DECALS art: on a wall (`side` a compass side; at [u, v]: u along
                                  the wall as for windows, v the centre's height as a share of the wall's) or on the
                                  floor (`side` "floor"; at [u, v] across the room from its south-west corner; `height`
                                  lays it on a surface that high instead, e.g. a book on a dresser's worktop); size [w,
                                  h] metres
  entrances [DOOR, ...]           one per line (see DOORS)
  props [{asset, at, yaw, scale, block, blockBox, wall, height, palette, light, clearWall, mirror}]   reused kit
                                  scenery: block = radius (tiles) closed on the walk grid, blockBox [hx, hy] = a
                                  rectangle (half extents along the piece's own X and Z) turned by yaw; wall = the
                                  compass side of the wall it stands against: it cuts away with that wall; mirror true
                                  = the piece drawn mirrored across its own X (left for right), so one model standing
                                  in a row need not repeat itself (the walk grid is the same either way)
  lights [{at, height, colour, energy, range}]   at most MAX_LIGHTS_PER_ROOM in any room (props that are lamps count)
  npcs [{name, role, occupation, actorType, facing, tile, greeting, mapCategory?, mapLabel?}]
  interactives [{object, tile, role, text, label?, at?, target?, height?, radius?}]   role one of INTERACTIVE_ROLES;
                                  `label` the short name the client shows on hover (else the text's first clause), `at`
                                  [x, y] the point of the prop or picture it describes (the click shape stands there:
                                  retarget_underground.py writes a pick-only objects.json record, no ring, no model),
                                  `target` the server's target column (default by role: notice, crafting; the anvil's
                                  "smithing"), `height`/`radius` the pick's size (metres; else the prop's at `at`)
  sealedStairs [{room, side, at}] a flight of stairs up to a shut door in the room's outer wall: art only, no portal
  specialAreas [{kind, room, factor?}]   optional: a server special area (eloria/areas.py) over one room's floor, the
                                  tiles inside its walls (room_tiles(); the wall rows and the doorways in them stay
                                  outside it). `kind` one of SPECIAL_AREAS (the server's kinds), `factor` its
                                  multiplier (default the kind's, as the server's own rows use it: fast_reading 3).
                                  publish_server.py writes one `area | kind | map | x0 | y0 | x1 | y1 | factor` row per
                                  entry into the overlay's continent-v2/special_areas.txt (eloria/areas.py reads it)
  nodes [], spawns []             required and empty: the town has no harvest nodes and no encounters

DOORS ("entrances"; write each on ONE line):
  {map, kind: "building", object, tile, position, returnTile, arrival, exit, exitFacing, category?, label, exitLabel}
  `tile` is the exterior door tile on `map` (the object stands there; clicking it walks the player to it and in) and
  `returnTile` where the way out lands; `position` the painted door point on the exterior facade (world metres) that
  cartography draws. A building door has no scene marker. Inside, the same object stands on `exit` (the first walkable
  tile inside the street door, set into the wall `exitFacing` [dx, dy] points at) and lands players on `arrival` (two or
  three tiles in). `category` is a map_categories.py shop category (the door's dot colour; left out for a tan entrance
  dot), `label` the door's name outside and `exitLabel` the way-out's name inside.
  {map, kind: "underground", marker, ...} is the cave form (a scene marker, underground_source.py) and is accepted too.

PASSAGES (top level): underground_source.py's form, {object, name, art, ends: [{section, tile, arrival, facing?,
object?, art?, label?}, x2]}, with the building arts "stairs_up" (a flight up to an opening) and "stairs_down" (a
stairwell down into the floor). `label` is the way's name on that end ("Upstairs: the guest rooms").

OBJECT IDS: building doors 59201-59220 (one id serves both ends), passage ends 59221-59240 (two ids each), interior
interactives 59251-59299; every id once in the source (the publisher checks the maps and objects.json).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import underground_source as S

SCHEMA = "eloria-landfall-town-v1"
STYLES = ("tavern", "shop", "smithy", "house", "castle", "magic")
SIDES = ("north", "south", "east", "west")
# a side's outward direction in tile units (x, y): south is -y, toward the default camera
SIDE_TILE = {"north": (0, 1), "south": (0, -1), "east": (1, 0), "west": (-1, 0)}
FLOORS = ("oak_planks", "limestone_flagstone", "cobalt_tile", "packed_earth")
WALLS = ("lime_plaster", "soot_brick", "ashlar_wall", "timber_band")
PEOPLES = ("greyhaven", "glasswarden", "orun", "ssarathi", "luminous", "votary", "mycelari", "stoneborn")
DECALS = tuple(f"banner_{people}" for people in PEOPLES) + (
    "rug_tavern", "rug_runner", "rug_home", "map_landfall", "star_chart", "botanical_prints", "painting_unlit_boat",
    "book_recipes")
DOOR_KINDS = ("building", "underground")
PASSAGE_ARTS = S.MOUTH_ARTS + ("stairs_up", "stairs_down")
FACINGS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
INTERACTIVE_ROLES = ("information", "crafting_station")
INTERACTIVE_KEYS = ("object", "tile", "role", "text")
INTERACTIVE_OPTIONAL = ("label", "at", "target", "height", "radius")
# a room's special area (`specialAreas`): the server's kinds (eloria/areas.py VALID_KINDS) and the multiplier each takes
# when the source names none, as the server's own rows in config/eloria/special_areas.txt use them
SPECIAL_AREAS = {"fast_reading": 3, "fast_regeneration": 3, "harvest_speed": 2, "experience": 2, "cheap_magic": 2,
                 "no_magic": 2}
SPECIAL_AREA_KEYS = ("kind", "room")
SPECIAL_FACTORS = range(2, 11)
DOOR_IDS = range(59201, 59221)
PASSAGE_IDS = range(59221, 59241)
INTERACTIVE_IDS = range(59251, 59300)
ACTOR_TYPES = range(300, 378)
BLACKSPACE = 19
EDGE = 3
MIN_LINK_WIDTH = 2.4
MAX_LIGHTS_PER_ROOM = 6
TOP_KEYS = ("schema", "map", "sections", "passages")
SECTION_KEYS = ("id", "name", "style", "danger", "about", "rooms", "roomNames", "links", "floors", "walls", "windows",
                "decals", "entrances", "props", "lights", "npcs", "interactives", "sealedStairs", "specialAreas", "nodes",
                "spawns")
PROP_KEYS = ("asset", "at", "yaw", "scale", "block", "blockBox", "wall", "height", "palette", "light", "clearWall",
             "mirror")
# one item per line in dump(): the lists people edit a row at a time (retarget-style tools find a door by its line)
PER_LINE = ("entrances", "props", "lights", "windows", "decals", "npcs", "interactives", "sealedStairs")
HEAD = ("id", "name", "style", "danger")
# map_categories.py is the one category table (the dots role's); this copy only stands in while it is missing
_FALLBACK_CATEGORIES = ("tavern", "general_store", "flower_shop", "magic_shop", "blacksmith", "bookshop")


class SourceError(S.SourceError):
    """The town source holds something this format cannot read (a subclass of underground_source.SourceError)."""


def categories():
    """The shop categories a door or a shopkeeper may name (map_categories.CATEGORIES)."""
    try:
        import map_categories
    except ImportError:
        return _FALLBACK_CATEGORIES
    return tuple(map_categories.CATEGORIES)


# --- reading -----------------------------------------------------------------------------------------------------


def load(path):
    """The source at `path` as a dict (not checked: see check())."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _pair(value, where, kind=int):
    if not (isinstance(value, list) and len(value) == 2 and all(isinstance(v, kind) and not isinstance(v, bool)
                                                                 for v in value)):
        raise SourceError(f"{where}: give [x, y] as two {'whole numbers' if kind is int else 'numbers'}")
    return list(value)


def _number(value, where, low=None, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SourceError(f"{where}: give a number")
    if low is not None and value < low or high is not None and value > high:
        raise SourceError(f"{where}: {value} lies outside {low}..{high}")
    return value


def _text(value, where):
    if not isinstance(value, str) or not value.strip():
        raise SourceError(f"{where}: give a non-empty text")
    return value


def rooms(section):
    """The section's rooms as rectangles (x0, y0, x1, y1) in tiles, in source order."""
    return [(cx - rx, cy - ry, cx + rx, cy + ry) for cx, cy, rx, ry in section["rooms"]]


def room_tiles(section, room):
    """The served tiles of one room's floor as inclusive bounds (x0, y0, x1, y1): every tile whose centre lies inside
    the room's walls (a wall stands on the row of tiles its edge centres, so those rows and the doorways in them are
    outside)."""
    cx, cy, rx, ry = section["rooms"][room]
    return (int(round(cx - rx + .5)), int(round(cy - ry + .5)), int(round(cx + rx - 1.5)), int(round(cy + ry - 1.5)))


def special_areas(item):
    """A section's special areas (or every section's, given the source) as dicts {kind, room, factor, bounds (x0, y0,
    x1, y1: room_tiles()), section, index}, in source order."""
    if "sections" in item:
        return [area for section in item["sections"] for area in special_areas(section)]
    sid = item.get("id", "?")
    result = []
    for index, entry in enumerate(item.get("specialAreas", [])):
        where = f"{sid}: special area {index}"
        if not isinstance(entry, dict) or not set(SPECIAL_AREA_KEYS) <= set(entry):
            raise SourceError(f"{where}: give {{kind, room}} (and a factor)")
        extra = sorted(set(entry) - set(SPECIAL_AREA_KEYS) - {"factor"})
        if extra:
            raise SourceError(f"{where}: unknown keys {extra}")
        if entry["kind"] not in SPECIAL_AREAS:
            raise SourceError(f"{where}: kind {entry['kind']!r} is not one of {sorted(SPECIAL_AREAS)} (eloria/areas.py)")
        room = entry["room"]
        if not isinstance(room, int) or isinstance(room, bool) or room not in range(len(item.get("rooms", []))):
            raise SourceError(f"{where}: room {room!r} is not one of the section's rooms")
        factor = entry.get("factor", SPECIAL_AREAS[entry["kind"]])
        if not isinstance(factor, int) or isinstance(factor, bool) or factor not in SPECIAL_FACTORS:
            raise SourceError(f"{where}: factor {factor!r} is not a whole multiplier {SPECIAL_FACTORS.start}-"
                              f"{SPECIAL_FACTORS.stop - 1}")
        result.append({"kind": entry["kind"], "room": room, "factor": factor, "bounds": room_tiles(item, room),
                       "section": sid, "index": index})
    return result


def room_of(section, x, y):
    """The index of the first room holding the point (x, y) (edges included), or None."""
    for index, (x0, y0, x1, y1) in enumerate(rooms(section)):
        if x0 <= x <= x1 and y0 <= y <= y1:
            return index
    return None


def wall_of(section, room):
    """The wall surface of one room (the section's `walls`, a surface or a list per room)."""
    walls = section.get("walls")
    if isinstance(walls, list):
        return walls[room]
    return walls


def doors(item):
    """A section's doors, or (given the whole source) every section's, as dicts {map, kind, object, tile, position,
    returnTile, arrival, exit, exitFacing, category, label, exitLabel, marker?, index, section}: `category`, `label`
    and `exitLabel` are None where the door has none (a tan dot; the cave form)."""
    if "sections" in item:
        return [door for section in item["sections"] for door in doors(section)]
    sid = item.get("id", "?")
    if "entrance" in item:
        raise SourceError(f"{sid}: the town source writes its doors as `entrances`")
    result = []
    for index, door in enumerate(item.get("entrances", [])):
        where = f"{sid}: entrance {index}"
        if not isinstance(door, dict):
            raise SourceError(f"{where}: give a door record")
        kind = door.get("kind", "building")
        if kind not in DOOR_KINDS:
            raise SourceError(f"{where}: kind {kind!r} is not one of {DOOR_KINDS}")
        needed = ["map", "kind", "object", "tile", "position", "returnTile", "arrival", "exit"]
        if kind == "building":
            needed += ["label", "exitLabel"]
            if "marker" in door:
                raise SourceError(f"{where}: a building door has no scene marker (its tile is checked against the "
                                  "exterior's served grid)")
        else:
            needed.append("marker")
        missing = [k for k in needed if k not in door]
        if missing:
            raise SourceError(f"{where} lacks {missing}")
        known = set(needed) | {"exitFacing", "category", "label", "exitLabel", "marker"}
        extra = sorted(set(door) - known)
        if extra:
            raise SourceError(f"{where}: unknown keys {extra}")
        if not isinstance(door["object"], int) or isinstance(door["object"], bool):
            raise SourceError(f"{where}: object must be a whole number")
        for key in ("tile", "returnTile", "arrival", "exit"):
            _pair(door[key], f"{where} {key}")
        if not (isinstance(door["position"], list) and len(door["position"]) == 3):
            raise SourceError(f"{where}: position is the door's world point [x, y, z]")
        for value in door["position"]:
            _number(value, f"{where} position")
        facing = door.get("exitFacing", [0, -1])
        if tuple(facing) not in SIDE_TILE.values():
            raise SourceError(f"{where}: exitFacing {facing} must point straight at one wall ([0,-1] south, [0,1] "
                              "north, [-1,0] west or [1,0] east)")
        if "category" in door and door["category"] not in categories():
            raise SourceError(f"{where}: map category {door['category']!r} is not one of {list(categories())} "
                              "(map_categories.py); leave it out for the tan entrance dot")
        for key in ("label", "exitLabel"):
            if key in door:
                _text(door[key], f"{where} {key}")
        if door["arrival"] == door["exit"]:
            raise SourceError(f"{where}: arrival and exit are one tile")
        record = {**copy.deepcopy(door), "kind": kind, "exitFacing": list(facing),
                  "category": door.get("category"), "label": door.get("label"), "exitLabel": door.get("exitLabel"),
                  "index": index, "section": sid}
        result.append(record)
    return result


def passages(design):
    """The source's passages, each {object, name, art, ends: [end, end], index} where an end is {section, tile,
    arrival, facing (or None), object, art, label (or None), passage, end (0 or 1), to}: underground_source.passages()
    with the building arts stairs_up and stairs_down and an end's own `label`."""
    result = []
    for index, passage in enumerate(design.get("passages", [])):
        ends = passage.get("ends", [])
        if len(ends) != 2:
            raise SourceError(f"passage {index}: give exactly two ends")
        art = passage.get("art", "stairs")
        if art not in PASSAGE_ARTS:
            raise SourceError(f"passage {index}: art {art!r} is not one of {PASSAGE_ARTS}")
        normal = []
        for end_index, end in enumerate(ends):
            where = f"passage {index} end {end_index}"
            for key in ("section", "tile", "arrival"):
                if key not in end:
                    raise SourceError(f"{where} lacks {key}")
            extra = sorted(set(end) - {"section", "tile", "arrival", "facing", "object", "art", "label"})
            if extra:
                raise SourceError(f"{where}: unknown keys {extra}")
            object_id = end.get("object", passage.get("object", 0) + end_index if "object" in passage else None)
            if not isinstance(object_id, int) or object_id <= 0:
                raise SourceError(f"{where}: no object id (give the passage's `object`)")
            mouth = end.get("art", art)
            if mouth not in PASSAGE_ARTS:
                raise SourceError(f"{where}: art {mouth!r} is not one of {PASSAGE_ARTS}")
            facing = end.get("facing")
            if facing is not None and tuple(facing) not in SIDE_TILE.values() and mouth in ("stairs_up", "stairs_down"):
                raise SourceError(f"{where}: a building stair faces straight at one wall ([0,1], [0,-1], [1,0], [-1,0])")
            if "label" in end:
                _text(end["label"], f"{where} label")
            normal.append({"section": end["section"], "tile": _pair(end["tile"], f"{where} tile"),
                           "arrival": _pair(end["arrival"], f"{where} arrival"),
                           "facing": list(facing) if facing is not None else None, "object": object_id,
                           "art": mouth, "label": end.get("label"), "passage": index, "end": end_index})
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
    """Every arrival of a section as (kind, label, [x, y]): its doors' then its passage ends'; the first is primary."""
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


def npcs(item):
    """A section's NPCs (or every section's, given the source) as dicts with `section` and `index` added."""
    if "sections" in item:
        return [npc for section in item["sections"] for npc in npcs(section)]
    sid = item.get("id", "?")
    result = []
    for index, npc in enumerate(item.get("npcs", [])):
        where = f"{sid}: npc {index}"
        if not isinstance(npc, dict):
            raise SourceError(f"{where}: give an NPC record")
        missing = [k for k in ("name", "role", "occupation", "actorType", "facing", "tile", "greeting") if k not in npc]
        if missing:
            raise SourceError(f"{where} lacks {missing}")
        extra = sorted(set(npc) - {"name", "role", "occupation", "actorType", "facing", "tile", "greeting",
                                   "mapCategory", "mapLabel"})
        if extra:
            raise SourceError(f"{where}: unknown keys {extra}")
        for key in ("name", "role", "occupation", "greeting"):
            _text(npc[key], f"{where} {key}")
        if not isinstance(npc["actorType"], int) or npc["actorType"] not in ACTOR_TYPES:
            raise SourceError(f"{where}: actorType {npc['actorType']!r} is not a reviewed body ({ACTOR_TYPES.start}-"
                              f"{ACTOR_TYPES.stop - 1})")
        if npc["facing"] not in FACINGS:
            raise SourceError(f"{where}: facing {npc['facing']!r} is not one of {FACINGS}")
        _pair(npc["tile"], f"{where} tile")
        if "mapCategory" in npc and npc["mapCategory"] not in categories():
            raise SourceError(f"{where}: map category {npc['mapCategory']!r} is not one of {list(categories())}")
        if "mapLabel" in npc:
            _text(npc["mapLabel"], f"{where} mapLabel")
        result.append({**copy.deepcopy(npc), "section": sid, "index": index})
    return result


def interactives(item):
    """A section's interior interactives (or every section's, given the source), with `section` and `index` added."""
    if "sections" in item:
        return [entry for section in item["sections"] for entry in interactives(section)]
    sid = item.get("id", "?")
    result = []
    for index, entry in enumerate(item.get("interactives", [])):
        where = f"{sid}: interactive {index}"
        if not isinstance(entry, dict) or not set(INTERACTIVE_KEYS) <= set(entry):
            raise SourceError(f"{where}: give {{object, tile, role, text}}")
        extra = sorted(set(entry) - set(INTERACTIVE_KEYS) - set(INTERACTIVE_OPTIONAL))
        if extra:
            raise SourceError(f"{where}: unknown keys {extra}")
        if not isinstance(entry["object"], int) or entry["object"] not in INTERACTIVE_IDS:
            raise SourceError(f"{where}: object {entry['object']!r} lies outside the interior interactive band "
                              f"{INTERACTIVE_IDS.start}-{INTERACTIVE_IDS.stop - 1}")
        if entry["role"] not in INTERACTIVE_ROLES:
            raise SourceError(f"{where}: role {entry['role']!r} is not one of {INTERACTIVE_ROLES}")
        _pair(entry["tile"], f"{where} tile")
        _text(entry["text"], f"{where} text")
        for key in ("label", "target"):
            if key in entry:
                _text(entry[key], f"{where} {key}")
                if any(mark in entry[key] for mark in ("|", "#", "\n", "\r")) or entry[key] != entry[key].strip():
                    raise SourceError(f"{where}: {key} {entry[key]!r} is padded or holds '|', '#' or a line break")
        if "at" in entry:
            _pair(entry["at"], f"{where} at", (int, float))
        if "height" in entry:
            _number(entry["height"], f"{where} height", .3, 5)
        if "radius" in entry:
            _number(entry["radius"], f"{where} radius", .2, 3)
        result.append({**copy.deepcopy(entry), "section": sid, "index": index})
    return result


def interactive_label(entry):
    """An interactive's short name: its `label`, else its text up to the first colon or full stop."""
    if entry.get("label"):
        return entry["label"]
    text = entry["text"].strip()
    cut = min((i for i in (text.find(":"), text.find(". ")) if i > 0), default=len(text))
    return text[:cut].rstrip(".").strip()


def object_ids(design):
    """Every object id the source uses: (kind, id) for doors, passage ends, interactives and nodes, in source order."""
    result = []
    for section in design["sections"]:
        result += [("door", door["object"]) for door in doors(section)]
        result += [("node", oid) for oid, *_ in section.get("nodes", [])]
        result += [("interactive", entry["object"]) for entry in interactives(section)]
    result += [("passage", end["object"]) for passage in passages(design) for end in passage["ends"]]
    return result


# --- checking ----------------------------------------------------------------------------------------------------


def _gap(a, b):
    """The gap (tiles) between two rectangles (x0, y0, x1, y1): 0 when they touch or overlap."""
    dx = max(a[0] - b[2], b[0] - a[2], 0)
    dy = max(a[1] - b[3], b[1] - a[3], 0)
    return (dx * dx + dy * dy) ** .5


def _on_row(value):
    return abs((value % 1) - .5) < 1e-9


def shared_wall(section, a, b):
    """The wall rooms a and b share as ((x0, y0), (x1, y1)) (a straight segment), or None."""
    ra, rb = rooms(section)[a], rooms(section)[b]
    for one, two in ((ra, rb), (rb, ra)):
        if abs(one[2] - two[0]) < 1e-9:  # one's east edge is two's west edge
            low, high = max(one[1], two[1]), min(one[3], two[3])
            if high - low > 1e-9:
                return (one[2], low), (one[2], high)
        if abs(one[3] - two[1]) < 1e-9:  # one's north edge is two's south edge
            low, high = max(one[0], two[0]), min(one[2], two[2])
            if high - low > 1e-9:
                return (low, one[3]), (high, one[3])
    return None


def _check_section(design, section, cells):
    sid = section.get("id", "?")
    extra = sorted(set(section) - set(SECTION_KEYS))
    extra = [k for k in extra if not k.startswith("_")]
    if extra:
        raise SourceError(f"{sid}: unknown keys {extra}")
    for key in ("id", "name", "style", "danger", "rooms", "roomNames", "links", "floors", "walls", "nodes", "spawns"):
        if key not in section:
            raise SourceError(f"{sid}: lacks {key}")
    for key in ("id", "name", "danger"):
        _text(section[key], f"{sid} {key}")
    if section["style"] not in STYLES:
        raise SourceError(f"{sid}: style {section['style']!r} is not one of {STYLES}")
    if section["nodes"] or section["spawns"]:
        raise SourceError(f"{sid}: the town has no harvest nodes or encounters (`nodes` and `spawns` stay empty)")
    count = len(section["rooms"])
    if not count:
        raise SourceError(f"{sid}: give at least one room")
    for index, room in enumerate(section["rooms"]):
        where = f"{sid}: room {index}"
        if not (isinstance(room, list) and len(room) == 4):
            raise SourceError(f"{where}: give [cx, cy, rx, ry]")
        cx, cy, rx, ry = (_number(v, where) for v in room)
        if rx <= 0 or ry <= 0:
            raise SourceError(f"{where}: half extents must be positive")
        if not all(_on_row(v) for v in (cx - rx, cx + rx, cy - ry, cy + ry)):
            raise SourceError(f"{where}: its edges {[cx - rx, cy - ry, cx + rx, cy + ry]} must lie on tile-row "
                              "centres (x.5), so each wall stands on one row of tiles")
    boxes = rooms(section)
    for a in range(count):
        for b in range(a + 1, count):
            one, two = boxes[a], boxes[b]
            if min(one[2], two[2]) - max(one[0], two[0]) > 1e-9 and min(one[3], two[3]) - max(one[1], two[1]) > 1e-9:
                raise SourceError(f"{sid}: rooms {a} and {b} overlap (rooms share walls, never floor)")
    # one connected floor: every room reaches room 0 through shared walls
    seen, stack = {0}, [0]
    while stack:
        a = stack.pop()
        for b in range(count):
            if b not in seen and shared_wall(section, a, b):
                seen.add(b)
                stack.append(b)
    if len(seen) != count:
        raise SourceError(f"{sid}: rooms {sorted(set(range(count)) - seen)} share no wall with the rest of the building")
    for x0, y0, x1, y1 in boxes:
        if x0 < EDGE or y0 < EDGE or x1 > cells - EDGE or y1 > cells - EDGE:
            raise SourceError(f"{sid}: a room comes within {EDGE} tiles of the map's edge")
    names = section["roomNames"]
    if not isinstance(names, list) or len(names) != count:
        raise SourceError(f"{sid}: roomNames must name each of the {count} rooms")
    for index, name in enumerate(names):
        _text(name, f"{sid} roomNames {index}")
    floors = section["floors"]
    if not isinstance(floors, list) or len(floors) != count or any(f not in FLOORS for f in floors):
        raise SourceError(f"{sid}: floors must give one of {FLOORS} for each of the {count} rooms")
    walls = section["walls"]
    if isinstance(walls, list):
        if len(walls) != count or any(w not in WALLS for w in walls):
            raise SourceError(f"{sid}: walls must be one of {WALLS} or one per room")
    elif walls not in WALLS:
        raise SourceError(f"{sid}: walls must be one of {WALLS} or one per room")
    for index, link in enumerate(section["links"]):
        where = f"{sid}: link {index}"
        if not (isinstance(link, list) and len(link) in (3, 4)):
            raise SourceError(f"{where}: give [a, b, width] or [a, b, width, [[x, y]]]")
        a, b, width = link[:3]
        if not all(isinstance(v, int) and 0 <= v < count for v in (a, b)) or a == b:
            raise SourceError(f"{where}: rooms {a}, {b} are not two of the section's rooms")
        _number(width, where)
        if width < MIN_LINK_WIDTH:
            raise SourceError(f"{where}: a doorway {width} m wide leaves no walkable tile between the wall margins "
                              f"(at least {MIN_LINK_WIDTH})")
        if not shared_wall(section, a, b):
            raise SourceError(f"{where}: rooms {a} and {b} share no wall")
        if len(link) == 4 and not (isinstance(link[3], list) and len(link[3]) == 1):
            raise SourceError(f"{where}: the doorway's centre is one point [[x, y]]")
    for index, window in enumerate(section.get("windows", [])):
        where = f"{sid}: window {index}"
        if not isinstance(window, dict) or sorted(window) != sorted(("room", "side", "at", "width")):
            raise SourceError(f"{where}: give exactly {{room, side, at, width}}")
        if window["room"] not in range(count) or window["side"] not in SIDES:
            raise SourceError(f"{where}: name one of the rooms and one of {SIDES}")
        _number(window["at"], f"{where} at", 0, 1)
        _number(window["width"], f"{where} width", .4, 4)
    for index, decal in enumerate(section.get("decals", [])):
        where = f"{sid}: decal {index}"
        if not isinstance(decal, dict) or sorted(set(decal) - {"height"}) != sorted(("image", "room", "side", "at",
                                                                                       "size")):
            raise SourceError(f"{where}: give exactly {{image, room, side, at, size}} (and a floor decal's height)")
        if "height" in decal:
            if decal.get("side") != "floor":
                raise SourceError(f"{where}: only a floor decal lies at a height (on a surface)")
            _number(decal["height"], f"{where} height", .05, 3)
        if decal["image"] not in DECALS:
            raise SourceError(f"{where}: image {decal['image']!r} is not one of the decal surfaces {DECALS}")
        if decal["room"] not in range(count) or decal["side"] not in SIDES + ("floor",):
            raise SourceError(f"{where}: name one of the rooms and a side ({SIDES} or floor)")
        for value in _pair(decal["at"], f"{where} at", (int, float)):
            _number(value, f"{where} at", 0, 1)
        for value in _pair(decal["size"], f"{where} size", (int, float)):
            _number(value, f"{where} size", .1, 12)
    for index, prop in enumerate(section.get("props", [])):
        where = f"{sid}: prop {index}"
        if not isinstance(prop, dict) or "asset" not in prop or "at" not in prop:
            raise SourceError(f"{where}: give at least {{asset, at}}")
        extra = sorted(set(prop) - set(PROP_KEYS))
        if extra:
            raise SourceError(f"{where}: unknown keys {extra}")
        _text(prop["asset"], f"{where} asset")
        x, y = _pair(prop["at"], f"{where} at", (int, float))
        if room_of(section, x, y) is None:
            raise SourceError(f"{where}: {prop['at']} stands in none of the rooms")
        for key, low in (("yaw", None), ("scale", .05), ("block", 0), ("height", None), ("clearWall", 0)):
            if key in prop:
                _number(prop[key], f"{where} {key}", low)
        if "blockBox" in prop:
            for value in _pair(prop["blockBox"], f"{where} blockBox", (int, float)):
                _number(value, f"{where} blockBox", .05, 20)
        if "wall" in prop and prop["wall"] not in SIDES:
            raise SourceError(f"{where}: wall {prop['wall']!r} is not one of {SIDES}")
        if "light" in prop and not isinstance(prop["light"], bool):
            raise SourceError(f"{where}: light is true or false")
        if "mirror" in prop and prop["mirror"] is not True:
            raise SourceError(f"{where}: mirror is true or left out")
        if "palette" in prop and not isinstance(prop["palette"], dict):
            raise SourceError(f"{where}: palette is {{stone, mineral}}")
    lit = [0] * count
    for index, light in enumerate(section.get("lights", [])):
        where = f"{sid}: light {index}"
        if not isinstance(light, dict) or sorted(light) != sorted(("at", "height", "colour", "energy", "range")):
            raise SourceError(f"{where}: give exactly {{at, height, colour, energy, range}}")
        x, y = _pair(light["at"], f"{where} at", (int, float))
        room = room_of(section, x, y)
        if room is None:
            raise SourceError(f"{where}: {light['at']} stands in none of the rooms")
        lit[room] += 1
        _number(light["height"], f"{where} height", 0, 8)
        _number(light["energy"], f"{where} energy", 0, 8)
        _number(light["range"], f"{where} range", .5, 40)
        colour = light["colour"]
        if not (isinstance(colour, list) and len(colour) == 3):
            raise SourceError(f"{where}: colour is [r, g, b]")
        for value in colour:
            _number(value, f"{where} colour", 0, 1)
    for room, total in enumerate(lit):
        if total > MAX_LIGHTS_PER_ROOM:
            raise SourceError(f"{sid}: room {room} has {total} lights (at most {MAX_LIGHTS_PER_ROOM}: one key and a "
                              "few fills)")
    for index, stair in enumerate(section.get("sealedStairs", [])):
        where = f"{sid}: sealed stair {index}"
        if not isinstance(stair, dict) or sorted(stair) != sorted(("room", "side", "at")):
            raise SourceError(f"{where}: give exactly {{room, side, at}}")
        if stair["room"] not in range(count) or stair["side"] not in SIDES:
            raise SourceError(f"{where}: name one of the rooms and one of {SIDES}")
        _number(stair["at"], f"{where} at", 0, 1)
    areas = special_areas(section)
    if len({(area["kind"], area["room"]) for area in areas}) != len(areas):
        raise SourceError(f"{sid}: a room names the same special area twice")
    for area in areas:
        x0, y0, x1, y1 = area["bounds"]
        if x1 < x0 or y1 < y0:
            raise SourceError(f"{sid}: special area {area['index']}: room {area['room']} has no floor inside its walls")
    for door in doors(section):
        where = f"{sid}: entrance {door['index']}"
        for key in ("arrival", "exit"):
            x, y = door[key]
            if room_of(section, x + .5, y + .5) is None:
                raise SourceError(f"{where}: its {key} {door[key]} is not in any of the section's rooms")
    for npc in npcs(section):
        x, y = npc["tile"]
        if room_of(section, x + .5, y + .5) is None:
            raise SourceError(f"{sid}: npc {npc['name']} stands in none of the rooms")
    for entry in interactives(section):
        x, y = entry["tile"]
        if room_of(section, x + .5, y + .5) is None:
            raise SourceError(f"{sid}: interactive {entry['object']} stands in none of the rooms")
        if "at" in entry and room_of(section, *entry["at"]) is None:
            raise SourceError(f"{sid}: interactive {entry['object']}: its point `at` {entry['at']} is in none of the "
                              "rooms")


def check(design):
    """Structural checks of the whole source (rectangle arithmetic only; the builder checks the walk grid): the map,
    every section's keys and rooms, the blackspace between sections, doors, passages, NPCs and interactives, unique ids
    in their bands. Raises SourceError; returns True."""
    extra = sorted(set(design) - set(TOP_KEYS))
    if extra:
        raise SourceError(f"unknown top-level keys {extra}")
    if design.get("schema") != SCHEMA:
        raise SourceError(f"schema must be {SCHEMA!r}")
    info = design.get("map", {})
    for key in ("id", "name", "alias", "cells", "builder", "environment", "camera"):
        if key not in info:
            raise SourceError(f"map lacks {key}")
    cells = info["cells"]
    if not isinstance(cells, int) or cells <= 0 or cells % 6:
        raise SourceError("map cells must be a positive multiple of 6 (the server's collision scale)")
    if info["builder"] != "build_town_interiors":
        raise SourceError("map builder must be build_town_interiors")
    if not isinstance(info["environment"], dict):
        raise SourceError("map environment is the package's environment block")
    camera = info["camera"]
    if not isinstance(camera, dict) or any(k not in camera for k in ("distance", "minDistance", "maxDistance",
                                                                     "pitchDegrees", "zoomStep")):
        raise SourceError("map camera gives distance, minDistance, maxDistance, pitchDegrees and zoomStep")
    sections = design.get("sections", [])
    ids = [s.get("id") for s in sections]
    if len(set(ids)) != len(ids):
        raise SourceError("section ids must be unique")
    for section in sections:
        _check_section(design, section, cells)
    for i, one in enumerate(sections):
        for two in sections[i + 1:]:
            gap = min(_gap(a, b) for a in rooms(one) for b in rooms(two))
            if gap < BLACKSPACE:
                raise SourceError(f"{one['id']} and {two['id']} stand {gap:.1f} tiles apart: keep at least "
                                  f"{BLACKSPACE} tiles of blackspace between sections (local chat reaches 18)")
    for passage in passages(design):
        for end in passage["ends"]:
            if end["section"] not in ids:
                raise SourceError(f"passage {passage['index']}: no section {end['section']!r}")
            section = sections[ids.index(end["section"])]
            for key in ("tile", "arrival"):
                x, y = end[key]
                if room_of(section, x + .5, y + .5) is None:
                    raise SourceError(f"passage {passage['index']} end {end['end']}: its {key} is in none of "
                                      f"{end['section']}'s rooms")
            if end["object"] not in PASSAGE_IDS:
                raise SourceError(f"passage {passage['index']} end {end['end']}: object {end['object']} lies outside "
                                  f"the passage band {PASSAGE_IDS.start}-{PASSAGE_IDS.stop - 1}")
    for section in sections:
        primary_arrival(design, section)
        for door in doors(section):
            if door["kind"] == "building" and door["object"] not in DOOR_IDS:
                raise SourceError(f"{section['id']}: door object {door['object']} lies outside the building door band "
                                  f"{DOOR_IDS.start}-{DOOR_IDS.stop - 1}")
    counts = {}
    for _kind, oid in object_ids(design):
        counts[oid] = counts.get(oid, 0) + 1
    repeated = sorted(oid for oid, n in counts.items() if n > 1)
    if repeated:
        raise SourceError(f"object ids used twice in the town source: {repeated}")
    return True


# --- writing -----------------------------------------------------------------------------------------------------


compact = S.compact


def _section_lines(section):
    keys = [k for k in section if not k.startswith("_")]
    head = [k for k in HEAD if k in section]
    lines = [", ".join(f"{json.dumps(k)}: {json.dumps(section[k], ensure_ascii=False)}" for k in head)]
    for key in keys:
        if key in head:
            continue
        if key in PER_LINE and section[key]:
            body = ",\n".join("        " + compact(item) for item in section[key])
            lines.append(f'"{key}": [\n' + body + "\n      ]")
        else:
            lines.append(f"{json.dumps(key)}: {compact(section[key])}")
    return "    {\n" + ",\n".join("      " + line for line in lines) + "\n    }"


def dump(design):
    """content/landfall_town.json in its hand-laid-out style: one map key per line, one section key per line, one door,
    prop, light, window, decal, NPC and interactive per line, one passage per line; keys starting with `_` (the
    builder's annotations) are left out. Write the result as bytes (LF)."""
    info = design["map"]
    head = (f'{{\n  "schema": {json.dumps(design["schema"])},\n  "map": {{\n'
            + ",\n".join(f"    {json.dumps(k)}: {compact(v)}" for k, v in info.items() if not k.startswith("_"))
            + '\n  },\n  "sections": [\n')
    text = head + ",\n".join(_section_lines(s) for s in design["sections"]) + "\n  ]"
    if "passages" in design:
        if design["passages"]:
            text += ',\n  "passages": [\n' + ",\n".join("    " + compact(p) for p in design["passages"]) + "\n  ]"
        else:
            text += ',\n  "passages": []'
    return text + "\n}\n"
