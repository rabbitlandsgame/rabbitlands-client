"""The client's cartography is generated from the packages, and is current.

The continent picture the Tab map shows is every exterior region's own
minimap laid out to scale, and each region's preview is the pixels of its
minimap the live Tab map frames. `build_continent_map.py` derives all of it;
this fails when a region redrew its minimap, moved on the layout, or the
checked-in JSON was edited by hand, so that what the map window shows can
never drift from the maps underneath it.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "eloria-assets" / "tools" / "build_continent_map.py"
SPEC = importlib.util.spec_from_file_location("build_continent_map", SOURCE)
tool = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tool
SPEC.loader.exec_module(tool)

RESOURCE_PREFIX = "res://../"


def test_checked_in_cartography_and_continent_picture_are_current():
    assert tool.check() == []


def test_framing_follows_the_live_tab_map():
    """`map_view.gd` prefers mapBounds, then playableBounds, then the server's
    addressable rectangle, then the mesh; a preview must frame the same."""
    mesh = {"min": [-810.0, -42.0, -810.0], "max": [810.0, 348.0, 810.0]}
    with_map_bounds = {"asset": {"bounds": mesh,
                                 "mapBounds": {"min": [-360.0, -42.0, -360.0],
                                               "max": [360.0, 348.0, 360.0]},
                                 "playableBounds": {"min": [-1.0, 0.0, -1.0],
                                                    "max": [1.0, 0.0, 1.0]}}}
    assert tool.framing(with_map_bounds) == (-360.0, -360.0, 360.0, 360.0)
    with_playable = {"asset": {"bounds": mesh,
                               "playableBounds": {"min": [-174.0, -18.0, -401.0],
                                                  "max": [401.0, 143.0, 174.0]}}}
    assert tool.framing(with_playable) == (-174.0, -401.0, 401.0, 174.0)
    addressable = {"asset": {"bounds": {"min": [-104.0, -21.0, -176.0],
                                        "max": [176.0, 75.0, 104.0]}},
                   "coordinateTransform": {"addressableWorldBounds": {
                       "min": [-58.0, -133.0], "max": [133.0, 58.0]}}}
    assert tool.framing(addressable) == (-58.0, -133.0, 133.0, 58.0)
    mesh_only = {"asset": {"bounds": {"min": [-1.0, -2.0, -3.0], "max": [4.0, 5.0, 6.0]}}}
    assert tool.framing(mesh_only) == (-1.0, -3.0, 4.0, 6.0)


def test_crop_is_the_framed_pixels_and_maps_back_to_the_world():
    minimap = {"pixelsPerMetre": 1.0, "worldMin": [-810.0, -810.0], "imageSize": [1620, 1620]}
    crop = tool.tab_map_crop(minimap, (-360.0, -360.0, 360.0, 360.0))
    assert crop == (450, 450, 720, 720)
    assert tool.crop_world(minimap, crop) == ([-360.0, -360.0], [360.0, 360.0])
    # A framing wider than the picture is clamped to it, never padded.
    assert tool.tab_map_crop(minimap, (-900.0, -900.0, 900.0, 900.0)) == (0, 0, 1620, 1620)


def test_atlas_coordinates_keep_a_common_origin_and_scale():
    layout = {'metresPerPixel': 2, 'originMetres': [-40, -20]}
    assert tool.atlas_point([100.5, 300.5], layout) == [70.25, 160.25]
    assert tool.atlas_point([-40, -20], layout) == [0, 0]


def test_every_region_is_a_real_tab_map_laid_out_to_scale():
    cartography = json.loads((ROOT / "godot-client" / "data" / "maps" / "cartography.json")
                             .read_text(encoding="utf-8"))
    assert cartography["schemaVersion"] == tool.SCHEMA_VERSION
    continent = cartography["continent"]
    assert "concept" not in continent["texture"]
    assert (ROOT / continent["texture"][len(RESOURCE_PREFIX):]).exists()
    scale = float(continent["metresPerPixel"])
    width, height = continent["imageSize"]
    seen = set()
    for region in cartography["regions"]:
        tab_map = region["tabMap"]
        assert "concept" not in tab_map["texture"], region["serverMap"]
        assert "preview" not in region, region["serverMap"]
        assert (ROOT / tab_map["texture"][len(RESOURCE_PREFIX):]).exists(), region["serverMap"]
        assert region["serverMap"] in continent["sources"], region["serverMap"]
        x, y, w, h = region["continentRect"]
        assert 0 <= x and 0 <= y and x + w <= width and y + h <= height, region["serverMap"]
        metres_wide = tab_map["worldMax"][0] - tab_map["worldMin"][0]
        metres_tall = tab_map["worldMax"][1] - tab_map["worldMin"][1]
        assert abs(w * scale - metres_wide) <= scale, region["serverMap"]
        assert abs(h * scale - metres_tall) <= scale, region["serverMap"]
        assert tab_map["region"][2] == round(metres_wide) and tab_map["region"][3] == round(metres_tall)
        seen.add(region["serverMap"])
    assert {"four_gates", "crownwater", "sunmane_steppe", "whitehorn_range"} <= seen


def test_compact_atlas_preserves_every_declared_connection_and_ferry_type():
    layout=tool.load_json(tool.LAYOUT)
    atlas=tool.atlas_connections(layout)
    graph=tool.load_json(tool.CONNECTIONS)['connections']
    assert {(e['from'],e['to'],e['type']) for e in atlas} == {
        (e['from'],e['to'],e['type']) for e in graph}
    # The published graph is the authority for counts: the diagonal continent
    # declares 18 land links and 3 ferries; the legacy compact layout had 24/7.
    assert len(atlas)==len(graph) and len(graph)>=21
    assert sum(e['type']=='ferry' for e in atlas)==sum(e['type']=='ferry' for e in graph)
    declared={frozenset((e['from'],e['to'])) for e in graph}
    assert all(frozenset((e['from'],e['to'])) in declared for e in atlas)


def test_compact_atlas_does_not_reintroduce_large_empty_gaps():
    layout=tool.load_json(tool.LAYOUT)
    cartography,_=tool.compose(layout,tool.load_json(tool.REGISTRY))
    width,height=cartography['continent']['imageSize']
    area=sum(r['continentRect'][2]*r['continentRect'][3] for r in cartography['regions'])
    # Real minimaps cover over half the atlas, instead of the former~18%.
    assert area/(width*height)>.55
    rects={r['serverMap']:r['continentRect'] for r in cartography['regions']}
    # Every published land link joins two territories that touch on the common
    # atlas lattice; the pair list follows the graph rather than a fixed layout.
    graph=tool.load_json(tool.CONNECTIONS)['connections']
    pairs=sorted({tuple(sorted((e['from'],e['to']))) for e in graph if e['type']!='ferry'})
    assert len(pairs)>=6
    for a,b in pairs:
        x,y,w,h=rects[a];xx,yy,ww,hh=rects[b]
        gap_x=max(0,x-(xx+ww),xx-(x+w))
        gap_y=max(0,y-(yy+hh),yy-(y+h))
        assert (gap_x**2+gap_y**2)**.5<=25,(a,b,gap_x,gap_y)


def test_atlas_crossings_and_region_footprints_share_actual_world_coordinates():
    layout = tool.load_json(tool.LAYOUT)
    geography = tool.load_json(tool.GEOGRAPHY)
    cartography, _ = tool.compose(layout, tool.load_json(tool.REGISTRY))
    registry = tool.load_json(tool.REGISTRY)['maps']
    graph = tool.load_json(tool.CONNECTIONS)['connections']
    for source, drawn in zip(graph, cartography['connections']):
        if source['type'] == 'ferry': continue
        points = []
        for key in ('from', 'to'):
            region = source[key]
            manifest = tool.load_json(tool.resource_to_path(registry[region]['manifest']))
            frame = next(f for f in manifest['streamingBorders'] if f['portal'] == source[key+'_portal'])
            translation = geography['regions'][region]['translation']
            points.append(tool.atlas_point([frame['anchor'][0]+translation[0],
                                             frame['anchor'][2]+translation[2]], layout))
        assert points[0] == points[1] == drawn['points'][0] == drawn['points'][-1], source
    for region in cartography['regions']:
        spec = geography['regions'][region['serverMap']]
        assert region['continentPolygon'] == [tool.atlas_point(p, layout) for p in spec['ownershipPolygon']]
        assert region['globalTranslation'] == spec['translation']


def test_check_catches_changed_picture_even_with_unchanged_dimensions(monkeypatch):
    original=tool.draw
    def altered(layout,cartography,tiles):
        result=original(layout,cartography,tiles)
        result.paste((255,0,255),(0,0,30,30))
        return result
    monkeypatch.setattr(tool,'draw',altered)
    assert 'continent picture content is stale; run build_continent_map.py' in tool.check()
