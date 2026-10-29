"""Tiny storage/provenance fixtures; no Godot, cook, export or game assets."""
import copy
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import release_world_preparation as world


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)
    return path


@pytest.fixture
def generation(tmp_path):
    project = tmp_path / "repo/godot-client"
    put(project / "project.godot", b"config_version=5\n")
    world.write_json(project / world.geometry.SCOPE, {"schema": 1, "maps": ["fixture"]})
    world.write_json(project / world.geometry.REGISTRY, {"maps": {"fixture": {}}})
    source = "eloria-assets/maps/fixture/chunks/00_00/world.json"
    raw = put(project.parent / source, b'{"asset":{"id":"fixture__chunk_00_00"}}')
    plan = {"targets": [{"kind": "world", "source": "res://../" + source,
                         "id": "fixture__chunk_00_00"}], "producer_sha256": "d" * 64}
    key = "world|" + source
    user = tmp_path / "user"
    policies = dict(zip(world.NAMESPACES, ("a" * 64, "b" * 64, "c" * 64)))
    compatibility = world.data_digest([world.POLICY, *policies.values(), "Windows"])
    geometry_root = f"res://prepared-world/{compatibility}/geometry/{policies['geometry']}"
    inputs = [{"path": source, "sha256": world.digest(raw)}]
    native = {}
    for kind, suffix in (("geometry", "scn"), ("collision", "rlc"), ("paving", "res")):
        data = (kind + " opaque native bytes").encode()
        sha = hashlib.sha256(data).hexdigest()
        if kind == "geometry":
            uri = geometry_root + f"/blobs/{sha}.{suffix}"
            put(project / uri[6:], data)
        else:
            path = f"{world.NAMESPACES[kind]}/{policies[kind]}/blobs/{sha}.{suffix}"
            put(user / path, data)
            uri = "user://" + path
        native[kind] = (uri, sha, data)
    for kind, policy in policies.items():
        entry = {"schema": 4 if kind == "geometry" else 1, "policy": policy,
                 "source": source, "source_digest": "e" * 64, "inputs": inputs}
        path, sha, _ = native[kind]
        if kind == "geometry":
            entry.update(kind="world", primary=path, payloads={path: sha}, shared_meshes={}, bindings={})
        elif kind == "collision":
            entry.update(blob=path, sha256=sha)
        else:
            entry.update(meshes={"Ground": {"blob": path, "sha256": sha}})
        identity = world.data_digest(["world", source] if kind == "geometry" else source)
        root = project / geometry_root[6:] if kind == "geometry" else user / world.NAMESPACES[kind] / policy
        world.write_json(root / "entries" / (identity + ".json"), entry)
    meta = {"scope_complete": True, "platform": "Windows", "renderer": "forward_plus",
            "engine": {"hash": "engine", "string": "4.7.2.stable"}, "geometry_schema": 4,
            "engine_executable_sha256": "f" * 64,
            "geometry_root": geometry_root,
            "user_data_path": str(user), "scope_sha256": world.digest(project / world.geometry.SCOPE),
            "registry_sha256": world.digest(project / world.geometry.REGISTRY),
            "target_keys": [key], "collision_target_keys": [key], "paving_target_keys": [key],
            **{kind + "_policy": policy for kind, policy in policies.items()}}
    return project, plan, {"ok": True, "release_metadata": meta}, native, raw


def test_complete_generation_is_portable_and_native_bytes_unchanged(generation, tmp_path):
    project, plan, report, native, _ = generation
    output = tmp_path / "generation"
    catalog = world.collect(project, plan, report, output)
    checked = world.validate(project, output / "catalog.json", plan=plan, platform="windows")
    assert checked["files"] == 6
    assert catalog["target_keys"] == ["world|eloria-assets/maps/fixture/chunks/00_00/world.json"]
    for kind, (_, sha, original) in native.items():
        path = next(path for path in catalog["files"] if path.startswith(kind + "/") and "/blobs/" in path)
        assert (output / path).read_bytes() == original
        assert world.digest(output / path) == sha
    for path in output.rglob("*.json"):
        assert "user://" not in path.read_text()
        assert str(tmp_path) not in path.read_text()
    # Repeating a cook receipt with another private profile path does not
    # change any shipped metadata or native payload bytes.
    another = tmp_path / "other-output"
    world.collect(project, plan, report, another)
    assert (output / "catalog.json").read_bytes() == (another / "catalog.json").read_bytes()


