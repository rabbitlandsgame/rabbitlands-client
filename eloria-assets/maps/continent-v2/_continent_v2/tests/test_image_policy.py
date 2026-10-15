"""_continent_v2/image_policy.py: the rules the v2 publisher applies to source images before the chunk exporter.

The synthetic cases build tiny glTF documents (PNG images in the binary chunk) and check that a resampled image is
swapped for its recorded derived bytes as a new buffer view, that a derived file missing from the pool or not
hashing to its record is refused, and that the wrap resample keeps a tiling image tiling. The exporter case runs
nymara-regions' scene_io.Exporter on a policy-applied document: the source image is never written or counted, the
derived one is, under its own sha. The package cases check the committed isle packages against image_policy.json:
no cell names a rule's source image any more, and the cells sample the derived grounds. The kept cases: a rule for
an image the policy keeps uncompressed (keepUncompressed) is refused, the hub paving (owner call 2026-10-03) has no
rule and keeps its 1254 px bytes, and no committed package names a retired copy or was published while a rule still
swapped a kept image (they fail until the territory is republished with the current policy).

    python -m pytest eloria-assets/maps/continent-v2/_continent_v2/tests/test_image_policy.py -q
"""
from __future__ import annotations

import hashlib
import io
import json
import math
from pathlib import Path
import sys

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
CHECKOUT = V2.parents[3]
sys.path.insert(0, str(V2))
import image_policy as IP  # noqa: E402

REGIONS = tuple(entry["id"] for entry in json.loads(
    (CHECKOUT / "godot-client/world_authoring/continent-v2/territories.json").read_text(encoding="utf-8"))["entries"])


def png(array: np.ndarray) -> bytes:
    from PIL import Image
    buffer = io.BytesIO()
    Image.fromarray(array.astype(np.uint8)).save(buffer, format="PNG")
    return buffer.getvalue()


