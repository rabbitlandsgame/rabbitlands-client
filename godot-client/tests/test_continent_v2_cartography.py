"""The continent-v2 isles' tab maps are generated from their packages, and are current (serve plan CV14).

    python3 -m pytest godot-client/tests/test_continent_v2_cartography.py -q

A chunk-streamed isle holds only the chunks round the player, so its Tab map and minimap need the isle's own picture
(minimap.webp, drawn from the package's chunks by _continent_v2/render_minimap.py) and a cartography row framing it
(godot-client/data/maps/cartography-continent-v2.json, written by _continent_v2/publish_cartography.py; main.gd
appends its rows after cartography.json's). This fails when a package was republished without its picture being
drawn again, a picture or a frame moved, a boat moved or a boat route changed, cartography.json's pixel lattice
changed, or the file was edited by hand.

The marker tests check what the tool writes (compose) where they judge the rules rather than the file, so a stale file
fails the first test alone. The map categories (map_categories.py) are one table with the client's
(service_map_overlay.gd CATEGORY_COLOURS) and the map legend (main.tscn MapLegend).
"""
from __future__ import annotations

import functools
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
V2 = ROOT / "eloria-assets" / "maps" / "continent-v2" / "_continent_v2"
SERVICE_OVERLAY = ROOT / "godot-client" / "src" / "ui" / "service_map_overlay.gd"
ENTRANCE_OVERLAY = ROOT / "godot-client" / "src" / "ui" / "entrance_map_overlay.gd"
MAIN_SCENE = ROOT / "godot-client" / "src" / "app" / "main.tscn"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, V2 / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


tool = load("publish_cartography")
render = load("render_minimap")


