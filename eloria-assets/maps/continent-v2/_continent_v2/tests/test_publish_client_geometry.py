"""_continent_v2/publish_client.py: a v2 cell counts its geometry at 1.0 x its GLB; every legacy map keeps 5 x.

ContinentChunkStream (godot-client/src/world/continent_chunk_stream.gd) adds a cell's geometryResidentBytes to the
images it brings when it decides what stays resident under maximumResidentBytes. The twelve territories' exporter
(nymara-regions/_continent/build_continent.py) and Four Gates publish 5 x the chunk GLB's bytes there; the v2
publisher did the same until the owner call of 2026-10-03, which set 1.0 x for continent-v2 only (a v2 cell's mesh
memory measured 0.45-0.48 x its GLB). The client is not changed: the figure travels in the v2 manifests alone.

The synthetic cases need only the publisher module. The legacy cases read every streamed territory manifest outside
continent-v2 in this checkout, the figures the client budgets with: each cell's geometry is still 5 x the bytes of
the GLB it names (and those are the shipped file's bytes), its estimate still sums geometry and images, and the
budget is still 256 MiB. The package case checks every committed isle package: it records the factor
(publication.json geometryResidentFactor) and every cell carries it, so a stale or mis-merged republish that writes
5 x again fails (a package published before the call fails until the territory is republished).

    python -m pytest eloria-assets/maps/continent-v2/_continent_v2/tests/test_publish_client_geometry.py -q
"""
from __future__ import annotations

import inspect
import json
import math
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
CHECKOUT = V2.parents[3]
MAPS = CHECKOUT / "eloria-assets" / "maps"
sys.path.insert(0, str(V2))
import publish_client as PC  # noqa: E402

REGIONS = tuple(entry["id"] for entry in json.loads(
    (CHECKOUT / "godot-client/world_authoring/continent-v2/territories.json").read_text(encoding="utf-8"))["entries"])
LEGACY_FACTOR = 5


def test_a_v2_cell_counts_its_glb_once():
    assert PC.GEOMETRY_RESIDENT_FACTOR == 1.0
    for size in (1, 12, 617_280, 13_957_123, 104_857_600):
        assert PC.geometry_resident_bytes(size) == size
    assert PC.geometry_resident_bytes(0) == 1, "the client refuses a cell whose figure is below 1"


def test_the_publisher_writes_that_figure_into_every_cell():
    source = inspect.getsource(PC.main)
    assert 'geometry = geometry_resident_bytes(stats["glbBytes"])' in source
    assert '"geometryResidentBytes": geometry' in source
    assert '"estimatedResidentBytes": geometry + sum(stats["sharedResourceResidentBytes"].values())' in source
    assert 'record["geometryResidentFactor"] = GEOMETRY_RESIDENT_FACTOR' in source
    assert '["glbBytes"] * 5' not in source


def test_the_legacy_exporter_keeps_five_times():
    text = (MAPS / "nymara-regions" / "_continent" / "build_continent.py").read_text(encoding="utf-8")
    assert "geometry_bytes=chunk_stats['glbBytes']*5" in text


def legacy_manifests():
    found = []
    for path in sorted(MAPS.rglob("world.json")):
        relative = path.relative_to(MAPS)
        if relative.parts[0] == "continent-v2" or "chunks" in relative.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if '"streamingChunks"' in text and json.loads(text).get("streamingChunks"):
            found.append(pytest.param(path, id=relative.parent.as_posix()))
    return found or [pytest.param(None, marks=pytest.mark.skip(reason="no streamed legacy map in this checkout"))]


@pytest.mark.parametrize("manifest_path", legacy_manifests())
def test_legacy_figures_keep_five_times_their_glb(manifest_path):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stream = manifest["streamingChunks"]
    assert stream["maximumResidentBytes"] == PC.SHIPPING_BUDGET
    assert stream["chunks"]
    for cell in stream["chunks"]:
        child_path = manifest_path.parent / cell["manifest"]
        child = json.loads(child_path.read_text(encoding="utf-8"))
        glb = child_path.parent / child["asset"]["glb"]
        assert cell["glbBytes"] == glb.stat().st_size, (cell["id"], "the figure is the shipped GLB's")
        assert cell["geometryResidentBytes"] == LEGACY_FACTOR * cell["glbBytes"], cell["id"]
        assert cell["estimatedResidentBytes"] == cell["geometryResidentBytes"] + sum(
            cell["sharedResourceResidentBytes"].values()), cell["id"]


def packages():
    # Every active map must publish; a missing package must not silently remove coverage.
    return [pytest.param(MAPS / "continent-v2" / region / "client", id=region)
            for region in REGIONS]


@pytest.mark.parametrize("package", packages())
def test_a_package_published_with_the_factor_carries_it(package):
    record = json.loads((package / "publication.json").read_text(encoding="utf-8"))
    assert "geometryResidentFactor" in record, "published before the 1.0 x geometry figure: republish the territory"
    assert record["geometryResidentFactor"] == PC.GEOMETRY_RESIDENT_FACTOR
    manifest = json.loads((package / "world.json").read_text(encoding="utf-8"))
    for cell in manifest["streamingChunks"]["chunks"]:
        glb = package / Path(cell["manifest"]).parent / "world.glb"
        assert cell["glbBytes"] == glb.stat().st_size, cell["id"]
        assert cell["geometryResidentBytes"] == math.ceil(PC.GEOMETRY_RESIDENT_FACTOR * cell["glbBytes"]), cell["id"]
        assert cell["estimatedResidentBytes"] == cell["geometryResidentBytes"] + sum(
            cell["sharedResourceResidentBytes"].values()), cell["id"]