@pytest.mark.parametrize("failure", ["coverage", "source", "blob"])
def test_incomplete_or_changed_generations_fail_closed(generation, tmp_path, failure):
    project, plan, report, native, source = generation
    output = tmp_path / "bad"
    if failure == "coverage":
        report = copy.deepcopy(report)
        report["release_metadata"]["collision_target_keys"] = []
        with pytest.raises(ValueError, match="coverage"):
            world.collect(project, plan, report, output)
        return
    world.collect(project, plan, report, output)
    if failure == "source":
        source.write_bytes(b"changed source")
    else:
        blob = next(output.rglob("*.scn"))
        blob.write_bytes(b"changed native bytes")
    with pytest.raises(ValueError, match="changed"):
        world.validate(project, output / "catalog.json", plan=plan, platform="windows")


def test_plan_and_runtime_sources_share_canonical_keys():
    assert world.runtime_name("res://../eloria-assets/maps/a/world.json") == "eloria-assets/maps/a/world.json"
    assert world.runtime_name("res://assets/world/tree.glb") == "godot-client/assets/world/tree.glb"
    assert world.target_key({"kind": "asset", "source": "res://assets/world/tree.glb"}) == "asset|godot-client/assets/world/tree.glb"
    for source in ("res://../../private", "godot-client/../eloria-assets/a", "eloria-assets/%2e%2e/a"):
        with pytest.raises(ValueError):
            world.runtime_name(source)


def test_actual_import_overlay_hides_only_unshipped_raw_sources(tmp_path, monkeypatch):
    import prepared_content_package
    from release_prepared_content import _Overlay
    project, stage = tmp_path / "repo/godot-client", tmp_path / "stage"
    remap = "assets/world/biome/ground.png.import"
    image = remap.removesuffix(".import")
    product = ".godot/imported/ground.ctex"
    original = b"original editor remap"
    exported = b'path="res://.godot/imported/ground.ctex"\x00'
    put(project / remap, original)
    put(project / image, b"source pixels")
    put(project / product, b"native texture")
    payloads = {remap: exported, product: b"native texture"}

    class View:
        def __init__(self, _stage): self.entries = payloads
        def read(self, name, maximum=1 << 20): return payloads[name]
        def runtime_hash(self, name): return hashlib.sha256(payloads[name.removeprefix("godot-client/")]).hexdigest()

    monkeypatch.setattr(prepared_content_package, "ExportView", View)
    overlay = _Overlay(project.parent, tmp_path / "backups", None)
    try:
        result = world.runtime_import_overlay(project, stage, overlay)
        assert result["hidden_unshipped_sources"] == [image]
        assert not (project / image).exists()
        assert (project / remap).read_bytes() == exported
    finally:
        overlay.restore()
    assert (project / image).read_bytes() == b"source pixels"
    assert (project / remap).read_bytes() == original


def test_cache_pruning_preserves_unknown_profiles(tmp_path):
    platform = tmp_path / "windows"
    current, old, unknown = (platform / (letter * 64) for letter in "abc")
    for path in (current, old, unknown): path.mkdir(parents=True)
    world.write_json(old / "world-cache-owner.json", {"schema": 1, "policy": world.POLICY,
        "platform": "windows", "namespace": old.name})
    assert world.prune_cache_namespaces(current) == [old.name]
    assert current.is_dir() and unknown.is_dir() and not old.exists()


def test_reused_build_reset_requires_ownership_and_exact_descriptor(tmp_path):
    project = tmp_path / "godot-client"
    put(project / "prepared-world/blob.res", b"owned native")
    with pytest.raises(ValueError, match="Unowned"):
        world.reset_build(project)
    owner = world._claim_build(project)
    descriptor = project / world.DESCRIPTOR
    world.write_json(descriptor, {"generated": True})
    owner["descriptor_sha256"] = world.digest(descriptor)
    world.write_json(project / world.BUILD_OWNER, owner)
    world.reset_build(project)
    assert not descriptor.exists() and not (project / "prepared-world").exists()
    assert not (project / world.BUILD_OWNER).exists()
