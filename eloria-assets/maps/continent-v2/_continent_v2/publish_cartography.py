"""publish_cartography.py: the rebuilt continent's tab maps, for the game client's map window.

  python -B eloria-assets/maps/continent-v2/_continent_v2/publish_cartography.py [--check] [--checkout <worktree>]

The client's Tab map and minimap lay a region's own picture under the map cameras when cartography names it (main.gd
_install_map_picture, src/world/map_picture.gd), and draw the neighbours' pictures beside it; without one they show
the live world, and a chunk-streamed isle holds only the chunks round the player. The twelve-territory continent's
cartography is godot-client/data/maps/cartography.json, which eloria-assets/tools/build_continent_map.py derives for
the regions continent-layout.json lays out on that continent's picture. That tool cannot take the continent-v2
territories, and is not edited for them: it lays out only the twelve, and its own bytes are an input the continent's
master atlas certifies (nymara-regions/_continent/cartography/continent-atlas.json), so any edit makes test_cartography
fail until the whole master is rendered again from continent.glb.

So this tool writes their rows to a file of their own, godot-client/data/maps/cartography-continent-v2.json, in the
same shape as cartography.json's regions, and main.gd appends them after that file's rows. One row per territory the
server serves on the continent-v2 frame (registry status continent-v2-served, continentGeography.frame continent-v2),
in registry order:
  name            the package's asset name (the catalog label the registry row carries)
  serverMap       the map id
  frame           "continent-v2": the client compares and draws outlines only within one frame
  tabMap          the package's minimap.webp (render_minimap.py draws it from the chunks), framed as the live Tab map
                  frames the territory (build_continent_map.framing, tab_map_crop, crop_world: imported, never copied)
  continentPolygon, continentLabel   the ownership polygon and its area centroid, in cartography.json's pixel
                  lattice (its continent originMetres and metresPerPixel), so main.gd turns them into the map's metres
                  as it turns every other row's
  globalTranslation   the registry row's continent translation
  serviceMarkers  the package's shop dots (publish_client.py: every NPC marker with a mapCategory)
  storageMarkers  the package's storage chests
  entranceMarkers every door into an interior that stands on this map, from every interior source (INTERIOR_SOURCES:
                  content/underground.json's caves through underground_source.doors, content/landfall_town.json's
                  building rooms through town_source.doors): its label (a building door's own `label`, else its
                  section's name), position [x, z] and height (the door's `position`: a cave's marker, a building's
                  painted door on the facade), serverTile (the door tile), objectId (main.gd hides the server's portal
                  P of that object under the dot), kind ("underground" | "building") and, for a building door that
                  leads into a shop, its category (map_categories.py). The client draws a building door as a round
                  dot in its category's colour (the tan entrance dot without one), labelled on hover only, a size down
                  on the minimap and not at all on the continent overview; a cave keeps its permanent label.
No row has a continentRect: the isles are not on the twelve-territory continent's picture.
The top-level interiors object holds what an interior's own map draws (an interior has no tab map row):
  interiors.<map id>.serviceMarkers   the interior's shopkeepers (a section's `npcs` with a mapCategory) as
                  {label, name, category, position [x, z], height, serverTile, section}, placed on their post tiles'
                  centres by the interior's coordinate transform (its registry row's, else the builders' frame: tile
                  (x, y) is world (x, h, cells - y)). main.gd draws those of the section the player stands in and hides
                  the shopkeeper's own blue dot by name, as on a territory. Omitted when no interior keeps a shop.
An unknown category is refused, never dropped (map_categories.py).
The separate overview object places all regions, including every ownership component, on a Landfall picture
composed from their existing minimaps. Its image-local polygons and row identities drive the clickable overview.

The boatNetwork object is the Landfall boat network (content/boat-network.json) as the overview draws it, in
continent metres (the overview's originMetres frame):
  docks           one per dock: its id, label and serverMap, its position (the middle of its boats), and its boats:
                  per berth the dock it sails to, the destination its "Bound for X." text names (the phrase
                  MapObject3D.destination() reads), its objectId and its position
  routes          one per route: its two docks and the points of its line (the two docks' positions)
A boat's position is its interactive marker in the map's scene (<map>--obj-boat-<other dock>, or the hand-authored
marker a route's "existing" names) plus the territory's translation; its row in content/server-rows.json must say
"Bound for <the other dock's label>.", so the map names what the boat says.

--check exits 1 when the file differs from what this tool writes (godot-client/tests/test_continent_v2_cartography.py
runs it): a picture was redrawn, a frame or polygon moved, a boat moved or a route changed, cartography.json's lattice
changed, or the file was edited by hand.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import io
import math

from PIL import Image, ImageChops, ImageDraw
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import map_categories as MC
import ownership
import underground_source as US

DEFAULT_CHECKOUT = Path(__file__).resolve().parents[4]
TOOL = "eloria-assets/maps/continent-v2/_continent_v2/publish_cartography.py"
REGISTRY = "godot-client/data/maps/registry.json"
CARTOGRAPHY = "godot-client/data/maps/cartography.json"
OUTPUT = "godot-client/data/maps/cartography-continent-v2.json"
OVERVIEW = "eloria-assets/maps/continent-v2/_continent_v2/cartography/landfall-map.webp"
BOAT_NETWORK = "eloria-assets/maps/continent-v2/_continent_v2/content/boat-network.json"
SERVER_ROWS = "eloria-assets/maps/continent-v2/_continent_v2/content/server-rows.json"
CATALOG = "godot-client/world_authoring/continent-v2/territories.json"
# MapObject3D.BOAT_DESTINATION_PHRASE: the client names a boat's destination by the words after it.
BOAT_PHRASE = "Bound for "
FRAME = "continent-v2"
SERVED_STATUSES = {"continent-v2-served"}
SCHEMA = "eloria-cartography-continent-v2-v1"
# The interiors' sources, in the order their doors are listed: (source, the module that reads its doors, the kind of
# door it holds unless a door names its own). A missing source has no doors.
INTERIOR_SOURCES = (
    ("eloria-assets/maps/continent-v2/_continent_v2/content/underground.json", "underground_source", "underground"),
    ("eloria-assets/maps/continent-v2/_continent_v2/content/landfall_town.json", "town_source", "building"),
)
DOOR_KINDS = ("underground", "building")


class CartographyError(ValueError):
    """A served territory this tool cannot give a tab map."""


def interior_sources(checkout: Path) -> list[tuple[str, dict, object, str]]:
    """Every interior source the checkout holds, as (its path, its JSON, its door reader module, its door kind)."""
    result = []
    for relative, reader_name, kind in INTERIOR_SOURCES:
        path = Path(checkout) / relative
        if not path.is_file():
            continue
        try:
            reader = US if reader_name == US.__name__ else importlib.import_module(reader_name)
        except ModuleNotFoundError as error:
            if error.name != reader_name:
                raise
            raise CartographyError(f"{relative} is read by _continent_v2/{reader_name}.py, which is missing") from None
        result.append((relative, read_json(path), reader, kind))
    return result


def section_doors(reader, section) -> list[dict]:
    """A section's doors through its source's reader; a reader without `doors` reads them as underground_source does
    (underground.py reader_of: the town's reader keeps the underground's functions it does not define)."""
    return getattr(reader, "doors", US.doors)(section)


def section_npcs(reader, section) -> list[dict]:
    """A section's NPCs through its source's reader (`npcs`), else its `npcs` rows (underground.py section_npcs)."""
    found = getattr(reader, "npcs", None)
    return list(found(section)) if found else list(section.get("npcs", []))


def entrance_markers(key: str, sources) -> list[dict]:
    """The entranceMarkers of map `key`: every door of every interior section that stands on it, in source order.

    sources is interior_sources(); each door comes from its source's reader (`doors(section)`)."""
    rows, seen = [], {}
    for relative, design, reader, default_kind in sources:
        for section in design.get("sections", []):
            for door in section_doors(reader, section):
                if door["map"] != key:
                    continue
                where = f"{relative} {section.get('id', '?')} door {door.get('index', '?')}"
                kind = door.get("kind", default_kind)
                if kind not in DOOR_KINDS:
                    raise CartographyError(f"{where}: kind {kind!r} is not one of {DOOR_KINDS}")
                object_id = int(door["object"])
                if object_id in seen:
                    raise CartographyError(f"{where}: object {object_id} is also {seen[object_id]}'s door on {key}")
                seen[object_id] = where
                row = {"label": str(door.get("label") or section["name"]),
                       "position": [door["position"][0], door["position"][2]],
                       "height": door["position"][1],
                       "serverTile": list(door["tile"]), "objectId": object_id, "kind": kind}
                category = door.get("category")
                if category is not None:
                    if kind != "building":
                        raise CartographyError(f"{where}: only a building door leads into a shop; a {kind} door "
                                               "keeps the tan entrance dot")
                    try:
                        row["category"] = MC.check(category, where)
                    except MC.CategoryError as error:
                        raise CartographyError(str(error)) from None
                rows.append(row)
    return rows


