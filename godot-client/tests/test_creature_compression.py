"""Real round-trips, corrupt payloads, staging links, and prepared-source identity."""
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import creature_compression as codec
import package_client as package
import prepared_content_package as prepared


def glb(uri="skin.png", data=b"\0" * 32768):
    document = json.dumps({"asset": {"version": "2.0"}, "images": [{"uri": uri}],
                           "buffers": [{"byteLength": len(data)}]}).encode()
    document += b" " * (-len(document) % 4)
    body = struct.pack("<II", len(document), 0x4E4F534A) + document
    body += struct.pack("<II", len(data), 0x004E4942) + data
    return b"glTF" + struct.pack("<II", 2, 12 + len(body)) + body


def test_exact_complete_file_round_trip_including_signed_zero_and_unknown_metadata():
    raw = glb(data=struct.pack("<4f", 0.0, -0.0, 1.0, -2.5) * 4096)
    packed = codec.encode(raw)
    assert len(packed) < len(raw)
    assert codec.decode(packed) == raw


@pytest.mark.parametrize("damage", ["truncated", "trailing", "version", "digest", "size", "limit", "body", "frame"])
def test_corruption_and_unbounded_decoding_are_rejected(damage):
    packed = bytearray(codec.encode(glb()))
    if damage == "truncated": packed = packed[:-1]
    if damage == "trailing": packed += b"unexpected"
    if damage == "version": packed[7] = ord("2")
    if damage == "digest": packed[24] ^= 1
    if damage == "size": struct.pack_into("<Q", packed, 8, 123)
    if damage == "limit": struct.pack_into("<Q", packed, 8, codec.MAX_BYTES + 1)
    if damage == "body": packed[-3] ^= 127
    if damage == "frame": packed[56] ^= 127
    with pytest.raises(codec.PayloadError): codec.decode(bytes(packed))


def test_staging_breaks_hardlinks_and_preserves_sources_and_texture_resolution(tmp_path):
    build, app = tmp_path / "source", tmp_path / "stage/app"
    relative = codec.CREATURE_ROOT + "nested/test.glb"
    source = build / relative
    target = app / relative.removeprefix("godot-client/")
    source.parent.mkdir(parents=True); target.parent.mkdir(parents=True)
    raw = glb("../textures/skin.png"); source.write_bytes(raw); os.link(source, target)
    receipt = codec.stage(build, app, {relative}, compress=True)
    assert source.read_bytes() == raw
    assert target.read_bytes().startswith(codec.MAGIC)
    assert not os.path.samefile(source, target)
    assert codec.read_bytes(target) == raw
    assert codec.source_digest(target) == hashlib.sha256(raw).hexdigest()
    assert receipt["installed_bytes"] < receipt["source_bytes"]
    assert package.gltf_image_uris(target) == ["../textures/skin.png"]


def test_incompressible_file_stays_raw_and_other_actor_types_are_untouched(tmp_path):
    build, app = tmp_path / "source", tmp_path / "app"
    names = [codec.CREATURE_ROOT + "noise.glb", "godot-client/assets/actors/native/equipment/hat.glb"]
    for name in names:
        src, dst = build / name, app / name.removeprefix("godot-client/")
        src.parent.mkdir(parents=True, exist_ok=True); dst.parent.mkdir(parents=True, exist_ok=True)
        raw = glb(data=os.urandom(4096)) if "creatures/" in name else b"equipment"
        src.write_bytes(raw); dst.write_bytes(raw)
    # Small valid GLB + random payload can still compress its JSON, so use a
    # deterministic encoder result larger than the input to exercise selection.
    original = codec.encode
    try:
        codec.encode = lambda raw: raw + b"larger"
        result = codec.stage(build, app, set(names), compress=True)
    finally:
        codec.encode = original
    assert len(result["files"]) == 1 and not result["files"][0]["compressed"]
    for name in names: assert (build / name).read_bytes() == (app / name.removeprefix("godot-client/")).read_bytes()


def test_staging_cannot_be_pointed_at_the_authored_source_itself(tmp_path):
    relative = codec.CREATURE_ROOT + "source.glb"
    source = tmp_path / relative
    source.parent.mkdir(parents=True)
    raw = glb(); source.write_bytes(raw)
    with pytest.raises(codec.PayloadError, match="staging path"):
        codec.stage(tmp_path, tmp_path / "godot-client", {relative})
    assert source.read_bytes() == raw


def test_default_staging_keeps_raw_glbs_without_encoder_or_source_mutation(tmp_path, monkeypatch):
    build, app = tmp_path / "source", tmp_path / "stage/app"
    relative = codec.CREATURE_ROOT + "raw.glb"
    source, target = build / relative, app / relative.removeprefix("godot-client/")
    source.parent.mkdir(parents=True); target.parent.mkdir(parents=True)
    raw = glb(); source.write_bytes(raw); os.link(source, target)
    def forbidden_encode(_raw):
        raise AssertionError("Raw production staging must not encode or load zstandard")
    monkeypatch.setattr(codec, "encode", forbidden_encode)
    receipt = codec.stage(build, app, {relative})
    assert source.read_bytes() == target.read_bytes() == raw
    assert receipt["format"] == "glTF-2.0" and not receipt["compression_requested"]
    assert receipt["source_bytes"] == receipt["installed_bytes"] == len(raw)
    assert not receipt["files"][0]["compressed"]


def test_prepared_source_identity_comes_from_decoded_content_not_header(tmp_path, monkeypatch):
    app = tmp_path / "app"
    name = "assets/actors/native/creatures/test.glb"
    path = app / name; path.parent.mkdir(parents=True)
    raw = glb(); path.write_bytes(codec.encode(raw))
    def loose_view(self, stage):
        self.stage = stage
        self.entries = {}
    monkeypatch.setattr(prepared.ExportView, "__init__", loose_view)
    view = prepared.ExportView(tmp_path)
    assert view.runtime_hash("godot-client/" + name) == hashlib.sha256(raw).hexdigest()
    bad = bytearray(path.read_bytes()); bad[24:56] = hashlib.sha256(b"forged source").digest(); path.write_bytes(bad)
    with pytest.raises(codec.PayloadError): view.runtime_hash("godot-client/" + name)


def test_packager_rejects_corrupt_payload_instead_of_skipping_texture_check(tmp_path):
    path = tmp_path / "test.glb"
    path.write_bytes(codec.encode(glb())[:-1])
    with pytest.raises(package.PackageError, match="Invalid compressed creature"):
        package.gltf_document(path)
