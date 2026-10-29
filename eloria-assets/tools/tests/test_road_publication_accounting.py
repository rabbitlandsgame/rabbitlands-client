"""Road payloads belong in chunk residency, never in authoring-stage scans."""
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import publish_finish as finish


def test_private_stages_are_not_shipped_geometry_or_manifests(tmp_path, monkeypatch):
    published = tmp_path / "suncoil/client/chunks/00_00"
    staged = tmp_path / "suncoil/client/.local/bake/00_00"
    for directory in (published, staged):
        directory.mkdir(parents=True)
        (directory / "world.glb").write_bytes(b"geometry")
        (directory / "world.json").write_text("{}")
    monkeypatch.setattr(finish, "MAPS", tmp_path)
    assert finish.glbs([tmp_path]) == [published / "world.glb"]
    assert finish.every_manifest() == [published / "world.json"]


def test_field_accounting_includes_decoded_cpu_and_gpu_cost(tmp_path):
    (tmp_path / "coverage.png").write_bytes(b"compressed coverage")
    (tmp_path / "ids.zst").write_bytes(b"compressed ids")
    (tmp_path / "coefficients.zst").write_bytes(b"compressed coefficients")
    metadata = {"field": {"coverage_mips": [
        {"file": "coverage.png", "width": 4, "height": 4}],
        "triangle_ids": {"file": "ids.zst", "uncompressed_bytes": 32},
        "affine_coefficients": {"file": "coefficients.zst", "uncompressed_bytes": 64, "record_count": 2}}}
    path = tmp_path / "roads.json"
    path.write_text(json.dumps(metadata))
    manifest = {"roadGround": {"metadata": "roads.json", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}}
    resident, stored = finish.road_ground_figures(manifest, tmp_path / "world.json")
    assert resident == 2 * (16 + 32 + 64) + 16 + 2
    assert stored == sum(file.stat().st_size for file in tmp_path.iterdir())
    path.write_text("{}")
    with pytest.raises(ValueError, match="changed before accounting"):
        finish.road_ground_figures(manifest, tmp_path / "world.json")
