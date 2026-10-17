"""publish_server.py: serve the continent-v2 isles from a server checkout: vendored grids, content overlay, manifest.

  python -B eloria-assets/maps/continent-v2/_continent_v2/publish_server.py --server <server checkout> \
         --bake <active-map-id>=<bake> [--bake <next-active-map-id>=<bake> ...] --stage m1|m2|m3|m4 \
         (--check | --apply) [--maps-root <dir holding continent-v2/<region>/client/>] [--crossings <crossings.json>] \
         [--record <publication.json>] [--checkout <worktree>] [--report <summary.json>]

Supply exactly one --bake per active catalog map; the current section partition has fifteen maps. Catalog, checked
frames and server-tables.json must agree on that set. <bake> is each territory's region bake (the directory holding
continent-authoring.json) of the committed scene: the
one its published package was made from (the package's provenance.snapshotSha256 and its collision block's
sourceSnapshotSha256 must be the bake's SHA-256, and the bake's scene SHA-256 the committed scene file's).

What it writes into --server (route B of the serve plan, section 2.3):

  tools/collision/<region>.escg.gz, manifest.json   by the server's own tools/sync_authored_collision.py --client
                                                    <maps root> --region <region>, per map (build_served: the package
                                                    grid, checked and vendored byte for byte)
  config/eloria/continent-v2/                       the content overlay, every file CRLF, written as bytes:
      README                                        what this directory is
      maps.txt                                      every active map row; the land crossings both ways (crossings.json,
                                                    crossings_v2.py); the one-way exit ferry, object-bound; the
                                                    isle boats, object-bound, one row each way
      spawns.txt                                    every <region>/content/spawns.json row, each with its leash:N
      harvesting.txt                                the resources the isles add (server-tables.json) and every
                                                    harvestable marker of the bakes, by objectId
      npcs.txt                                      the new people (server-rows.json group "new") at their markers,
                                                    each with its marker's optional extras "occupation" as an
                                                    occupation= option beside actor_type= (eloria/npcs.py)
      interactives.txt                              every interactive marker with its server-rows.json role/target/text
      exterior_connections.json                     the land links (crossings.json exteriorConnections)
      questlines.txt                                content/questlines.txt with TX/TY/MAP resolved from uniquely owned
                                                    markers and NPCMAP from actual giver posts (S1-S3, ids 26-28);
                                                    from stage m2 only
      landing.json                                  Signed Ashore's places (eloria-landing-v1, eloria/landing.py):
                                                    targets/cast carry map and tile; register/ferry carry {map, id}
      homes.json                                    the home's points (eloria-homes-v1; eloria/home.py)
      home_npcs.txt                                 the re-homed people at their isle posts: each one's npcs.txt row
                                                    with only the map, the tile and the greeting changed
  config/eloria/client_content_manifest.json       the isles' maps[] entries and a continentV2 block, through the
                                                    legacy publisher's own serializer (publish_continent_geography.
                                                    json_bytes), then LF -> CRLF; refused unless re-serializing the
                                                    file as it stands reproduces it byte for byte. diagonalContinent
                                                    and continentGeography are never touched.
And into this checkout: _continent_v2/publication.json (--record), what was published from what, by SHA-256: isle
facts only (every file of every stage, the inputs' digests, row counts), the same whatever the server tree's base
tables, code or stage, so a server-only change never makes --check differ on the client's record.

--stage is the serve plan's milestone the server tree is at (section 5). m1 serves every overlay file except
questlines.txt (the inert landing.json, homes.json and home_npcs.txt included, as S5 lists them); m2 adds
questlines.txt (S14), and needs eloria/landing.py in the tree: before M2's quest_offers region gate and the chapter's
isle cast, the errands' givers stand only at Four Gates and would offer them there. m3 and m4 serve what m2 does and
need eloria/home.py as well. --apply removes an overlay file the stage does not serve; --check reports one.

Every content coordinate comes from a scene marker or a content table's local metres, through frames.py. Default
arrivals use the shared arrivals.resolve contract: an original authored spawn where present, otherwise validated
hash-bound generatedArrival metadata outside the authored marker arrays. Generated arrivals add no scene markers.
The chapter's hub is the landing descriptor's map; targets, cast and ferry can belong to other active isles. Retired
map entries are removed using catalog retirement metadata. Fresh IDs have no position migration.
The ferry's landing is the destination's arrival as the legacy publication left it (the server's
eloria/continent_geography.py MAPS[<map>]['arrival'], which the client's legacy publisher writes), refused unless
every other copy agrees (the manifest's maps[] entry and continentGeography region, the client's generated
publication) and unless it and its eight neighbours are walkable on the destination's vendored grid, steppable from
it, and none is a walk-over trigger.
An isle boat is a portal interactive whose portal.destinationMap is another active isle (owner 2026-10-14: R5, the
Ravenhead-Tollholm boat that closes the eastern loop). Boats come in pairs: portal.returnBy names the boat on the
destination map that sails back, and that boat must name this one. Each lands on the runtime point its
portal.landingMarker names on the destination map (role BOAT_LANDING_ROLE), within BOAT_LANDING_REACH tiles of the
boat that sails back but not on its tile, and the landing passes the row rule below (itself and its eight neighbours
open and reached, none a walk-over trigger, no NPC post). The reach stays the land reach: a boat is a shortcut and
never the only way to a place, so a boat that stops sailing strands no one. A boat is an object portal: the server
never takes it for a land crossing (World.check_portal and the exit marks read land_connections only for walk-over
portals), it adds nothing to exterior_connections.json, and the client gets no streaming or walk-routing link for
it. The manifest's continentV2 block and the record list the boats under "boats", apart from the exit "ferries".

Checks, all fail closed (nothing is relocated; a row is moved in its source, never here):
- every row's tile and its eight neighbours are open on the served grid after storage erosion (the server's
  eloria.collision.with_storage_collision) and reached from some map's arrival over the land crossings (portal
  triggers are stepped onto and fire, never walked across) with every NPC post closed, as the server blocks the tile
  an NPC stands on (an NPC's own post need only be open ground; a harvest node's own tile is closed, as the node is a
  body, and only its ring is judged; storage occupies a solid 3x3 body with a reachable two-tile approach ring):
  spawns, harvest nodes, NPC posts (new and re-homed),
  interactives, the ferry trigger, the boats' triggers and landings, the arrivals and home points, every landing
  target, approach and cast post, and
  every quest stage tile (a landing target on a node, like one on a post, is walked to an approach tile); every
  lane's departure and arrival are reached;
- a harvest node is judged by the harvest approach rule instead (D4, HARVEST_APPROACH_RULE; "ring" restores the
  eight-neighbour rule): at least three of its ring tiles open and reached, or a reached tile within Chebyshev 2, and
  the tile the server's World.free_player_tile walks a harvester to is reached and within Chebyshev 2; and no node's
  tile centre lies within a road's half-width (D11, harvest_presentation.road_offenders: the bake's road paths);
- a spawn's creature exists, is passive, and its footprint fits (eloria.collision.erode_for_footprint);
- every row lies inside its own map's ownership polygon;
- object ids are unique per map across nodes and interactives, positive and below the exits' 60000;
- NPC posts are unique and stand on no trigger, arrival, home point, spawn row or interactive;
- the overlay loads with the server's own loaders over a copy of the base tables (duplicates, foreign maps, inline
  '#', row shapes), and landing.json, homes.json and home_npcs.txt pass the server's parsers when the server tree
  has eloria/landing.py and eloria/home.py, and this tool's own copy of their rules always.
The 19 rows of the B14 pocket (server-tables.json holdBack) are served only if every one of them passes; otherwise
all 19 are held back and recorded, and any other failure refuses the publish.

--check builds everything and compares it with the server tree and the record, writing nothing there (the sync runs
into a temporary folder seeded with the server's vendored manifest); it exits 1 on any difference. --apply writes.
The server's loader counts and parser results, and the ferry landing's copies and grid, go to the run's summary
(stdout, --report), not to the record. The packages must come from one export_collision.py run (crossings_v2's
check_one_run).
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

import numpy as np

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True
import frames  # noqa: E402
import arrivals as arrival_rules
import ownership
import export_collision as X  # noqa: E402
import crossings_v2 as CV  # noqa: E402
import underground as U  # noqa: E402
import harvest_presentation as HP  # noqa: E402

DEFAULT_CHECKOUT = frames.DEFAULT_CHECKOUT
TOOL = "eloria-assets/maps/continent-v2/_continent_v2/publish_server.py"
V2 = "eloria-assets/maps/continent-v2"
CONTENT = V2 + "/_continent_v2/content"
SERVER_ROWS = CONTENT + "/server-rows.json"
SERVER_TABLES = CONTENT + "/server-tables.json"
QUESTLINES = CONTENT + "/questlines.txt"
DEFAULT_RECORD = V2 + "/_continent_v2/publication.json"
CLIENT_PUBLICATION = "eloria-assets/maps/nymara-regions/_continent/generated/publication.json"
RECORD_SCHEMA = "eloria-continent-v2-publication-v1"
PROFILE = "config/eloria"
OVERLAY = "continent-v2"
MANIFEST = "client_content_manifest.json"
MANIFEST_BLOCK = "continentV2"
LANDING_SCHEMA = "eloria-landing-v1"
HOMES_SCHEMA = "eloria-homes-v1"
LANDING_TARGETS = ("olive_grove", "lemon_garden", "sage_meadow", "flint_outcrop", "bramble_edge", "resin_pines",
                   "warren", "temple_door", "lake_reeds", "causeway_mid", "ferry_quay", "pine_knoll")
HOME_ROLES = ("arrival", "beam", "respawn", "underworld")
# The isle boats (owner 2026-10-14: R5): the role of the runtime point a boat lands on, and how far (Chebyshev tiles)
# that landing may lie from the boat that sails back: the server's portal_activation_distance (eloria/settings.py,
# 8), so a passenger who steps off can use the boat home without walking a step.
BOAT_LANDING_ROLE = "boat-landing"
BOAT_LANDING_REACH = 8
EXIT_OBJECTS = 60000
MAX_LEASH = 200
INTERACTIVE_ROLES = {"storage", "crafting_station", "training", "information", "water_source", "scenery_effect",
                     "portal", "secret", "gate", "cache", "waystone"}
FORBIDDEN = ("|", "#", "\n", "\r")
# An NPC's occupation (the line a client draws under the name), as eloria/npcs.py's loader holds it: one more
# comma-separated option in the row's portrait column, so it may not hold a separator or the brackets drawn round it.
OCCUPATION_LIMIT = 32
OCCUPATION_FORBIDDEN = frozenset("|#,=<>")
RING = [(dx, dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1)]
NEIGHBOURS = [(dx, dy) for dx, dy in RING if dx or dy]
APPROACH_SEARCH = 6
# D4, the harvest approach rule (owner-approved 2026-10-14, landfall-audit-2026-10-14/harvest/FINDINGS.md 5.3): a
# harvest node passes when at least HARVEST_RING_MINIMUM of its eight ring tiles are open and reached, or some open,
# reached tile lies within HARVEST_REACH (Chebyshev) of it, so a seam can stand against a cliff, a reed bed in the
# shallows and a promoted tree beside a wall. The server is unchanged: it walks a harvester to the first walkable tile
# World.free_player_tile finds round the node and harvests within Chebyshev 2 (world._harvest_loop), so that tile
# must also be reached (Checker.node). "ring" restores the old rule (all eight neighbours open and reached). Only
# harvest nodes take it: spawns, NPC posts, interactives, landing targets and quest stages keep their rules.
HARVEST_APPROACH_RULE = "reach-side"
HARVEST_RING_MINIMUM = 3
HARVEST_REACH = 2
# World.free_player_tile's search radius (range(1, 20)).
SERVER_FREE_TILE_RADIUS = 19
# D11 (owner-approved 2026-10-14): no harvest node on a road. harvest_presentation.road_offenders.
HARVEST_ROAD_CHECK = True
# The overlay's files, in the order the README lists them and this tool writes them.
FILES = ("README", "maps.txt", "spawns.txt", "harvesting.txt", "npcs.txt", "interactives.txt",
         "exterior_connections.json", "questlines.txt", "landing.json", "homes.json", "home_npcs.txt")
# Independently authored server services are loaded beside the generated roster.
# Validate them with the server loaders, but never overwrite or retire them.
PRESERVED_FILES = ("service_npcs.txt",)
LOADER_TABLES = ("maps.txt", "spawns.txt", "harvesting.txt", "npcs.txt", "interactives.txt", "questlines.txt",
                 "exterior_connections.json")
# The serve plan's milestones (section 5) and what each serves of the overlay (section 2.3; S5 at M1, S14 at M2).
# Every file is S5's at M1, the inert landing.json, homes.json and home_npcs.txt included (nothing reads them until
# the chapter's and the home's code arrive), except questlines.txt: the overlay loader reads it the moment it exists,
# and before M2's quest_offers region gate (kit K2) and the isle cast (landing_install_isle_cast) the side errands'
# givers stand only at Four Gates, so every player there would be offered errands on an isle they cannot reach yet.
STAGES = ("m1", "m2", "m3", "m4")
FIRST_STAGE = {"questlines.txt": "m2"}
# The server code a stage needs in the tree it is published into.
STAGE_CODE = {"m1": (), "m2": ("eloria/landing.py",), "m3": ("eloria/landing.py", "eloria/home.py"),
              "m4": ("eloria/landing.py", "eloria/home.py")}


def stage_files(stage):
    """The overlay files served at `stage`, in FILES order."""
    return tuple(name for name in FILES if STAGES.index(FIRST_STAGE.get(name, "m1")) <= STAGES.index(stage))
GENERATED = "Written by " + TOOL + "; do not hand-edit: change its sources and run it again."


class PublishError(ValueError):
    """A refusal: a stale or disagreeing input, or a row that breaks a check."""


def say(*parts):
    """Progress goes to stderr: stdout carries only the run's JSON summary."""
    print(*parts, file=sys.stderr, flush=True)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise PublishError(f"missing {path}") from None


