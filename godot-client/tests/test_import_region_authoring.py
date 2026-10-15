from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


TOOL = Path(__file__).resolve().parents[1] / "tools/import_region_authoring.py"
SPEC = importlib.util.spec_from_file_location("import_region_authoring", TOOL)
assert SPEC and SPEC.loader
I = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(I)


def test_all_explicit_authored_region_adapters_are_registered():
    assert I.ADAPTERS == {
        "amethyst-v1": "import_amethyst_authoring",
        "mirrorhold-v1": "import_mirrorhold_authoring",
        "published-generic-v1": "import_published_authoring",
        "sunmane-v1": "import_sunmane_authoring",
        "whitehorn-v1": "import_whitehorn_authoring",
    }


def test_generic_importer_has_no_default_region_adapter(tmp_path, monkeypatch):
    spec = tmp_path / "region.json"
    scene = tmp_path / "client/godot-client/world_authoring/regions/example/example.tscn"
    manifest = tmp_path / "client/eloria-assets/maps/nymara-regions/example/world.json"
    scene.parent.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)
    scene.write_text('[gd_scene format=3]\nregion_id = "example"\n', encoding="utf-8")
    manifest.write_text(json.dumps({"asset": {"id": "example"}}), encoding="utf-8")
    document = {
        "schema": I.catalog.SPEC_SCHEMA, "regionId": "example", "label": "Example",
        "adapter": "unregistered-v1",
        "paths": {"scene": "godot-client/world_authoring/regions/example/example.tscn",
                  "manifest": "eloria-assets/maps/nymara-regions/example/world.json",
                  "snapshot": "eloria-assets/maps/nymara-regions/example/authoring/continent-authoring.json"},
        "continentTranslation": [0, 0, 0],
        "server": {"origin": [0, 0], "cells": [2, 2], "collisionOriginMetres": [0, 0]},
        "terrain": {"origin": [0, 0], "cellMetres": 2, "vertices": [2, 2]},
        "authority": {"ownedRouteIds": [], "requiredRouteIds": [],
                      "ownedPlanFeatureIds": []},
        "gameplay": {"runtimeBindingCount": 0, "runtimePointCount": 0,
                     "existingMarkerBindingCount": 0},
    }
    spec.write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr(I.catalog, "CLIENT", tmp_path / "client")
    argv = ["--region-spec", str(spec)]
    for flag in ("source-world", "source-manifest", "roads", "plan", "base-heights",
                 "resolved-heights", "runtime-bindings", "runtime-profile-root"):
        argv += [f"--{flag}", str(tmp_path / flag)]
    with pytest.raises(I.catalog.CatalogError, match="unsupported explicit adapter"):
        I.main(argv)


def test_adapter_handoff_uses_spec_output_and_preserves_force(monkeypatch):
    contract = SimpleNamespace(scene_path=Path("C:/repo/godot-client/world_authoring/regions/r/r.tscn"))
    args = SimpleNamespace(
        output=None, source_world=Path("world.glb"), source_manifest=Path("world.json"),
        roads=Path("roads.json"), plan=Path("plan.json"), base_heights=Path("base.bin"),
        resolved_heights=Path("resolved.bin"), runtime_bindings=Path("bindings.json"),
        runtime_profile_root=Path("legacy-server-profile"),
        composed=Path("composed.pkl"), composition=Path("composition.json"),
        export_ledger=Path("export.json"), published_master=Path("continent.glb"),
        force=True,
    )
    values = I.adapter_arguments(args, contract)
    assert "--force" in values
    assert values[values.index("--output") + 1] == str(contract.scene_path.parent.resolve())
    assert values[values.index("--export-ledger") + 1] == "export.json"
    assert values[values.index("--runtime-profile-root") + 1] == "legacy-server-profile"