def service_category(key: str, mark: dict) -> str:
    """A package's shop dot category, checked (a package published before the table learnt a category is refused)."""
    try:
        return MC.check(mark["category"], f"{key} {mark.get('name', '?')}")
    except MC.CategoryError as error:
        raise CartographyError(str(error)) from None


def door_maps(sources) -> set[str]:
    """Every map a door of an interior source stands on."""
    return {door["map"] for _, design, reader, _ in sources for section in design.get("sections", [])
            for door in section_doors(reader, section)}


def tile_position(transform: dict, tile) -> tuple[list[float], float]:
    """A server tile's centre as the client places it ([x, z] metres, height): CoordinateAdapter.tile_center."""
    scale = float(transform.get("metresPerTile", 1.0))
    origin = [float(v) for v in transform.get("origin", [0, 0, 0])]
    server_origin = [float(v) for v in transform.get("serverOrigin", [0, 0])]
    local_x = float(tile[0]) + 0.5 - server_origin[0]
    local_y = float(tile[1]) + 0.5 - server_origin[1]
    z = -local_y if transform.get("invertServerY", True) else local_y
    return ([origin[0] + local_x * scale, origin[2] + z * scale],
            float(transform.get("walkingHeight", origin[1])))


def interior_transform(design: dict, registry: dict) -> dict:
    """The interior's coordinate transform: its registry row's (what the client places tiles by), else the builders'
    frame (build_underground.world: tile (x, y) is world (x, h, cells - y) at floor height 0)."""
    row = registry.get("maps", {}).get(design["map"]["id"])
    if isinstance(row, dict) and row.get("coordinateTransform"):
        return row["coordinateTransform"]
    cells = int(design["map"]["cells"])
    return {"metresPerTile": 1.0, "serverOrigin": [0, cells], "origin": [0, 0, 0], "walkingHeight": 0.0,
            "invertServerY": True}