def document(images: list[bytes], normal_of: list[int | None]) -> tuple[dict, bytes]:
    """A glTF JSON + binary with one texture per image and one material per normal_of entry (its normalTexture's
    texture index, or None), each material also sampling texture 0 as base colour."""
    body = bytearray()
    views = []
    for data in images:
        body.extend(b"\0" * ((-len(body)) % 4))
        views.append({"buffer": 0, "byteOffset": len(body), "byteLength": len(data)})
        body.extend(data)
    doc = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(body)}], "bufferViews": views,
           "images": [{"bufferView": i, "mimeType": "image/png"} for i in range(len(images))],
           "textures": [{"source": i} for i in range(len(images))], "materials": []}
    for normal in normal_of:
        material = {"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}
        if normal is not None:
            material["normalTexture"] = {"index": normal, "scale": 1.0}
        doc["materials"].append(material)
    return doc, bytes(body)


def view_bytes(doc, body, image):
    view = doc["bufferViews"][doc["images"][image]["bufferView"]]
    return body[view["byteOffset"]:view["byteOffset"] + view["byteLength"]]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def test_a_resampled_image_is_its_recorded_copy(tmp_path):
    ground = png(np.random.default_rng(3).integers(0, 255, (10, 10, 4)))
    other = png(np.full((8, 8, 3), 40))
    derived = IP.resample_wrapped(ground, (12, 12))
    (tmp_path / f"{sha(derived)}.png").write_bytes(derived)
    doc, body = document([other, ground], [None])
    policy = {"schema": IP.SCHEMA, "resample": {sha(ground): {"size": [12, 12], "derived": sha(derived)}}}
    doc, out, stats = IP.apply(doc, body, tmp_path, policy)
    assert view_bytes(doc, out, 1) == derived
    assert view_bytes(doc, out, 0) == other, "the other image keeps its bytes"
    assert doc["images"][1]["mimeType"] == "image/png"
    assert doc["bufferViews"][-1]["byteOffset"] % 4 == 0
    assert doc["buffers"][0]["byteLength"] == len(out) and out[:len(body)] == body
    assert stats["resampledImages"] == [sha(ground)]


def test_a_derived_file_is_never_recomputed(tmp_path):
    ground = png(np.random.default_rng(4).integers(0, 255, (10, 10, 3)))
    doc, body = document([ground], [None])
    rule = {"size": [12, 12], "derived": "0" * 64}
    policy = {"schema": IP.SCHEMA, "resample": {sha(ground): rule}}
    with pytest.raises(FileNotFoundError, match="--record"):
        IP.apply(doc, body, tmp_path, policy)
    (tmp_path / ("0" * 64 + ".png")).write_bytes(b"not the recorded bytes")
    with pytest.raises(ValueError, match="does not hash"):
        IP.apply(doc, body, tmp_path, policy)


def test_wrap_resample_keeps_a_tiling_image_tiling():
    x = np.arange(30)
    wave = 128 + 100 * np.sin(2 * math.pi * x / 30)                     # one period across the tile
    image = np.repeat(np.repeat(wave[None, :, None], 30, axis=0), 3, axis=2)
    from PIL import Image
    out = np.asarray(Image.open(io.BytesIO(IP.resample_wrapped(png(image), (32, 32))))).astype(float)
    expected = 128 + 100 * np.sin(2 * math.pi * ((np.arange(32) + 0.5) * 30 / 32 - 0.5) / 30)
    assert out.shape == (32, 32, 3)
    assert np.abs(out[0, :, 0] - expected).max() <= 2.0, "the wave continues across the wrapped edge"
    assert abs(out.mean() - image.mean()) < 0.6
    flat = IP.resample_wrapped(png(np.full((30, 30, 4), [10, 20, 30, 200])), (32, 32))
    assert np.unique(np.asarray(Image.open(io.BytesIO(flat))).reshape(-1, 4), axis=0).tolist() == [[10, 20, 30, 200]]


def test_the_exporter_writes_and_counts_only_what_the_policy_left(tmp_path):
    sys.path.insert(0, str(CHECKOUT / "eloria-assets/maps/nymara-regions/_continent"))
    S = pytest.importorskip("scene_io")
    base = png(np.full((8, 8, 3), 90))
    ground = png(np.random.default_rng(5).integers(0, 255, (10, 10, 4)))
    derived = IP.resample_wrapped(ground, (12, 12))
    pool = tmp_path / "pool"
    pool.mkdir()
    (pool / f"{sha(derived)}.png").write_bytes(derived)
    doc, body = document([base, ground], [None])
    doc["materials"].append({"pbrMetallicRoughness": {"baseColorTexture": {"index": 1}}})
    doc["meshes"] = [{"primitives": [{"attributes": {}, "material": 0}, {"attributes": {}, "material": 1}]}]
    doc["nodes"] = [{"name": "piece", "mesh": 0}]
    doc["scenes"] = [{"nodes": [0]}]
    doc["accessors"] = []
    policy = {"schema": IP.SCHEMA, "resample": {sha(ground): {"size": [12, 12], "derived": sha(derived)}}}
    doc, body, _ = IP.apply(doc, body, pool, policy)
    shared = tmp_path / "shared"
    exporter = S.Exporter(tmp_path / "chunk" / "world.glb", shared)
    exporter.add(doc, body, [0])
    stats = exporter.write()
    assert set(stats["sharedResourceResidentBytes"]) == {sha(base), sha(derived)}
    assert stats["sharedResourceResidentBytes"][sha(derived)] == math.ceil(12 * 12 * 4 * 4 / 3)
    assert sorted(p.name for p in shared.iterdir()) == sorted([f"{sha(base)}.png", f"{sha(derived)}.png"])


def test_the_committed_policy_holds():
    policy = IP.load_policy()
    assert IP.check(policy, IP.SHARED) == []
    for digest, rule in policy.get("resample", {}).items():
        assert [v % 4 for v in rule["size"]] == [0, 0]
        assert rule["derived"] != digest


def packages():
    # Every active map must publish; a missing package must not silently remove coverage.
    return [pytest.param(CHECKOUT / "eloria-assets/maps/continent-v2" / region / "client" / "world.json",
                         id=region) for region in REGIONS]


@pytest.mark.parametrize("manifest_path", packages())
def test_no_cell_names_a_rule_source_any_more(manifest_path):
    policy = IP.load_policy()
    retired = set(policy.get("resample", {}))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    named = {s for entry in manifest["streamingChunks"]["chunks"] for s in entry["sharedResourceResidentBytes"]}
    assert named & retired == set()
    record = json.loads((manifest_path.parent / "publication.json").read_text(encoding="utf-8"))
    # The partition can leave a map with none of these source grounds. Require the
    # derived bytes for every rule source its publication actually processed.
    applied = {digest for side in record["imagePolicy"].values()
               for digest in side["resampledImages"]}
    assert applied <= retired, "publication names an unknown image-policy source"
    derived = {policy["resample"][digest]["derived"] for digest in applied}
    assert derived <= named, "a processed rule source must sample its recorded derived bytes"


PAVING = "e9adde18e1b92def62b1a8a83748d3ce0a32ff8c3d53753bbd363e6a9bcff951"


def test_a_kept_image_refuses_a_resample_rule(tmp_path):
    ground = png(np.random.default_rng(6).integers(0, 255, (10, 10, 3)))
    derived = IP.resample_wrapped(ground, (12, 12))
    (tmp_path / f"{sha(derived)}.png").write_bytes(derived)
    rule = {"size": [12, 12], "derived": sha(derived)}
    policy = {"schema": IP.SCHEMA, "resample": {sha(ground): rule}}
    assert IP.check(policy, tmp_path) == []
    policy["keepUncompressed"] = {sha(ground): {"what": "a paving", "why": "an owner call"}}
    problems = IP.check(policy, tmp_path)
    assert len(problems) == 1 and "keepUncompressed" in problems[0]
    doc, body = document([ground], [None])
    with pytest.raises(ValueError, match="keepUncompressed"):
        IP.apply(doc, body, tmp_path, policy)


def test_the_hub_paving_ships_its_own_bytes():
    """Owner call 2026-10-03: the castle plaza and court paving stays uncompressed. No rule swaps it for the BC7 copy,
    so the cells sample the 1254 px source again, which no BC sidecar holds (build_vram_textures.py excludes a size
    that is not a multiple of 4) and the client uploads RGBA8."""
    from PIL import Image
    policy = IP.load_policy()
    assert PAVING not in policy.get("resample", {})
    assert PAVING in policy.get("keepUncompressed", {})
    data = (IP.SHARED / f"{PAVING}.png").read_bytes()
    assert sha(data) == PAVING
    with Image.open(io.BytesIO(data)) as picture:
        size = picture.size
    assert list(size) == policy["keepUncompressed"][PAVING]["sourceSize"]
    assert any(v % 4 for v in size), "a size a BC format holds would get a sidecar"
    doc, body = document([png(np.full((8, 8, 3), 40)), data], [None])
    views = len(doc["bufferViews"])
    doc, out, stats = IP.apply(doc, body, IP.SHARED, policy)
    assert stats["imagesResampled"] == 0 and out == body and len(doc["bufferViews"]) == views
    assert view_bytes(doc, out, 1) == data


@pytest.mark.parametrize("manifest_path", packages())
def test_no_cell_samples_a_retired_copy(manifest_path):
    """A committed package samples a kept image's own bytes (keepUncompressed), never the copy a retired rule swapped
    in, and was not published while such a rule still held. A stale or mis-merged republish fails here."""
    policy = IP.load_policy()
    kept = policy.get("keepUncompressed", {})
    record = json.loads((manifest_path.parent / "publication.json").read_text(encoding="utf-8"))
    applied = {digest for side in (record.get("imagePolicy") or {}).values()
               for digest in side.get("resampledImages", [])}
    assert applied & set(kept) == set(), "published while a rule still swapped a kept image: republish the territory"
    retired = {entry["retiredDerived"] for entry in kept.values() if entry.get("retiredDerived")}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    named = {s for entry in manifest["streamingChunks"]["chunks"] for s in entry["sharedResourceResidentBytes"]}
    assert named & retired == set()
