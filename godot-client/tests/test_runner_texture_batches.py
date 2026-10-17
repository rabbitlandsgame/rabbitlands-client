"""Cold-cache quality scratch must not scale with the entire texture collection."""
from pathlib import Path
import sys
import json
import shutil
import os

from PIL import Image
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_vram_textures as textures


def test_batches_bound_all_mip_levels_without_dropping_items(tmp_path):
    items = []
    for index in range(7):
        path = tmp_path / f"image-{index}.png"
        Image.new("RGB", (16, 16)).save(path)
        items.append({"src": str(path), "key": index})
    # Each 16x16 BC7 chain plus header fits 516 bytes; two fit this budget.
    batches = list(textures.texture_batches(items, limit=1100))
    assert [len(batch) for batch in batches] == [2, 2, 2, 1]
    assert [item for batch in batches for item in batch] == items


def test_single_oversized_texture_fails_before_encoding(tmp_path):
    path = tmp_path / "too-large.png"
    Image.new("RGB", (64, 64)).save(path)
    with pytest.raises(textures.BuildError, match="scratch budget"):
        list(textures.texture_batches([{"src": str(path)}], limit=1000))


def test_cold_batched_encodes_keep_quality_metadata_and_linked_outputs(tmp_path, monkeypatch):
    try:
        godot = textures.find_godot(None)
    except textures.BuildError:
        pytest.skip("Godot 4.7.2 editor is required for the encode integration check.")
    fixture = Path(__file__).parent / "fixtures/vram"
    maps, cache, out = tmp_path / "maps", tmp_path / "cache", tmp_path / "output"
    for name in ("first", "second"):
        shutil.copytree(fixture, maps / name, ignore=shutil.ignore_patterns("vram", "*.py"))
    groups = []
    def one_encode_per_batch(items):
        for group in items:
            groups.append(group)
            group["_dds_bytes"] = 128 * 1024
            yield [group]
    monkeypatch.setattr(textures, "texture_batches", one_encode_per_batch)
    result = textures.build([maps], out, cache, godot, procs=1, link_output=True, cache_budget_bytes=8 * 1024**2)
    assert result["encoded"] > 0 and len(groups) > 1
    assert all(len(group["items"]) >= 2 for group in groups)
    assert not list((cache / "_work").glob("*.dds"))
    files = list(cache.glob("*.evt"))
    linked = 0
    for index_path in out.rglob("index.json"):
        for row in json.loads(index_path.read_text())["images"].values():
            target = index_path.parent / row["file"]
            assert any(os.path.samefile(target, source) for source in files)
            linked += 1
    assert linked > 0


def test_cache_reservation_rejects_growth_before_encoding(tmp_path):
    (tmp_path / "existing.evt").write_bytes(bytes(128))
    textures.check_cache_budget(tmp_path, 256, additional=128)
    with pytest.raises(textures.BuildError, match="disk budget"):
        textures.check_cache_budget(tmp_path, 256, additional=129)
