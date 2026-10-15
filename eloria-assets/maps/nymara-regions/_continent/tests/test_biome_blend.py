"""The two sides of a streamed biome seam sample one world-space palette."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import biome_blend as B
from world_layout import ownership_map


def _signed(owner: np.ndarray, names: list[str]) -> dict[str, np.ndarray]:
    return {name: (distance_transform_edt(owner == index) -
                   distance_transform_edt(owner != index)) * 2.0
            for index, name in enumerate(names)}


def _sample(array: np.ndarray, column: float) -> np.ndarray:
    """The exact linear-filter interpolation at z row 20 and world x=column."""
    coordinate = column / B.PIXEL_METRES + B.GUTTER - 0.5
    low = int(np.floor(coordinate))
    fraction = coordinate - low
    return array[20, low] * (1.0 - fraction) + array[20, low + 1] * fraction


def test_quantized_gutters_match_with_different_palette_channel_order():
    owner = np.empty((96, 144), dtype=int)
    owner[:, :38] = 0
    owner[:, 38:66] = 1
    owner[:, 66:] = 2
    world = SimpleNamespace(x0=0.0, z0=0.0, plan={"seed": 2042})
    names = ["west", "middle", "east"]
    signed = _signed(owner, names)
    physical = []
    for chunk, local_names in ((0, ["west", "middle"]), (1, ["middle", "east"])):
        xx, zz = B._pixel_positions(world, chunk, 0)
        full = B._weights(world, names, signed, xx, zz)
        channels = np.zeros((*xx.shape, 4))
        for channel, name in enumerate(local_names):
            channels[..., channel] = full[..., names.index(name)]
        encoded = B._png(channels)
        decoded = np.asarray(Image.open(io.BytesIO(encoded)), dtype=float) / 255.0
        at_edge = _sample(decoded, 96.0 - chunk * 96.0)
        physical.append({name: at_edge[channel] for channel, name in enumerate(local_names)})
    assert physical[0]["middle"] == physical[1]["middle"]
    assert physical[0]["middle"] > 0.99
    assert physical[0]["west"] == physical[1]["east"] == 0.0


def test_world_space_weight_is_continuous_at_fractional_boundary_positions():
    owner = np.zeros((96, 96), dtype=int)
    owner[:, 48:] = 1
    world = SimpleNamespace(x0=0.0, z0=0.0, plan={"seed": 2042})
    names = ["amberwood", "grey_moors"]
    signed = _signed(owner, names)
    tiles = []
    for chunk in (0, 1):
        xx, zz = B._pixel_positions(world, chunk, 0)
        weights = B._weights(world, names, signed, xx, zz)
        rgba = np.zeros((*xx.shape, 4))
        rgba[..., :2] = weights
        tiles.append(np.asarray(Image.open(io.BytesIO(B._png(rgba))), dtype=float) / 255.0)
    np.testing.assert_array_equal(tiles[0][:, -2:, :], tiles[1][:, :2, :])
    for offset in (-0.7, -0.2, 0.0, 0.2, 0.7):
        position = 96.0 + offset
        first = _sample(tiles[0], position)
        second = _sample(tiles[1], position - 96.0)
        np.testing.assert_allclose(first, second, rtol=0.0, atol=2e-15)
        assert abs(first[0] + first[1] - 1.0) <= 1.0 / 255.0


def test_saved_custom_base_requires_explicit_opt_in():
    texture = "godot-client/world_authoring/regions/amberwood/assets/textures/continental-ground.png"
    pbr = {"albedoColor": [1.0] * 4, "albedoTexture": texture,
           "normalTexture": None, "ormTexture": None, "roughness": 0.95,
           "metallic": 0.0, "normalScale": 1.0, "uvScale": [1.0] * 3,
           "uvOffset": [0.8, 0.5, 0.0]}
    base = {"preset": "Custom", "pbr": pbr, "rotationDegrees": 31.0}
    terrain = {"baseSurface": base, "previewUvMetresInverse": 0.17,
               "biomePalette": [{"id": "heath", "role": "heath",
                                 "surface": {"preset": "Custom", "pbr": pbr,
                                             "rotationDegrees": -19.0}}]}
    snapshots = {"amberwood": SimpleNamespace(document={"terrain": terrain})}
    world = SimpleNamespace(authoring_snapshots=snapshots)
    assert B.palette_sources(world) == {}
    base["biomeBlendEnabled"] = True
    result = B.palette_sources(world)
    assert list(result) == ["amberwood"]
    assert result["amberwood"]["base"]["rotationDegrees"] == 31.0
    assert result["amberwood"]["base"]["uvOffset"] == [0.8, 0.5]
    assert result["amberwood"]["secondary"]["role"] == "heath"
    assert result["amberwood"]["secondary"]["rotationDegrees"] == -19.0


def test_published_twelve_region_plan_fits_four_chunk_channels():
    plan = json.loads((HERE / "diagonal-plan.json").read_text(encoding="utf-8"))
    ids, owner, _, _ = ownership_map(plan)
    # 30 m exceeds the 12 m half-band plus 3 m warp and one 1.5 m gutter.
    # Test the union across each complete 96 m chunk, not just one pixel.
    near = np.stack([distance_transform_edt(owner != index) * 2.0 <= 30.0
                     for index in range(len(ids))])
    maximum = 0
    for row in range(0, owner.shape[0], 48):
        for column in range(0, owner.shape[1], 48):
            number = int(np.count_nonzero(np.any(
                near[:, row:row + 48, column:column + 48], axis=(1, 2))))
            maximum = max(maximum, number)
    assert len(ids) == 12
    assert maximum == 4


def test_numeric_mask_import_settings_are_generated_with_future_masks(tmp_path, monkeypatch):
    monkeypatch.setattr(B.AUTHORING, 'CLIENT', tmp_path)
    path = tmp_path / 'godot-client/assets/world/biome_blend/masks/07_08-base.png'
    record = B._mask_record(path, B._png(np.zeros((66, 66, 4))))
    settings = Path(str(path) + '.import').read_text(encoding='utf-8')
    assert record['path'] == 'res://assets/world/biome_blend/masks/07_08-base.png'
    assert 'process/fix_alpha_border=false' in settings
    assert 'process/premult_alpha=false' in settings
    assert 'detect_3d/compress_to=0' in settings
    assert 'compress/mode=0' in settings
    assert f'source_file="{record["path"]}"' in settings
    sidecar = Path(str(path) + '.import')
    sidecar.write_text(settings.replace('compress/mode=0', 'compress/mode=2')
                       .replace('process/premult_alpha=false', 'process/premult_alpha=true')
                       .replace('process/fix_alpha_border=false', 'process/fix_alpha_border=true')
                       .replace('detect_3d/compress_to=0', 'detect_3d/compress_to=1'),
                       encoding='utf-8')
    B._mask_record(path, path.read_bytes())
    repaired = sidecar.read_text(encoding='utf-8')
    assert 'compress/mode=0' in repaired
    assert 'process/premult_alpha=false' in repaired
    assert 'process/fix_alpha_border=false' in repaired
    assert 'detect_3d/compress_to=0' in repaired
