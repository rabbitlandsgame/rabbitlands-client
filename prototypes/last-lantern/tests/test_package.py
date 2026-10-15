"""Validate the exported map contract, not screenshots or mirrored UI code."""
import gzip
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import build_map


def load(name):
    return json.loads((ROOT / "package" / name).read_text(encoding="utf-8"))


def test_native_grids_match_preview_and_server():
    layout = load("layout.json")
    world = load("world.json")
    native = (ROOT / "package/collision.bin").read_bytes()
    assert struct.unpack_from("<4sHHII", native) == (b"EWCG", 2, 0, 240, 240)
    server = gzip.decompress((ROOT / "package/lantern_reach.escg.gz").read_bytes())
    assert struct.unpack_from("<4sHHI", server) == (b"ESCG", 1, 200, 120)
    assert list(server[12:]) == layout["walkGrid"]
    for y in range(120):
        for x in range(120):
            expected = layout["walkGrid"][y*120+x]
            for dy in (0, 1):
                for dx in (0, 1):
                    assert native[16+(y*2+dy)*240+x*2+dx] == expected
    assert world["collision"]["cellMetres"] == .5
    assert world["coordinateTransform"]["origin"] == [-.5, 0, .5]


def test_every_marker_resolves_to_an_exposed_target_and_approach():
    layout, quest = load("layout.json"), load("quest.json")
    targets = {t["id"]: t for t in layout["targets"]}
    assert len(targets) == len(layout["targets"])
    ids = [t["objectId"] for t in targets.values() if "objectId" in t]
    assert len(ids) == len(set(ids))
    for step in quest["steps"]:
        target = targets[step["target"]]
        x, y = target["approach"]
        assert layout["walkGrid"][y*120+x], step["id"]
        assert max(abs(x-target["tile"][0]), abs(y-target["tile"][1])) <= 2
    for name in ("reed", "quartz"):
        t = targets[name]
        x, y = t["tile"]
        # Every immediate neighbor is open: neither node is tucked behind a
        # wall, a gate, the edge of the walk surface or a building footprint.
        assert all(layout["walkGrid"][(y+dy)*120+x+dx]
                   for dy in (-1, 0, 1) for dx in (-1, 0, 1))


def test_exported_scene_has_real_walk_surfaces_and_correct_extent():
    blob = (ROOT / "package/world.glb").read_bytes()
    magic, version, length = struct.unpack_from("<4sII", blob)
    assert magic == b"glTF" and version == 2 and length == len(blob)
    size, kind = struct.unpack_from("<I4s", blob, 12)
    assert kind == b"JSON"
    doc = json.loads(blob[20:20+size])
    walk = [n for n in doc["nodes"] if n["name"].startswith("Walk_")]
    # The art pass blends grass/path colours on one connected floor mesh.
    assert walk
    assert any("BeaconTower" in n["name"] for n in doc["nodes"])
    assert any("GroundedFerry" in n["name"] for n in doc["nodes"])
    for node in walk:
        primitive = doc["meshes"][node["mesh"]]["primitives"][0]
        acc = doc["accessors"][primitive["attributes"]["POSITION"]]
        assert acc["min"][0] >= -.5 and acc["max"][0] <= 119.5
        assert acc["min"][2] >= -119.5 and acc["max"][2] <= .5


def test_generation_is_reproducible():
    files = ["layout.json", "quest.json", "world.glb", "collision.bin", "lantern_reach.escg.gz", "world.json", "art.json"]
    files += [str(path.relative_to(ROOT/"package")) for path in sorted((ROOT/"package/models").glob("*.glb"))]
    before = {name: (ROOT/"package"/name).read_bytes() for name in files}
    build_map.build()
    assert before == {name: (ROOT/"package"/name).read_bytes() for name in files}


def test_art_preserves_the_reviewed_route_and_quest():
    import hashlib
    for name, digest in {
        "collision.bin": "5e4abbf804e7c8e405b66350c700994bb286a6d4a042149d07dd712e952cafc8",
        "quest.json": "b1777c7d72d5be759a33b93000f890694a235a01933caf109d3411f3a805fb2a",
        # Storage approach markers stand outside the chests' solid footprints.
        "layout.json": "8521660d461049d1b3e27a3fcfa5bd82d01f007f85287dd19703f62ec68c6a1a",
    }.items():
        assert hashlib.sha256((ROOT/"package"/name).read_bytes()).hexdigest() == digest


def test_large_dressing_is_outside_walkable_tiles_and_targets():
    import math
    layout, art = load("layout.json"), load("art.json")
    for entry in art["solidDressing"]:
        x,y = entry["tile"]
        r = entry["radius"]
        for yy in range(math.floor(y-r),math.ceil(y+r)+1):
            for xx in range(math.floor(x-r),math.ceil(x+r)+1):
                if 0 <= xx < 120 and 0 <= yy < 120:
                    assert not layout["walkGrid"][yy*120+xx]
        assert all(math.dist([x,y],t["tile"]) >= 5 for t in layout["targets"])


def test_quest_supplies_and_handoff_are_closed():
    q = load("quest.json")
    assert {s["scene"] for s in q["steps"]} == set(range(1, 9))
    assert len({s["id"] for s in q["steps"]}) == len(q["steps"])
    assert q["recipe"]["ingredients"] == {"Wood Plank": 1, "Cloth Roll": 1}
    assert q["recipe"]["tools"] == ["Hatchet"]
    assert q["trade"]["sellPrice"] >= q["trade"]["buyPrice"]
    assert q["handoff"]["map"] == "four_gates" and not q["handoff"]["repeatOldIntro"]
    assert not q["reward"]["repeatable"]