def interior_service_markers(relative: str, design: dict, transform: dict, reader=US) -> list[dict]:
    """An interior's shopkeepers: every section `npcs` row with a mapCategory, on its post tile's centre."""
    marks = []
    for section in design.get("sections", []):
        for npc in section_npcs(reader, section):
            where = f"{relative} {section.get('id', '?')} {npc.get('name', '?')}"
            try:
                category = MC.service_category(npc, where)
            except MC.CategoryError as error:
                raise CartographyError(str(error)) from None
            if category is None:
                continue
            position, height = tile_position(transform, npc["tile"])
            marks.append({"label": str(npc.get("mapLabel") or npc["name"]), "name": str(npc["name"]),
                          "category": category, "position": position, "height": height,
                          "serverTile": [int(npc["tile"][0]), int(npc["tile"][1])], "section": section["id"]})
    return marks


def interiors(sources, registry: dict) -> dict:
    """The top-level interiors object: {map id: {serviceMarkers}} for every interior that keeps a shop."""
    result = {}
    for relative, design, reader, _kind in sources:
        marks = interior_service_markers(relative, design, interior_transform(design, registry), reader)
        if marks:
            map_id = design["map"]["id"]
            if map_id in result:
                raise CartographyError(f"{relative}: map {map_id} is another interior source's too")
            result[map_id] = {"serviceMarkers": marks}
    return result


