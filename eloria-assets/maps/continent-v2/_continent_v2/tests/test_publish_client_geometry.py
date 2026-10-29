"""Every streamed cell counts its geometry at 1.0 x its GLB: continent-v2's publish_client.py and the legacy maps alike.

ContinentChunkStream (godot-client/src/world/continent_chunk_stream.gd) adds a cell's geometryResidentBytes to the
images it brings when it decides what stays resident under maximumResidentBytes. The v2 publisher wrote 5 x the chunk
GLB's bytes there until the owner call of 2026-10-03 set 1.0 x for continent-v2 (a v2 cell's mesh memory measured
0.45-0.48 x its GLB). The twelve legacy territories' exporter (nymara-regions/_continent/build_continent.py, Four
Gates included) kept 5 x until the owner call of 2026-10-16 set 1.0 x for them too (publish_finish.py
LEGACY_RESIDENT_FACTOR; their pooled prototypes measured 0.91 x their GLB, none above 1.0, their own meshes 0.31 x).
The client is not changed: the figure travels in the manifests alone.

The synthetic cases need only the publisher module. The legacy cases read every streamed territory manifest outside
continent-v2 in this checkout, the figures the client budgets with: each cell's geometry is 1 x the bytes of the GLB
it names (and those are the shipped file's bytes), and the budget is still 256 MiB. The package case checks every
committed isle package: it records the factor (publication.json geometryResidentFactor) and every cell carries it, so
a stale or mis-merged republish that writes 5 x again fails (a package published before the call fails until the
territory is republished).

Both kinds of cell also state the pooled prototypes their chunk draws (sharedMeshResidentBytes, written by
publish_finish.py's restamp at the cell's own factor): a prop the space passes moved into maps/_shared/meshes left the
chunk's GLB but is still drawn while the cell is resident, and the stream counts each prototype once. Its estimate
sums geometry, images and prototypes.

    python -m pytest eloria-assets/maps/continent-v2/_continent_v2/tests/test_publish_client_geometry.py -q
"""
from __future__ import annotations

import functools
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
LEGACY_FACTOR = 1.0


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
    # The prototype figures come from the space passes, at the v2 factor, before the record reads the manifest.
    assert source.index("PF.finish([out], factor=GEOMETRY_RESIDENT_FACTOR)") < source.index(
        'manifest = json.loads((out / "world.json").read_text(encoding="utf-8"))')
    assert '["glbBytes"] * 5' not in source


def test_the_legacy_exporters_count_their_glb_once():
    assert PC.PF.LEGACY_RESIDENT_FACTOR == LEGACY_FACTOR, "owner call 2026-10-16: the legacy maps count 1.0 x too"
    text = (MAPS / "nymara-regions" / "_continent" / "build_continent.py").read_text(encoding="utf-8")
    assert "geometry_bytes=max(1,math.ceil(PF.LEGACY_RESIDENT_FACTOR*chunk_stats['glbBytes']))" in text
    assert "chunk_stats['glbBytes']*5" not in text


@functools.cache
def pool_index(directory):
    return json.loads((directory / "index.json").read_text(encoding="utf-8"))["prototypes"]


def drawn_prototypes(child_path, child, factor):
    """What a chunk's pooled prototypes cost at `factor`, from the pool index (which must match the file)."""
    figures = {}
    for uri in child.get("externalMeshes") or {}:
        target = (child_path.parent / uri).resolve()
        index = pool_index(target.parent)
        assert index[target.stem]["bytes"] == target.stat().st_size, (uri, "the pool index is behind its file")
        figures[target.stem] = math.ceil(factor * index[target.stem]["bytes"])
    return figures


def check_estimate(cell, child_path, child, factor):
    prototypes = drawn_prototypes(child_path, child, factor)
    assert cell.get("sharedMeshResidentBytes", {}) == prototypes, (cell["id"], "the prototypes it draws")
    assert cell["estimatedResidentBytes"] == cell["geometryResidentBytes"] + sum(
        cell["sharedResourceResidentBytes"].values()) + sum(prototypes.values()) + cell.get("roadGroundResidentBytes", 0), cell["id"]


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
def test_legacy_figures_count_their_glb_once(manifest_path):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stream = manifest["streamingChunks"]
    assert stream["maximumResidentBytes"] == PC.SHIPPING_BUDGET
    assert stream["chunks"]
    for cell in stream["chunks"]:
        child_path = manifest_path.parent / cell["manifest"]
        child = json.loads(child_path.read_text(encoding="utf-8"))
        glb = child_path.parent / child["asset"]["glb"]
        assert cell["glbBytes"] == glb.stat().st_size, (cell["id"], "the figure is the shipped GLB's")
        assert cell["geometryResidentBytes"] == max(1, math.ceil(LEGACY_FACTOR * cell["glbBytes"])), cell["id"]
        check_estimate(cell, child_path, child, LEGACY_FACTOR)


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
        child_path = package / cell["manifest"]
        glb = child_path.parent / "world.glb"
        assert cell["glbBytes"] == glb.stat().st_size, cell["id"]
        assert cell["geometryResidentBytes"] == math.ceil(PC.GEOMETRY_RESIDENT_FACTOR * cell["glbBytes"]), cell["id"]
        check_estimate(cell, child_path, json.loads(child_path.read_text(encoding="utf-8")),
                       PC.GEOMETRY_RESIDENT_FACTOR)
        assert record["estimatedResidentMiB"][cell["id"]] == round(cell["estimatedResidentBytes"] / 1048576, 1)
