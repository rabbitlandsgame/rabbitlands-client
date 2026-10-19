"""The continent-v2 isles' tab maps are generated from their packages, and are current (serve plan CV14).

    python3 -m pytest godot-client/tests/test_continent_v2_cartography.py -q

A chunk-streamed isle holds only the chunks round the player, so its Tab map and minimap need the isle's own picture
(minimap.webp, drawn from the package's chunks by _continent_v2/render_minimap.py) and a cartography row framing it
(godot-client/data/maps/cartography-continent-v2.json, written by _continent_v2/publish_cartography.py; main.gd
appends its rows after cartography.json's). This fails when a package was republished without its picture being
drawn again, a picture or a frame moved, cartography.json's pixel lattice changed, or the file was edited by hand.
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
    storage_maps = {"landfall", "greenlight", "hearthcroft", "stagheath", "coilmere"}
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


def test_entrance_markers_match_the_authored_mines_and_barrow():
    import frames
    sections = read("eloria-assets/maps/continent-v2/_continent_v2/content/underground.json")["sections"]
    expected = {s["entrance"]["map"]: s for s in sections}
    rows = read(tool.OUTPUT)["regions"]
    assert sum(len(row["entranceMarkers"]) for row in rows) == 4
    for row in rows:
        markers = row["entranceMarkers"]
        assert len(markers) == (1 if row["serverMap"] in expected else 0)
        if markers:
            section = expected[row["serverMap"]]
            entrance = section["entrance"]
            marker = markers[0]
            assert marker["label"] == section["name"]
            assert marker["objectId"] == entrance["object"]
            assert marker["serverTile"] == entrance["tile"]
            assert list(frames.load(row["serverMap"], ROOT).tile(*marker["position"])) == entrance["tile"]


def test_landfall_overview_places_all_components_in_its_own_image():
    import hashlib
    from PIL import Image
    data = read(tool.OUTPUT)
    overview = data["overview"]
    assert overview["name"] == "Landfall" and overview["frame"] == "continent-v2"
    assert [r["serverMap"] for r in overview["regions"]] == [r["serverMap"] for r in data["regions"]]
    assert len(overview["regions"]) == 18
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