def crlf(text):
    """Text with every line ending CRLF, as bytes (the overlay's files are written bytes in, bytes out)."""
    if "\r" in text:
        raise PublishError("generated text already holds a carriage return")
    return text.replace("\n", "\r\n").encode("utf-8")


def json_crlf(value):
    return crlf(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def portrait_options(text):
    """An npcs.txt portrait column (`actor_type=376,occupation=Grove-Keeper`) as {option: value}."""
    return {key.strip(): value.strip() for key, _, value in (part.partition("=") for part in str(text).split(","))
            if key.strip()}


def npc_portrait(actor_type, occupation="", facing=""):
    """The portrait column of a published npcs.txt row: the body, then the occupation when there is one."""
    return (f"actor_type={int(actor_type)}" + (f",occupation={occupation}" if occupation else "")
            + (f",facing={facing}" if facing else ""))


def npc_facing(record):
    """Quantize the authoring marker's local X/Z vector to the wire compass."""
    import math
    vector = record.get("facing")
    if vector is None:
        return ""
    if (not isinstance(vector, (list, tuple)) or len(vector) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in vector)
            or math.hypot(vector[0], vector[2]) < 0.0001):
        raise PublishError(f"{record.get('id')}: NPC facing needs a finite nonzero X/Z vector")
    step = int(math.floor(math.atan2(vector[0], -vector[2]) / (math.pi / 4) + 0.5)) % 8
    return ("N", "NE", "E", "SE", "S", "SW", "W", "NW")[step]


def occupation_field(value, name, where):
    """A marker's optional extras 'occupation', held to the server loader's rules (eloria/npcs.py
    occupation_for): '' when the marker has none. The name stays simple and the job goes here, so a name that still
    starts with its own occupation is refused."""
    if value is None:
        return ""
    text = value if isinstance(value, str) else ""
    if (not text or text != " ".join(text.split()) or len(text) > OCCUPATION_LIMIT
            or any(char in OCCUPATION_FORBIDDEN or not char.isprintable() for char in text)):
        raise PublishError(f"{where}: occupation {value!r} is empty, padded, longer than {OCCUPATION_LIMIT} "
                           f"characters, or holds one of {''.join(sorted(OCCUPATION_FORBIDDEN))!r}")
    if name.casefold() == text.casefold() or name.casefold().startswith(text.casefold() + " "):
        raise PublishError(f"{where}: {name!r} already carries its occupation {text!r}: keep the name simple")
    return text


def plain_field(value, where):
    text = str(value)
    if any(mark in text for mark in FORBIDDEN) or text != text.strip() or not text:
        raise PublishError(f"{where}: {text!r} is empty, padded, or holds '|', '#' or a line break")
    return text


# --- the client side -------------------------------------------------------------------------------------------------

def read_bake(region, bake, checkout, frame):
    """A region bake: refused unless it is this region's, on this frame, from the committed scene file."""
    path = Path(bake)
    path = path / "continent-authoring.json" if path.is_dir() else path
    raw = path.read_bytes()
    doc = json.loads(raw)
    if doc.get("regionId") != region:
        raise PublishError(f"{path} is a bake of {doc.get('regionId')!r}, not {region}")
    server = doc.get("server", {})
    if (list(server.get("origin", [])) != list(frame.origin) or list(server.get("cells", [])) != list(frame.cells)
            or [float(v) for v in doc.get("continentTranslation", [])] != list(frame.translation)):
        raise PublishError(f"{region}: the bake's server frame differs from frames.py's: re-bake the committed scene")
    scene = doc.get("sources", {}).get("scene", {})
    scene_path = Path(checkout) / scene.get("path", "")
    if not scene.get("path") or not scene_path.is_file():
        raise PublishError(f"{region}: the bake names no scene file in this checkout")
    if sha256_file(scene_path) != scene.get("sha256"):
        raise PublishError(f"{region}: the bake was made from scene {scene.get('sha256')}, and the committed "
                           f"{scene['path']} is {sha256_file(scene_path)}: re-bake it")
    return SimpleNamespace(region=region, doc=doc, path=path, sha256=sha256_bytes(raw), scene_sha256=scene["sha256"])


MARKER_SECTIONS = ("spawnPoints", "harvestables", "npcMarkers", "interactives", "runtimePoints")


def markers_of(bake, frame):
    """{record id: (section, record)} of the bake's served gameplay sections, each record's tile through frames.py and
    held to the serverTile the bake recorded. A portal or runtime-binding marker is refused: nothing serves it yet."""
    out = {}
    gameplay = bake.doc.get("gameplay", {})
    for section in ("portals", "runtimeBindings"):
        if gameplay.get(section):
            raise PublishError(f"{bake.region}: the bake holds {section} markers, which this tool does not serve")
    for section in MARKER_SECTIONS:
        for record in gameplay.get(section, []):
            identity = record.get("id")
            if not identity or identity in out:
                raise PublishError(f"{bake.region}: marker id {identity!r} is missing or used twice")
            if "position" in record:
                x, _y, z = record["position"]
                tile = list(frame.tile(x, z))
                if "serverTile" in record and list(record["serverTile"]) != tile:
                    raise PublishError(f"{bake.region}: {identity} records tile {record['serverTile']}, frames.py "
                                       f"says {tile}")
                record = dict(record, tile=tile)
            out[identity] = (section, record)
    return out


def packages_of(checkout, maps_root, codec, bakes):
    """Each map's published package and the served grid it carries, checked against the bake and frames.py."""
    table = CV.package_inputs(checkout, maps_root, codec, log=lambda *_: None)
    for region, entry in table.items():
        manifest = entry["manifest"]
        bake = bakes[region]
        provenance = manifest.get("provenance", {}).get("snapshotSha256")
        exported = (manifest.get("collision") or {}).get("sourceSnapshotSha256")
        if provenance != bake.sha256 or exported != bake.sha256:
            raise PublishError(f"{region}: the package was published from snapshot {provenance} (collision from "
                               f"{exported}), not the bake given ({bake.sha256}): give the bake it was made from")
        package = Path(entry["package"])
        collision = (package / manifest["collision"]["binary"]).read_bytes()
        if sha256_bytes(collision) != manifest["collision"].get("sha256"):
            raise PublishError(f"{region}: collision.bin differs from the package's collision.sha256")
        entry["collisionSha256"] = manifest["collision"]["sha256"]
        entry["servedBytes"] = (package / manifest["collision"]["servedGrid"]["binary"]).read_bytes()
    return table


def content_tables(checkout, regions):
    checkout = Path(checkout)
    rows = read_json(checkout / SERVER_ROWS)
    tables = read_json(checkout / SERVER_TABLES)
    spawns = {region: read_json(checkout / V2 / region / "content" / "spawns.json") for region in regions}
    template = (checkout / QUESTLINES).read_text(encoding="utf-8")
    shas = {path: sha256_file(checkout / path) for path in
            [SERVER_ROWS, SERVER_TABLES, QUESTLINES] + [f"{V2}/{r}/content/spawns.json" for r in regions]}
    rename_path = f"{V2}/_continent_v2/marker-renames.json"
    if (checkout / rename_path).is_file():
        shas[rename_path] = sha256_file(checkout / rename_path)
    if rows.get("schema") != "eloria-continent-v2-server-rows-v1":
        raise PublishError(f"{SERVER_ROWS}: unexpected schema {rows.get('schema')!r}")
    if tables.get("schema") != "eloria-continent-v2-server-tables-v1":
        raise PublishError(f"{SERVER_TABLES}: unexpected schema {tables.get('schema')!r}")
    for region, doc in spawns.items():
        if doc.get("schema") != "eloria-continent-v2-spawns-v1" or doc.get("map") != region:
            raise PublishError(f"{region}/content/spawns.json: not this map's spawn table")
    return SimpleNamespace(rows=rows, tables=tables, spawns=spawns, template=template, shas=shas)


# --- the server side -------------------------------------------------------------------------------------------------

def literal_assignment(path, name):
    """A module-level `name = <literal>` from a Python file, without importing it."""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise PublishError(f"{path} assigns no {name}")


def server_side(server, codec, regions, frame_table, arrivals):
    """The server checkout's modules and base tables, and the preconditions the serve plan puts before CV8's --apply:
    the content overlay (S2), and the isles' REGIONS, MAP_TILES_WIDE_BY_NAME and ARRIVAL_TILES (S3/S5) and SOURCES."""
    server = Path(server).resolve()
    profile = server / PROFILE
    try:
        overlay = importlib.import_module("eloria.content_overlay")
    except ImportError:
        raise PublishError(f"{server} has no eloria/content_overlay.py: the overlay loaders (serve plan S2) come "
                           "first") from None
    if overlay.DIRECTORY != OVERLAY or getattr(overlay, "MAP_TABLE", "maps.txt") != "maps.txt":
        raise PublishError(f"the server's overlay directory is {overlay.DIRECTORY!r}, not {OVERLAY!r}")
    maps_module = sys.modules["generate_nymara_maps"]
    import continent_v2_registry as isle_registry
    isle_registry.register({r: {"serverCells": list(frame_table[r].cells), "arrival": list(arrivals[r])}
                            for r in regions}, maps_module, codec.sources)
    problems = []
    for region in regions:
        cells = frame_table[region].cells[0]
        if region not in maps_module.REGIONS:
            problems.append(f"{region} is not in tools/generate_nymara_maps.py REGIONS")
        wide = maps_module.MAP_TILES_WIDE_BY_NAME.get(region)
        if wide is None or wide * maps_module.COLLISION_SCALE != cells:
            problems.append(f"MAP_TILES_WIDE_BY_NAME[{region!r}] is {wide}, the frame needs {cells // 6}")
        if tuple(maps_module.ARRIVAL_TILES.get(region, ())) != tuple(arrivals[region]):
            problems.append(f"ARRIVAL_TILES[{region!r}] is {maps_module.ARRIVAL_TILES.get(region)}, the package's "
                            f"arrival {arrivals[region]}")
        source = codec.sources.SOURCES.get(region)
        if (source is None or source.kind != codec.sources.SERVED_GRID
                or source.relative != f"{OVERLAY}/{region}/client/collision.bin"):
            problems.append(f"tools/collision_sources.py SOURCES[{region!r}] is not the package's served grid")
    if problems:
        raise PublishError("the server checkout does not register the isles yet (the server workflow adds REGIONS "
                           "and the sizes before this --apply): " + "; ".join(problems))
    from eloria.maps import load_maps
    from eloria.npcs import load_npcs
    from eloria.interactives import load_interactives
    from eloria.harvesting import load_harvesting
    from eloria.creatures import load_creatures
    base_maps, base_portals = load_maps(profile / "maps.txt", overlay=False)
    clash = sorted(set(regions) & set(base_maps))
    if clash:
        raise PublishError(f"the base maps.txt already defines {clash}")
    npc_lines = {}
    for line in (profile / "npcs.txt").read_text(encoding="utf-8").splitlines():
        fields = [f.strip() for f in line.split("|")]
        if line.strip() and not line.lstrip().startswith("#") and fields[0] == "npc" and 8 <= len(fields) <= 9:
            npc_lines.setdefault(fields[1].casefold(), fields)
    resources, _nodes = load_harvesting(profile / "harvesting.txt", overlay=False)
    manifest_path = profile / MANIFEST
    return SimpleNamespace(
        root=server, profile=profile, overlay=overlay, maps_module=maps_module, base_maps=base_maps,
        base_portals=base_portals, base_npcs=load_npcs(profile / "npcs.txt", overlay=False), npc_lines=npc_lines,
        base_interactives=load_interactives(profile / "interactives.txt", overlay=False),
        base_resources=set(resources), creatures=load_creatures(profile / "creatures.txt"),
        manifest_path=manifest_path, manifest_raw=manifest_path.read_bytes(),
        geography=literal_assignment(server / "eloria" / "continent_geography.py", "MAPS"))