def read_json(path: Path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def legacy_tool(checkout: Path):
    """eloria-assets/tools/build_continent_map.py of the checkout, imported (its framing rules are map_view.gd's)."""
    source = Path(checkout) / "eloria-assets" / "tools" / "build_continent_map.py"
    spec = importlib.util.spec_from_file_location("build_continent_map_for_v2", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def territories_tool(checkout: Path):
    """godot-client/tools/continent_v2_territories.py of the checkout, imported for its .tscn reader."""
    source = Path(checkout) / "godot-client" / "tools" / "continent_v2_territories.py"
    spec = importlib.util.spec_from_file_location("continent_v2_territories_for_cartography", source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # its dataclasses look their module up
    spec.loader.exec_module(module)
    return module


def polygon_centroid(points) -> list[float]:
    """The area centroid of a simple polygon: the label point of a territory."""
    area = cx = cz = 0.0
    for (x0, z0), (x1, z1) in zip(points, list(points[1:]) + list(points[:1])):
        cross = float(x0) * float(z1) - float(x1) * float(z0)
        area += cross
        cx += (float(x0) + float(x1)) * cross
        cz += (float(z0) + float(z1)) * cross
    if abs(area) < 1e-9:
        raise CartographyError("an ownership polygon without area")
    return [cx / (3.0 * area), cz / (3.0 * area)]


def served(registry: dict) -> list[tuple[str, dict]]:
    return [(key, entry) for key, entry in registry.get("maps", {}).items()
            if isinstance(entry, dict) and entry.get("status") in SERVED_STATUSES
            and (entry.get("continentGeography") or {}).get("frame") == FRAME]


def compose(checkout: Path = DEFAULT_CHECKOUT) -> dict:
    checkout = Path(checkout)
    tool = legacy_tool(checkout)
    registry = read_json(checkout / REGISTRY)
    continent = read_json(checkout / CARTOGRAPHY)["continent"]
    lattice = {"originMetres": continent["originMetres"], "metresPerPixel": continent["metresPerPixel"]}
    regions, sources = [], {}
    doors = interior_sources(checkout)
    unserved = sorted(door_maps(doors) - {key for key, _ in served(registry)})
    if unserved:
        raise CartographyError(f"interior doors stand on {unserved}, which no served territory is: their dots would "
                               "be dropped")
    water_rgb = None
    for key, entry in served(registry):
        manifest_path = tool.resource_to_path(entry["manifest"])
        manifest = read_json(manifest_path)
        minimap = manifest.get("minimap") or {}
        if not minimap.get("image"):
            raise CartographyError(f"{key}: the package has no map picture; run _continent_v2/render_minimap.py "
                                   f"--region {key} --apply")
        image_path = manifest_path.parent / minimap["image"]
        if not image_path.is_file():
            raise CartographyError(f"{key}: {image_path} is missing")
        colour = minimap.get("cartographyRender", {}).get("waterRGB", [79, 150, 157])
        if water_rgb is not None and colour != water_rgb:
            raise CartographyError(f"{key}: overview minimaps use different ocean colours")
        water_rgb = colour
        translation = [float(v) for v in entry["continentGeography"]["translation"]]
        geography = manifest.get("continentGeography") or {}
        if [float(v) for v in geography.get("translation", [])] != translation:
            raise CartographyError(f"{key}: the package's continent translation is not its registry row's")
        crop = tool.tab_map_crop(minimap, tool.framing(manifest))
        world_min, world_max = tool.crop_world(minimap, crop)
        polygons = ownership.rings(geography)
        shape = ownership.geometry(polygons)
        centroid = shape.centroid
        sources[key] = hashlib.sha256(image_path.read_bytes()).hexdigest()
        regions.append({
            "name": str(manifest.get("asset", {}).get("name", key)),
            "serverMap": key,
            "frame": FRAME,
            "tabMap": {"texture": tool.path_to_resource(image_path), "region": list(crop),
                       "worldMin": world_min, "worldMax": world_max},
            "continentPolygon": [tool.atlas_point(point, lattice) for point in polygons[0]],
            "continentPolygons": [[tool.atlas_point(point, lattice) for point in ring] for ring in polygons],
            "continentLabel": tool.atlas_point([centroid.x,centroid.y], lattice),
            "globalTranslation": translation,
            "serviceMarkers": [{"label": mark["label"], "name": mark["name"],
                                "category": service_category(key, mark),
                                "position": [mark["position"][0], mark["position"][2]],
                                "height": mark["position"][1], "serverTile": mark["serverTile"]}
                               for mark in manifest.get("serviceMarkers", [])],
            "storageMarkers": [{"label": mark.get("name", mark.get("label", "Storage")),
                                "position": [mark["position"][0], mark["position"][2]],
                                "serverTile": mark["serverTile"], "objectId": mark["objectId"]}
                               for mark in manifest.get("interactives", []) if mark.get("type") == "storage"],
            # every door of every interior section on this map (a section may have several: underground_source)
            "entranceMarkers": entrance_markers(key, doors),
        })
    data = {"schema": SCHEMA, "generator": TOOL,
            "note": ("The continent-v2 territories' tab maps, appended by the client after cartography.json's regions. "
                     "Generated: run the generator after a map picture, a frame or a polygon changes."),
            "frame": FRAME, "lattice": lattice, "sources": sources, "regions": regions}
    rooms = interiors(doors, registry)
    if rooms:
        data["interiors"] = rooms
    network = boat_network(checkout, dict(served(registry)))
    if network is not None:
        data["boatNetwork"] = network
    data["overview"] = overview_layout(data)
    data["overview"]["waterRGB"] = water_rgb
    data["overview"]["sha256"] = hashlib.sha256(overview_bytes(checkout, data)).hexdigest()
    return data


def boat_network(checkout: Path, served_maps: dict, network: dict | None = None,
                 rows: dict | None = None) -> dict | None:
    """The boat network's docks and routes in continent metres; None where the checkout has no network.

    served_maps is {map id: registry row} of the served territories; network and rows default to the checkout's
    content/boat-network.json and content/server-rows.json."""
    checkout = Path(checkout)
    if network is None:
        if not (checkout / BOAT_NETWORK).is_file():
            return None
        network = read_json(checkout / BOAT_NETWORK)
    if rows is None:
        rows = read_json(checkout / SERVER_ROWS)
    docks = network.get("docks", {})
    routes = network.get("routes", [])
    labels = {key: str(dock["label"]) for key, dock in docks.items()}
    sailed, existing = set(), {}
    for route in routes:
        a, b = route["docks"]
        for here, there in ((a, b), (b, a)):
            if here not in docks:
                raise CartographyError(f"the route {a}-{b} names no dock {here!r}")
            if there not in docks[here].get("berths", {}):
                raise CartographyError(f"{here}: no berth for its route to {there}")
            sailed.add((here, there))
        for here, marker in (route.get("existing") or {}).items():
            existing[(here, b if here == a else a)] = marker
    tool = territories_tool(checkout)
    scenes = {entry["id"]: entry["scenePath"] for entry in read_json(checkout / CATALOG)["entries"]}
    rows_by_map = rows.get("maps", {})
    placed, positions = [], {}
    for key, dock in docks.items():
        map_id = dock["map"]
        if map_id not in served_maps or map_id not in scenes:
            raise CartographyError(f"{key}: its map {map_id} is not served on the {FRAME} frame")
        translation = [float(v) for v in served_maps[map_id]["continentGeography"]["translation"]]
        scene = tool.load_scene(tool.res_to_path(scenes[map_id], checkout))
        boats = []
        for other in dock.get("berths", {}):
            if (key, other) not in sailed:
                raise CartographyError(f"{key}: its berth for {other} is on no route")
            marker = existing.get((key, other), f"{map_id}--obj-boat-{other}")
            path = "Gameplay/Interactives/" + marker
            if scene.node(path) is None:
                raise CartographyError(f"{key}: {scenes[map_id]} has no boat {marker}; run "
                                       "godot-client/tools/author_continent_v2_boats.py --apply")
            row = rows_by_map.get(map_id, {}).get("interactives", {}).get(marker)
            if row is None:
                raise CartographyError(f"{key}: content/server-rows.json serves no {marker}")
            wanted = f"{BOAT_PHRASE}{labels[other]}."
            if not str(row.get("text", "")).startswith(wanted):
                raise CartographyError(f"{marker}: its text does not begin {wanted!r}, so the map would name "
                                       "another destination than the boat")
            local = scene.world(path)[:3, 3]
            boats.append({"to": other, "destination": labels[other], "objectId": int(row["objectId"]),
                          "position": [round(float(local[0]) + translation[0], 2),
                                       round(float(local[2]) + translation[2], 2)]})
        if not boats:
            raise CartographyError(f"{key}: a dock without boats")
        boats.sort(key=lambda boat: (boat["destination"], boat["to"]))
        positions[key] = [round(sum(boat["position"][i] for boat in boats) / len(boats), 2) for i in (0, 1)]
        placed.append({"id": key, "label": labels[key], "serverMap": map_id, "position": positions[key],
                       "boats": boats})
    return {"source": BOAT_NETWORK, "docks": placed,
            "routes": [{"docks": list(route["docks"]), "points": [positions[key] for key in route["docks"]]}
                       for route in routes]}


def overview_layout(data: dict) -> dict:
    """A separate north-up group atlas; legacy pixel coordinates stay unchanged."""
    scale = float(data["lattice"]["metresPerPixel"])
    origin = data["lattice"]["originMetres"]
    points = [p for row in data["regions"] for ring in row["continentPolygons"] for p in ring]
    if not points:
        raise CartographyError("the Landfall overview has no served regions")
    padding = 32  # 64m at the existing two-metre lattice.
    low = [math.floor(min(p[i] for p in points)) - padding for i in (0, 1)]
    high = [math.ceil(max(p[i] for p in points)) + padding for i in (0, 1)]
    regions = []
    for row in data["regions"]:
        rings = [[[round(p[i] - low[i], 3) for i in (0, 1)] for p in ring]
                 for ring in row["continentPolygons"]]
        flat = [p for ring in rings for p in ring]
        minimum = [min(p[i] for p in flat) for i in (0, 1)]
        maximum = [max(p[i] for p in flat) for i in (0, 1)]
        regions.append({"serverMap": row["serverMap"], "name": row["name"],
                        "rect": [*minimum, *[maximum[i] - minimum[i] for i in (0, 1)]],
                        "polygons": rings,
                        "label": [round(row["continentLabel"][i] - low[i], 3) for i in (0, 1)]})
    return {"name": "Landfall", "frame": FRAME,
            "texture": "res://../" + OVERVIEW,
            "imageSize": [high[i] - low[i] for i in (0, 1)],
            "originMetres": [origin[i] + low[i] * scale for i in (0, 1)],
            "metresPerPixel": scale, "regions": regions}


def overview_bytes(checkout: Path, data: dict) -> bytes:
    """Compose existing minimap crops, masked by every component; no GPU render."""
    tool = legacy_tool(checkout)
    overview = data["overview"]
    scale = overview["metresPerPixel"]
    origin = overview["originMetres"]
    canvas = Image.new("RGB", tuple(overview["imageSize"]), tuple(overview["waterRGB"]))
    for row, region in zip(data["regions"], overview["regions"]):
        tab = row["tabMap"]
        translation = row["globalTranslation"]
        low = [tab["worldMin"][i] + translation[i * 2] for i in (0, 1)]
        high = [tab["worldMax"][i] + translation[i * 2] for i in (0, 1)]
        rect_low = [round((low[i] - origin[i]) / scale) for i in (0, 1)]
        rect_high = [round((high[i] - origin[i]) / scale) for i in (0, 1)]
        with Image.open(tool.resource_to_path(tab["texture"])) as image:
            x, y, w, h = tab["region"]
            piece = image.convert("RGBA").crop((x, y, x + w, y + h))
            piece = piece.resize(tuple(rect_high[i] - rect_low[i] for i in (0, 1)), Image.Resampling.LANCZOS)
        mask = Image.new("L", piece.size)
        pen = ImageDraw.Draw(mask)
        for ring in region["polygons"]:
            pen.polygon([(p[0] - rect_low[0], p[1] - rect_low[1]) for p in ring], fill=255)
        piece.putalpha(ImageChops.multiply(piece.getchannel("A"), mask))
        canvas.paste(piece, tuple(rect_low), piece)
    output = io.BytesIO()
    canvas.save(output, "WEBP", lossless=True, method=6)
    return output.getvalue()


def encode(data: dict) -> bytes:
    return (json.dumps(data, indent=2) + "\n").encode("utf-8")


def check(checkout: Path = DEFAULT_CHECKOUT) -> list[str]:
    try:
        wanted = compose(checkout)
    except CartographyError as error:
        return [str(error)]
    path = Path(checkout) / OUTPUT
    if not path.is_file():
        return [f"{OUTPUT} is missing; run {TOOL}"]
    current = read_json(path)
    problems = [f"{OUTPUT} '{key}' is stale; run {TOOL}" for key in sorted(set(current) | set(wanted))
            if current.get(key) != wanted.get(key)]
    image_path = Path(checkout) / OVERVIEW
    if not image_path.is_file() or hashlib.sha256(image_path.read_bytes()).hexdigest() != wanted["overview"]["sha256"]:
        problems.append(f"{OVERVIEW} is missing or stale; run {TOOL}")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 when the file is not what this tool writes")
    ap.add_argument("--checkout", type=Path, default=DEFAULT_CHECKOUT)
    args = ap.parse_args(argv)
    if args.check:
        problems = check(args.checkout)
        for problem in problems:
            print(problem)
        return 1 if problems else 0
    try:
        data = compose(args.checkout)
    except CartographyError as error:
        print(f"refused: {error}")
        return 1
    image_path = args.checkout / OVERVIEW
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(overview_bytes(args.checkout, data))
    (args.checkout / OUTPUT).write_bytes(encode(data))
    for region in data["regions"]:
        print(f"  {region['serverMap']:14s} {region['tabMap']['region']} of {Path(region['tabMap']['texture']).name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
