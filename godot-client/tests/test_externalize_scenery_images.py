import copy
import importlib.util
import json
from pathlib import Path
import struct
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "godot-client/tools"))
from scenery_image_sources import KEY, POLICY, ELIGIBLE, sha, validate, glb_chunks

spec = importlib.util.spec_from_file_location("externalize_scenery", ROOT / "eloria-assets/tools/externalize_scenery_images.py")
E = importlib.util.module_from_spec(spec)
spec.loader.exec_module(E)


def fixture(tmp_path):
    root = tmp_path / "repo"
    path = root / "godot-client/assets/world/test/model.glb"
    path.parent.mkdir(parents=True)
    image = b"\x89PNG\r\n\x1a\nexact source bytes including transparent RGB"
    geometry = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    document = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(geometry + image)}],
                "bufferViews": [{"buffer": 0, "byteLength": len(geometry)},
                                {"buffer": 0, "byteOffset": len(geometry), "byteLength": len(image)}],
                "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"}],
                "images": [{"bufferView": 1, "mimeType": "image/png", "name": "source"}],
                "textures": [{"source": 0}], "samplers": [{"wrapS": 10497}],
                "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
                "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "material": 0}]}]}
    path.write_bytes(E.encode(document, geometry + image))
    return root, path, image, geometry, document


def test_image_extraction_keeps_encoded_bytes_and_geometry(tmp_path):
    root, path, image, geometry, document = fixture(tmp_path)
    result, generated, proof = E.transform(root, path, {})
    assert list(generated.values()) == [image]
    path.write_bytes(result)
    for destination, data in generated.items():
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    d, binary = glb_chunks(path)
    assert binary[:len(geometry)] == geometry
    assert d["materials"] == document["materials"]
    assert d["accessors"] == document["accessors"]
    assert d["images"][0]["extras"] == {POLICY: ".", ELIGIBLE: True}
    assert proof["retained_view_payloads_byte_identical"]
    assert validate(root, path)["images"][0]["sha256"] == sha(image)
    again, files, _ = E.transform(root, path, {})
    assert again == result and files == {}


def test_reuses_only_declared_canonical_contents(tmp_path):
    root, path, image, _, _ = fixture(tmp_path)
    canonical = root / "eloria-assets/maps/_shared/images/canonical.png"
    canonical.parent.mkdir(parents=True)
    canonical.write_bytes(image)
    result, generated, _ = E.transform(root, path, {sha(image): canonical})
    assert not generated
    path.write_bytes(result)
    record = validate(root, path)["images"][0]
    assert record["path"] == canonical
    assert record["policy_directory"] == path.parent
    canonical.write_bytes(image + b"changed")
    with pytest.raises(ValueError, match="missing/changed"):
        validate(root, path)


def test_nonimage_reference_prevents_view_retirement(tmp_path):
    root, path, image, geometry, d = fixture(tmp_path)
    d["extras"] = {"retainedUnknown": {"bufferView": 1}}
    path.write_bytes(E.encode(d, geometry + image))
    result, _, proof = E.transform(root, path, {})
    assert proof["removed_image_only_views"] == []
    path.write_bytes(result)
    assert len(glb_chunks(path)[0]["bufferViews"]) == 2


def test_existing_uri_is_not_rebased_or_newly_sidecar_eligible(tmp_path):
    root, path, image, geometry, d = fixture(tmp_path)
    original = {"uri": "legacy.png", "name": "intentional resource", "mimeType": "image/png"}
    (path.parent / "legacy.png").write_bytes(image)
    d["images"].append(copy.deepcopy(original))
    path.write_bytes(E.encode(d, geometry + image))
    result, _, _ = E.transform(root, path, {})
    path.write_bytes(result)
    converted = glb_chunks(path)[0]["images"][1]
    assert {key: converted[key] for key in original} == original
    assert converted["extras"][ELIGIBLE] is False


@pytest.mark.parametrize("policy", ["%2e", "../../../../actors", "/absolute", "C:/escape", "..\\escape"])
def test_unsafe_or_changed_policy_rejected(tmp_path, policy):
    root, path, _, _, _ = fixture(tmp_path)
    result, _, _ = E.transform(root, path, {})
    path.write_bytes(result)
    d, _ = glb_chunks(path)
    d["images"][0]["extras"][POLICY] = policy
    d["extras"][KEY]["imagePolicies"][d["images"][0]["uri"]] = [policy]
    with pytest.raises(ValueError):
        validate(root, path, d, verify_bytes=False)


def test_plan_apply_preflights_and_recovers(tmp_path):
    root, path, image, _, _ = fixture(tmp_path)
    original = path.read_bytes()
    shipping = tmp_path / "shipping.json"
    shipping.write_text(json.dumps({"files": []}))
    stage = tmp_path / "stage"
    record = E.plan(root, shipping, stage)
    assert record["models_checked"] == 1 and record["new_image_count"] == 1
    path.write_bytes(original + b"changed")
    with pytest.raises(ValueError, match="source changed"):
        E.apply(stage / "plan.json", root / ".local/recovery")
    assert not (root / ".local/recovery").exists()
    path.write_bytes(original)
    receipt = E.apply(stage / "plan.json", root / ".local/recovery")
    assert receipt["all_external_source_hashes_verified"]
    assert (root / ".local/recovery/godot-client/assets/world/test/model.glb").read_bytes() == original
    assert validate(root, path)["images"][0]["sha256"] == sha(image)


def test_current_output_records_refresh_without_rewriting_authoring_history(tmp_path):
    root, path, _, _, _ = fixture(tmp_path)
    provenance = root / "eloria-assets/source/world_objects/underground/reused-scenery.json"
    provenance.parent.mkdir(parents=True)
    original = {"source": "private-original-reference", "sourceSha256": "a" * 64,
                "output": path.relative_to(root).as_posix(), "sha256": "b" * 64,
                "bounds": [[0, 0, 0], [1, 1, 1]], "sourceBinaryPrefixPreserved": True,
                "newModelGeneration": False, "geometrySelection": "Complete source model"}
    provenance.write_text(json.dumps({"assets": [original]}))
    shipping = tmp_path / "shipping.json"
    shipping.write_text(json.dumps({"files": []}))
    stage = tmp_path / "stage"
    E.plan(root, shipping, stage)
    updated = json.loads((stage / "files" / provenance.relative_to(root)).read_text())["assets"][0]
    for key in ("source", "sourceSha256", "bounds", "newModelGeneration", "geometrySelection"):
        assert updated[key] == original[key]
    assert updated["sourceBinaryPrefixPreserved"] is False
    assert updated["storageEquivalence"]["encodedImageBytesIdentical"] is True
    assert updated["images"][0]["uri"].endswith(".png")