# --- the served grids and the reach ----------------------------------------------------------------------------------

def eroded_codes(region, entry, storage_tiles):
    """The served codes after the server's own storage erosion."""
    from eloria.collision import CollisionMap, with_storage_collision
    grid = entry["grid"]
    ground = with_storage_collision(CollisionMap.from_grid(grid), sorted(storage_tiles))
    return np.frombuffer(ground.heights, dtype=np.uint16).reshape(grid.height, grid.width).copy(), ground


def union_reach(codes, arrivals, lanes, climb):
    """{region: reached} from every map's arrival over the server's steps, a walk-over trigger fired when stepped
    onto (never walked across) and landing its walker on the far map's arrival cell."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import breadth_first_order
    regions = list(codes)
    offset, total = {}, 0
    for region in regions:
        offset[region] = total
        total += codes[region].size
    terminals = {region: set() for region in regions}
    for source, x, y, *_ in lanes:
        terminals[source].add((x, y))
    sources, targets = [], []
    for region in regions:
        c = codes[region]
        rows, cols = c.shape
        index = np.arange(c.size, dtype=np.int64).reshape(c.shape) + offset[region]
        stop = np.zeros(c.shape, bool)
        for x, y in terminals[region]:
            stop[y, x] = True
        for (dy, dx), ok in X.legal_steps(c, climb).items():
            ok = ok & ~stop
            start = index[ok]
            sources.append(start)
            targets.append(start + dy * cols + dx)
    for source, x, y, destination, ax, ay in lanes:
        sources.append(np.array([offset[source] + y * codes[source].shape[1] + x], np.int64))
        targets.append(np.array([offset[destination] + ay * codes[destination].shape[1] + ax], np.int64))
    seeds = [offset[r] + arrivals[r][1] * codes[r].shape[1] + arrivals[r][0] for r in regions]
    sources.append(np.full(len(seeds), total, np.int64))
    targets.append(np.asarray(seeds, np.int64))
    sources, targets = np.concatenate(sources), np.concatenate(targets)
    graph = coo_matrix((np.ones(len(sources), np.int8), (sources, targets)), shape=(total + 1, total + 1)).tocsr()
    order = breadth_first_order(graph, total, directed=True, return_predecessors=False)
    reached = np.zeros(total + 1, bool)
    reached[order] = True
    return {r: reached[offset[r]:offset[r] + codes[r].size].reshape(codes[r].shape) for r in regions}


class Checker:
    """Collects every row's failures; the B14 pocket's rows are judged as one.

    `codes` are the grids the walkers walk (the served codes after storage erosion with every NPC post closed, as
    the server's blocking_tiles closes them) and `reached` their union reach; `ground` the same codes with the posts
    open, against which an NPC's own post is judged."""

    def __init__(self, codes, reached, frame_table, polygons, ground=None):
        self.codes, self.reached, self.frames, self.polygons = codes, reached, frame_table, polygons
        self.ground = codes if ground is None else ground
        self.failures = []

    def ring(self, region, tile, kind, identity, *, ring=True, polygon=True, post=False, body=False):
        """The tile and (ring) its eight neighbours open and reached; a `post` (an NPC's own tile, which no walker
        enters) need only be open ground, its neighbours reached; a `body` (a harvest node's own tile, which the
        served grid closes: export_collision.harvest_mask) is judged by its neighbours alone."""
        frame = self.frames[region]
        x, y = int(tile[0]), int(tile[1])
        problems = []
        if not frame.contains(x, y):
            problems.append("outside the map")
        else:
            if polygon:
                cx, cz = frame.continent(x, y)
                if not bool(ownership.contains(cx, cz, self.polygons[region])):
                    problems.append("outside its own ownership polygon")
            offsets = RING if ring else [(0, 0)]
            blocked, unreached = [], []
            for dx, dy in offsets:
                nx, ny = x + dx, y + dy
                if body and not (dx or dy):
                    continue
                if post and not (dx or dy):
                    if not self.ground[region][ny, nx]:
                        blocked.append([nx, ny])
                    continue
                state = self._cell(region, nx, ny, canonical_owner=body and bool(dx or dy))
                if state == "blocked":
                    blocked.append([nx, ny])
                elif state == "unreached":
                    unreached.append([nx, ny])
                elif state != "open":
                    problems.append(state)
            if blocked:
                problems.append(f"blocked {blocked}")
            if unreached:
                problems.append(f"not reached {unreached}")
        if problems:
            self.failures.append({"kind": kind, "id": identity, "map": region, "tile": [x, y],
                                  "problems": problems})
        return not problems

    def _cell(self, region, nx, ny, *, canonical_owner=False):
        """One tile as a walker meets it: "open" (open and reached), "blocked", "unreached", or a sentence naming
        what is inconsistent about it. `canonical_owner`: a harvest node's surroundings can include the neighbour
        map's imported seam strip; that physical cell is judged on its unique owning map, retaining the open alias,
        identical height code and strict owner reach checks."""
        frame = self.frames[region]
        if not frame.contains(nx, ny) or not self.codes[region][ny, nx]:
            return "blocked"
        owner, ox, oy = region, nx, ny
        cx, cz = frame.continent(nx, ny)
        if canonical_owner and not ownership.contains(cx, cz, self.polygons[region]):
            owners = [r for r in self.frames if ownership.contains(cx, cz, self.polygons[r])]
            if len(owners) != 1 or owners[0] not in self.codes or owners[0] not in self.reached:
                return f"no unique active owner for ring tile {[nx, ny]}"
            owner = owners[0]
            canonical = self.frames[owner]
            ox, oy = canonical.tile(cx-canonical.translation[0], cz-canonical.translation[2])
            if not canonical.contains(ox, oy) or not np.allclose(canonical.continent(ox, oy),
                                                                [cx, cz], rtol=0, atol=1e-8):
                return f"canonical frame mismatch for ring tile {[nx, ny]}"
            if not self.codes[owner][oy, ox]:
                return "blocked"
            if self.codes[region][ny, nx] != self.codes[owner][oy, ox]:
                return f"canonical height mismatch for ring tile {[nx, ny]}"
        return "open" if self.reached[owner][oy, ox] else "unreached"

    def server_walk_tile(self, region, x, y):
        """The tile the server walks a harvester to for a node at (x, y): World.free_player_tile's search (the
        node's own tile, then each square ring outward, columns west to east and each column north to south) over
        the served grid as is_walkable reads it (storage eroded, NPC posts open: the server's walkability does not
        know them), ignoring the players and creatures that stand there at run time. None when nothing is open."""
        ground, frame = self.ground[region], self.frames[region]

        def walkable(tx, ty):
            return frame.contains(tx, ty) and bool(ground[ty, tx])

        if walkable(x, y):
            return [x, y]
        for radius in range(1, SERVER_FREE_TILE_RADIUS + 1):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if max(abs(dx), abs(dy)) == radius and walkable(x + dx, y + dy):
                        return [x + dx, y + dy]
        return None

    def node(self, region, tile, identity, *, rule=None):
        """A harvest node by the harvest approach rule (D4, HARVEST_APPROACH_RULE); "ring" is the old rule, every one
        of its eight neighbours open and reached (`ring(..., body=True)`). The node's own tile is a body the served
        grid closes (export_collision.harvest_mask) and is not judged. Integrity problems on its eight ring tiles
        (a seam-strip alias without a unique owner, another frame or height) still fail it, as they did."""
        rule = HARVEST_APPROACH_RULE if rule is None else rule
        if rule == "ring":
            return self.ring(region, tile, "node", identity, body=True)
        if rule != "reach-side":
            raise PublishError(f"unknown harvest approach rule {rule!r}")
        frame = self.frames[region]
        x, y = int(tile[0]), int(tile[1])
        problems = []
        if not frame.contains(x, y):
            problems.append("outside the map")
        else:
            if not bool(ownership.contains(*frame.continent(x, y), self.polygons[region])):
                problems.append("outside its own ownership polygon")
            states = {}
            for dy in range(-HARVEST_REACH, HARVEST_REACH + 1):
                for dx in range(-HARVEST_REACH, HARVEST_REACH + 1):
                    if dx or dy:
                        states[dx, dy] = self._cell(region, x + dx, y + dy, canonical_owner=True)
            problems.extend(states[step] for step in NEIGHBOURS
                            if states[step] not in ("open", "blocked", "unreached"))
            ring_open = sum(states[step] == "open" for step in NEIGHBOURS)
            if ring_open < HARVEST_RING_MINIMUM and not any(s == "open" for s in states.values()):
                problems.append(f"no approach: {ring_open} of 8 ring tiles open and reached (needs "
                                f"{HARVEST_RING_MINIMUM}) and no reached tile within Chebyshev {HARVEST_REACH}")
            walk_to = self.server_walk_tile(region, x, y)
            if walk_to is None:
                problems.append("the server finds no walkable tile round it (World.free_player_tile)")
            else:
                step = (walk_to[0] - x, walk_to[1] - y)
                if max(abs(step[0]), abs(step[1])) > HARVEST_REACH:
                    problems.append(f"the server walks a harvester to {walk_to} (World.free_player_tile), beyond "
                                    f"Chebyshev {HARVEST_REACH}")
                elif step != (0, 0) and states[step] != "open":
                    post = frame.contains(*walk_to) and not self.codes[region][walk_to[1], walk_to[0]]
                    problems.append(f"the server walks a harvester to {walk_to} (World.free_player_tile), which "
                                    + ("is an NPC post" if post else "is not reached"))
        if problems:
            self.failures.append({"kind": "node", "id": identity, "map": region, "tile": [x, y],
                                  "problems": problems})
        return not problems

    def storage(self, region, tile, identity):
        """A chest occupies 3x3 tiles; its complete outer approach ring must be reachable.

        Storage can be used from four tiles away. The two-tile ring is outside
        the stamped body, within that range, and keeps a chest off narrow paths.
        """
        before = len(self.failures)
        x, y = map(int, tile)
        self.ring(region, tile, "storage", identity, ring=False, body=True)
        frame = self.frames[region]
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                at = [x + dx, y + dy]
                if max(abs(dx), abs(dy)) == 2:
                    self.ring(region, at, "storage approach", identity, ring=False)
                elif (not frame.contains(*at)
                      or not ownership.contains(*frame.continent(*at), self.polygons[region])
                      or self.codes[region][at[1], at[0]]):
                    self.failures.append({"kind": "storage", "id": identity, "map": region,
                                          "tile": at, "problems": ["body is outside ownership or not blocked"]})
        return len(self.failures) == before


# --- the rows --------------------------------------------------------------------------------------------------------

def compose(ctx, *, log=say):
    """Every row, file and record, checked; nothing is written. ctx: checkout, frames, packages, bakes, tables,
    crossings, server, codec. Returns the publication namespace."""
    tables, rows = ctx.tables.tables, ctx.tables.rows
    map_rows = tables["maps"]
    if sorted(m["id"] for m in map_rows) != sorted(ctx.frames):
        raise PublishError(f"{SERVER_TABLES} maps {[m['id'] for m in map_rows]} are not the catalog's "
                           f"{sorted(ctx.frames)}")
    # Keep every generated table in server-tables.json's active catalog map order.
    regions = [m["id"] for m in map_rows]
    catalog = {e["id"]: e for e in frames.catalog_entries(ctx.checkout)}
    aliases = {}
    for definition in ctx.server.base_maps.values():
        for name in (definition.map_id, *definition.aliases):
            aliases[name.casefold()] = definition.map_id
    for m in map_rows:
        for name in (m["id"], m["alias"]):
            if name.casefold() in aliases:
                raise PublishError(f"{m['id']}: {name!r} already names the base map {aliases[name.casefold()]!r}")
    markers = {region: markers_of(ctx.bakes[region], ctx.frames[region]) for region in regions}
    arrivals = {region: ctx.packages[region]["arrival"] for region in regions}
    for region in regions:
        spawn = arrival_rules.resolve(ctx.bakes[region].doc, ctx.frames[region], ctx.checkout)
        if list(ctx.frames[region].tile(spawn["position"][0], spawn["position"][2])) != arrivals[region]:
            raise PublishError(f"{region}: resolved default arrival is not the package's arrival")

    def marker(region, identity, section=None):
        found = markers[region].get(identity)
        if found is None or (section and found[0] != section):
            raise PublishError(f"{region}: no {section or 'marker'} {identity!r} in the bake")
        return found[1]

    # Storage bodies are stamped by the server before reach and approach checks.
    interactive_rows = []
    storage = {region: set() for region in regions}
    for region in regions:
        table = rows["maps"].get(region, {}).get("interactives", {})
        found = {i: rec for i, (s, rec) in markers[region].items() if s == "interactives"}
        if set(found) != set(table):
            raise PublishError(f"{region}: interactive markers {sorted(found)} and server-rows.json entries "
                               f"{sorted(table)} differ")
        for identity in sorted(found, key=lambda i: table[i]["objectId"]):
            rec, entry = found[identity], table[identity]
            role = entry["role"]
            if role not in INTERACTIVE_ROLES:
                raise PublishError(f"{identity}: role {role!r} is not a server interactive role")
            if rec.get("type") != role or rec.get("objectId") != entry["objectId"]:
                raise PublishError(f"{identity}: the marker says type {rec.get('type')!r} object "
                                   f"{rec.get('objectId')!r}, server-rows.json {role!r} {entry['objectId']}")
            interactive_rows.append({"map": region, "id": identity, "object": int(entry["objectId"]),
                                     "tile": rec["tile"], "role": role,
                                     "target": plain_field(entry["target"], f"{identity} target"),
                                     "text": plain_field(entry["text"], f"{identity} text"), "entry": entry})
            if role == "storage":
                storage[region].add(tuple(rec["tile"]))
    codes, grounds = {}, {}
    for region in regions:
        codes[region], grounds[region] = eroded_codes(region, ctx.packages[region], storage[region])
    lanes = [tuple(row) for row in ctx.crossings["portals"]]
    for source, x, y, destination, ax, ay in lanes:
        if not codes[destination][ay, ax]:
            raise PublishError(f"lane {source} ({x}, {y}) lands on blocked {destination} ({ax}, {ay})")
    climb = int(ctx.codec.climb_units)
    polygons = {region: ctx.packages[region]["polygon"] for region in regions}
    hold = tables.get("holdBack", {})
    held_spawns = set(hold.get("spawns", []))
    held_nodes = {(n["map"], n["id"]) if isinstance(n, dict) else n for n in hold.get("nodes", [])}
    held_map = hold.get("map")

    def in_pocket(kind, region, identity):
        return ((kind == "spawn" and identity in held_spawns)
                or (kind == "node" and ((region, identity) in held_nodes or identity in held_nodes))) \
            and (held_map is None or region == held_map)

    # Spawns.
    spawn_rows = []
    for region in regions:
        frame = ctx.frames[region]
        for record in ctx.tables.spawns[region]["spawns"]:
            x, z = record["local"]
            tile = list(frame.tile(x, z))
            leash = record.get("leash")
            if type(leash) is not int or not 1 <= leash <= MAX_LEASH:
                raise PublishError(f"{record['id']}: leash {leash!r} is not 1-{MAX_LEASH}")
            creature = ctx.server.creatures.get(record["creature"])
            if creature is None:
                raise PublishError(f"{record['id']}: no creature {record['creature']!r} in the server's creatures.txt")
            if creature.raw.get("aggressive", "0").strip() not in ("", "0"):
                raise PublishError(f"{record['id']}: {record['creature']} is aggressive; the isles field only "
                                   "passive species")
            spawn_rows.append({"map": region, "id": record["id"], "creature": plain_field(record["creature"],
                                                                                        record["id"]),
                               "tile": tile, "leash": leash, "footprint": creature.footprint})
    nodes = []
    resources_added = [r["name"] for r in tables["resources"]]
    known_resources = {r.casefold() for r in ctx.server.base_resources} | {r.casefold() for r in resources_added}
    for name in resources_added:
        if name.casefold() in {r.casefold() for r in ctx.server.base_resources}:
            raise PublishError(f"resource {name} is already in the base harvesting.txt")
    for region in regions:
        for identity, (section, rec) in sorted(markers[region].items()):
            if section != "harvestables":
                continue
            object_id, resource = rec.get("objectId"), rec.get("resource")
            if type(object_id) is not int or not resource:
                raise PublishError(f"{identity}: a harvestable marker needs an integer objectId and a resource")
            if resource.casefold() not in known_resources:
                raise PublishError(f"{identity}: resource {resource!r} is neither a base resource nor one "
                                   f"{SERVER_TABLES} adds")
            nodes.append({"map": region, "id": object_id, "marker": identity, "tile": rec["tile"],
                          "resource": plain_field(resource, identity)})
    nodes.sort(key=lambda n: (regions.index(n["map"]), n["id"]))
    # A node is a body on its tile (export_collision.harvest_mask closes it): harvested from its ring, never stood on.
    node_tiles = {(n["map"], tuple(n["tile"])): n["marker"] for n in nodes}
    # NPCs: the new people (npcs.txt) and the re-homed (home_npcs.txt).
    new_people, rehomed = [], []
    for region in regions:
        table = rows["maps"].get(region, {}).get("npcs", {})
        found = {i: rec for i, (s, rec) in markers[region].items() if s == "npcMarkers"}
        if set(found) != set(table):
            raise PublishError(f"{region}: NPC markers {sorted(found)} and server-rows.json entries {sorted(table)} "
                               "differ")
        for identity in sorted(found):
            rec, entry = found[identity], table[identity]
            name = plain_field(entry["name"], f"{identity} name")
            # A re-homed person's marker names its body; a new person's names the race block server-rows.json
            # chose the body from (B3 notes 6.1).
            block = rec.get("actorTypeBlock")
            body_ok = (rec.get("actorType") == entry["actorType"] if "actorType" in rec
                       else isinstance(block, list) and len(block) == 2 and block[0] <= entry["actorType"] <= block[1])
            if rec.get("name", rec.get("label")) != name or not body_ok:
                raise PublishError(f"{identity}: the marker names {rec.get('name')!r} body "
                                   f"{rec.get('actorType', block)}, server-rows.json {name!r} body {entry['actorType']}")
            person = {"map": region, "id": identity, "name": name, "tile": rec["tile"],
                      "role": plain_field(entry["role"], f"{identity} role"), "actorType": int(entry["actorType"]),
                      "greeting": plain_field(entry["greeting"], f"{identity} greeting"),
                      "occupation": occupation_field(rec.get("occupation"), name, identity),
                      "facing": npc_facing(rec)}
            if entry["group"] == "new":
                if name.casefold() in ctx.server.npc_lines:
                    raise PublishError(f"{identity}: {name} is already in the base npcs.txt; a new person needs a "
                                       "new name")
                new_people.append(person)
            elif entry["group"] == "re-homed":
                base = ctx.server.npc_lines.get(name.casefold())
                if base is None:
                    raise PublishError(f"{identity}: {name} is nobody in the base npcs.txt; home_npcs.txt moves "
                                       "people, it does not add them")
                options = portrait_options(base[6])
                if (base[5].casefold() != person["role"].casefold()
                        or options.get("actor_type") != str(person["actorType"])):
                    raise PublishError(f"{identity}: npcs.txt has {name} as {base[5]} {base[6]}, server-rows.json "
                                       f"as {person['role']} actor_type={person['actorType']}")
                # home_npcs.txt copies the base row's portrait column, occupation and all: a move keeps it.
                if "occupation" in rec and person["occupation"] != options.get("occupation", ""):
                    raise PublishError(f"{identity}: npcs.txt has {name}'s occupation as "
                                       f"{options.get('occupation', '')!r}, the marker {person['occupation']!r}; a "
                                       "move keeps the occupation")
                person["base"] = base
                rehomed.append(person)
            else:
                raise PublishError(f"{identity}: group {entry['group']!r} is neither new nor re-homed")
    # The reach every row is judged by: the server blocks the tile an NPC stands on for every walker
    # (World.blocking_tiles; an NPC is one tile), and from M2 the re-homed people stand on the isle too (the chapter's
    # cast, then home_npcs.txt), so all ten posts are closed. A post in a one-tile pass then fails the rows beyond it
    # here rather than stranding them on the server.
    walk = {region: codes[region].copy() for region in regions}
    for p in new_people + rehomed:
        if ctx.frames[p["map"]].contains(*p["tile"]):
            walk[p["map"]][p["tile"][1], p["tile"][0]] = 0
    reached = union_reach(walk, arrivals, lanes, climb)
    check = Checker(walk, reached, ctx.frames, polygons, ground=codes)
    # The portal interactives: the exit ferry, to a legacy map's arrival, and the isle boats, to another isle.
    ferries = [row for row in interactive_rows if row["role"] == "portal"]
    ferry_rows, boat_rows = [], []
    for row in ferries:
        portal = row["entry"].get("portal") or {}
        destination = portal.get("destinationMap")
        if not destination or portal.get("oneWay") is not True:
            raise PublishError(f"{row['id']}: a portal interactive needs portal.destinationMap and oneWay true")
        if destination in regions:
            boat_rows.append(isle_boat(row, portal, markers))
            continue
        landing = ferry_landing(ctx, destination)
        ferry_rows.append({**row, "destination": destination, "landing": landing["tile"], "landingCheck": landing})
    pair_boats(boat_rows)
    # Object ids.
    for region in regions:
        ids = Counter([n["id"] for n in nodes if n["map"] == region]
                      + [i["object"] for i in interactive_rows if i["map"] == region])
        twice = sorted(i for i, n in ids.items() if n > 1)
        bad = sorted(i for i in ids if not 0 < i < EXIT_OBJECTS)
        if twice or bad:
            raise PublishError(f"{region}: object ids used twice {twice}, out of range {bad}")
    # Points: homes, landing, quest stages.
    home_table = tables.get("homes", {})
    homes = {}
    for region, roles in home_table.items():
        if region not in regions or sorted(k for k in roles if k != "note") != sorted(HOME_ROLES):
            raise PublishError(f"{SERVER_TABLES} homes[{region!r}] must name the four roles on a catalog map")
        homes[region] = {role: marker(region, roles[role])["tile"] for role in HOME_ROLES}
    land = tables["landing"]
    lmap = land["map"]
    npc_posts = {(p["map"], tuple(p["tile"])): p["name"] for p in new_people + rehomed}
    if len(npc_posts) != len(new_people) + len(rehomed):
        raise PublishError("two NPC posts share a tile")
    triggers = {(s, x, y) for s, x, y, *_ in lanes}
    lane_arrivals = {(d, ax, ay) for *_, d, ax, ay in lanes}
    targets = {}
    for region in regions:
        for identity, (section, rec) in sorted(markers[region].items()):
            if section != "runtimePoints" or rec.get("role") not in land["targetRoles"]:
                continue
            key = rec.get("target")
            if not key or key in targets:
                raise PublishError(f"{identity}: a landing target needs a unique `target`")
            entry = {"map": region, "tile": rec["tile"], "marker": identity}
            if "radius" in rec:
                if type(rec["radius"]) is not int or not 0 <= rec["radius"] <= 64:
                    raise PublishError(f"{identity}: radius must be 0-64")
                entry["radius"] = rec["radius"]
            targets[key] = entry
    missing = [key for key in LANDING_TARGETS if key not in targets]
    if missing:
        raise PublishError(f"landing targets without a marker: {missing}")
    for key, entry in targets.items():
        region, tile = entry["map"], tuple(entry["tile"])
        if (region, tile) in npc_posts or (region, *tile) in triggers or (region, tile) in node_tiles:
            entry["approach"] = approach_for(region, tile, entry.get("radius", 3), walk, reached, npc_posts,
                                             triggers, ctx.frames)
            entry["why"] = "target shares an NPC post, harvest node or trigger"
    cast = [{"name": p["name"], "map": p["map"], "tile": p["tile"],
             **({"facing": p["facing"]} if p.get("facing") else {})} for p in rehomed]
    landing_arrival = marker(lmap, land["arrival"])["tile"]
    by_marker = {r["id"]: r for r in interactive_rows}
    if land["register"] not in by_marker or land["ferry"] not in by_marker:
        raise PublishError("landing register or ferry marker has no interactive binding")
    register, ferry = by_marker[land["register"]], by_marker[land["ferry"]]
    if register["role"] != "information" or ferry["role"] != "portal":
        raise PublishError("the landing register must be information and the ferry a portal")
    if any(b["id"] == ferry["id"] for b in boat_rows):
        raise PublishError("the landing's ferry must be the exit ferry, not an isle boat")
    ferry_point = marker(ferry["map"], land["ferryPoint"])["tile"]
    if ferry_point != ferry["tile"]:
        raise PublishError("the ferry runtime point and interactive differ")
    questlines, stage_tiles = resolve_questlines(ctx.tables.template, markers, lmap,
                                               people=new_people + rehomed)
    # Every check, per row.
    held = []
    pocket = []
    spawn_tiles = {(s["map"], tuple(s["tile"])) for s in spawn_rows}
    for s in spawn_rows:
        before = len(check.failures)
        check.ring(s["map"], s["tile"], "spawn", s["id"])
        if not s["footprint"].is_single_tile:
            from eloria.collision import erode_for_footprint
            fits = erode_for_footprint(grounds[s["map"]], s["footprint"])
            if not fits.walkable(*s["tile"]):
                check.failures.append({"kind": "spawn", "id": s["id"], "map": s["map"], "tile": s["tile"],
                                       "problems": [f"footprint {s['footprint']} does not fit"]})
        if (s["map"], tuple(s["tile"])) in npc_posts:
            check.failures.append({"kind": "spawn", "id": s["id"], "map": s["map"], "tile": s["tile"],
                                   "problems": [f"stands on {npc_posts[(s['map'], tuple(s['tile']))]}'s post"]})
        if in_pocket("spawn", s["map"], s["id"]):
            pocket.extend(check.failures[before:])
            del check.failures[before:]
    roads = {}
    for n in nodes:
        before = len(check.failures)
        check.node(n["map"], n["tile"], n["id"])
        if HARVEST_ROAD_CHECK:
            # D11: no node on a road (the scene's Roads/* curves at their saved widths).
            if n["map"] not in roads:
                roads[n["map"]] = HP.road_segments(ctx.bakes[n["map"]].doc.get("paths", []))
            x, z = ctx.frames[n["map"]].local(*n["tile"])
            hit = HP.road_clearance(x, z, roads[n["map"]])
            if hit is not None:
                check.failures.append({"kind": "node", "id": n["id"], "map": n["map"], "tile": n["tile"],
                                       "problems": [f"on road {hit[1]}: the tile's centre lies {hit[0]:.2f} m inside "
                                                    "its half-width (D11)"]})
        if in_pocket("node", n["map"], n["id"]):
            pocket.extend(check.failures[before:])
            del check.failures[before:]
    for p in new_people + rehomed:
        check.ring(p["map"], p["tile"], "npc", p["name"], post=True)
        clash = [what for what, hit in (("a walk-over trigger", (p["map"], *p["tile"]) in triggers),
                                        ("a lane's arrival", (p["map"], *p["tile"]) in lane_arrivals),
                                        ("a spawn row", (p["map"], tuple(p["tile"])) in spawn_tiles),
                                        ("an interactive", any(i["map"] == p["map"] and i["tile"] == p["tile"]
                                                               for i in interactive_rows)),
                                        ("an arrival or home point", p["tile"] == arrivals[p["map"]] or any(
                                            p["tile"] == t for t in homes.get(p["map"], {}).values())),
                                        ("a boat's landing", any(b["destination"] == p["map"]
                                                                 and b["landing"] == p["tile"] for b in boat_rows)))
                 if hit]
        if clash:
            check.failures.append({"kind": "npc", "id": p["name"], "map": p["map"], "tile": p["tile"],
                                   "problems": [f"stands on {', '.join(clash)}"]})
    for i in interactive_rows:
        if i["role"] == "storage":
            check.storage(i["map"], i["tile"], i["object"])
        else:
            check.ring(i["map"], i["tile"], "interactive", i["object"])
    for region in regions:
        check.ring(region, arrivals[region], "arrival", region)
    for region, points in homes.items():
        for role, tile in points.items():
            check.ring(region, tile, "home", role)
    check.ring(lmap, landing_arrival, "landing", "arrival")
    for key, entry in targets.items():
        # a target on an NPC's post is judged as the post is (open ground; the walker stands on its approach), one
        # on a harvest node as the node is (its ring)
        check.ring(entry["map"], entry["tile"], "landing", key, ring=("approach" not in entry),
                   post=(entry["map"], tuple(entry["tile"])) in npc_posts, body=(entry["map"], tuple(entry["tile"])) in node_tiles)
        if "approach" in entry:
            check.ring(entry["map"], entry["approach"], "landing", key + " approach")
    for post in cast:
        check.ring(post["map"], post["tile"], "landing", "cast " + post["name"], post=True)
    for key, (region, tile) in stage_tiles.items():
        check.ring(region, tile, "quest stage", key, body=(region, tuple(tile)) in node_tiles)
    for source, x, y, destination, ax, ay in lanes:
        if not reached[source][y, x]:
            check.failures.append({"kind": "lane", "id": f"{source}->{destination}", "map": source, "tile": [x, y],
                                   "problems": ["the departure is not reached"]})
        if not reached[destination][ay, ax]:
            check.failures.append({"kind": "lane", "id": f"{source}->{destination}", "map": destination,
                                   "tile": [ax, ay], "problems": ["the arrival is not reached"]})
    for b in boat_rows:
        # the trigger is an interactive, judged above; the landing by the same rule, and kept clear of every
        # walk-over trigger, post and object, and beside the boat that sails back
        check.ring(b["destination"], b["landing"], "boat landing", b["id"])
        x, y = b["landing"]
        problems = [f"a walk-over trigger at {[x + dx, y + dy]} in its ring" for dx, dy in RING
                    if (b["destination"], x + dx, y + dy) in triggers]
        if (b["destination"], (x, y)) in npc_posts:
            problems.append(f"it is {npc_posts[(b['destination'], (x, y))]}'s post")
        problems += [f"it is interactive {i['object']}'s tile" for i in interactive_rows
                     if i["map"] == b["destination"] and i["tile"] == b["landing"]]
        back = by_marker[b["returnBy"]]
        distance = max(abs(x - back["tile"][0]), abs(y - back["tile"][1]))
        if distance > BOAT_LANDING_REACH:
            problems.append(f"it is {distance} tiles from the boat back ({b['returnBy']}), more than "
                            f"{BOAT_LANDING_REACH}")
        if problems:
            check.failures.append({"kind": "boat landing", "id": b["id"], "map": b["destination"], "tile": [x, y],
                                   "problems": problems})
    if check.failures:
        raise PublishError(f"{len(check.failures)} rows fail the checks: " + json.dumps(check.failures[:12]))
    if pocket:
        held = sorted(held_spawns) + sorted(f"{n[0]}:{n[1]}" if isinstance(n, tuple) else str(n) for n in held_nodes)
        spawn_rows = [s for s in spawn_rows if not in_pocket("spawn", s["map"], s["id"])]
        nodes = [n for n in nodes if not in_pocket("node", n["map"], n["id"])]
        log(f"held back the B14 pocket's {len(held)} rows: {len(pocket)} failures, e.g. {pocket[:2]}")
    landing_doc = {"schema": LANDING_SCHEMA, "map": lmap, "arrival": landing_arrival,
                   "objects": {"register": {"map": register["map"], "id": register["object"]},
                               "ferry": {"map": ferry["map"], "id": ferry["object"]}},
                   "targets": {key: {k: v for k, v in entry.items() if k in ("map", "tile", "approach", "radius")}
                               for key, entry in sorted(targets.items())},
                   "cast": cast,
                   "provenance": {"tool": TOOL, "markers": {key: entry["marker"] for key, entry in
                                                            sorted(targets.items())},
                                  "approaches": {key: entry["why"] for key, entry in sorted(targets.items())
                                                 if "why" in entry}}}
    homes_doc = {"schema": HOMES_SCHEMA, "homes": homes,
                 "provenance": {"tool": TOOL, "points": {region: {role: home_table[region][role] for role in HOME_ROLES}
                                                         for region in homes}}}
    pub = SimpleNamespace(regions=regions, map_rows=map_rows, catalog=catalog, lanes=lanes, ferries=ferry_rows,
                          boats=boat_rows, spawns=spawn_rows, nodes=nodes, new_people=new_people, rehomed=rehomed,
                          interactives=interactive_rows, questlines=questlines, landing=landing_doc, homes=homes_doc,
                          held=held, pocket_failures=pocket, arrivals=arrivals, reached=reached, codes=codes,
                          resources=tables["resources"], stage_tiles=stage_tiles)
    pub.files = overlay_files(ctx, pub)
    U.attach(ctx, pub, PublishError)
    return pub


def isle_boat(row, portal, markers):
    """An isle boat: the portal interactive `row` whose server-rows.json portal sails to another active isle and lands
    on the BOAT_LANDING_ROLE runtime point portal.landingMarker names there; portal.returnBy names the boat back."""
    destination, where = portal["destinationMap"], row["id"]
    if destination == row["map"]:
        raise PublishError(f"{where}: a boat sails to another isle, not round its own map")
    landing_id, back = portal.get("landingMarker"), portal.get("returnBy")
    if not isinstance(landing_id, str) or not isinstance(back, str):
        raise PublishError(f"{where}: an isle boat needs portal.landingMarker (a {BOAT_LANDING_ROLE} runtime point "
                           f"on {destination}) and portal.returnBy (the boat on {destination} that sails back)")
    found = markers[destination].get(landing_id)
    if found is None or found[0] != "runtimePoints" or found[1].get("role") != BOAT_LANDING_ROLE:
        raise PublishError(f"{where}: {destination} has no {BOAT_LANDING_ROLE} runtime point {landing_id!r}")
    return {**row, "destination": destination, "landing": list(found[1]["tile"]), "landingMarker": landing_id,
            "returnBy": back}


def pair_boats(boats):
    """Boats come in pairs: each one's portal.returnBy is a boat on its destination that sails back to its map and
    names it in turn, so no boat strands a passenger on the far shore."""
    by_id = {b["id"]: b for b in boats}
    for b in boats:
        back = by_id.get(b["returnBy"])
        if (back is None or back["map"] != b["destination"] or back["destination"] != b["map"]
                or back["returnBy"] != b["id"]):
            raise PublishError(f"{b['id']}: portal.returnBy {b['returnBy']!r} is not a boat on {b['destination']} "
                               f"that sails back to {b['map']} and names {b['id']} as its way back")


def approach_for(region, tile, radius, codes, reached, npc_posts, triggers, frame_table):
    """The nearest tile within the target's radius a walker can stand on with its ring reached: not an NPC post,
    not a trigger (nearest first, then north-west first)."""
    frame = frame_table[region]
    x0, y0 = tile
    best = None
    limit = min(radius, APPROACH_SEARCH)
    for dy in range(-limit, limit + 1):
        for dx in range(-limit, limit + 1):
            x, y = x0 + dx, y0 + dy
            if not (dx or dy) or (region, (x, y)) in npc_posts or (region, x, y) in triggers:
                continue
            if all(frame.contains(x + ex, y + ey) and codes[region][y + ey, x + ex] and reached[region][y + ey, x + ex]
                   for ex, ey in RING):
                key = (max(abs(dx), abs(dy)), dx * dx + dy * dy, y, x)
                if best is None or key < best[0]:
                    best = (key, [x, y])
    if best is None:
        raise PublishError(f"{region} {list(tile)}: no approach tile within radius {radius}")
    return best[1]


PLACEHOLDER = re.compile(r"<T([XY]):([A-Za-z0-9_-]+)>")


def resolve_questlines(template, markers, region, *, people=()):
    """The overlay questlines.txt: the template's quest blocks with each TX/TY placeholder the marker's tile, and the
    stage tiles it used (for the checks)."""
    lines = [line for line in template.splitlines() if not line.lstrip().startswith("#")]
    while lines and not lines[0].strip():
        lines.pop(0)
    used = {}

    def substitute(match):
        axis, identity = match.group(1), match.group(2)
        hits = [(r, rows[identity]) for r, rows in markers.items() if identity in rows]
        if len(hits) != 1:
            raise PublishError(f"{QUESTLINES}: marker {identity!r} has {len(hits)} owners")
        owner, found = hits[0]
        if found is None or found[0] != "runtimePoints":
            raise PublishError(f"{QUESTLINES}: no runtime point {identity!r} on {region}")
        tile = found[1]["tile"]
        used[identity] = (owner, tile)
        return str(tile[0] if axis == "X" else tile[1])

    body = PLACEHOLDER.sub(substitute, "\n".join(lines).rstrip("\n") + "\n")
    def map_substitute(match):
        identity = match.group(1)
        owners = [r for r, rows in markers.items() if identity in rows]
        if len(owners) != 1:
            raise PublishError(f"{QUESTLINES}: map marker {identity!r} lacks a unique owner")
        return owners[0]
    body = re.sub(r"<MAP:([A-Za-z0-9_-]+)>", map_substitute, body)
    def npc_map(match):
        owners = {p["map"] for p in people if p["name"] == match.group(1)}
        if len(owners) != 1:
            raise PublishError(f"{QUESTLINES}: giver {match.group(1)!r} lacks a unique map")
        return owners.pop()
    body = re.sub(r"<NPCMAP:([^>]+)>", npc_map, body)
    if "<T" in body or "<MAP:" in body or "<NPCMAP:" in body or "QID" in body:
        raise PublishError(f"{QUESTLINES}: a placeholder is left unresolved")
    for number, line in enumerate(body.splitlines(), 1):
        if "#" in line or "|" in line:
            raise PublishError(f"{QUESTLINES}:{number}: a quest line may not hold '#' or '|'")
    header = ("# continent-v2 overlay: Landfall's side errands S1-S3 (quest ids 26-28).\n"
              f"# {GENERATED}\n"
              f"# Source: {QUESTLINES}; stage tiles from the active maps' runtime points.\n\n")
    return header + body, used


# --- the ferry's landing ---------------------------------------------------------------------------------------------

def ferry_landing(ctx, destination):
    """The destination's arrival as the legacy publication left it, every copy agreeing, checked walkable."""
    server = ctx.server
    copies = {}
    entry = server.geography.get(destination)
    if not entry or "arrival" not in entry:
        raise PublishError(f"the server's eloria/continent_geography.py MAPS has no arrival for {destination}")
    copies["server eloria/continent_geography.py MAPS"] = list(entry["arrival"])
    manifest = json.loads(server.manifest_raw)
    for item in manifest.get("maps", []):
        if item.get("id") == destination and "arrival" in item:
            copies["client_content_manifest.json maps[]"] = list(item["arrival"])
    region = manifest.get("continentGeography", {}).get("regions", {}).get(destination, {})
    if "arrival" in region:
        copies["client_content_manifest.json continentGeography"] = list(region["arrival"])
    client = Path(ctx.checkout) / CLIENT_PUBLICATION
    if client.is_file():
        published = read_json(client).get("regions", {}).get(destination, {})
        if "arrival" in published:
            copies["client " + CLIENT_PUBLICATION] = list(published["arrival"])
    values = {tuple(v) for v in copies.values()}
    if len(values) != 1:
        raise PublishError(f"{destination}'s arrival copies disagree: {copies}")
    tile = list(values.pop())
    if destination not in server.base_maps:
        raise PublishError(f"the ferry's destination {destination} is not a base map")
    sys.path.insert(0, str(server.root / "tools"))
    import authored_collision as A
    from eloria.collision import CollisionMap, with_storage_collision
    path = server.root / "tools" / "collision" / f"{destination}.escg.gz"
    if not path.is_file():
        raise PublishError(f"no vendored grid {path} for the ferry's destination")
    manifest_grids = read_json(server.root / "tools" / "collision" / "manifest.json")
    limit = int(manifest_grids["climbLimit"])
    storage = [(o.x, o.y) for o in server.base_interactives.values() if o.map_id == destination
               and o.role == "storage"]
    ground = with_storage_collision(CollisionMap.from_grid(A.read_grid(path)), storage)
    triggers = {(p.x, p.y) for p in server.base_portals if p.source == destination and p.object_id is None}
    npcs = {(n.x, n.y) for n in server.base_npcs if n.map_id == destination}
    x, y = tile
    problems = []
    if not ground.walkable(x, y):
        problems.append("the landing is not walkable")
    if (x, y) in triggers:
        problems.append("the landing is a walk-over trigger")
    if (x, y) in npcs:
        problems.append("an NPC stands on the landing")
    for dx, dy in NEIGHBOURS:
        if not ground.walkable(x + dx, y + dy):
            problems.append(f"({x + dx}, {y + dy}) beside it is not walkable")
        elif not ground.can_step(x, y, x + dx, y + dy, limit):
            problems.append(f"({x + dx}, {y + dy}) beside it cannot be stepped to")
        elif (x + dx, y + dy) in triggers:
            problems.append(f"({x + dx}, {y + dy}) beside it is a walk-over trigger")
    if problems:
        raise PublishError(f"the ferry's landing {destination} {tile} is refused: " + "; ".join(problems))
    return {"tile": tile, "copies": copies, "grid": str(path.relative_to(server.root).as_posix()),
            "gridSha256": sha256_file(path)}


# --- the files -------------------------------------------------------------------------------------------------------

README = """continent-v2 overlay
====================

{generated}

The continent-v2 isles (Landfall, The Tollholms and The Gull Skerries) are served from this directory,
beside the profile's certified tables, which stay byte-identical. Each content loader reads the file of the same name
here and appends its rows after every base row (eloria/content_overlay.py holds the rules it enforces at startup);
`continent_v2_overlay = 0` in server.txt, or ELORIA_CONTENT_OVERLAY=0, serves the profile without it.

  maps.txt                    the exterior and shared interior maps, land crossings, ferry, boats, and underground
                              doors
  spawns.txt                  the isles' wild animals and underground encounters, each with its leash
  harvesting.txt              the resources the isles add, and every harvest node
  npcs.txt                    the isles' new people
  interactives.txt            the Landing Register desk, ferry, boats, storage, and underground doors
  exterior_connections.json   the land links between the isles
  questlines.txt              Landfall's side errands (published from M2, with the chapter's code)
  landing.json                Signed Ashore's places (eloria/landing.py)
  homes.json                  the home's points, read only while home_map moves the home (eloria/home.py)
  home_npcs.txt               the people the home migration moves, read only while home_map moves the home

Every position comes from the client's scene markers and content tables through the territory frame
(eloria-assets/maps/continent-v2/_continent_v2/frames.py); the client records what it published from in
eloria-assets/maps/continent-v2/_continent_v2/publication.json.
"""


def table_text(lines, header):
    return "".join(f"# {line}\n" if line else "#\n" for line in header) + "\n" + "".join(line + "\n" for line in lines)


def overlay_files(ctx, pub):
    """{file name: bytes} of the whole overlay directory."""
    labels = {e["id"]: e["label"] for e in frames.catalog_entries(ctx.checkout)}
    files = {"README": crlf(README.format(generated=GENERATED))}
    lines = [f"map | {m['id']} | {plain_field(labels[m['id']], m['id'] + ' label')} | "
             f"{plain_field(m['file'], m['id'] + ' file')} | {plain_field(m['alias'], m['id'] + ' alias')}"
             for m in pub.map_rows]
    for connection in ctx.crossings["connections"]:
        identities = [end["region"] for end in connection["ends"]]
        rows = [row for row in pub.lanes if {row[0], row[3]} == set(identities)]
        lines.append("")
        each = Counter(row[0] for row in rows)
        lines.append(f"# {connection['id']} ({'road' if connection.get('road', True) else 'roadless'} border): "
                     + ", ".join(f"{each[r]} lanes from {r}" for r in identities))
        for row in rows:
            lines.append("portal | " + " | ".join(str(v) for v in row))
    for f in pub.ferries:
        lines.append("")
        lines.append(f"# the exit ferry, one way: object {f['object']} on {f['map']}; it lands on {f['destination']}'s "
                     "arrival")
        lines.append(f"portal | {f['map']} | {f['object']} | {f['tile'][0]} | {f['tile'][1]} | {f['destination']} | "
                     f"{f['landing'][0]} | {f['landing'][1]}")
    for b in pub.boats:
        lines.append("")
        lines.append(f"# an isle boat, one way, paired with {b['returnBy']}: object {b['object']} on {b['map']}; it "
                     f"lands on {b['destination']}'s {b['landingMarker']}")
        lines.append(f"portal | {b['map']} | {b['object']} | {b['tile'][0]} | {b['tile'][1]} | {b['destination']} | "
                     f"{b['landing'][0]} | {b['landing'][1]}")
    files["maps.txt"] = crlf(table_text(lines, [
        "continent-v2 overlay: the isles' maps, their land crossings, the exit ferry and the isle boats.", GENERATED,
        "Lanes: crossings.json (crossings_v2.py); a lane's arrival is its departure cell read in the neighbour's frame."]))
    lines = []
    for region in pub.regions:
        rows = [s for s in pub.spawns if s["map"] == region]
        if not rows:
            continue
        if lines:
            lines.append("")
        lines.append(f"# {region}: {len(rows)} rows from {V2}/{region}/content/spawns.json")
        lines += [f"spawn | {s['map']} | {s['creature']} | {s['tile'][0]} | {s['tile'][1]} | leash:{s['leash']}"
                  for s in rows]
    files["spawns.txt"] = crlf(table_text(lines, [
        "continent-v2 overlay: the isles' wild animals, each held by its own leash.", GENERATED]))
    lines = [f"resource | {plain_field(r['name'], 'resource')} | {int(r['level'])} | {int(r['experience'])} | "
             f"{r['seconds']} | {plain_field(r['tool'], 'tool')}" for r in pub.resources]
    lines += [f"node | {n['map']} | {n['id']} | {n['tile'][0]} | {n['tile'][1]} | {n['resource']}" for n in pub.nodes]
    files["harvesting.txt"] = crlf(table_text(lines, [
        "continent-v2 overlay: the resources the isles add, and every harvest node (from the scene's markers).",
        GENERATED, "No row may carry a '#': this table's loader does not strip an inline comment."]))
    lines = [f"npc | {p['name']} | {p['map']} | {p['tile'][0]} | {p['tile'][1]} | {p['role']} | "
             f"{npc_portrait(p['actorType'], p.get('occupation', ''), p.get('facing', ''))} | {p['greeting']}" for p in pub.new_people]
    files["npcs.txt"] = crlf(table_text(lines, [
        "continent-v2 overlay: the isles' new people at their scene posts.", GENERATED,
        "No row may carry a '#': this table's loader does not strip an inline comment."]))
    lines = [f"{i['map']} | {i['object']} | {i['tile'][0]} | {i['tile'][1]} | {i['role']} | {i['target']} | "
             f"{i['text']}" for i in pub.interactives]
    files["interactives.txt"] = crlf(table_text(lines, [
        "continent-v2 overlay: the isles' interactive objects.", GENERATED,
        "No row may carry a '#': this table's loader does not strip an inline comment."]))
    files["exterior_connections.json"] = json_crlf({**ctx.crossings["exteriorSettings"],
                                                    "connections": ctx.crossings["exteriorConnections"]})
    files["questlines.txt"] = crlf(pub.questlines)
    files["landing.json"] = json_crlf(pub.landing)
    files["homes.json"] = json_crlf(pub.homes)
    lines = []
    for p in pub.rehomed:
        base = list(p["base"])
        if p.get("facing"):
            options = portrait_options(base[6])
            options["facing"] = p["facing"]
            base[6] = ",".join(f"{key}={value}" for key, value in options.items())
        row = ["npc", p["name"], p["map"], str(p["tile"][0]), str(p["tile"][1]), base[5], base[6], p["greeting"]]
        if len(base) == 9:
            row.append(base[8])
        lines.append(" | ".join(row))
    files["home_npcs.txt"] = crlf(table_text(lines, [
        "continent-v2 overlay: the people the home migration moves, at their isle posts.", GENERATED,
        "Read before npcs.txt, and only while home_map names a map other than four_gates (eloria/home.py): each row is",
        "the person's npcs.txt row with only the map, the tile, facing and the greeting changed.",
        "No row may carry a '#': the NPC loader does not strip an inline comment."]))
    for name in ("harvesting.txt", "npcs.txt", "interactives.txt", "questlines.txt", "home_npcs.txt"):
        for number, line in enumerate(files[name].decode("utf-8").splitlines(), 1):
            if line.strip() and not line.lstrip().startswith("#") and "#" in line:
                raise PublishError(f"{name}:{number}: an overlay row carries a '#'")
    assert list(files) == list(FILES), list(files)
    return files


# --- validating with the server's own code ---------------------------------------------------------------------------

def validate_with_server(ctx, pub):
    """Load the overlay with the server's loaders over a copy of the base tables, and parse landing.json, homes.json
    and home_npcs.txt with the server's chapter and home code when the server tree has it."""
    from eloria.maps import load_maps
    from eloria.spawns import load_spawns
    from eloria.harvesting import load_harvesting
    from eloria.npcs import load_npcs
    from eloria.interactives import load_interactives
    from eloria.questlines import load_questlines
    from eloria.exterior_connections import load_land_connections, load_land_frames
    report = {}
    with tempfile.TemporaryDirectory(prefix="publish_server_") as scratch:
        profile = Path(scratch) / "eloria"
        (profile / OVERLAY).mkdir(parents=True)
        for name in LOADER_TABLES:
            source = ctx.server.profile / name
            if source.is_file():
                shutil.copyfile(source, profile / name)
        for name, data in pub.files.items():
            (profile / OVERLAY / name).write_bytes(data)
        for name in PRESERVED_FILES:
            source = ctx.server.profile / OVERLAY / name
            if source.is_file():
                shutil.copyfile(source, profile / OVERLAY / name)
        maps, portals = load_maps(profile / "maps.txt", overlay=True)
        report["maps"] = len(maps)
        report["portals"] = len(portals)
        report["spawns"] = len(load_spawns(profile / "spawns.txt", overlay=True))
        resources, nodes = load_harvesting(profile / "harvesting.txt", overlay=True)
        report["resources"], report["nodes"] = len(resources), len(nodes)
        report["npcs"] = len(load_npcs(profile / "npcs.txt", overlay=True))
        report["interactives"] = len(load_interactives(profile / "interactives.txt", overlay=True))
        report["questlines"] = len(load_questlines(profile / "questlines.txt", overlay=True))
        land = load_land_connections(profile / "exterior_connections.json", overlay=True)
        frames_ = load_land_frames(profile / "exterior_connections.json", overlay=True)
        isles = set(pub.regions)
        report["landPairs"] = sorted(f"{a}-{b}" for a, b in land if a in isles or b in isles)
        report["landFrames"] = sorted(f"{a}-{b}" for a, b in frames_ if a in isles or b in isles)
        for (a, b), (near, far) in frames_.items():
            if a in isles:
                for source, x, y, destination, ax, ay in pub.lanes:
                    if (source, destination) == (a, b):
                        from eloria.exterior_connections import neighbour_tile
                        if tuple(neighbour_tile((near, far), x, y)) != (ax, ay):
                            raise PublishError(f"the server's land frames send {a} ({x}, {y}) elsewhere than the "
                                               f"lane's arrival ({ax}, {ay})")
        expected_pairs = {(a["region"], b["region"]) for c in ctx.crossings["connections"]
                          for a, b in (c["ends"], c["ends"][::-1])}
        if {pair for pair in land if pair[0] in isles} != expected_pairs:
            raise PublishError(f"the server reads land pairs {sorted(land)} from the overlay, not {expected_pairs}")
        own_rules(pub)
        report["landingParser"] = report["homesParser"] = "this tool's rules (the server tree has no "\
            "eloria/landing.py / eloria/home.py)"
        try:
            landing_module = importlib.import_module("eloria.landing")
        except ImportError:
            landing_module = None
        if landing_module is not None:
            layout = landing_module.load_layout(profile / OVERLAY / "landing.json")
            report["landingParser"] = f"eloria.landing.parse_layout: {len(layout.targets)} targets, " \
                                      f"{len(layout.cast)} cast"
        try:
            home_module = importlib.import_module("eloria.home")
        except ImportError:
            home_module = None
        if home_module is not None:
            homes = home_module.load_homes(profile / OVERLAY / "homes.json")
            rows = home_module.read_home_npcs(profile / OVERLAY / "home_npcs.txt", home_map=pub.landing["map"],
                                              base=load_npcs(profile / "npcs.txt", overlay=False), allowed_maps=pub.regions)
            report["homesParser"] = f"eloria.home.parse_homes: {sorted(homes)}; read_home_npcs: {len(rows)} rows"
    return report


def own_rules(pub):
    """landing.json and homes.json held to the schemas the server's chapter and home code document."""
    land = pub.landing
    tile_ok = lambda t: isinstance(t, list) and len(t) == 2 and all(type(n) is int and 0 <= n <= 0xFFFF for n in t)
    if set(land) - {"schema", "map", "arrival", "objects", "targets", "cast", "provenance"} or \
            land["schema"] != LANDING_SCHEMA or not tile_ok(land["arrival"]):
        raise PublishError("landing.json breaks eloria-landing-v1")
    if set(land["objects"]) != {"register", "ferry"} or land["objects"]["register"] == land["objects"]["ferry"]:
        raise PublishError("landing.json objects must name the register and the ferry")
    for key, entry in land["targets"].items():
        if not set(entry) <= {"map", "tile", "approach", "radius"} or not tile_ok(entry["tile"]) or \
                ("approach" in entry and not tile_ok(entry["approach"])):
            raise PublishError(f"landing.json target {key} breaks eloria-landing-v1")
    if sorted(c["name"] for c in land["cast"]) != sorted({c["name"] for c in land["cast"]}) or \
            not all({"name", "map", "tile"} <= set(c) <= {"name", "map", "tile", "facing"}
                    and tile_ok(c["tile"])
                    and c.get("facing", "N") in ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
                    for c in land["cast"]):
        raise PublishError("landing.json cast breaks eloria-landing-v1")
    homes = pub.homes
    if set(homes) - {"schema", "homes", "provenance"} or homes["schema"] != HOMES_SCHEMA or not homes["homes"]:
        raise PublishError("homes.json breaks eloria-homes-v1")
    for region, points in homes["homes"].items():
        if region == "four_gates" or set(points) != set(HOME_ROLES) or not all(tile_ok(t) for t in points.values()):
            raise PublishError(f"homes.json home {region} breaks eloria-homes-v1")


# --- the manifest ----------------------------------------------------------------------------------------------------

def manifest_bytes(ctx, pub, stage):
    """client_content_manifest.json with the isles' maps[] entries and the continentV2 block of `stage`."""
    import publish_continent_geography as shared
    raw = ctx.server.manifest_raw
    data = json.loads(raw)
    if shared.json_bytes(data).replace(b"\n", b"\r\n") != raw:
        raise PublishError(f"{MANIFEST}: re-serializing it does not reproduce it byte for byte; this tool will not "
                           "rewrite it (splice the entries by hand)")
    before = {key: copy.deepcopy(data[key]) for key in ("diagonalContinent", "continentGeography") if key in data}
    portals = {}
    for row in pub.lanes:
        portals.setdefault(row[0], []).append({"server_tile": [row[1], row[2]], "destination": row[3]})
    for f in pub.ferries + pub.boats:
        portals.setdefault(f["map"], []).append({"server_tile": list(f["tile"]), "destination": f["destination"]})
    entries = []
    for m in pub.map_rows:
        region = m["id"]
        frame = ctx.frames[region]
        transform = copy.deepcopy(ctx.packages[region]["manifest"]["coordinateTransform"])
        entries.append({"id": region, "server_cells": frame.cells[0], "arrival": list(pub.arrivals[region]),
                        "server_origin": list(frame.origin), "coordinateTransform": transform,
                        "serverCells": list(frame.cells), "serverStorageVersion": 1, "serverTileMin": [0, 0],
                        "portals": portals.get(region, [])})
    retired = set(read_json(ctx.checkout / frames.CATALOG).get("retiredMapIds", ()))
    entries.extend(U.manifest_entries(pub))
    if pub.underground is not None:
        for source, _object, x, y, destination, _ax, _ay in pub.underground.portals:
            entry = next(e for e in entries if e["id"] == source)
            entry["portals"].append({"server_tile": [x, y], "destination": destination})
    maps = data.setdefault("maps", [])
    maps[:] = [m for m in maps if m.get("id") not in retired]
    for entry in entries:
        at = next((k for k, item in enumerate(maps) if item.get("id") == entry["id"]), None)
        if at is None:
            maps.append(entry)
        else:
            maps[at] = entry
    data[MANIFEST_BLOCK] = manifest_block(ctx, pub, stage)
    for key, value in before.items():
        if data[key] != value:
            raise PublishError(f"{key} would change")
    return shared.json_bytes(data).replace(b"\n", b"\r\n"), entries


def boat_entries(pub):
    """The isle boats as the manifest block, the record and the summary list them: one entry each way."""
    return [{"map": b["map"], "object": b["object"], "trigger": b["tile"], "destination": b["destination"],
             "landing": b["landing"], "landingMarker": b["landingMarker"], "returnBy": b["returnBy"]}
            for b in pub.boats]


def manifest_block(ctx, pub, stage):
    block = {
        "schema": 1, "tool": TOOL, "stage": stage,
        "overlay": {"directory": f"{PROFILE}/{OVERLAY}",
                    "files": {name: sha256_bytes(pub.files[name]) for name in stage_files(stage)}},
        "maps": {m["id"]: {"name": pub.catalog[m["id"]]["label"], "alias": m["alias"],
                           "serverOrigin": list(ctx.frames[m["id"]].origin),
                           "serverCells": list(ctx.frames[m["id"]].cells),
                           "translation": list(ctx.frames[m["id"]].translation),
                           "arrival": list(pub.arrivals[m["id"]]),
                           "servedGridSha256": ctx.packages[m["id"]]["servedGridSha256"],
                           "collisionSha256": ctx.packages[m["id"]]["collisionSha256"],
                           "snapshotSha256": ctx.bakes[m["id"]].sha256,
                           "sceneSha256": ctx.bakes[m["id"]].scene_sha256}
                 for m in pub.map_rows},
        "crossingsSha256": ctx.crossings_sha256,
        "ferries": [{"map": f["map"], "object": f["object"], "trigger": f["tile"], "destination": f["destination"],
                     "landing": f["landing"]} for f in pub.ferries],
        "boats": boat_entries(pub),
        "heldBack": pub.held,
        "rowCounts": {"spawnsByMap": dict(Counter(row["map"] for row in pub.spawns)),
                      "nodes": len(pub.nodes), "newNpcs": len(pub.new_people),
                      "rehomedNpcs": len(pub.rehomed), "interactives": len(pub.interactives)},
    }
    if getattr(pub, "underground", None) is not None:
        u = pub.underground
        block["interiorMaps"] = {u.region: u.metadata}
        block["undergroundPortals"] = u.portals
        block["undergroundRows"] = u.rows
    return block


# --- vendoring -------------------------------------------------------------------------------------------------------

def run_sync(server, maps_root, region, out=None):
    command = [sys.executable, "-B", str(Path(server) / "tools" / "sync_authored_collision.py"),
               "--client", str(maps_root), "--region", region]
    if out is not None:
        command += ["--out", str(out)]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(command, cwd=str(server), env=env, capture_output=True, text=True)
    if result.returncode:
        raise PublishError(f"the server's sync refused {region}: {result.stdout.strip()} {result.stderr.strip()}")
    return result.stdout.strip()


def vendor(ctx, regions, out):
    """Run the server's sync for each map into `out` (the server's tools/collision, or a scratch folder seeded with
    its manifest); check the header discipline (AC-6) and that the vendored file is the package's byte for byte."""
    retired = retired_maps(ctx, regions)
    lines = []
    for region in regions:
        lines.append(run_sync(ctx.server.root, ctx.maps_root, region, out))
        blob = (Path(out) / f"{region}.escg.gz").read_bytes()
        if blob != ctx.packages[region]["servedBytes"]:
            raise PublishError(f"{region}: the vendored grid differs from the package's served-grid.escg.gz")
        grid = ctx.codec.served_grid.decode_file(blob)          # the codec refuses a header whose flags are not 0
        if (grid.climb_mm, grid.unit_mm, grid.datum_mm) != (1000, 50, -100000):
            raise PublishError(f"{region}: the vendored header states climb {grid.climb_mm} unit {grid.unit_mm} "
                               f"datum {grid.datum_mm}")
    if retired:
        manifest_path = Path(out) / "manifest.json"
        manifest = read_json(manifest_path)
        manifest["maps"] = [row for row in manifest.get("maps", []) if row.get("map") not in retired]
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
        for region in retired:
            (Path(out) / f"{region}.escg.gz").unlink(missing_ok=True)
    return lines


def retired_maps(ctx, active):
    """Explicit catalog retirements only; never infer a grid deletion from the active map set."""
    values = read_json(ctx.checkout / frames.CATALOG).get("retiredMapIds", [])
    if not isinstance(values, list) or any(not isinstance(v, str) or
                                         re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", v) is None for v in values):
        raise PublishError("catalog retiredMapIds must be safe map IDs")
    retired = set(values)
    if retired.intersection(active):
        raise PublishError("catalog cannot retire an active map")
    return retired


def strip_sources(manifest, regions):
    out = copy.deepcopy(manifest)
    for entry in out.get("maps", []):
        if entry.get("map") in regions:
            entry.pop("source", None)
    return out


# --- the record ------------------------------------------------------------------------------------------------------

def record_bytes(ctx, pub, manifest_entries):
    """The client's record of the publication: isle facts only (the inputs' digests, every row count, every file of
    every stage), so it reads the same whatever the server tree's base tables, code or stage are; the server's
    loader counts and parser checks go to the run's summary (--report), never here."""
    record = {
        "schema": RECORD_SCHEMA, "tool": TOOL,
        "about": "what publish_server.py served from what, by SHA-256: rerun it with --check to compare a server tree. "
                 "servedReachTiles is the union reach with every NPC post standing (closed).",
        "maps": {region: {"frame": {"origin": list(ctx.frames[region].origin), "cells": list(ctx.frames[region].cells),
                                    "translation": list(ctx.frames[region].translation)},
                          "bake": {"snapshotSha256": ctx.bakes[region].sha256,
                                   "sceneSha256": ctx.bakes[region].scene_sha256},
                          "package": {"collisionSha256": ctx.packages[region]["collisionSha256"],
                                      "servedGridSha256": ctx.packages[region]["servedGridSha256"]},
                          "arrival": list(pub.arrivals[region]),
                          "rows": {"spawns": sum(1 for s in pub.spawns if s["map"] == region),
                                   "nodes": sum(1 for n in pub.nodes if n["map"] == region),
                                   "npcs": sum(1 for p in pub.new_people if p["map"] == region),
                                   "homeNpcs": sum(1 for p in pub.rehomed if p["map"] == region),
                                   "interactives": sum(1 for i in pub.interactives if i["map"] == region),
                                   "laneDepartures": sum(1 for row in pub.lanes if row[0] == region)},
                          "npcPosts": sum(1 for p in pub.new_people + pub.rehomed if p["map"] == region),
                          "servedReachTiles": int(pub.reached[region].sum())}
                 for region in pub.regions},
        "inputs": {"crossingsSha256": ctx.crossings_sha256, "contentTables": ctx.tables.shas},
        "ferries": [{"map": f["map"], "object": f["object"], "trigger": f["tile"], "destination": f["destination"],
                     "landing": f["landing"]} for f in pub.ferries],
        "boats": boat_entries(pub),
        "heldBack": pub.held,
        "server": {"overlay": {name: sha256_bytes(data) for name, data in pub.files.items()},
                   "stages": {stage: {"files": list(stage_files(stage)),
                                      "manifestBlockSha256": sha256_bytes(json.dumps(
                                          manifest_block(ctx, pub, stage), sort_keys=True).encode())}
                              for stage in STAGES},
                   "manifestEntriesSha256": sha256_bytes(json.dumps(manifest_entries, sort_keys=True).encode()),
                   "vendored": {region: ctx.packages[region]["servedGridSha256"] for region in pub.vendor_regions}},
    }
    if pub.underground is not None:
        record["interiors"] = {pub.underground.region: {**pub.underground.metadata,
                              "rows": pub.underground.rows, "walkableTiles": pub.underground.walkable}}
    return (json.dumps(record, indent=1, ensure_ascii=False) + "\n").encode("utf-8")


# --- the command -----------------------------------------------------------------------------------------------------

def gather(a, *, log=say):
    checkout = a.checkout.resolve()
    codec = X.server_codec(a.server)
    importlib.import_module("publish_continent_geography")
    frame_table = {region: frames.load(region, checkout) for region in frames.regions(checkout)}
    bakes = {}
    for item in a.bake:
        region, _, directory = item.partition("=")
        if not directory or region in bakes:
            raise PublishError(f"--bake {item!r}: give REGION=DIR once per map")
        if region not in frame_table:
            raise PublishError(f"--bake {region}: not in the continent-v2 catalog")
        bakes[region] = read_bake(region, directory, checkout, frame_table[region])
    if set(bakes) != set(frame_table):
        raise PublishError(f"give a bake for every map of the catalog: {sorted(frame_table)}")
    maps_root = (a.maps_root or checkout / "eloria-assets" / "maps").resolve()
    packages = packages_of(checkout, maps_root, codec, bakes)
    for region, entry in packages.items():
        entry["grid"] = codec.served_grid.decode_file(entry["servedBytes"])
    plan_path = checkout / X.PLAN
    crossings_path = (a.crossings or checkout / CV.DEFAULT_OUT)
    crossings = CV.load(crossings_path, packages, sha256_file(plan_path))
    server = server_side(a.server, codec, list(frame_table), frame_table,
                         {r: e["arrival"] for r, e in packages.items()})
    tables = content_tables(checkout, list(frame_table))
    return SimpleNamespace(checkout=checkout, codec=codec, frames=frame_table, bakes=bakes, maps_root=maps_root,
                           packages=packages, crossings=crossings, crossings_sha256=sha256_file(crossings_path),
                           server=server, tables=tables, record=(a.record or checkout / DEFAULT_RECORD))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--server", required=True, type=Path, help="the server checkout to publish into")
    ap.add_argument("--bake", action="append", required=True, metavar="REGION=DIR",
                    help="the region bake each package was published from")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="compare with the server tree; write nothing")
    mode.add_argument("--apply", action="store_true", help="vendor the grids and write the overlay and the manifest")
    ap.add_argument("--stage", required=True, choices=STAGES,
                    help="the serve plan's milestone the server tree is at: m1 serves every overlay file but "
                         "questlines.txt, which m2 adds (it needs eloria/landing.py, the chapter's code, in the tree)")
    ap.add_argument("--maps-root", type=Path, default=None,
                    help="the folder holding continent-v2/<region>/client/ (default: eloria-assets/maps here)")
    ap.add_argument("--crossings", type=Path, default=None, help=f"crossings.json (default {CV.DEFAULT_OUT})")
    ap.add_argument("--record", type=Path, default=None, help=f"the publication record (default {DEFAULT_RECORD})")
    ap.add_argument("--checkout", type=Path, default=DEFAULT_CHECKOUT)
    ap.add_argument("--report", type=Path, default=None, help="also write the run's summary JSON here")
    a = ap.parse_args(argv)
    started = time.time()
    try:
        missing = [path for path in STAGE_CODE[a.stage] if not (Path(a.server) / path).is_file()]
        if missing:
            raise PublishError(f"stage {a.stage} needs {missing} in the server tree (the serve plan's {a.stage.upper()} "
                               "code lands before its data): publish an earlier stage")
        ctx = gather(a)
        pub = compose(ctx)
        validation = validate_with_server(ctx, pub)
        manifest, entries = manifest_bytes(ctx, pub, a.stage)
        record = record_bytes(ctx, pub, entries)
        served = stage_files(a.stage)
        server = ctx.server.root
        overlay_dir = server / PROFILE / OVERLAY
        unknown = sorted(p.name for p in overlay_dir.iterdir()
                         if p.name not in FILES + PRESERVED_FILES) if overlay_dir.is_dir() else []
        if unknown:
            raise PublishError(f"{overlay_dir} holds files this tool does not write: {unknown}")
        later = [name for name in FILES if name not in served and (overlay_dir / name).exists()]
        summary = {"mode": "check" if a.check else "apply", "stage": a.stage, "files": list(served),
                   "rows": {k: v for k, v in json.loads(record)["maps"].items()},
                   "lanes": len(pub.lanes), "heldBack": pub.held,
                   "ferries": [{"map": f["map"], "object": f["object"], "trigger": f["tile"],
                                "destination": f["destination"], "landing": f["landing"],
                                "landingCopies": f["landingCheck"]["copies"], "landingGrid": f["landingCheck"]["grid"],
                                "landingGridSha256": f["landingCheck"]["gridSha256"]} for f in pub.ferries],
                   "boats": boat_entries(pub),
                   "serverLoaders": validation}
        if a.check:
            differences = []
            for name in served:
                path = overlay_dir / name
                if not path.is_file() or path.read_bytes() != pub.files[name]:
                    differences.append(f"{PROFILE}/{OVERLAY}/{name}")
            differences += [f"{PROFILE}/{OVERLAY}/{name} (not served at {a.stage})" for name in later]
            if ctx.server.manifest_path.read_bytes() != manifest:
                differences.append(f"{PROFILE}/{MANIFEST}")
            record_path = Path(ctx.record)
            if not record_path.is_file() or record_path.read_bytes() != record:
                differences.append(str(record_path))
            with tempfile.TemporaryDirectory(prefix="publish_server_vendor_") as scratch:
                collision = server / "tools" / "collision"
                shutil.copyfile(collision / "manifest.json", Path(scratch) / "manifest.json")
                vendor(ctx, pub.vendor_regions, scratch)
                for region in pub.vendor_regions:
                    mine = collision / f"{region}.escg.gz"
                    if not mine.is_file() or mine.read_bytes() != (Path(scratch) / f"{region}.escg.gz").read_bytes():
                        differences.append(f"tools/collision/{region}.escg.gz")
                for region in retired_maps(ctx, pub.regions):
                    if (collision / f"{region}.escg.gz").exists():
                        differences.append(f"tools/collision/{region}.escg.gz (retired)")
                theirs = json.loads((Path(scratch) / "manifest.json").read_text(encoding="utf-8"))
                mine = json.loads((collision / "manifest.json").read_text(encoding="utf-8"))
                if strip_sources(theirs, pub.vendor_regions) != strip_sources(mine, pub.vendor_regions):
                    differences.append("tools/collision/manifest.json")
                elif theirs != mine:
                    summary["provenanceOnly"] = ("tools/collision/manifest.json differs only in the isles' recorded "
                                                 "source (the client commit the sync names)")
            summary["differences"] = differences
            summary["check"] = "clean" if not differences else "differs"
        else:
            summary["vendored"] = vendor(ctx, pub.vendor_regions, server / "tools" / "collision")
            overlay_dir.mkdir(parents=True, exist_ok=True)
            for name in served:
                (overlay_dir / name).write_bytes(pub.files[name])
            for name in later:
                (overlay_dir / name).unlink()
            ctx.server.manifest_path.write_bytes(manifest)
            Path(ctx.record).parent.mkdir(parents=True, exist_ok=True)
            Path(ctx.record).write_bytes(record)
            for name in served:
                if (overlay_dir / name).read_bytes() != pub.files[name]:
                    raise PublishError(f"{name} did not read back as written")
            summary["written"] = [f"{PROFILE}/{OVERLAY}/{name}" for name in served] + [f"{PROFILE}/{MANIFEST}",
                                                                                       str(ctx.record)]
            summary["removed"] = [f"{PROFILE}/{OVERLAY}/{name}" for name in later]
    except (PublishError, CV.CrossingsError, X.ExportError, frames.FrameError) as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1
    summary["seconds"] = round(time.time() - started, 1)
    text = json.dumps(summary, indent=1, ensure_ascii=False)
    if a.report:
        Path(a.report).write_text(text + "\n", encoding="utf-8", newline="\n")
    print(text)
    return 0 if a.apply or summary["check"] == "clean" else 1


if __name__ == "__main__":
    sys.exit(main())
