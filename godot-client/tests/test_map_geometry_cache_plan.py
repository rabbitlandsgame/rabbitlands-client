"""Geometry scope planning uses runtime leaves and preserves exact source closure."""
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

import pytest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))
import map_geometry_cache as cache


def write_json(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def glb(path, document=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(document or {"asset": {"version": "2.0"}}).encode()
    data += b" " * (-len(data) % 4)
    path.write_bytes(struct.pack("<5I", 0x46546C67, 2, 20 + len(data), len(data), 0x4E4F534A) + data)
    return path


@pytest.fixture
def project(tmp_path):
    project = tmp_path / "client" / "godot-client"
    project.mkdir(parents=True)
    (project / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    return project


def world(project, name):
    path = project.parent / "eloria-assets" / "maps" / name / "world.json"
    identity = name.replace("/", "__")
    write_json(path, {"asset": {"id": identity, "glb": "world.glb"}})
    glb(path.parent / "world.glb")
    return path, "res://../eloria-assets/maps/" + name + "/world.json"


def setup_scope(project, maps, roots, overlays=None):
    write_json(project / cache.REGISTRY, {"maps": maps})
    write_json(project / cache.SCOPE, {"schema": 1, "version": 1, "maps": roots,
                                      "asset_overlays": overlays or []})


@pytest.mark.parametrize("maps", [
    {"valid": {"alias": "missing"}},
    {"valid": {"alias": "other"}, "other": {"alias": "valid"}},
])
def test_dangling_alias_and_cycle_are_rejected(project, maps):
    setup_scope(project, maps, ["valid"])
    with pytest.raises(cache.PlanError, match="alias|Alias"):
        cache.plan(project)


def test_missing_scoped_root_is_rejected(project):
    setup_scope(project, {}, ["missing"])
    with pytest.raises(cache.PlanError, match="Dangling"):
        cache.plan(project)


def test_tier_aliases_prepare_each_of_seventeen_gauntlets_once(project):
    maps, roots = {}, []
    for index in range(17):
        identity = f"region_{index}_gauntlet"
        _, source = world(project, identity)
        maps[identity] = {"manifest": source}
        roots.append(identity)
        for tier in (2, 3):
            alias = f"{identity}_{tier}"
            maps[alias] = {"alias": identity}
            roots.append(alias)
    setup_scope(project, maps, roots)
    result = cache.plan(project)
    assert result["summary"]["canonical_maps"] == 17
    assert result["summary"]["world_targets"] == 17
    assert all(len(row["aliases"]) == 2 for row in result["roots"])


def test_streamed_root_uses_declared_leaves_and_never_opens_preview_glb(project):
    root, source = world(project, "continent")
    leaf, leaf_source = world(project, "continent/chunks/00_00")
    write_json(root, {"asset": {"id": "continent", "glb": "missing-preview.glb"},
                      "streamingChunks": {"chunks": [{"id": "00_00", "manifest": "chunks/00_00/world.json"}]}})
    setup_scope(project, {"continent": {"manifest": source}}, ["continent"])
    result = cache.plan(project)
    assert [row["source"] for row in result["targets"]] == [leaf_source]
    assert not any("preview" in row["source"] for row in result["source_closure"])
    assert leaf.is_file()


def test_duplicate_leaf_cannot_be_prepared_twice(project):
    root, source = world(project, "continent")
    world(project, "continent/chunks/00_00")
    write_json(root, {"asset": {"id": "continent", "glb": "world.glb"},
                      "streamingChunks": {"chunks": [
                          {"id": "a", "manifest": "chunks/00_00/world.json"},
                          {"id": "b", "manifest": "chunks/00_00/world.json"}]}})
    setup_scope(project, {"continent": {"manifest": source}}, ["continent"])
    with pytest.raises(cache.PlanError, match="Duplicate scene leaf"):
        cache.plan(project)


def test_chunk_path_traversal_is_rejected_even_within_asset_tree(project):
    root, source = world(project, "continent")
    world(project, "other")
    write_json(root, {"asset": {"id": "continent", "glb": "world.glb"},
                      "streamingChunks": {"chunks": [{"id": "a", "manifest": "../other/world.json"}]}})
    setup_scope(project, {"continent": {"manifest": source}}, ["continent"])
    with pytest.raises(cache.PlanError, match="Path traversal"):
        cache.plan(project)


def test_external_image_cannot_escape_runtime_asset_scope(project):
    path, source = world(project, "map")
    glb(path.parent / "world.glb", {"images": [{"uri": "../../../../outside.png"}]})
    setup_scope(project, {"map": {"manifest": source}}, ["map"])
    with pytest.raises(cache.PlanError, match="escaped"):
        cache.plan(project)


def test_road_metadata_and_fields_are_verified_native_source_inputs(project):
    path, source = world(project, "map")
    field = path.parent / "ids.zst"
    field.write_bytes(b"compact road field")
    metadata = write_json(path.parent / "roads.json", {
        "schema": "rabbitlands-road-terrain-blend-v1",
        "resources": {field.name: hashlib.sha256(field.read_bytes()).hexdigest()}})
    manifest = json.loads(path.read_text())
    manifest["roadGround"] = {"metadata": metadata.name,
                              "sha256": hashlib.sha256(metadata.read_bytes()).hexdigest()}
    write_json(path, manifest)
    setup_scope(project, {"map": {"manifest": source}}, ["map"])
    result = cache.plan(project)
    roads = [row for row in result["source_closure"] if "road_ground" in row["kinds"]]
    assert {Path(row["source"]).name for row in roads} == {"roads.json", "ids.zst"}
    field.write_bytes(b"changed after preparation")
    with pytest.raises(cache.PlanError, match="resource changed"):
        cache.plan(project)


def test_closure_preserves_verification_and_prototype_image_path_aliases(project):
    path, source = world(project, "map")
    maps_root = path.parent.parent
    declared = maps_root / "declared" / "same.png"
    actual = maps_root / "actual" / "same.png"
    for image in (declared, actual):
        image.parent.mkdir(parents=True)
        image.write_bytes(b"identical source image bytes")
    image_digest = hashlib.sha256(actual.read_bytes()).hexdigest()
    proto = glb(maps_root / "_shared" / "prop.glb", {"images": [{"uri": "../actual/same.png"}]})
    proto_digest = hashlib.sha256(proto.read_bytes()).hexdigest()
    write_json(proto.parent / "index.json", {"prototypes": {"prop": {
        "images": {"../actual/same.png": image_digest}}}})
    write_json(path, {"asset": {"id": "map", "glb": "world.glb"},
                      "externalResources": {"../declared/same.png": image_digest},
                      "externalMeshes": {"../_shared/prop.glb": proto_digest}})
    setup_scope(project, {"map": {"manifest": source}}, ["map"])
    result = cache.plan(project)
    image_files = [row for row in result["source_closure"] if "image" in row["kinds"]]
    assert len(image_files) == 2
    assert result["summary"]["unique_external_image_contents"] == 1
    assert result["summary"]["shared_prototypes"] == 1
    assert any("prototype_index" in row["kinds"] for row in result["source_closure"])
    actual.write_bytes(b"changed after manifest publication")
    with pytest.raises(cache.PlanError, match="digest differs"):
        cache.plan(project)


def test_overlay_adds_only_used_asset_sources_once(project):
    _, source = world(project, "landfall_insides")
    asset = glb(project / "assets" / "world" / "used.glb")
    config = "res://data/world/underground-scenery.json"
    config_path = project / "data/world/underground-scenery.json"
    write_json(config_path, {"map": "landfall_insides", "assets": {
        "one": "res://assets/world/used.glb", "same_source": "res://assets/world/used.glb",
        "unused": "res://assets/world/missing.glb"},
        "placements": [{"asset": "one"}, {"asset": "same_source"}, {"asset": "one"}]})
    setup_scope(project, {"landfall_insides": {"manifest": source}}, ["landfall_insides"],
                [{"owner": "landfall_insides", "config": config}])
    result = cache.plan(project)
    assert result["summary"]["asset_targets"] == 1
    assert result["targets"][1]["source"] == "res://assets/world/used.glb"
    assert asset.is_file()
    config_path.unlink()
    assert cache.plan(project, include_assets=False)["summary"]["asset_targets"] == 0


def test_production_scope_is_retained_and_candidates_cover_registered_interiors():
    scope = cache.read_json(PROJECT / cache.SCOPE)
    candidates = cache.read_json(PROJECT / "data/maps/geometry-cache-interior-candidates.json")
    registry = cache.read_json(PROJECT / cache.REGISTRY)["maps"]
    catalog = cache.read_json(PROJECT / "world_authoring/continent-v2/territories.json")
    landfall = {entry["id"] for entry in catalog["entries"]}
    gauntlets = {key for key, value in registry.items() if "gauntlet" in key and "manifest" in value}
    interiors = {"landfall_insides"} | {
        cache.resolve_alias(registry, key) for key, value in registry.items()
        if ("interiorOf" in value or "insidesOf" in value)
        and cache.resolve_alias(registry, key) not in gauntlets
    }
    assert set(scope["groups"]["landfall_continent"]) == landfall
    assert len(landfall) == 17
    assert set(scope["groups"]["gauntlets"]) == gauntlets
    assert len(gauntlets) == 17
    production = landfall | gauntlets | {"landfall_insides"}
    assert set(scope["maps"]) == production
    assert len(scope["maps"]) == len(production)
    assert all(cache.resolve_alias(registry, key) == key for key in scope["maps"])
    # Registered inventory and tested candidates do not imply runtime promotion.
    # Every interior is explicitly reproducible, while slower candidates stay
    # outside the automatic production preparation and native consumer scope.
    assert candidates["schema"] == scope["schema"] == 1
    assert set(candidates["groups"]["interiors"]) == interiors
    assert len(candidates["groups"]["interiors"]) == len(interiors)
    assert set(candidates["maps"]) == landfall | gauntlets | interiors
    assert len(candidates["maps"]) == len(landfall | gauntlets | interiors)
    assert all(cache.resolve_alias(registry, key) == key for key in candidates["maps"])
    assert candidates["asset_overlays"] == scope["asset_overlays"]
    for group in ("landfall_continent", "gauntlets", "landfall_insides"):
        assert candidates["groups"][group] == scope["groups"][group]
    interior_sources = [registry[key]["manifest"] for key in interiors]
    assert len(set(interior_sources)) == len(interior_sources)
    assert len([key for key in registry if "alias" in registry[key]
                and cache.resolve_alias(registry, key) in gauntlets]) == 34


def test_interior_aliases_share_one_world_target_with_canonical_source(project):
    _, source = world(project, "cave_assembly")
    setup_scope(project, {
        "cave": {"manifest": source, "interiorOf": "exterior"},
        "old_cave": {"alias": "cave"},
        "older_cave": {"alias": "old_cave"},
    }, ["cave", "old_cave", "older_cave"])
    result = cache.plan(project)
    assert result["summary"]["canonical_maps"] == 1
    assert result["summary"]["world_targets"] == 1
    assert result["targets"][0]["source"] == source
    assert set(result["roots"][0]["aliases"]) == {"old_cave", "older_cave"}


def test_supplied_job_targets_are_validated_and_assets_can_be_excluded(project):
    _, source = world(project, "map")
    document = {"schema": 1, "targets": [{"kind": "world", "source": source, "id": "map"},
        {"kind": "asset", "source": "res://missing.glb", "id": "asset"}]}
    assert len(cache._job_targets(project, document, include_assets=False)) == 1
    document["targets"] = [{"kind": "world", "source": "res://../../outside.json", "id": "bad"}]
    with pytest.raises(cache.PlanError, match="escaped"):
        cache._job_targets(project, document, include_assets=True)


def build_inputs(project, monkeypatch):
    _, source = world(project, "map")
    script = project / "src/world/map_geometry_prepare.gd"
    script.parent.mkdir(parents=True)
    script.write_text("# Fake engine tests never execute this file.\n", encoding="utf-8")
    godot = project.parent / "fake-engine.exe"
    godot.write_bytes(b"not executed")
    plan = write_json(project / "plan.json", {"schema": 1, "targets": [
        {"kind": "world", "source": source, "id": "map"}]})
    monkeypatch.setattr(cache, "_ignored_output", lambda path: path.mkdir(parents=True, exist_ok=True))
    return godot, plan


class WaitingEngine:
    def __init__(self):
        self.returncode = None
        self.terminations = 0
        self.kills = 0

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminations += 1
        self.returncode = -15

    def kill(self):
        self.kills += 1
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


def test_engine_parse_error_stops_only_the_owned_child_and_preserves_logs(project, monkeypatch):
    godot, plan = build_inputs(project, monkeypatch)
    child = WaitingEngine()

    def start(command, *, stdout, stderr, **kwargs):
        stderr.write("SCRIPT ERROR: Parse Error: deliberate fake error\n")
        stderr.flush()
        return child

    monkeypatch.setattr(cache.subprocess, "Popen", start)
    with pytest.raises(cache.PlanError, match="engine error"):
        cache.build(project, godot, plan_path=plan)
    assert child.terminations == 1
    assert child.kills == 0
    logs = list((project / "test-artifacts/map-geometry-prepare/jobs").glob("*/stderr.log"))
    assert len(logs) == 1
    assert "deliberate fake error" in logs[0].read_text()


def test_engine_deadline_terminates_the_owned_child(project, monkeypatch):
    godot, plan = build_inputs(project, monkeypatch)
    child = WaitingEngine()
    monkeypatch.setattr(cache.subprocess, "Popen", lambda *args, **kwargs: child)
    ticks = iter([100.0, 101.0])
    monkeypatch.setattr(cache.time, "monotonic", lambda: next(ticks))
    with pytest.raises(cache.PlanError, match="exceeded"):
        cache.build(project, godot, plan_path=plan, timeout_seconds=0.1)
    assert child.terminations == 1
    assert child.kills == 0


def test_build_producer_environment_is_isolated_and_success_requires_report(project, monkeypatch):
    godot, plan = build_inputs(project, monkeypatch)
    monkeypatch.setenv("RABBITLANDS_PREPARED_CONTENT", "require-pilot")
    monkeypatch.setenv("ELORIA_NO_MAP_CACHE", "0")
    monkeypatch.setenv("ELORIA_VRAM_TEXTURES", "force")
    observed = {}
    child = WaitingEngine()
    child.returncode = 0

    def start(command, *, env, **kwargs):
        observed.update(env)
        job = cache.read_json(Path(env["ELORIA_GEOMETRY_JOB"]))
        assert job["resume"] is True
        assert len(job["targets"]) == 1
        cache._write_json(Path(job["output_report"]), {
            "ok": True, "prepared": 1, "reused": 0, "failed": [], "entries": []})
        return child

    monkeypatch.setattr(cache.subprocess, "Popen", start)
    result = cache.build(project, godot, plan_path=plan, resume=True)
    assert result["ok"] is True
    assert observed["RABBITLANDS_PREPARED_CONTENT"] == "raw"
    assert observed["ELORIA_NO_MAP_CACHE"] == "1"
    assert observed["ELORIA_VRAM_TEXTURES"] == "0"
    assert observed["APPDATA"] == observed["LOCALAPPDATA"] == result["user_root"]
    assert os.environ["RABBITLANDS_PREPARED_CONTENT"] == "require-pilot"
    assert os.environ["ELORIA_NO_MAP_CACHE"] == "0"
    assert os.environ["ELORIA_VRAM_TEXTURES"] == "force"
    assert child.terminations == 0


def test_zero_exit_without_report_is_not_success(project, monkeypatch):
    godot, plan = build_inputs(project, monkeypatch)
    child = WaitingEngine()
    child.returncode = 0
    monkeypatch.setattr(cache.subprocess, "Popen", lambda *args, **kwargs: child)
    with pytest.raises(cache.PlanError, match="did not produce a preparation report"):
        cache.build(project, godot, plan_path=plan)
