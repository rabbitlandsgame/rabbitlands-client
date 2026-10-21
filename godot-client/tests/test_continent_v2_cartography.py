"""The continent-v2 isles' tab maps are generated from their packages, and are current (serve plan CV14).

    python3 -m pytest godot-client/tests/test_continent_v2_cartography.py -q

A chunk-streamed isle holds only the chunks round the player, so its Tab map and minimap need the isle's own picture
(minimap.webp, drawn from the package's chunks by _continent_v2/render_minimap.py) and a cartography row framing it
(godot-client/data/maps/cartography-continent-v2.json, written by _continent_v2/publish_cartography.py; main.gd
appends its rows after cartography.json's). This fails when a package was republished without its picture being
drawn again, a picture or a frame moved, a boat moved or a boat route changed, cartography.json's pixel lattice
changed, or the file was edited by hand.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V2 = ROOT / "eloria-assets" / "maps" / "continent-v2" / "_continent_v2"


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
    assert set(by_name) == {"Rowan Hale", "Bettany Orl"}
    assert by_name["Rowan Hale"]["category"] == "general_store"
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


def test_entrance_markers_match_the_authored_underground_doors():
    """One entrance marker per door of every underground section (a section may have several doors, on one map or
    several: underground_source.doors), on the door's map, tile and object."""
    import frames
    source = load("underground_source")
    sections = read("eloria-assets/maps/continent-v2/_continent_v2/content/underground.json")["sections"]
    expected = {}
    for section in sections:
        for door in source.doors(section):
            expected.setdefault(door["map"], []).append((section, door))
    doors = sum(len(listed) for listed in expected.values())
    assert doors >= len([s for s in sections if source.doors(s)])
    rows = read(tool.OUTPUT)["regions"]
    assert sum(len(row["entranceMarkers"]) for row in rows) == doors
    for row in rows:
        markers = row["entranceMarkers"]
        listed = expected.get(row["serverMap"], [])
        assert len(markers) == len(listed)
        by_object = {marker["objectId"]: marker for marker in markers}
        for section, door in listed:
            marker = by_object[door["object"]]
            assert marker["label"] == section["name"]
            assert marker["serverTile"] == door["tile"]
            assert list(frames.load(row["serverMap"], ROOT).tile(*marker["position"])) == door["tile"]


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