def read(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


@functools.lru_cache(maxsize=1)
def composed() -> dict:
    """What publish_cartography.py writes for this checkout (a few seconds; once per run)."""
    return tool.compose(ROOT)


def test_the_tab_maps_and_their_pictures_are_current():
    assert tool.check(ROOT) == []
    served = [key for key, _ in tool.served(read(tool.REGISTRY))]
    assert render.check(ROOT, served) == []


def test_every_served_isle_has_a_row_of_its_own_frame_in_the_legacy_lattice():
    registry = read(tool.REGISTRY)["maps"]
    data = read(tool.OUTPUT)
    continent = read(tool.CARTOGRAPHY)["continent"]
    assert data["lattice"] == {"originMetres": continent["originMetres"],
                               "metresPerPixel": continent["metresPerPixel"]}
    served = [key for key, _ in tool.served({"maps": registry})]
    active = {entry["id"] for entry in read("godot-client/world_authoring/continent-v2/territories.json")["entries"]}
    assert len(served) == len(active) and set(served) == active
    assert [row["serverMap"] for row in data["regions"]] == served
    legacy = {row["serverMap"] for row in read(tool.CARTOGRAPHY)["regions"]}
    for row in data["regions"]:
        key = row["serverMap"]
        assert key not in legacy
        assert row["frame"] == "continent-v2" and "continentRect" not in row
        assert row["name"] == registry[key]["label"]
        assert row["globalTranslation"] == registry[key]["continentGeography"]["translation"]
        manifest = json.loads(tool.legacy_tool(ROOT).resource_to_path(registry[key]["manifest"]).read_text(
            encoding="utf-8"))
        bounds = manifest["asset"]["mapBounds"]
        # the picture is the live Tab map's frame, so the crop is the whole picture
        assert row["tabMap"]["worldMin"] == [bounds["min"][0], bounds["min"][2]]
        assert row["tabMap"]["worldMax"] == [bounds["max"][0], bounds["max"][2]]
        assert row["tabMap"]["region"] == [0, 0, *manifest["minimap"]["imageSize"]]
        scale, origin = continent["metresPerPixel"], continent["originMetres"]
        geography = manifest["continentGeography"]
        polygons = geography.get("ownershipPolygons", [geography["ownershipPolygon"]])
        pixel_rings = [[[(x - origin[0]) / scale, (z - origin[1]) / scale] for x, z in ring]
                       for ring in polygons]
        assert row["continentPolygon"] == pixel_rings[0]
        assert row["continentPolygons"] == pixel_rings
        # The label uses the full union, including detached ownership components.
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
        centroid = unary_union([Polygon(ring) for ring in polygons]).centroid
        assert row["continentLabel"] == [round((centroid.x - origin[0]) / scale, 3),
                                         round((centroid.y - origin[1]) / scale, 3)]


def test_landfall_services_keep_their_authored_merchant_posts():
    import frames
    row = next(row for row in read(tool.OUTPUT)["regions"] if row["serverMap"] == "landfall")
    by_name = {mark["name"]: mark for mark in row["serviceMarkers"]}
    assert set(by_name) == {"Rowan Hale", "Bettany Orl", "Mara Vell"}
    assert by_name["Rowan Hale"]["category"] == "general_store"
    assert by_name["Mara Vell"]["category"] == "general_store"
    assert by_name["Mara Vell"]["serverTile"] == [117, 212]
    assert by_name["Bettany Orl"]["category"] == "tavern"
    frame = frames.load("landfall", ROOT)
    for marker in by_name.values():
        assert list(frame.tile(*marker["position"])) == marker["serverTile"]


def test_the_label_point_is_the_area_centroid():
    assert tool.polygon_centroid([[0, 0], [4, 0], [4, 2], [0, 2]]) == [2.0, 1.0]
    centroid = tool.polygon_centroid([[0, 0], [4, 0], [4, 1], [1, 1], [1, 4], [0, 4]])
    assert [round(v, 4) for v in centroid] == [1.3571, 1.3571]   # (4 x (2, .5) + 3 x (.5, 2.5)) / 7


def test_five_storage_markers_match_the_published_tiles_and_preview_positions():
    import frames
    storage_maps = {"landfall", "greenlight", "hearthcroft", "stagheath", "brambleshaw"}
    for row in read(tool.OUTPUT)["regions"]:
        mid = row["serverMap"]
        markers = row["storageMarkers"]
        assert len(markers) == (1 if mid in storage_maps else 0)
        manifest = read(f"eloria-assets/maps/continent-v2/{mid}/client/world.json")
        chests = [mark for mark in manifest["interactives"] if mark["type"] == "storage"]
        assert len(chests) == len(markers)
        for marker, chest in zip(markers, chests):
            assert marker["position"] == [chest["position"][0], chest["position"][2]]
            assert marker["serverTile"] == chest["serverTile"]
            assert list(frames.load(mid, ROOT).tile(*marker["position"])) == marker["serverTile"]
            assert marker["objectId"] == chest["objectId"] == 22


def test_entrance_markers_match_the_authored_interior_doors():
    """One entrance marker per door of every interior section (a section may have several doors, on one map or
    several: underground_source.doors, town_source.doors), on the door's map, tile and object. A cave's marker stands
    on its door tile under its section's name; a building's stands at its painted door beside the door tile, under the
    door's own label, with its kind and its shop's category."""
    import frames
    sources = tool.interior_sources(ROOT)
    assert sources and sources[0][0] == tool.INTERIOR_SOURCES[0][0]
    caves = sources[0][1]["sections"]
    expected = {}
    for _relative, design, reader, kind in sources:
        for section in design["sections"]:
            for door in tool.section_doors(reader, section):
                expected.setdefault(door["map"], []).append((section, door, door.get("kind", kind)))
    doors = sum(len(listed) for listed in expected.values())
    assert doors >= len([s for s in caves if tool.US.doors(s)])
    rows = composed()["regions"]
    assert sum(len(row["entranceMarkers"]) for row in rows) == doors
    for row in rows:
        markers = row["entranceMarkers"]
        listed = expected.get(row["serverMap"], [])
        assert len(markers) == len(listed)
        by_object = {marker["objectId"]: marker for marker in markers}
        for section, door, kind in listed:
            marker = by_object[door["object"]]
            assert marker["kind"] == kind
            assert marker["serverTile"] == door["tile"]
            tile = list(frames.load(row["serverMap"], ROOT).tile(*marker["position"]))
            if kind == "building":
                assert marker["label"] == (door.get("label") or section["name"])
                assert marker.get("category") == door.get("category")
                # underground.py DOOR_REACH: the painted point stands within 6 tiles of the door tile
                assert max(abs(tile[0] - door["tile"][0]), abs(tile[1] - door["tile"][1])) <= 6, marker
            else:
                assert marker["label"] == section["name"]
                assert "category" not in marker
                assert tile == door["tile"]


class DoorReader:
    """A synthetic source's door reader: a section's `entrances`, indexed, as town_source.doors gives them."""

    @staticmethod
    def doors(section):
        return [{**door, "index": index} for index, door in enumerate(section.get("entrances", []))]


def town(**door) -> dict:
    """A one-section town source with one building door (the tavern's, Door A)."""
    row = {"map": "landfall", "kind": "building", "object": 59201, "tile": [107, 250],
           "position": [-174.6, 121.49, -2.1], "returnTile": [104, 247], "arrival": [40, 302], "exit": [40, 303],
           "label": "The Unlit Boat", "exitLabel": "The avenue"}
    row.update(door)
    return {"map": {"id": "landfall_town", "cells": 324},
            "sections": [{"id": "tavern_ground", "name": "The Unlit Boat", "entrances": [row], "npcs": []}]}


def test_a_building_door_is_drawn_in_its_shops_colour_under_its_own_label():
    sources = [("town.json", town(category="tavern", label="Corran's door"), DoorReader, "building")]
    assert tool.entrance_markers("landfall", sources) == [
        {"label": "Corran's door", "position": [-174.6, -2.1], "height": 121.49, "serverTile": [107, 250],
         "objectId": 59201, "kind": "building", "category": "tavern"}]
    assert tool.entrance_markers("pinebrow", sources) == []
    # a house: no category (the tan entrance dot); no label of its own: its section's name
    house = town()
    del house["sections"][0]["entrances"][0]["label"]
    [row] = tool.entrance_markers("landfall", [("town.json", house, DoorReader, "building")])
    assert row["label"] == "The Unlit Boat" and "category" not in row and row["kind"] == "building"
    assert tool.door_maps([("town.json", house, DoorReader, "building")]) == {"landfall"}


@pytest.mark.parametrize("door, refusal", [
    ({"category": "bookshop"}, "bookshop"),                      # unknown: refused, not dropped
    ({"kind": "cave", "category": None}, "kind 'cave'"),
    ({"kind": "underground", "category": "tavern"}, "only a building door"),
])
def test_a_door_the_maps_cannot_draw_is_refused(door, refusal):
    design = town(**door)
    if door.get("category") is None:
        del design["sections"][0]["entrances"][0]["category"]
    with pytest.raises(tool.CartographyError, match=refusal):
        tool.entrance_markers("landfall", [("town.json", design, DoorReader, "building")])


def test_two_doors_on_one_object_are_refused():
    design = town()
    design["sections"][0]["entrances"].append(dict(design["sections"][0]["entrances"][0], tile=[131, 254]))
    with pytest.raises(tool.CartographyError, match="object 59201"):
        tool.entrance_markers("landfall", [("town.json", design, DoorReader, "building")])


def test_interior_shopkeepers_are_drawn_on_their_posts_in_their_sections():
    design = town()
    design["sections"][0]["npcs"] = [
        {"name": "Corran Orl", "role": "shop", "tile": [40, 300], "mapCategory": "tavern", "mapLabel": "The taproom"},
        {"name": "Wenna", "role": "dialogue", "tile": [44, 300]},
    ]
    design["sections"].append({"id": "smithy", "name": "The forge", "npcs": [
        {"name": "Garrow", "role": "shop", "tile": [120, 280], "mapCategory": "blacksmith"}]})
    sources = [("town.json", design, DoorReader, "building")]
    block = tool.interiors(sources, {"maps": {}})
    assert block == {"landfall_town": {"serviceMarkers": [
        {"label": "The taproom", "name": "Corran Orl", "category": "tavern", "position": [40.5, 23.5], "height": 0.0,
         "serverTile": [40, 300], "section": "tavern_ground"},
        {"label": "Garrow", "name": "Garrow", "category": "blacksmith", "position": [120.5, 43.5], "height": 0.0,
         "serverTile": [120, 280], "section": "smithy"}]}}
    # The tile under the dot is the post: the client's godot_to_server (x, cells - z, floored).
    for mark in block["landfall_town"]["serviceMarkers"]:
        assert [int(mark["position"][0]), int(324 - mark["position"][1])] == mark["serverTile"]
    # The registry row's transform is what the client places tiles by, so it wins over the builders' frame.
    lifted = {"maps": {"landfall_town": {"coordinateTransform": {
        "metresPerTile": 1.0, "serverOrigin": [0, 324], "origin": [0, 0, 0], "walkingHeight": 2.5,
        "invertServerY": True}}}}
    assert {mark["height"] for mark in tool.interiors(sources, lifted)["landfall_town"]["serviceMarkers"]} == {2.5}
    # An interior without a shopkeeper has no block; an unknown category is refused, not dropped.
    assert tool.interiors([("town.json", town(), DoorReader, "building")], {"maps": {}}) == {}
    design["sections"][1]["npcs"][0]["mapCategory"] = "armoury"
    with pytest.raises(tool.CartographyError, match="armoury"):
        tool.interiors(sources, {"maps": {}})


def test_the_interior_sources_are_the_publishers():
    """publish_cartography.py reads the same interior sources, readers and door kinds, in the same order, as
    underground.py SOURCES publishes (a source added there and not here would publish doors the maps never draw)."""
    underground = importlib.import_module("underground")  # _continent_v2 is on the path (publish_cartography)
    assert tool.INTERIOR_SOURCES == tuple((spec.source, spec.reader, spec.kind) for spec in underground.SOURCES)
    assert tool.DOOR_KINDS == tuple(underground.DOOR_KINDS)


def test_every_interior_frame_is_its_builders():
    """The registry row an interior's tiles are placed by is the frame its builder draws (tile (x, y) at world
    (x, h, cells - y)), so a shopkeeper's dot stands on the post the server serves."""
    registry = read(tool.REGISTRY)
    for _relative, design, _reader, _kind in tool.interior_sources(ROOT):
        row = registry["maps"].get(design["map"]["id"])
        if row is None:
            continue
        builders = tool.interior_transform(design, {"maps": {}})
        for tile in ([0, 0], [17, 203], [design["map"]["cells"] - 1, 5]):
            assert tool.tile_position(row["coordinateTransform"], tile) == tool.tile_position(builders, tile)


def test_every_shop_door_leads_to_a_shopkeeper_of_its_colour():
    """A building door is coloured by the shop behind it, so the section it opens into keeps a shopkeeper of that
    category (whose dot inside is the same colour). A section may keep two shops (the market's general store and
    flower shop), each street door naming its own."""
    town_sources = [source for source in tool.interior_sources(ROOT) if source[3] == "building"]
    if not town_sources:
        pytest.skip(f"{tool.INTERIOR_SOURCES[1][0]} is not written yet")
    # The room shells come before their cast (PLAN-DRAFT phase C writes the `npcs`): until a section of a town keeps
    # anyone, its coloured doors have no shopkeeper to check. Once any NPC row exists, every shop door needs its own.
    if not any(tool.section_npcs(reader, section) for _r, design, reader, _k in town_sources
               for section in design["sections"]):
        pytest.skip("no town section keeps an NPC yet (the cast is written after the room shells)")
    data = composed()
    for relative, design, reader, _kind in town_sources:
        drawn = {(mark["section"], mark["category"])
                 for mark in data.get("interiors", {}).get(design["map"]["id"], {}).get("serviceMarkers", [])}
        for section in design["sections"]:
            for door in tool.section_doors(reader, section):
                if door.get("category"):
                    assert (section["id"], door["category"]) in drawn, (
                        f"{relative} {section['id']}: its door {door.get('label')!r} is drawn as a "
                        f"{door['category']}, and no shopkeeper of that category stands inside")


def test_one_category_table_for_the_publishers_the_client_and_the_legend():
    """map_categories.py, service_map_overlay.gd CATEGORY_COLOURS and the legend name the same shops in the same
    colours, each with a round dot (diamonds are the server's pins); doors without a shop are the tan entrance dot."""
    categories = tool.MC.CATEGORIES
    source = SERVICE_OVERLAY.read_text(encoding="utf-8")
    block = re.search(r"\nconst CATEGORY_COLOURS := \{\n(.*?)\n\}\n", source, re.S)
    assert block, "service_map_overlay.gd has no CATEGORY_COLOURS table"
    client = dict(re.findall(r'^\t"(\w+)": Color\("([0-9a-f]{6})"\),$', block.group(1), re.M))
    assert client == {key: colour for key, (colour, _legend) in categories.items()}
    assert len(block.group(1).splitlines()) == len(categories)
    entrance = re.search(r'\nconst DOT_COLOUR := Color\("([0-9a-f]{6})"\)', ENTRANCE_OVERLAY.read_text(encoding="utf-8"))
    assert entrance and entrance.group(1) == tool.MC.ENTRANCE_COLOUR
    scene = MAIN_SCENE.read_text(encoding="utf-8").split('[node name="MapLegend"', 1)[1]
    legend = re.search(r'\ntext = "(.*?)"\n', scene, re.S).group(1).splitlines()
    for colour, name in categories.values():
        assert f"[color=#{colour}]●[/color] {name}" in legend
    assert f"[color=#{tool.MC.ENTRANCE_COLOUR}]•[/color] {tool.MC.ENTRANCE_LEGEND}" in legend
    names = {name for _colour, name in categories.values()}
    assert not [line for line in legend if "◆" in line and line.split("[/color] ", 1)[-1] in names]
    assert tool.MC.colour() == tool.MC.ENTRANCE_COLOUR and tool.MC.colour("blacksmith") == "9d73d8"
    with pytest.raises(tool.MC.CategoryError):
        tool.MC.check("books")


def test_landfall_overview_places_all_components_in_its_own_image():
    import hashlib
    from PIL import Image
    data = read(tool.OUTPUT)
    overview = data["overview"]
    assert overview["name"] == "Landfall" and overview["frame"] == "continent-v2"
    assert [r["serverMap"] for r in overview["regions"]] == [r["serverMap"] for r in data["regions"]]
    assert len(overview["regions"]) == 17
    source_scale = data["lattice"]["metresPerPixel"]
    source_origin = data["lattice"]["originMetres"]
    for source, region in zip(data["regions"], overview["regions"]):
        assert len(region["polygons"]) == len(source["continentPolygons"])
        for old_ring, new_ring in zip(source["continentPolygons"], region["polygons"]):
            for old, new in zip(old_ring, new_ring):
                for i in (0, 1):
                    assert abs((old[i] * source_scale + source_origin[i]) -
                               (new[i] * overview["metresPerPixel"] + overview["originMetres"][i])) < .002
                    assert 0 <= new[i] < overview["imageSize"][i]
    assert len(next(r for r in overview["regions"] if r["serverMap"] == "ravenhead")["polygons"]) == 1
    image_path = ROOT / tool.OVERVIEW
    assert hashlib.sha256(image_path.read_bytes()).hexdigest() == overview["sha256"]
    with Image.open(image_path) as image:
        assert list(image.size) == overview["imageSize"]


def test_overview_check_refuses_corrupt_picture(tmp_path, monkeypatch):
    data = read(tool.OUTPUT)
    monkeypatch.setattr(tool, "compose", lambda checkout: data)
    metadata = tmp_path / tool.OUTPUT
    metadata.parent.mkdir(parents=True)
    assert any("missing" in problem for problem in tool.check(tmp_path))
    metadata.write_bytes(tool.encode(data))
    image = tmp_path / tool.OVERVIEW
    image.parent.mkdir(parents=True)
    image.write_bytes((ROOT / tool.OVERVIEW).read_bytes())
    assert tool.check(tmp_path) == []
    image.write_bytes(image.read_bytes()[:-10] + b"corrupt")
    assert any(tool.OVERVIEW in problem for problem in tool.check(tmp_path))


def test_the_boat_network_draws_every_route_between_the_boats_it_names():
    import math
    from shapely.geometry import Point, Polygon
    from shapely.ops import unary_union
    data = read(tool.OUTPUT)
    network = read(tool.BOAT_NETWORK)
    rows = read(tool.SERVER_ROWS)["maps"]
    drawn = data["boatNetwork"]
    assert drawn["source"] == tool.BOAT_NETWORK
    docks = {dock["id"]: dock for dock in drawn["docks"]}
    assert list(docks) == list(network["docks"])
    assert len(drawn["routes"]) == len(network["routes"]) == 12
    assert sum(len(dock["boats"]) for dock in docks.values()) == 24
    overview = data["overview"]
    for key, dock in docks.items():
        spec = network["docks"][key]
        assert dock["label"] == spec["label"] and dock["serverMap"] == spec["map"]
        assert sorted(boat["to"] for boat in dock["boats"]) == sorted(spec["berths"])
        boats_here = {row["objectId"]: row for row in rows[dock["serverMap"]]["interactives"].values()
                      if row.get("role") == "portal"}
        for boat in dock["boats"]:
            assert boat["destination"] == network["docks"][boat["to"]]["label"]
            # The destination the map names is the one the client reads off the boat (MapObject3D.destination).
            row = boats_here[boat["objectId"]]
            said = row["text"].split(tool.BOAT_PHRASE, 1)[1].split(". ", 1)[0].removesuffix(".")
            assert said == boat["destination"]
            assert row["portal"]["destinationMap"] == docks[boat["to"]]["serverMap"]
            assert math.dist(boat["position"], dock["position"]) < 25.0
        manifest = read(f"eloria-assets/maps/continent-v2/{dock['serverMap']}/client/world.json")
        geography = manifest["continentGeography"]
        land = unary_union([Polygon(ring) for ring in geography.get("ownershipPolygons",
                                                                    [geography["ownershipPolygon"]])])
        assert land.contains(Point(dock["position"])), f"{key} stands outside {dock['serverMap']}"
        pixel = [(dock["position"][i] - overview["originMetres"][i]) / overview["metresPerPixel"] for i in (0, 1)]
        assert all(0 <= pixel[i] < overview["imageSize"][i] for i in (0, 1))
    for route, spec in zip(drawn["routes"], network["routes"]):
        assert route["docks"] == spec["docks"]
        assert route["points"] == [docks[key]["position"] for key in spec["docks"]]
    # Both boat-only isles have routes drawn to the rest of the network.
    for isle in ({"coilmere", "suncoil"}, {"hornmere", "whitepeak"}):
        assert any((docks[a]["serverMap"] in isle) != (docks[b]["serverMap"] in isle)
                   for a, b in (route["docks"] for route in drawn["routes"]))


def test_the_boat_network_refuses_what_the_boats_do_not_say():
    import copy
    import pytest
    served = dict(tool.served(read(tool.REGISTRY)))
    network = read(tool.BOAT_NETWORK)
    rows = read(tool.SERVER_ROWS)
    assert tool.boat_network(ROOT, served, network, rows) == read(tool.OUTPUT)["boatNetwork"]
    unrouted = copy.deepcopy(network)
    unrouted["routes"] = unrouted["routes"][1:]
    with pytest.raises(tool.CartographyError, match="on no route"):
        tool.boat_network(ROOT, served, unrouted, rows)
    misnamed = copy.deepcopy(rows)
    row = misnamed["maps"]["reedfall"]["interactives"]["reedfall--obj-boat-stagheath"]
    row["text"] = row["text"].replace("Bound for Stagheath.", "Bound for Saltsound.")
    with pytest.raises(tool.CartographyError, match="does not begin"):
        tool.boat_network(ROOT, served, network, misnamed)
    unmoored = copy.deepcopy(network)
    route = next(route for route in unmoored["routes"] if route["docks"] == ["stagheath", "hornmere"])
    route["existing"] = {"hornmere": "hornmere--obj-boat-nowhere"}
    with pytest.raises(tool.CartographyError, match="has no boat"):
        tool.boat_network(ROOT, served, unmoored, rows)
    with pytest.raises(tool.CartographyError, match="not served"):
        tool.boat_network(ROOT, {key: row for key, row in served.items() if key != "hornmere"}, network, rows)
