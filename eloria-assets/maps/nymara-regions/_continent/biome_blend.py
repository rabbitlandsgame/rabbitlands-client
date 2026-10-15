"""World-space masks for saved terrain palettes.

The masks are colour inputs only. They do not move terrain, ownership, water,
roads, or collision. A one-pixel gutter on each 96 m tile gives neighbouring
chunks identical bilinear samples even at fractional positions on a seam.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, map_coordinates

import authoring as AUTHORING
import landscape as L
from world_layout import CELL, CHUNK


SCHEMA = "eloria-biome-blend-v1"
INNER_SIZE = 64
GUTTER = 1
PIXEL_METRES = CHUNK / INNER_SIZE
HALF_BLEND_METRES = 12.0
WARP_METRES = 3.0
SUPPORTED_ROLES = frozenset((
    "woodland", "heath", "wetland", "rock", "snow", "sand", "limestone",
    "steppe", "badland", "grassland", "tree_density",
))
MASK_ROOT = AUTHORING.CLIENT / "godot-client/assets/world/biome_blend/masks"


def _resource_path(path: str | None, where: str) -> tuple[str | None, str | None]:
    if path is None:
        return None, None
    source = AUTHORING._source_path(path, where)
    relative = source.relative_to(AUTHORING.CLIENT).as_posix()
    if not relative.startswith("godot-client/"):
        raise AUTHORING.AuthoringError(f"{where}: terrain texture must be in the Godot project")
    return "res://" + relative.removeprefix("godot-client/"), hashlib.sha256(source.read_bytes()).hexdigest()


def _surface_record(surface: dict, terrain: dict, where: str) -> dict:
    preset = surface["preset"]
    pbr = surface.get("pbr") if preset == "Custom" else surface.get("pbrOverrides")
    if not isinstance(pbr, dict):
        raise AUTHORING.AuthoringError(f"{where}: a saved PBR source material is required")
    textures = {}
    hashes = {}
    for field in ("albedoTexture", "normalTexture", "ormTexture"):
        textures[field], hashes[field] = _resource_path(pbr.get(field), f"{where}.{field}")
    if textures["albedoTexture"] is None:
        raise AUTHORING.AuthoringError(f"{where}: an albedo texture is required for biome blending")
    return {
        "preset": preset,
        "sourceSurfaceSha256": hashlib.sha256(json.dumps(surface, sort_keys=True,
            separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest(),
        **textures,
        "textureSha256": {field: value for field, value in hashes.items() if value is not None},
        "albedoColor": list(pbr["albedoColor"]),
        "roughness": float(pbr["roughness"]),
        "metallic": float(pbr["metallic"]),
        "normalStrength": float(pbr["normalScale"]),
        "baseUvMetresInverse": float(terrain["previewUvMetresInverse"]),
        "uvScale": list(pbr["uvScale"][:2]),
        "uvOffset": list(pbr["uvOffset"][:2]),
        "rotationDegrees": float(surface.get("rotationDegrees", 0.0)),
    }


def palette_sources(world) -> dict[str, dict]:
    """Use saved per-scene surfaces only; absent opt-in preserves old rendering."""
    result = {}
    for region, snapshot in getattr(world, "authoring_snapshots", {}).items():
        terrain = snapshot.document["terrain"]
        base = terrain["baseSurface"]
        if base.get("biomeBlendEnabled") is not True:
            continue
        additions = terrain.get("biomePalette", [])
        if len(additions) > 1:
            raise AUTHORING.AuthoringError(f"{region}: biome blend v1 permits one secondary surface")
        secondary = None
        if additions:
            entry = additions[0]
            role = entry.get("role")
            if role not in SUPPORTED_ROLES:
                raise AUTHORING.AuthoringError(f"{region}: unsupported biome role {role!r}")
            identity = entry.get("id")
            if not isinstance(identity, str) or not identity or ":" in identity:
                raise AUTHORING.AuthoringError(f"{region}: secondary biome id must be a stable local name")
            secondary = {"id": f"{region}:{identity}", "role": role,
                         **_surface_record(entry["surface"], terrain, f"{region}.biomePalette.{identity}")}
        result[region] = {"id": f"{region}:base", "base": _surface_record(base, terrain, f"{region}.baseSurface"),
                          "secondary": secondary}
    return result


def _smoothstep(low: float, high: float, value: np.ndarray) -> np.ndarray:
    t = np.clip((value - low) / (high - low), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _pixel_positions(world, cx: int, cz: int) -> tuple[np.ndarray, np.ndarray]:
    samples = np.arange(INNER_SIZE + 2 * GUTTER, dtype=float)
    x = world.x0 + cx * CHUNK + (samples - GUTTER + 0.5) * PIXEL_METRES
    z = world.z0 + cz * CHUNK + (samples - GUTTER + 0.5) * PIXEL_METRES
    return np.meshgrid(x, z)


def _weights(world, ids: list[str], signed: dict[str, np.ndarray], xx: np.ndarray,
             zz: np.ndarray) -> np.ndarray:
    # Warp the *sampling location* once for all regions. Applying a different
    # perturbation to each signed distance would make the two sides disagree.
    wx = xx + WARP_METRES * L._noise(xx, zz, 96, world.plan["seed"] + 511)
    wz = zz + WARP_METRES * L._noise(xx, zz, 96, world.plan["seed"] + 512)
    coords = np.stack(((wz - world.z0 - CELL * 0.5) / CELL,
                       (wx - world.x0 - CELL * 0.5) / CELL))
    raw = np.stack([_smoothstep(-HALF_BLEND_METRES, HALF_BLEND_METRES,
                map_coordinates(signed[region], coords, order=1, mode="nearest")) for region in ids], axis=-1)
    total = raw.sum(axis=-1, keepdims=True)
    if np.any(total <= 0):
        raise AUTHORING.AuthoringError("biome mask has an uncovered pixel")
    return raw / total


def _png(array: np.ndarray) -> bytes:
    stream = io.BytesIO()
    Image.fromarray(np.uint8(np.clip(np.rint(array * 255.0), 0, 255)), "RGBA").save(stream, format="PNG")
    return stream.getvalue()


def _mask_record(path: Path, data: bytes) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file() or path.read_bytes() != data:
        path.write_bytes(data)
    relative = path.relative_to(AUTHORING.CLIENT / "godot-client").as_posix()
    resource = "res://" + relative
    # RGBA channels are four independent numeric weights. Godot's default
    # alpha-border repair changes RGB beneath zero alpha, which corrupts the
    # rare four-palette corner even when the PNG itself is exact. Persist the
    # importer settings with every generated mask for clean clones and later
    # palette refreshes, without changing ordinary albedo imports.
    imported = f"{path.name}-{hashlib.md5(resource.encode('utf-8')).hexdigest()}.ctex"
    sidecar = Path(str(path) + '.import')
    if sidecar.is_file():
        settings = sidecar.read_text(encoding='utf-8')
        if f'source_file="{resource}"' not in settings or imported not in settings:
            raise AUTHORING.AuthoringError(f'{sidecar}: mask import identity drift')
        for key, value in (("compress/mode", "0"),
                           ("process/fix_alpha_border", "false"),
                           ("process/premult_alpha", "false"),
                           ("detect_3d/compress_to", "0")):
            settings, count = re.subn(rf'(?m)^{re.escape(key)}=[^\r\n]+$',
                                      f'{key}={value}', settings)
            if count != 1:
                raise AUTHORING.AuthoringError(f'{sidecar}: expected one {key} setting')
        if any(f'{key}={value}' not in settings for key, value in (
                ("compress/mode", "0"), ("process/fix_alpha_border", "false"),
                ("process/premult_alpha", "false"), ("detect_3d/compress_to", "0"))):
            raise AUTHORING.AuthoringError(f'{sidecar}: numeric mask import settings are incomplete')
    else:
        settings = f'''[remap]\n\nimporter="texture"\ntype="CompressedTexture2D"\npath="res://.godot/imported/{imported}"\nmetadata={{\n"vram_texture": false\n}}\n\n[deps]\n\nsource_file="{resource}"\ndest_files=["res://.godot/imported/{imported}"]\n\n[params]\n\ncompress/mode=0\ncompress/high_quality=false\ncompress/lossy_quality=0.7\ncompress/uastc_level=0\ncompress/rdo_quality_loss=0.0\ncompress/hdr_compression=1\ncompress/normal_map=0\ncompress/channel_pack=0\nmipmaps/generate=false\nmipmaps/limit=-1\nroughness/mode=0\nroughness/src_normal=""\nprocess/channel_remap/red=0\nprocess/channel_remap/green=1\nprocess/channel_remap/blue=2\nprocess/channel_remap/alpha=3\nprocess/fix_alpha_border=false\nprocess/premult_alpha=false\nprocess/normal_map_invert_y=false\nprocess/hdr_as_srgb=false\nprocess/hdr_clamp_exposure=false\nprocess/size_limit=0\ndetect_3d/compress_to=0\n'''
    if not sidecar.is_file() or sidecar.read_text(encoding='utf-8') != settings:
        sidecar.write_text(settings, encoding='utf-8', newline='\n')
    return {"path": resource, "sha256": hashlib.sha256(data).hexdigest()}


def build_masks(world, chunks: set[tuple[int, int]]) -> dict[tuple[int, int], dict]:
    """Emit only chunks whose complete palette is explicitly saved and opted in."""
    sources = palette_sources(world)
    if not sources:
        return {}
    ids = list(world.ids)
    signed = {}
    for index, region in enumerate(ids):
        owned = world.owner == index
        signed[region] = (distance_transform_edt(owned) - distance_transform_edt(~owned)) * CELL
    output = {}
    for cx, cz in sorted(chunks):
        xx, zz = _pixel_positions(world, cx, cz)
        weights = _weights(world, ids, signed, xx, zz)
        active = [index for index in range(len(ids)) if np.any(weights[..., index] > 1e-6)]
        if len(active) > 4:
            raise AUTHORING.AuthoringError(f"biome chunk {cx:02d}_{cz:02d} needs {len(active)} palettes; max 4")
        if not all(ids[index] in sources for index in active):
            continue
        palettes = [sources[ids[index]] for index in active]
        base = np.zeros((*xx.shape, 4), dtype=float)
        local = np.zeros_like(base)
        biome = None
        for channel, index in enumerate(active):
            base[..., channel] = weights[..., index]
            secondary = palettes[channel]["secondary"]
            if secondary is None:
                continue
            if biome is None:
                height = world.height_at(xx, zz)
                biome = L.biome_weights(xx, zz, height=height, plan=world.plan)
            role = secondary["role"]
            field = (L.vegetation_fields(xx, zz, height=height, plan=world.plan)["tree_density"]
                     if role == "tree_density" else biome[role])
            local[..., channel] = _smoothstep(0.08, 0.45, np.asarray(field))
        stem = f"{cx:02d}_{cz:02d}"
        first = _mask_record(MASK_ROOT / f"{stem}-base.png", _png(base))
        second = _mask_record(MASK_ROOT / f"{stem}-secondary.png", _png(local))
        output[cx, cz] = {
            "schema": SCHEMA, "coordinateSpace": "continent-global-xz",
            "origin": [float(world.x0 + cx * CHUNK), float(world.z0 + cz * CHUNK)],
            "innerSize": [INNER_SIZE, INNER_SIZE], "gutter": GUTTER,
            "metresPerPixel": PIXEL_METRES, "baseMask": first, "secondaryMask": second,
            "palettes": palettes,
            "dominantPaletteId": f"{ids[active[int(np.argmax(weights[1:-1, 1:-1, :][:, :, active].sum(axis=(0, 1))))]]}:base",
        }
    return output
