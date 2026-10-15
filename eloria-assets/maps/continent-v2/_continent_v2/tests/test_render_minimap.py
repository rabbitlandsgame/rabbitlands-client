"""_continent_v2/render_minimap.py: a continent-v2 territory's map picture, drawn from its published chunks.

The picture is framed as the live Tab map frames the territory (asset.mapBounds, whole metres, one pixel a metre),
holds the neighbours' ground that lies in the frame (moved by the difference of the continent translations), and is
stamped with what it was drawn from; --check reports a picture whose image or chunks (its own or a neighbour's) have
changed since. The drawing case renders two one-quad territories with the shared atlas renderer, which compiles its
native rasteriser: it skips without a C compiler (gcc or clang, or ELORIA_ATLAS_CC).
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
CHECKOUT = V2.parents[3]
sys.path.insert(0, str(V2))
import render_minimap as RM  # noqa: E402
import publish_client as PC  # noqa: E402

FRAME = "continent-v2"


def quad_glb(path: Path, x0, z0, x1, z1, y, colour, material="ground") -> None:
    """A GLB holding one flat quad (two triangles, facing up) with one untextured material."""
    positions = struct.pack("<12f", x0, y, z0, x1, y, z0, x1, y, z1, x0, y, z1)
    indices = struct.pack("<6H", 0, 2, 1, 0, 3, 2) + b"\0\0"
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
           "nodes": [{"name": "Terrain_fixture", "mesh": 0}],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "material": 0}]}],
           "materials": [{"name": material, "pbrMetallicRoughness": {"baseColorFactor": list(colour),
                                                                      "metallicFactor": 0.0}}],
           "buffers": [{"byteLength": len(positions) + len(indices)}],
           "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(positions)},
                           {"buffer": 0, "byteOffset": len(positions), "byteLength": 12}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": 4, "type": "VEC3",
                          "min": [min(x0, x1), y, min(z0, z1)], "max": [max(x0, x1), y, max(z0, z1)]},
                         {"bufferView": 1, "componentType": 5123, "count": 6, "type": "SCALAR"}]}
    body = json.dumps(doc).encode()
    body += b" " * (-len(body) % 4)
    binary = positions + indices
    total = 12 + 8 + len(body) + 8 + len(binary)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<I4s", len(body), b"JSON") + body
                     + struct.pack("<I4s", len(binary), b"BIN\0") + binary)


def fixture_checkout(root: Path) -> Path:
    """Two territories on one frame: `isle` (a 40 m square frame, its ground the west half) and `holm`, whose ground
    lies 10-30 m east of isle's origin, its west half inside isle's frame. A third map on another frame is never drawn."""
    entries, rows = [], {}
    for region, translation, quad, colour in (
            ("isle", [100.0, 0.0, 200.0], (-20, -20, 0, 20), (0.2, 0.7, 0.2, 1.0)),
            ("holm", [120.0, 0.0, 200.0], (-10, -20, 10, 20), (0.8, 0.2, 0.2, 1.0))):
        package = root / "eloria-assets" / "maps" / "continent-v2" / region / "client"
        quad_glb(package / "chunks" / "00_00" / "world.glb", *quad, 5.0, colour)
        (package / "chunks" / "00_00" / "world.json").write_text(json.dumps({"asset": {"glb": "world.glb"}}),
                                                                 encoding="utf-8")
        bounds = {"min": [-20.0, 0.0, -20.0], "max": [20.0, 6.0, 20.0]}
        chunk_bounds = {"min": [float(quad[0]), 5.0, float(quad[1])], "max": [float(quad[2]), 5.0, float(quad[3])]}
        (package / "world.json").write_text(json.dumps({
            "asset": {"id": region, "mapBounds": bounds, "playableBounds": bounds},
            "continentGeography": {"translation": translation},
            "streamingChunks": {"chunks": [{"id": "00_00", "manifest": "chunks/00_00/world.json",
                                            "bounds": chunk_bounds}]}}), encoding="utf-8")
        entries.append({"id": region, "label": region.title()})
        rows[region] = {"manifest": f"res://../eloria-assets/maps/continent-v2/{region}/client/world.json",
                        "status": "continent-v2-served",
                        "continentGeography": {"frame": FRAME, "translation": translation}}
    rows["elsewhere"] = {"manifest": "res://../eloria-assets/maps/elsewhere/world.json",
                         "continentGeography": {"translation": [100.0, 0.0, 200.0]}}
    for relative, data in ((RM.CATALOG, {"entries": entries}), (RM.REGISTRY, {"maps": rows})):
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_text(json.dumps(data), encoding="utf-8")
    return root


def test_the_frame_is_the_live_tab_maps_in_whole_metres():
    bounds = {"min": [-1019.0, -23.7, -1049.0], "max": [1019.0, 198.3, 989.0]}
    assert RM.frame_of({"asset": {"id": "x", "mapBounds": bounds}}) == ([-1019.0, -1049.0], [1019.0, 989.0],
                                                                        [2038, 2038])
    with pytest.raises(RM.MinimapError, match="not whole metres"):
        RM.frame_of({"asset": {"id": "x", "mapBounds": {"min": [-1.5, 0, 0], "max": [1, 0, 1]}}})


def test_the_neighbours_on_the_frame_are_drawn_moved_into_its_metres(tmp_path):
    root = fixture_checkout(tmp_path / "checkout")
    found = RM.sources(root, "isle")
    assert [s["region"] for s in found] == ["isle", "holm"]
    assert found[1]["offset"] == (20.0, 0.0)
    assert [s["region"] for s in RM.sources(root, "holm")] == ["holm", "isle"]


def stamp(root: Path, region: str, image: bytes, report: dict) -> Path:
    package = RM.package_of(root, region)
    (package / PC.MINIMAP).write_bytes(image)
    manifest = json.loads((package / "world.json").read_text(encoding="utf-8"))
    manifest["minimap"] = RM.minimap_block(manifest, report)
    (package / "world.json").write_text(json.dumps(manifest), encoding="utf-8")
    return package


def test_check_reports_a_missing_changed_or_stale_picture(tmp_path):
    root = fixture_checkout(tmp_path / "checkout")
    assert RM.check(root, ["isle"]) == ["isle: the package has no minimap block; run render_minimap.py --apply"]
    found = RM.sources(root, "isle")
    report = {"worldMin": [-20.0, -20.0], "worldMax": [20.0, 20.0], "imageSize": [40, 40], "styleVersion": 4,
              "imageSha256": RM.sha_bytes(b"RIFF isle"), "supersample": 2, "windowMetres": 256, "waterRGB": [1, 2, 3],
              "chunksSha256": PC.chunks_digest(found[0]["package"], found[0]["chunks"]),
              "neighbourChunksSha256": {"holm": PC.chunks_digest(found[1]["package"], found[1]["chunks"])}}
    package = stamp(root, "isle", b"RIFF isle", report)
    assert RM.check(root, ["isle"]) == []
    (package / PC.MINIMAP).write_bytes(b"RIFF edited")
    assert any("not the picture the manifest records" in p for p in RM.check(root, ["isle"]))
    (package / PC.MINIMAP).write_bytes(b"RIFF isle")
    # a neighbour republished: the picture of its ground in this frame is stale too
    quad_glb(found[1]["package"] / "chunks" / "00_00" / "world.glb", -10, -20, 10, 20, 7.0, (0.8, 0.2, 0.2, 1.0))
    assert RM.check(root, ["isle"]) == ["isle: the picture was drawn from other chunks than ['holm'] hold now; run "
                                        "render_minimap.py --region isle --apply"]


def compiler_available() -> bool:
    sys.path.insert(0, str(CHECKOUT / "eloria-assets" / "tools"))
    try:
        import atlas_soft_ground
        atlas_soft_ground.compiler()
        return True
    except Exception:  # noqa: BLE001 - any missing piece of the native toolchain
        return False


@pytest.mark.skipif(not compiler_available(), reason="the atlas renderer needs a C compiler")
def test_a_drawn_picture_holds_its_own_ground_and_the_neighbours_in_place(tmp_path):
    root = fixture_checkout(tmp_path / "checkout")
    # the drawing tool reads the atlas renderer from this checkout, so link the real tools in
    tools = root / "eloria-assets" / "tools"
    for relative in ("eloria-assets/tools", "eloria-assets/maps/nymara-regions/_toolkit",
                     "godot-client/src/world/soft_ground.gdshader"):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            if (CHECKOUT / relative).is_dir():
                import shutil
                shutil.copytree(CHECKOUT / relative, target, ignore=shutil.ignore_patterns("__pycache__", "*.glb"))
            else:
                target.write_bytes((CHECKOUT / relative).read_bytes())
    assert tools.is_dir()
    report = RM.render(root, "isle", tmp_path / "work", supersample=1, window=16, log=lambda *_: None)
    assert report["imageSize"] == [40, 40] and report["windows"] == 9
    assert set(report["neighbourChunksSha256"]) == {"holm"}
    from PIL import Image
    picture = Image.open(tmp_path / "work" / "isle" / PC.MINIMAP).convert("RGB")
    water = tuple(report["waterRGB"])
    west, east_edge = picture.getpixel((5, 20)), picture.getpixel((35, 20))
    middle = picture.getpixel((25, 20))   # isle x 5: neither isle's ground (x < 0) nor holm's (x >= 10)
    def near(a, b):
        return all(abs(int(p) - int(q)) <= 24 for p, q in zip(a, b))
    assert west[1] > west[0] and not near(west, water)        # isle's green ground
    assert east_edge[0] > east_edge[1] and not near(east_edge, water)   # holm's red ground, moved 20 m east
    assert near(middle, water)
    RM.apply(root, "isle", tmp_path / "work", report)
    assert RM.check(root, ["isle"]) == []
