"""_continent_v2/publish_client.py: the territory manifest lists every image its cells use (externalResources).

ContinentChunkStream.configure reads the VRAM sidecar index of each image directory the TERRITORY manifest names
before it corrects any cell's image figures (godot-client/src/world/vram_textures.gd read_indexes_for). The v2
publisher wrote {} there, so the budget never read an index and counted every compressed image at its RGBA8 figure.
territory_resources rebuilds the list from the chunk manifests, with URIs relative to the territory's GLB directory.

The synthetic cases need nothing but the publisher module. The package cases check the committed isle packages
for every active catalog map: the territory list is exactly the union of the chunks' lists, every URI resolves to
the chunk's own file, and build_vram_textures.inventory plans the territory's entries into the chunks' directory.

    python -m pytest eloria-assets/maps/continent-v2/_continent_v2/tests/test_publish_client_resources.py -q
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
CHECKOUT = V2.parents[3]
sys.path.insert(0, str(V2))
sys.path.insert(0, str(CHECKOUT / "godot-client" / "tools"))
import publish_client as PC  # noqa: E402

REGIONS = tuple(entry["id"] for entry in json.loads(
    (CHECKOUT / "godot-client/world_authoring/continent-v2/territories.json").read_text(encoding="utf-8"))["entries"])
CHUNK_URI = "../../../../_continent_v2/shared-assets/{}.{}"
TERRITORY_URI = "../../_continent_v2/shared-assets/{}.{}"


def write_chunk(out, name, shas):
    chunk = out / "chunks" / name
    chunk.mkdir(parents=True, exist_ok=True)
    resources = {CHUNK_URI.format(sha, ext): sha for sha, ext in shas}
    (chunk / "world.json").write_text(json.dumps({"asset": {"id": f"x__chunk_{name}", "glb": "world.glb"},
                                                  "externalResources": resources}), encoding="utf-8")


def layout(tmp_path):
    out = tmp_path / "continent-v2" / "isle" / "client"
    out.mkdir(parents=True)
    return out


def test_union_rebased_to_the_territory(tmp_path):
    out = layout(tmp_path)
    a, b, c = "a" * 64, "b" * 64, "c" * 64
    write_chunk(out, "05_11", [(a, "png"), (b, "jpg")])
    write_chunk(out, "05_12", [(b, "jpg"), (c, "png")])
    write_chunk(out, "06_11", [])
    resources = PC.territory_resources(out, ["05_11", "05_12", "06_11"])
    assert resources == {TERRITORY_URI.format(a, "png"): a, TERRITORY_URI.format(b, "jpg"): b,
                         TERRITORY_URI.format(c, "png"): c}
    assert list(resources) == sorted(resources), "sorted, so a republish of the same cells writes the same bytes"
    # Each territory URI names the same file as the chunk URI it came from.
    for uri in resources:
        chunk_uri = CHUNK_URI.format(*Path(uri).name.split("."))
        assert os.path.normpath(out / uri) == os.path.normpath(out / "chunks" / "05_11" / chunk_uri)


def test_only_the_named_cells(tmp_path):
    out = layout(tmp_path)
    write_chunk(out, "05_11", [("a" * 64, "png")])
    write_chunk(out, "09_09", [("d" * 64, "png")])          # a stale folder a --chunks test publish left out
    assert PC.territory_resources(out, ["05_11"]) == {TERRITORY_URI.format("a" * 64, "png"): "a" * 64}


def test_one_uri_two_digests_is_refused(tmp_path):
    out = layout(tmp_path)
    chunk = out / "chunks"
    write_chunk(out, "05_11", [("a" * 64, "png")])
    (chunk / "05_12").mkdir()
    (chunk / "05_12" / "world.json").write_text(json.dumps({"asset": {"glb": "world.glb"}, "externalResources": {
        CHUNK_URI.format("a" * 64, "png"): "e" * 64}}), encoding="utf-8")
    with pytest.raises(ValueError, match="another chunk"):
        PC.territory_resources(out, ["05_11", "05_12"])


def packages():
    # Every active map must publish; a missing package must not silently remove coverage.
    return [pytest.param(CHECKOUT / "eloria-assets/maps/continent-v2" / region / "client" / "world.json",
                         id=region) for region in REGIONS]


@pytest.mark.parametrize("manifest_path", packages())
def test_committed_package_lists_its_cells_images(manifest_path):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    out = manifest_path.parent
    names = [entry["id"] for entry in manifest["streamingChunks"]["chunks"]]
    listed = manifest.get("externalResources") or {}
    assert listed == PC.territory_resources(out, names)
    shas = set()
    for entry in manifest["streamingChunks"]["chunks"]:
        shas |= set(entry["sharedResourceResidentBytes"])
    assert set(listed.values()) == shas, "every image the budget counts is listed, and nothing else"
    for uri, digest in listed.items():
        path = out / uri
        assert path.is_file(), uri
        assert path.name.startswith(digest)
    sample = sorted(listed.items())[:5]
    for uri, digest in sample:
        assert hashlib.sha256((out / uri).read_bytes()).hexdigest() == digest


@pytest.mark.parametrize("manifest_path", packages())
def test_sidecar_tool_plans_the_territory_into_the_pool(manifest_path):
    tool = pytest.importorskip("build_vram_textures")
    found = tool.inventory([manifest_path.parents[2]])
    directories = {directory for directory, _ in found}
    assert directories == {(manifest_path.parents[2] / "_continent_v2" / "shared-assets").resolve()}
