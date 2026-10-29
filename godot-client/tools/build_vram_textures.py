#!/usr/bin/env python3
"""Build the VRAM-compressed sidecars of the content-addressed map images.

    python godot-client/tools/build_vram_textures.py                 # every map, in place
    python godot-client/tools/build_vram_textures.py --out-root DIR  # into a package stage

Use --manifest PATH for one territory's declared chunks and prototypes, or
--scope-group landfall_continent for all seventeen current territories. These
scoped runs require a separate --out-root and keep source image pools intact.

Map packages name their shared images by URI and list each one with its
sha256 in the manifest's externalResources. The client used to decode every
one of them to RGBA8 on the GPU (4 bytes a pixel, plus a third for mips). This
tool writes, beside each directory of such images, a vram/ folder:

  vram/<sha256>.<recipe>.evt   16-byte header ('EVT1', raw DDS size, flags with
                               bit0 = zstd, reserved) + one zstd frame (level
                               19) holding a DDS with the full mip chain,
                               already block compressed
  vram/index.json              schema, recipeVersion, encoder, and per source
                               sha: file, recipe, format, width, height,
                               mipmaps, gpuBytes, rawBytes, fileBytes, sha256,
                               roles; plus every excluded sha with its reason
  vram/report.json             the per-image quality numbers (not shipped)

The client (src/world/vram_textures.gd) uploads a sidecar as it is when the
renderer can sample its format, and decodes the JPEG/PNG otherwise. Nothing
here changes a map package: manifests, GLBs and digests are untouched, and a
sidecar is keyed by the source's own sha.

Every directory is planned on its own. Two pools may hold the same bytes
(continent-v2's _continent_v2/shared-assets shares 315 images with
nymara-regions/_continent/shared-assets): each copy gets a sidecar in its own
directory's vram/, with the roles of the maps that name that copy, so a
directory's index is the same whether or not the other pool is in the tree.
Copies share one cached encode.

Recipes, from every glTF material slot that samples the image in any map
naming that copy:

  base        base colour / emissive, alpha unused  -> BC7 (sRGB view)
  base_alpha  base colour of a MASK/BLEND material whose alpha is used -> BC7
  orm         metallicRoughness and/or occlusion     -> BC1
  orm_bc7     an ORM map below its floor as BC1      -> BC7 (one second chance:
              BC1 shares endpoints across channels that ORM keeps unrelated)
  normal      normalTexture                          -> BC5 (Godot rebuilds Z)

`roles` lists every slot the encode was chosen for, as the client names them
(base, base_cutout for a base colour in a MASK/BLEND material, emissive,
normal, orm, occlusion). The client uses a sidecar only where the map it is
loading samples the image in those roles, so an index left over from before a
content change (a base colour that became a cutout, an ORM map now sampled as
colour) makes that image decode instead of rendering wrong.

Excluded (the client decodes them as before): an image used in two
incompatible roles (role_conflict), one no material samples
(no_material_role), a size that is not a multiple of 4, and any encode below
its quality floor:

  base / base_alpha  PSNR >= 36 dB (RGB) at mip 0, >= 30 dB at mips 1-3
  base_alpha         alpha flips <= 1.0 % at mip 0 and <= 2.0 % at mips 1-4,
                     at every alphaCutoff a MASK material cuts it at (0.45 on
                     every cutout today; 0.5 stands in for BLEND)
  normal             angular error mean <= 1.0 deg, p99 <= 3 deg at mip 0;
                     <= 1.5 / 4.5 deg at mips 1-2 (Z rebuilt from XY)
  orm                PSNR >= 33 dB per channel at mip 0, >= 28 dB at mips 1-2

  (a mip under 32 px on its shorter side is reported, not gated)

The game camera (-60 deg, 26 m) samples mips 1-4 of most map textures, where
block error grows, hence the per-mip floors. Mips are compared with the 2x2
average of the source (Image.generate_mipmaps). JPEG sources are decoded by
Pillow here and by Godot in the client; any difference between those two
decoders counts against the encode here, so the numbers err on the strict
side. report.json (not shipped) keeps every measured mip.

Encoding runs headless on the Godot 4.7.2 EDITOR binary (tools/vram_encode.gd)
in --procs processes; the export templates cannot encode. The mip chain is
Image.generate_mipmaps() on the decoded image, as the client builds it.

Encodes are cached by (source sha, recipe, recipe version, Godot version),
never by output: BC7 output is not bit-for-bit reproducible. The cache must be
a directory git ignores (the default, <repo>/.vram-encode-cache, is); entries
this run did not use are pruned unless --no-prune.

Needs numpy and Pillow (the quality check decodes the DDS with Pillow). With
the zstandard module, a cached encode whose measurement is out of date
(QUALITY_VERSION, or other alpha cutoffs) is measured again from its cached
sidecar; without it, it is encoded again.

Scenery (world-object) GLBs embed their images in the GLB's BIN chunk:

    python godot-client/tools/build_vram_textures.py \
        --scenery-config godot-client/data/world/town-scenery.json \
        --scenery-out-root STAGE/godot-client/assets/world ...

--scenery-config names a scenery config (its "assets" object maps ids to
res:// GLB paths; repeatable). Each bufferView image of those GLBs is planned
like a map image, keyed by the sha256 of its bytes, with the roles and
cutoffs of that GLB's materials, and its sidecar goes in the vram/ folder of
the GLB's own directory, which is where the client looks
(src/world/world_object_images.gd: the GLTFState's base path). The bytes are
extracted once into the cache's _embedded/ folder for the encoder. With
--scenery-out-root the vram/ folders are written under that root, mirroring
the GLB directories below godot-client/assets/world; without it they are
written beside the GLBs, which a scoped (--manifest) run refuses, as it
refuses to replace a source pool's index. URI images of a scenery GLB are left
alone (the client decodes them as before).

--unskip-map <map dir> (relative to a --maps root, e.g.
continent-v2/landfall_town) keeps planning the images that map's manifests
name even inside a --skip-dir directory: the package skips the whole shared
image pool (maps/_shared/images) but still ships sidecars for one map's images
there.
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CLIENT = Path(__file__).resolve().parents[1]
REPO = CLIENT.parent
PROJECT = REPO.parent
ENCODER = CLIENT / "tools" / "vram_encode.gd"
GODOT_EXE = "Godot_v4.7.2-stable_win64_console.exe"

SCHEMA = 1
# Raise when a recipe's encode changes (a different compressor call, channel
# set or mip rule): it is part of every cache key, so nothing old is reused,
# and the client refuses an index whose recipeVersion it does not know.
RECIPE_VERSION = 1
# Raise when measure() changes what it records: cached encodes are measured
# again from their cached sidecar (never re-encoded; needs the zstandard
# module, else they are encoded afresh).
QUALITY_VERSION = 2
CONTAINER = "EVT1 header + zstd(19) DDS with the full mip chain"
SIDECAR_DIR = "vram"
HEADER = struct.Struct("<4sIII")
FLAG_ZSTD = 1

SLOTS = {"baseColorTexture": "base", "emissiveTexture": "emissive", "normalTexture": "normal",
         "metallicRoughnessTexture": "orm", "occlusionTexture": "occlusion"}
FORMAT_OF = {"base": "bc7", "base_alpha": "bc7", "orm": "bc1", "orm_bc7": "bc7", "normal": "bc5"}
SECOND_CHANCE = {"orm": "orm_bc7"}
FLOORS = {"base_psnr": 36.0, "base_psnr_median": 42.0, "alpha_flip_mip0": 0.010,
          "alpha_flip_mip2": 0.015, "normal_mean_deg": 1.0, "normal_p99_deg": 3.0,
          "orm_psnr": 33.0,
          # The game camera (-60 deg, 26 m) samples mips 1-4 of most map
          # textures, where block error grows: floors for the smaller mips.
          "base_psnr_mips": 30.0, "alpha_flip_mips": 0.020, "normal_mean_deg_mips": 1.5,
          "normal_p99_deg_mips": 4.5, "orm_psnr_mips": 28.0}
# Mips measured per recipe (0 = full size); the per-mip floors gate mips
# 1..GATED_MIPS[recipe], alpha flips 1..ALPHA_GATED_MIPS.
MEASURED_MIPS = {"base": 4, "base_alpha": 4, "normal": 2, "orm": 2, "orm_bc7": 2}
GATED_MIPS = {"base": 3, "base_alpha": 3, "normal": 2, "orm": 2, "orm_bc7": 2}
ALPHA_GATED_MIPS = 4
# A mip smaller than this (its shorter side, in pixels) is reported, not
# gated: a handful of blocks makes PSNR and flip shares jump by whole steps.
MIN_GATED_MIP = 32
DDS_BLOCK_BYTES = {"bc1": 8, "bc5": 16, "bc7": 16}
PILLOW_BCN = {"bc1": ("RGBA", 1), "bc5": ("RGB", 5), "bc7": ("RGBA", 7)}
# Scenery GLBs live below this root (res://assets/world/...); --scenery-out-root mirrors their directories from it.
SCENERY_ROOT = CLIENT / "assets" / "world"
# Where the embedded images of scenery GLBs are extracted for the encoder, inside the (ignored) encode cache.
EMBEDDED_DIR = "_embedded"
EMBEDDED_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}


class BuildError(RuntimeError):
    pass


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


# --- inventory -----------------------------------------------------------------

def glb_json(path: Path) -> dict:
    with open(path, "rb") as handle:
        header = handle.read(20)
        if len(header) < 20 or header[:4] != b"glTF":
            raise ValueError("not a GLB")
        length = struct.unpack_from("<I", header, 12)[0]
        return json.loads(handle.read(length).decode("utf-8"))


def glb_chunks(path: Path) -> tuple[dict, bytes]:
    """A GLB's JSON document and its BIN chunk (b"" when it has none)."""
    data = path.read_bytes()
    if len(data) < 20 or data[:4] != b"glTF":
        raise ValueError("not a GLB")
    length = struct.unpack_from("<I", data, 12)[0]
    document = json.loads(data[20:20 + length].decode("utf-8"))
    offset = 20 + length
    binary = b""
    if offset + 8 <= len(data) and struct.unpack_from("<I", data, offset + 4)[0] == 0x004E4942:
        binary = data[offset + 8:offset + 8 + struct.unpack_from("<I", data, offset)[0]]
    return document, binary


def scenery_glbs(configs: list[Path]) -> list[Path]:
    """The GLBs a scenery config's "assets" object names (res:// paths below godot-client), in order, once each."""
    glbs: list[Path] = []
    for config in configs:
        try:
            assets = json.loads(config.read_text(encoding="utf-8-sig")).get("assets")
            if not isinstance(assets, dict) or not assets:
                raise ValueError("no assets object")
        except (OSError, ValueError, AttributeError) as error:
            raise BuildError(f"cannot read scenery config {config}: {error}") from error
        for asset, value in assets.items():
            if not isinstance(value, str) or not value.startswith("res://") or not value.lower().endswith(".glb"):
                raise BuildError(f"{config}: asset {asset} is not a res:// GLB path: {value!r}")
            glb = (CLIENT / value[len("res://"):]).resolve()
            if not glb.is_relative_to(SCENERY_ROOT.resolve()):
                raise BuildError(f"{config}: asset {asset} is outside {SCENERY_ROOT}: {value}")
            if not glb.is_file():
                raise BuildError(f"{config}: asset {asset} is missing: {glb}")
            if glb not in glbs:
                glbs.append(glb)
    return glbs


def embedded_images(glb: Path, extract_dir: Path) -> list[tuple[int, str, Path]]:
    """(image index, sha256, extracted file) for each bufferView image of a GLB. The bytes are written once, by
    sha, into extract_dir (the encoder and the quality check read files)."""
    document, binary = glb_chunks(glb)
    views = document.get("bufferViews", [])
    found = []
    for index, image in enumerate(document.get("images", [])):
        view_index = image.get("bufferView")
        if not isinstance(view_index, int) or not 0 <= view_index < len(views):
            continue
        view = views[view_index]
        if view.get("buffer", 0) != 0:
            raise BuildError(f"{glb}: image {index} lives outside the GLB's BIN chunk")
        start = view.get("byteOffset", 0)
        payload = binary[start:start + view["byteLength"]]
        if len(payload) != view["byteLength"]:
            raise BuildError(f"{glb}: image {index}'s bufferView runs past the BIN chunk")
        sha = hashlib.sha256(payload).hexdigest()
        suffix = EMBEDDED_TYPES.get(str(image.get("mimeType", "")).lower())
        if suffix is None:
            suffix = ".png" if payload[:8] == b"\x89PNG\r\n\x1a\n" else (
                ".jpg" if payload[:3] == b"\xff\xd8\xff" else (".webp" if payload[8:12] == b"WEBP" else None))
        if suffix is None:
            continue  # not an image this client decodes either
        target = extract_dir / (sha + suffix)
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != sha:
            extract_dir.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        found.append((index, sha, target))
    return found


def image_roles(document: dict) -> dict[int, set[tuple[str, str]]]:
    """glTF image index -> {(role, alphaMode)} over every material slot."""
    sources = []
    for texture in document.get("textures", []):
        source = texture.get("source")
        for extension in (texture.get("extensions") or {}).values():
            if isinstance(extension, dict) and "source" in extension:
                source = extension["source"]
        sources.append(source)
    roles: dict[int, set[tuple[str, str]]] = {}

    def walk(item, alpha):
        if isinstance(item, dict):
            for key, value in item.items():
                if key in SLOTS and isinstance(value, dict) and isinstance(value.get("index"), int):
                    index = value["index"]
                    if 0 <= index < len(sources) and sources[index] is not None:
                        roles.setdefault(sources[index], set()).add((SLOTS[key], alpha))
                else:
                    walk(value, alpha)
        elif isinstance(item, list):
            for value in item:
                walk(value, alpha)

    for material in document.get("materials", []):
        walk(material, material.get("alphaMode", "OPAQUE"))
    return roles


def image_cutoffs(document: dict) -> dict[int, set[float]]:
    """glTF image index -> the alpha thresholds its alpha is cut at: each MASK
    material's alphaCutoff (glTF default 0.5) for its base colour, and 0.5 as
    a stand-in for a BLEND material's. Godot's glTF import makes alphaCutoff
    the material's alpha_scissor_threshold, and the look's painted foliage
    keeps it (look_foliage.gd)."""
    sources = []
    for texture in document.get("textures", []):
        source = texture.get("source")
        for extension in (texture.get("extensions") or {}).values():
            if isinstance(extension, dict) and "source" in extension:
                source = extension["source"]
        sources.append(source)
    cutoffs: dict[int, set[float]] = {}

    def walk(item, cutoff):
        if isinstance(item, dict):
            for key, value in item.items():
                if key == "baseColorTexture" and isinstance(value, dict) and isinstance(value.get("index"), int):
                    index = value["index"]
                    if 0 <= index < len(sources) and sources[index] is not None:
                        cutoffs.setdefault(sources[index], set()).add(cutoff)
                elif key not in SLOTS:
                    walk(value, cutoff)
        elif isinstance(item, list):
            for value in item:
                walk(value, cutoff)

    for material in document.get("materials", []):
        mode = material.get("alphaMode", "OPAQUE")
        if mode == "MASK":
            walk(material, round(float(material.get("alphaCutoff", 0.5)), 4))
        elif mode == "BLEND":
            walk(material, 0.5)
    return cutoffs


def role_names(roles: set[tuple[str, str]]) -> list[str]:
    """The roles an index entry records, as the client (vram_textures.gd
    image_roles) names them: a base colour sampled by a MASK or BLEND
    material is base_cutout."""
    return sorted({"base_cutout" if role == "base" and alpha in ("MASK", "BLEND") else role
                   for role, alpha in roles})


def scope_group_manifests(groups: list[str]) -> list[Path]:
    """Resolve the current registry's map groups without planning/importing scenes."""
    if not groups:
        return []
    import map_geometry_cache as geometry
    try:
        scope = geometry.read_json(CLIENT / geometry.SCOPE)
        registry = geometry.read_json(CLIENT / geometry.REGISTRY)["maps"]
        paths = []
        for group in groups:
            identities = scope.get("groups", {}).get(group)
            if not isinstance(identities, list) or not identities:
                raise BuildError(f"unknown or empty map scope group: {group}")
            for identity in identities:
                canonical = geometry.resolve_alias(registry, identity)
                paths.append(geometry.source_path(CLIENT, registry[canonical]["manifest"]))
        return list(dict.fromkeys(paths))
    except (geometry.PlanError, KeyError, TypeError) as error:
        raise BuildError(f"cannot resolve map scope: {error}") from error


def _source_sha(path: Path, hashes: dict[Path, str]) -> str:
    if path not in hashes:
        hashes[path] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes[path]


def _check_source_sha(path: Path, expected: object, hashes: dict[Path, str]) -> str:
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise BuildError(f"invalid declared SHA256 for {path}: {expected!r}")
    actual = _source_sha(path, hashes)
    if actual != expected:
        raise BuildError(f"{path} does not hash to its declared SHA256 {expected}")
    return actual


def scoped_inputs(maps_roots: list[Path], manifests: list[Path],
                  hashes: dict[Path, str] | None = None) -> tuple[list[Path], list[Path]]:
    """Only declared runtime leaves and their prototypes; never root preview GLBs."""
    leaves, prototypes = set(), set()
    maps_roots = [root.resolve() for root in maps_roots]
    hashes = {} if hashes is None else hashes

    def inside(path: Path) -> Path:
        path = path.resolve()
        _containing_root(maps_roots, path.parent)
        return path

    def document(path: Path) -> dict:
        try:
            result = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(result, dict):
                raise ValueError("expected an object")
            return result
        except (OSError, ValueError) as error:
            raise BuildError(f"cannot read scoped manifest {path}: {error}") from error

    def leaf(path: Path, data: dict) -> None:
        if "streamingChunks" in data:
            raise BuildError(f"nested streaming manifest is not a scene leaf: {path}")
        glb = inside(path.parent / str(data.get("asset", {}).get("glb", "world.glb")))
        if not glb.is_file():
            raise BuildError(f"scoped scene is missing: {glb}")
        meshes = data.get("externalMeshes") or {}
        if not isinstance(meshes, dict):
            raise BuildError(f"invalid externalMeshes in {path}")
        for uri, expected in meshes.items():
            prototype = inside(glb.parent / str(uri))
            if not prototype.is_file():
                raise BuildError(f"scoped prototype is missing: {prototype}")
            _check_source_sha(prototype, expected, hashes)
            prototypes.add(prototype)
        leaves.add(path)

    if not manifests:
        raise BuildError("no map manifests selected")
    for source in manifests:
        path = inside(source)
        data = document(path)
        chunks = data.get("streamingChunks")
        if chunks is None:
            leaf(path, data)
            continue
        entries = chunks.get("chunks") if isinstance(chunks, dict) else None
        if not isinstance(entries, list) or not entries:
            raise BuildError(f"invalid streaming chunk list in {path}")
        for entry in entries:
            uri = entry.get("manifest") if isinstance(entry, dict) else None
            if not isinstance(uri, str) or not uri:
                raise BuildError(f"invalid streaming chunk manifest in {path}")
            child = inside(path.parent / uri)
            leaf(child, document(child))
    return sorted(leaves), sorted(prototypes)



POLICY_DIRECTORY_EXTRA = "rl_texture_policy_directory"
POLICY_COLLECTION = "externalImagePolicies"

def image_policy_directory(image: dict, glb: Path, maps_roots: list[Path]) -> Path:
    extras = image.get("extras", {})
    if not isinstance(extras, dict) or POLICY_DIRECTORY_EXTRA not in extras:
        return (glb.parent / str(image.get("uri", ""))).resolve().parent
    uri = extras[POLICY_DIRECTORY_EXTRA]
    if not isinstance(uri, str) or not uri or ":" in uri or "%" in uri or "\\" in uri or Path(uri).is_absolute():
        raise BuildError(f"invalid texture policy directory in {glb}: {uri!r}")
    directory = (glb.parent / uri).resolve()
    _containing_root(maps_roots, directory)
    return directory

def declared_policy_directories(manifest: dict, uri: str, glb: Path, maps_roots: list[Path]) -> list[Path]:
    policies = manifest.get(POLICY_COLLECTION, {})
    if not isinstance(policies, dict):
        raise BuildError(f"invalid {POLICY_COLLECTION} for {glb}")
    if uri not in policies:
        return [(glb.parent / uri).resolve().parent]
    values = policies[uri]
    if not isinstance(values, list) or not values:
        raise BuildError(f"invalid texture policy collection for {glb}: {uri}")
    return sorted({image_policy_directory({"extras": {POLICY_DIRECTORY_EXTRA: value}}, glb, maps_roots) for value in values})


def inventory(maps_roots: list[Path], manifests: list[Path] | None = None, scenery: list[Path] | None = None,
              extract_dir: Path | None = None, input_files: set[Path] | None = None) -> dict[tuple[Path, str], dict]:
    """(image directory, sha) -> {path, roles: {(role, alphaMode)}, maps: set, cutoffs: set}

    One record per COPY of an image: two pools can hold the same bytes (the
    continent-v2 pool shares 315 images with nymara-regions/_continent's), and
    each directory gets its own vram/ index. A copy's roles and cutoffs come
    only from the manifests whose URIs resolve to that copy, so one pool's index
    is what it would be if the other pool were not in the tree: keyed by sha
    alone, the first manifest found named every shared image's directory, the
    other pool's index lost them and an in-place run deleted their sidecars."""
    maps_roots = [root.resolve() for root in maps_roots]
    found: dict[tuple[Path, str], dict] = {}
    image_hashes: dict[Path, str] = {}
    manifest_count = 0
    selected = scoped_inputs(maps_roots, manifests, hashes=image_hashes) if manifests is not None else None
    prototype_indexes: dict[Path, dict] = {}

    def record_for(path: Path, sha: str, policy_directory: Path | None = None) -> dict:
        path = path.resolve()
        if selected is not None:
            _containing_root(maps_roots, path.parent)
            if not path.is_file():
                raise BuildError(f"scoped image is missing: {path}")
        return found.setdefault((policy_directory or path.parent, sha), {"path": path, "roles": set(), "maps": set(), "cutoffs": set()})

    for root in maps_roots:
        paths = ([path for path in selected[0] if _containing_root(maps_roots, path.parent) == root]
                 if selected is not None else sorted(root.rglob("world.json")))
        if input_files is not None:
            paths = [path for path in paths if path in input_files]
        for manifest_path in paths:
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError) as error:
                if selected is not None:
                    raise BuildError(f"cannot read scoped manifest {manifest_path}: {error}") from error
                continue
            resources = manifest.get("externalResources") or {}
            if not isinstance(resources, dict) or not resources:
                continue
            # A territory root lists its chunks' resources, but its own GLB is
            # a review file the client never loads; the chunks carry the roles.
            if "streamingChunks" in manifest:
                glb = manifest_path.parent / str(manifest.get("asset", {}).get("glb", "world.glb"))
                for uri, sha in resources.items():
                    if isinstance(sha, str) and len(sha) == 64:
                        for directory in declared_policy_directories(manifest, uri, glb, maps_roots):
                            record_for(glb.parent / uri, sha, directory)
                continue
            glb = manifest_path.parent / str(manifest.get("asset", {}).get("glb", "world.glb"))
            try:
                document = glb_json(glb)
            except (OSError, ValueError) as error:
                if selected is not None:
                    raise BuildError(f"cannot read scoped GLB {glb}: {error}") from error
                continue
            manifest_count += 1
            roles = image_roles(document)
            cutoffs = image_cutoffs(document)
            by_uri: dict[str, list[int]] = {}
            for index, image in enumerate(document.get("images", [])):
                if image.get("uri"): by_uri.setdefault(str(image["uri"]), []).append(index)
            for uri, sha in resources.items():
                if not isinstance(sha, str) or len(sha) != 64:
                    continue
                declared = declared_policy_directories(manifest, uri, glb, maps_roots)
                indices = by_uri.get(uri, [])
                if not indices:
                    for directory in declared: record_for(glb.parent / uri, sha, directory)
                for index in indices:
                    image = document["images"][index]
                    directory = image_policy_directory(image, glb, maps_roots)
                    if directory not in declared:
                        raise BuildError(f"undeclared texture policy in {glb}: {uri}")
                    record = record_for(glb.parent / uri, sha, directory)
                    record["roles"] |= roles.get(index, set())
                    record["cutoffs"] |= cutoffs.get(index, set())
                    record["maps"].add(str(manifest_path.parent.relative_to(root)))
    # Prototypes (shared_meshes.py) draw the same shared images, and since the
    # prop moved out of the chunk the chunk's GLB no longer names them: without
    # this the roles come back empty and the image loses its sidecar, which is
    # how nymara-regions' coverage fell from 565 MB to 52 MB.
    prototypes = 0
    for root in maps_roots:
        paths = ([path for path in selected[1] if _containing_root(maps_roots, path.parent) == root]
                 if selected is not None else sorted((root / "_shared" / "meshes").glob("*.glb")))
        if input_files is not None:
            paths = [path for path in paths if path in input_files]
        for glb in paths:
            try:
                document = glb_json(glb)
            except (OSError, ValueError) as error:
                if selected is not None:
                    raise BuildError(f"cannot read scoped prototype {glb}: {error}") from error
                continue
            roles = image_roles(document)
            cutoffs = image_cutoffs(document)
            named = False
            declared_images = None
            for index, image in enumerate(document.get("images", [])):
                uri = str(image.get("uri", ""))
                if not uri or uri.startswith("data:"):
                    continue
                path = (glb.parent / uri).resolve()
                if selected is not None:
                    _containing_root(maps_roots, path.parent)
                if not path.is_file():
                    if selected is not None:
                        raise BuildError(f"scoped prototype image is missing: {path}")
                    continue
                if selected is not None:
                    if declared_images is None:
                        index_path = (glb.parent / "index.json").resolve()
                        _containing_root(maps_roots, index_path.parent)
                        try:
                            if index_path not in prototype_indexes:
                                prototype_indexes[index_path] = json.loads(index_path.read_text(encoding="utf-8-sig"))
                            declared_images = prototype_indexes[index_path]["prototypes"][glb.stem]["images"]
                            if not isinstance(declared_images, dict):
                                raise ValueError("images must be an object")
                        except (OSError, ValueError, KeyError, TypeError) as error:
                            raise BuildError(f"cannot read scoped prototype image index for {glb}: {error}") from error
                    sha = _check_source_sha(path, declared_images.get(uri), image_hashes)
                else:
                    sha = _source_sha(path, image_hashes)
                policy_directory = image_policy_directory(image, glb, maps_roots)
                if isinstance(image.get("extras"), dict) and POLICY_DIRECTORY_EXTRA in image["extras"]:
                    index_path = glb.parent / "index.json"
                    if index_path not in prototype_indexes:
                        prototype_indexes[index_path] = json.loads(index_path.read_text(encoding="utf-8-sig"))
                    entry = prototype_indexes[index_path].get("prototypes", {}).get(glb.stem, {})
                    collection = entry.get("imagePolicies", {})
                    if uri not in collection or policy_directory not in declared_policy_directories(
                            {POLICY_COLLECTION: collection}, uri, glb, maps_roots):
                        raise BuildError(f"undeclared prototype texture policy in {glb}: {uri}")
                record = record_for(path, sha, policy_directory)
                record["roles"] |= roles.get(index, set())
                record["cutoffs"] |= cutoffs.get(index, set())
                record["maps"].add("_shared/meshes")
                named = True
            prototypes += 1 if named else 0
    # Scenery GLBs (world objects) embed their images: each is keyed by the GLB's own directory, where the client
    # looks for vram/ (world_object_images.gd), and encoded from its bytes extracted into the cache.
    scenery_images = 0
    for glb in scenery or []:
        if extract_dir is None:
            raise BuildError("scenery GLBs need an extraction directory")
        try:
            document = glb_json(glb)
            extracted = embedded_images(glb, extract_dir)
        except (OSError, ValueError, KeyError) as error:
            raise BuildError(f"cannot read scenery GLB {glb}: {error}") from error
        roles = image_roles(document)
        cutoffs = image_cutoffs(document)
        for index, sha, path in extracted:
            record = found.setdefault((glb.parent.resolve(), sha),
                                      {"path": path, "roles": set(), "maps": set(), "cutoffs": set()})
            record["roles"] |= roles.get(index, set())
            record["cutoffs"] |= cutoffs.get(index, set())
            record["maps"].add("scenery:" + glb.name)
            scenery_images += 1
    shas = {sha for _, sha in found}
    log(f"inventory: {len(shas)} content-addressed images ({len(found)} copies in "
        f"{len({directory for directory, _ in found})} directories) from {manifest_count} map packages "
        f"and {prototypes} prototypes" + (f"; {scenery_images} embedded images of {len(scenery)} scenery GLBs"
                                            if scenery else ""))
    return found



def delivery_policy(record: dict, source_dir: Path, skip: list[str] | None = None,
                    unskip: list[str] | None = None) -> dict:
    """Pure package planning policy, also used to prove lossless URI rebasing.

    The complete role/alpha pairs and cutoffs matter even when caller-excluded:
    merging only equally planned copies must not expand a skipped usage or turn
    an existing role conflict into a new encode. Quality verdicts remain the
    normal per-recipe, per-cutoff gates later in build().
    """
    recipe, reason = recipe_for(record)
    unskip = [str(name).replace(chr(92), "/").strip("/") for name in unskip or []]
    if skip and any(str(source_dir).replace(chr(92), "/").endswith(
            str(name).replace(chr(92), "/")) for name in skip) and not any(
            used == name or used.startswith(name + "/")
            for used in record["maps"] for name in unskip):
        recipe, reason = None, "excluded_by_caller"
    return {"recipe": recipe, "reason": reason, "roles": role_names(record["roles"]),
            "rolePairs": sorted([list(pair) for pair in record["roles"]]),
            "cutoffs": sorted(record.get("cutoffs") or [])}


def alpha_used(path: Path) -> bool:
    from PIL import Image
    with Image.open(path) as image:
        if image.mode not in ("RGBA", "LA", "P", "PA") and "transparency" not in image.info:
            return False
        import numpy as np
        return bool((np.asarray(image.convert("RGBA"))[..., 3] < 255).any())


def recipe_for(record: dict) -> tuple[str | None, str]:
    roles = {role for role, _ in record["roles"]}
    if not roles:
        return None, "no_material_role"
    if roles == {"normal"}:
        return "normal", ""
    if roles <= {"orm", "occlusion"}:
        return "orm", ""
    if roles <= {"base", "emissive"}:
        cutout = any(role == "base" and alpha in ("MASK", "BLEND") for role, alpha in record["roles"])
        if cutout and alpha_used(record["path"]):
            return "base_alpha", ""
        return "base", ""
    return None, "role_conflict: " + "+".join(sorted(roles))


# --- Godot -----------------------------------------------------------------------

def find_godot(explicit: str | None) -> Path:
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    if os.environ.get("ELORIA_GODOT"):
        candidates.append(Path(os.environ["ELORIA_GODOT"]))
    # The checkout's own copy, else the main checkout's beside (or above) this
    # worktree: the binary is untracked and lives in rabbitlands-client only.
    executable_names = (GODOT_EXE, GODOT_EXE.replace("_console", ""))
    candidates.extend(CLIENT / name for name in executable_names)
    candidates.extend(parent / "rabbitlands-client" / "godot-client" / name
                      for parent in REPO.parents for name in executable_names)
    on_path = shutil.which("godot")
    if on_path:
        candidates.append(Path(on_path))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise BuildError("Godot 4.7.2 editor binary not found; pass --godot or set ELORIA_GODOT")


def godot_version(godot: Path) -> str:
    out = subprocess.run([str(godot), "--headless", "--version"], capture_output=True, text=True,
                         timeout=120).stdout.strip().splitlines()
    version = out[-1].strip() if out else ""
    if not version.startswith("4."):
        raise BuildError(f"cannot read the Godot version from {godot}: {out!r}")
    return version


def encoder_project(cache: Path) -> Path:
    project = cache / "_encoder_project"
    project.mkdir(parents=True, exist_ok=True)
    (project / "project.godot").write_text(
        'config_version=5\n\n[application]\n\nconfig/name="eloria_vram_encode"\n\n'
        "[compression]\n\nformats/zstd/compression_level=19\n", encoding="utf-8", newline="\n")
    return project


def run_encoders(godot: Path, cache: Path, jobs: list[dict], procs: int) -> dict[tuple[str, str], dict]:
    if not jobs:
        return {}
    project = encoder_project(cache)
    work = cache / "_work"
    work.mkdir(parents=True, exist_ok=True)
    # Largest first, dealt round robin, so the processes finish together.
    jobs = sorted(jobs, key=lambda job: -os.path.getsize(job["src"]))
    batches = [jobs[index::procs] for index in range(procs)]
    env = dict(os.environ, APPDATA=str(cache / "_appdata"), LOCALAPPDATA=str(cache / "_appdata"),
               XDG_DATA_HOME=str(cache / "_appdata"), XDG_CONFIG_HOME=str(cache / "_appdata"))
    running = []
    for index, batch in enumerate(batches):
        if not batch:
            continue
        jobs_file = work / f"jobs{index}.json"
        jobs_file.write_text(json.dumps(batch), encoding="utf-8")
        log_file = open(work / f"encode{index}.log", "w", encoding="utf-8", errors="replace")
        process = subprocess.Popen([str(godot), "--headless", "--path", str(project), "--script", str(ENCODER)],
                                   stdout=log_file, stderr=subprocess.STDOUT,
                                   env=dict(env, VRAM_JOBS=str(jobs_file)))
        running.append((process, log_file, work / f"encode{index}.log"))
    # Keyed by (sha, recipe): one image can be encoded for two recipes in one
    # batch when two pools sample it in different roles.
    results: dict[tuple[str, str], dict] = {}
    for process, log_file, log_path in running:
        process.wait(timeout=3600)
        log_file.close()
        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("VRAM_RESULT "):
                result = json.loads(line[len("VRAM_RESULT "):])
                results[(result["sha"], result["recipe"])] = result
        if process.returncode != 0:
            raise BuildError(f"the encoder exited {process.returncode}; log: {log_path}")
    missing = [job["sha"] for job in jobs if (job["sha"], job["recipe"]) not in results]
    if missing:
        raise BuildError(f"the encoder gave no result for {len(missing)} images, e.g. {missing[:3]}")
    return results


# --- quality ------------------------------------------------------------------------

def _box_mips(array, levels):
    import numpy as np
    out = [array.astype(np.float64)]
    for _ in range(levels):
        a = out[-1]
        h, w = a.shape[0] // 2 * 2, a.shape[1] // 2 * 2
        a = a[:h, :w]
        out.append(np.floor((a[0::2, 0::2] + a[1::2, 0::2] + a[0::2, 1::2] + a[1::2, 1::2] + 2) / 4))
    return out


def _dds_level(dds: bytes, fmt: str, width: int, height: int, level: int):
    """One mip level of a DDS, decoded with Pillow's BCn decoder, as float RGBA."""
    import numpy as np
    from PIL import Image
    offset = 128 + (20 if dds[84:88] == b"DX10" else 0)
    block = DDS_BLOCK_BYTES[fmt]
    for _ in range(level):
        offset += max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * block
        width, height = max(1, width // 2), max(1, height // 2)
    size = max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * block
    mode, n = PILLOW_BCN[fmt]
    image = Image.frombytes(mode, (width, height), dds[offset:offset + size], "bcn", n)
    return np.asarray(image.convert("RGBA")).astype(np.float64)


def _psnr(a, b) -> float:
    import numpy as np
    mse = float(np.mean((a - b) ** 2))
    return 99.0 if mse == 0 else 10 * np.log10(255.0 ** 2 / mse)


def _unit_normals(array):
    import numpy as np
    xy = array[..., :2] / 255.0 * 2 - 1
    z = np.sqrt(np.clip(1 - (xy ** 2).sum(-1), 0, 1))
    vector = np.dstack([xy, z])
    return vector / np.maximum(np.linalg.norm(vector, axis=-1, keepdims=True), 1e-6)


def measure(task: tuple) -> dict:
    """Quality of one encode against the source (Pillow decode + box mips, the
    2x2 average Image.generate_mipmaps builds), per mip 0..MEASURED_MIPS:

      base, base_alpha  psnr / psnr_mips (RGB), bias (mip 0, per channel)
      base_alpha        alpha_flips {cutoff: [share per mip]} at every cutoff
                        a material cuts it at, and alpha_flip_max per mip
      normal            mean_deg / p99_deg and *_mips (Z rebuilt from XY)
      orm, orm_bc7      psnr_rgb / psnr_rgb_mips (per channel)
    """
    import numpy as np
    from PIL import Image
    source, dds_path, recipe, fmt, width, height, mipmaps, cutoffs = task
    dds = Path(dds_path).read_bytes()
    with Image.open(source) as image:
        reference = np.asarray(image.convert("RGBA")).astype(np.float64)
    levels = min(MEASURED_MIPS[recipe], int(mipmaps))
    references = _box_mips(reference, levels)
    decoded = [_dds_level(dds, fmt, width, height, level) for level in range(levels + 1)]
    metrics: dict = {"qualityVersion": QUALITY_VERSION, "size": [int(width), int(height)]}
    if recipe in ("base", "base_alpha"):
        metrics["psnr_mips"] = [round(_psnr(r[..., :3], d[..., :3]), 2) for r, d in zip(references, decoded)]
        metrics["psnr"] = metrics["psnr_mips"][0]
        bias = (decoded[0][..., :3] - reference[..., :3]).mean(axis=(0, 1))
        metrics["bias"] = [round(float(v), 3) for v in bias]
        if recipe == "base_alpha":
            flips = {}
            for cutoff in sorted(cutoffs or [0.5]):
                threshold = float(cutoff) * 255.0
                flips[f"{float(cutoff):g}"] = [round(float(((r[..., 3] >= threshold) != (d[..., 3] >= threshold)).mean()), 5)
                                              for r, d in zip(references, decoded)]
            metrics["cutoffs"] = sorted(float(c) for c in (cutoffs or [0.5]))
            metrics["alpha_flips"] = flips
            metrics["alpha_flip_max"] = [max(per[m] for per in flips.values()) for m in range(levels + 1)]
            metrics["alpha_flip_mip0"] = metrics["alpha_flip_max"][0]
            metrics["alpha_flip_mip2"] = metrics["alpha_flip_max"][min(2, levels)]
    elif recipe == "normal":
        means, p99s = [], []
        for r, d in zip(references, decoded):
            angle = np.degrees(np.arccos(np.clip((_unit_normals(r) * _unit_normals(d)).sum(-1), -1, 1)))
            means.append(round(float(angle.mean()), 3))
            p99s.append(round(float(np.percentile(angle, 99)), 3))
        metrics.update({"mean_deg": means[0], "p99_deg": p99s[0], "mean_deg_mips": means, "p99_deg_mips": p99s})
    elif recipe in ("orm", "orm_bc7"):
        metrics["psnr_rgb_mips"] = [[round(_psnr(r[..., c], d[..., c]), 2) for c in range(3)]
                                    for r, d in zip(references, decoded)]
        metrics["psnr_rgb"] = metrics["psnr_rgb_mips"][0]
    return metrics


def for_cutoffs(metrics: dict, cutoffs: list[float]) -> dict:
    """A base_alpha measurement as one directory's materials cut the image:
    an encode two pools share is measured at the union of their cutoffs, and
    each pool's verdict and report read only the cutoffs its own materials use
    (as a run without the other pool would have measured them)."""
    flips = metrics.get("alpha_flips")
    keys = sorted({f"{float(c):g}" for c in cutoffs}, key=float)
    if not flips or not keys or set(keys) == set(flips) or any(k not in flips for k in keys):
        return metrics
    kept = {k: flips[k] for k in keys}
    levels = len(next(iter(kept.values())))
    out = dict(metrics, cutoffs=[float(k) for k in keys], alpha_flips=kept)
    out["alpha_flip_max"] = [max(per[m] for per in kept.values()) for m in range(levels)]
    out["alpha_flip_mip0"] = out["alpha_flip_max"][0]
    out["alpha_flip_mip2"] = out["alpha_flip_max"][min(2, levels - 1)]
    return out


def _gated(recipe: str, values: list, metrics: dict, last: int | None = None) -> list[tuple[int, object]]:
    """(mip, value) for the mips 1..last (GATED_MIPS[recipe]) that were
    measured and are at least MIN_GATED_MIP pixels on their shorter side."""
    side = min(metrics.get("size") or [1 << 30])
    last = GATED_MIPS[recipe] if last is None else last
    return [(mip, values[mip]) for mip in range(1, min(last, len(values) - 1) + 1)
            if side >> mip >= MIN_GATED_MIP]


def verdict(recipe: str, metrics: dict, floors: dict) -> str:
    if recipe in ("base", "base_alpha"):
        if metrics["psnr"] < floors["base_psnr"]:
            return f"quality: psnr {metrics['psnr']} < {floors['base_psnr']}"
        if floors.get("base_psnr_mips") is not None:
            for mip, value in _gated(recipe, metrics.get("psnr_mips", []), metrics):
                if value < floors["base_psnr_mips"]:
                    return f"quality: psnr {value} < {floors['base_psnr_mips']} at mip {mip}"
    if recipe == "base_alpha":
        flips = metrics.get("alpha_flip_max", [metrics["alpha_flip_mip0"]])
        if flips[0] > floors["alpha_flip_mip0"]:
            return f"quality: alpha flips {flips[0]} > {floors['alpha_flip_mip0']} at mip 0"
        limit = floors.get("alpha_flip_mips")
        if limit is None:
            if metrics["alpha_flip_mip2"] > floors["alpha_flip_mip2"]:
                return f"quality: alpha flips {metrics['alpha_flip_mip2']} > {floors['alpha_flip_mip2']} at mip 2"
        else:
            for mip, value in _gated(recipe, flips, metrics, ALPHA_GATED_MIPS):
                if value > limit:
                    return f"quality: alpha flips {value} > {limit} at mip {mip}"
    if recipe == "normal":
        if metrics["mean_deg"] > floors["normal_mean_deg"] or metrics["p99_deg"] > floors["normal_p99_deg"]:
            return f"quality: normal error {metrics['mean_deg']} / {metrics['p99_deg']} deg"
        if floors.get("normal_mean_deg_mips") is not None:
            for (mip, mean), (_, p99) in zip(_gated(recipe, metrics.get("mean_deg_mips", []), metrics),
                                            _gated(recipe, metrics.get("p99_deg_mips", []), metrics)):
                if mean > floors["normal_mean_deg_mips"] or p99 > floors["normal_p99_deg_mips"]:
                    return f"quality: normal error {mean} / {p99} deg at mip {mip}"
    if recipe in ("orm", "orm_bc7"):
        if min(metrics["psnr_rgb"]) < floors["orm_psnr"]:
            return f"quality: channel psnr {min(metrics['psnr_rgb'])} < {floors['orm_psnr']}"
        if floors.get("orm_psnr_mips") is not None:
            for mip, value in _gated(recipe, metrics.get("psnr_rgb_mips", []), metrics):
                if min(value) < floors["orm_psnr_mips"]:
                    return f"quality: channel psnr {min(value)} < {floors['orm_psnr_mips']} at mip {mip}"
    return ""


# --- the build ------------------------------------------------------------------------

def ensure_ignored(path: Path) -> None:
    """The encode cache must never become tracked content."""
    path.mkdir(parents=True, exist_ok=True)
    probe = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if probe.returncode != 0:
        return  # not inside a git worktree
    ignored = subprocess.run(["git", "-C", str(path), "check-ignore", "-q", str(path / "probe.evt")])
    if ignored.returncode != 0:
        raise BuildError(f"the encode cache {path} is inside a git worktree and not ignored; "
                         "pass --cache outside it or add it to .gitignore")


def _zstd():
    """The zstandard module, or None (then stale measurements re-encode)."""
    try:
        import zstandard
    except ImportError:
        return None
    return zstandard


def cache_key(sha: str, recipe: str, version: str) -> str:
    return f"{sha}.{recipe}.r{RECIPE_VERSION}.{re.sub(r'[^A-Za-z0-9.]+', '_', version)}"


def texture_batches(items: list[dict], limit: int = 128 * 1024**2):
    """Bound the raw DDS files retained before each quality-check pass."""
    from PIL import Image
    batch, size = [], 0
    for item in items:
        with Image.open(item["src"]) as image:
            width, height = image.size
        # Upper bound for BC7/BC5: 16 bytes per 4x4 block, all mip levels,
        # plus the largest DDS header. BC1 uses fewer bytes.
        needed = 148
        while True:
            needed += max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * 16
            if width == height == 1:
                break
            width, height = max(1, width // 2), max(1, height // 2)
        if needed > limit:
            raise BuildError(f"Texture exceeds the runner's DDS scratch budget: {item['src']}")
        item["_dds_bytes"] = needed
        if batch and (size + needed > limit or len(batch) >= 64):
            yield batch
            batch, size = [], 0
        batch.append(item)
        size += needed
    if batch:
        yield batch


def check_cache_budget(cache: Path, limit: int | None, additional: int = 0):
    if limit is not None:
        used = sum(path.stat().st_size for path in cache.rglob("*") if path.is_file())
        if used + additional > limit:
            raise BuildError("Graphics cache and quality scratch would exceed the runner disk budget.")


def build(maps_roots: list[Path], out_root: Path | None, cache: Path, godot: Path, procs: int,
          prune: bool = True, floors: dict | None = None, skip: list[str] | None = None,
          link_output: bool = False, cache_budget_bytes: int | None = None,
          manifests: list[Path] | None = None, scenery_configs: list[Path] | None = None,
          scenery_out_root: Path | None = None, unskip: list[str] | None = None) -> dict:
    if manifests is not None and (out_root is None or any(
            out_root.resolve().is_relative_to(root.resolve()) for root in maps_roots)):
        raise BuildError("scoped preparation requires --out-root outside the source --maps trees; "
                         "a partial scope must not replace a shared source pool's index")
    if scenery_configs and manifests is not None and (
            scenery_out_root is None or scenery_out_root.resolve().is_relative_to(SCENERY_ROOT.resolve())):
        raise BuildError("scoped preparation with --scenery-config requires --scenery-out-root outside "
                         f"{SCENERY_ROOT}; a partial scope must not replace a scenery folder's index")
    if link_output and (out_root is None or out_root.resolve() == cache.resolve()):
        raise BuildError("--link-output requires a separate disposable output directory.")
    if link_output and scenery_configs and scenery_out_root is None:
        raise BuildError("--link-output with --scenery-config requires --scenery-out-root.")
    floors = dict(FLOORS, **(floors or {}))
    started = time.time()
    ensure_ignored(cache)
    version = godot_version(godot)
    scenery = scenery_glbs(scenery_configs or [])
    scenery_dirs = {glb.parent.resolve() for glb in scenery}
    found = inventory(maps_roots, manifests=manifests, scenery=scenery, extract_dir=cache / EMBEDDED_DIR)

    def target_of(source_dir: Path) -> Path:
        if source_dir in scenery_dirs:
            return scenery_target(source_dir, scenery_out_root)
        return sidecar_target(maps_roots, source_dir, out_root)

    targets = {source_dir: target_of(source_dir) for source_dir in {directory for directory, _ in found}}
    unskip = [str(name).replace(chr(92), "/").strip("/") for name in unskip or []]
    # Group by source directory: each gets its own vram/ folder.
    plans: dict[Path, dict] = {}
    for (source_dir, sha), record in sorted(found.items()):
        if not record["path"].is_file():
            continue
        if hashlib.sha256(record["path"].read_bytes()).hexdigest() != sha:
            raise BuildError(f"{record['path']} does not hash to its manifest sha {sha}")
        policy = delivery_policy(record, source_dir, skip, unskip)
        recipe, reason = policy["recipe"], policy["reason"]
        # Exclusions remain explicit, including a copy's inherited caller policy.
        plan = plans.setdefault(source_dir, {"images": {}, "excluded": {}})
        if recipe is None:
            plan["excluded"][sha] = reason
        else:
            plan["images"][sha] = {"recipe": recipe, "path": record["path"], "roles": role_names(record["roles"]),
                                   "cutoffs": sorted(record.get("cutoffs") or []), "dir": source_dir}

    used_keys: set[str] = set()
    counts = {"encoded": 0, "cached": 0, "remeasured": 0, "encodeSeconds": 0.0}

    def cutoffs_of(item: dict) -> list[float]:
        # Only a cutout's alpha is gated, at the thresholds its materials use.
        return [float(c) for c in item.get("cutoffs") or [0.5]] if item["recipe"] == "base_alpha" else []

    def ensure(items: list[dict], _bounded=False) -> None:
        """Encodes and measures every item whose cache entry is missing, and
        measures again (from the cached sidecar) every entry whose numbers an
        older measure() or other alpha cutoffs produced."""
        if link_output and not _bounded:
            # Keep every copy/cutoff of a shared encode in the same batch,
            # preserving the original quality proof while releasing DDS files
            # between batches instead of retaining the entire map set.
            grouped = {}
            for item in items:
                key = (item["sha"], item["recipe"])
                group = grouped.setdefault(key, {"src": str(item["path"]), "items": []})
                group["items"].append(item)
            for batch in texture_batches(list(grouped.values())):
                # Reserve both a worst-case compressed sidecar and its raw DDS
                # until quality measurement removes the latter.
                check_cache_budget(cache, cache_budget_bytes,
                                   2 * sum(group["_dds_bytes"] for group in batch) + 4 * 1024**2)
                ensure([item for group in batch for item in group["items"]], _bounded=True)
                check_cache_budget(cache, cache_budget_bytes)
            return
        jobs, remeasure = [], []
        # Two directories' copies of one image share one encode (the cache key
        # is the source sha and the recipe): it is queued once and measured at
        # every cutoff any copy's materials cut it at; each directory's verdict
        # then reads only its own cutoffs (for_cutoffs).
        distinct: dict[str, dict] = {}
        for item in items:
            key = cache_key(item["sha"], item["recipe"], version)
            item["key"] = key
            used_keys.add(key)
            first = distinct.setdefault(key, dict(item, cutoffs=[]))
            first["cutoffs"] = sorted(set(first["cutoffs"]) | set(cutoffs_of(item)))
        for item in distinct.values():
            key = item["key"]
            meta_path, evt_path = cache / f"{key}.json", cache / f"{key}.evt"
            if meta_path.is_file() and evt_path.is_file():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                quality = meta.get("quality", {})
                if "error" in meta or (quality.get("qualityVersion") == QUALITY_VERSION
                                       and quality.get("cutoffs", []) == cutoffs_of(item)):
                    continue
                if _zstd() is not None:
                    remeasure.append((item, meta))
                    continue
            jobs.append({"sha": item["sha"], "src": str(item["path"]), "recipe": item["recipe"],
                         "evt": str(cache / f"{key}.evt"), "dds": str(cache / "_work" / f"{key}.dds"),
                         "key": key, "cutoffs": cutoffs_of(item)})
        cached = len(distinct) - len(jobs) - len(remeasure)
        counts["cached"] += cached
        counts["encoded"] += len(jobs)
        counts["remeasured"] += len(remeasure)
        shared = f" ({len(distinct)} distinct encodes)" if len(distinct) != len(items) else ""
        log(f"{len(items)} sidecars wanted{shared}: {cached} cached, {len(remeasure)} to measure again, "
            f"{len(jobs)} to encode")
        began = time.time()
        results = run_encoders(godot, cache, jobs, max(1, min(procs, len(jobs))))
        counts["encodeSeconds"] += time.time() - began
        tasks = []
        for job in jobs:
            result = results[(job["sha"], job["recipe"])]
            if "error" in result:
                meta = {"error": result["error"], "width": result.get("width"), "height": result.get("height")}
                (cache / f"{job['key']}.json").write_text(json.dumps(meta), encoding="utf-8")
                Path(job["evt"]).touch()
                continue
            tasks.append((job, {key: result[key] for key in ("format", "width", "height", "mipmaps", "gpuBytes",
                                                            "rawBytes", "fileBytes", "sha256", "encodeMs")}))
        work = cache / "_work"
        work.mkdir(parents=True, exist_ok=True)
        for item, meta in remeasure:
            dds = work / f"{item['key']}.dds"
            data = (cache / f"{item['key']}.evt").read_bytes()
            dds.write_bytes(_zstd().ZstdDecompressor().decompress(data[HEADER.size:],
                                                                  max_output_size=HEADER.unpack_from(data)[1]))
            meta.pop("quality", None)
            tasks.append(({"sha": item["sha"], "src": str(item["path"]), "recipe": item["recipe"], "dds": str(dds),
                           "key": item["key"], "cutoffs": cutoffs_of(item)}, meta))
        if not tasks:
            return
        with futures.ProcessPoolExecutor(max_workers=max(1, min(os.cpu_count() or 4, 16))) as pool:
            quality = list(pool.map(measure, [(job["src"], job["dds"], job["recipe"], meta["format"], meta["width"],
                                               meta["height"], meta["mipmaps"], job["cutoffs"])
                                              for job, meta in tasks], chunksize=4))
        for (job, meta), metrics in zip(tasks, quality):
            meta["quality"] = metrics
            (cache / f"{job['key']}.json").write_text(json.dumps(meta), encoding="utf-8")
            Path(job["dds"]).unlink(missing_ok=True)

    def meta_of(item: dict) -> dict:
        return json.loads((cache / f"{item['key']}.json").read_text(encoding="utf-8"))

    primary = []
    for plan in plans.values():
        for sha, item in plan["images"].items():
            item["sha"] = sha
            primary.append(item)
    ensure(primary)
    # A recipe below its floor gets one second chance where a better format
    # exists for the role: an ORM map whose channels BC1 cannot keep apart is
    # tried as BC7 (2x BC1's size, still a quarter of RGBA8).
    retry = []
    for item in primary:
        meta = meta_of(item)
        if (item["recipe"] in SECOND_CHANCE and "error" not in meta
                and verdict(item["recipe"], meta["quality"], floors)):
            retry.append(dict(item, recipe=SECOND_CHANCE[item["recipe"]], first=item))
    if retry:
        ensure(retry)
        for item in retry:
            if "error" not in meta_of(item) and not verdict(item["recipe"], meta_of(item)["quality"], floors):
                plans[item["dir"]]["images"][item["sha"]] = item

    summary = {"encoder": f"godot {version} editor: Image.compress_from_channels (BPTC cvtt, S3TC etcpak)",
               "encoded": counts["encoded"], "cached": counts["cached"], "remeasured": counts["remeasured"],
               "encodeSeconds": round(counts["encodeSeconds"], 1), "directories": {}}
    # one PSNR per distinct encode: the copies of a shared image in two pools are one encode, and counting each copy
    # would weigh shared images twice in the set-level median (and make it depend on which pools are in the tree)
    base_psnr, psnr_keys = [], set()
    for source_dir, plan in sorted(plans.items()):
        target = targets[source_dir]
        # Recheck after encoding in case an existing stage's directory layout changed.
        target_of(source_dir)
        target.mkdir(parents=True, exist_ok=True)
        index = {"schema": SCHEMA, "recipeVersion": RECIPE_VERSION, "encoder": summary["encoder"],
                 "container": CONTAINER, "images": {}, "excluded": dict(sorted(plan["excluded"].items()))}
        report = {}
        for sha, item in sorted(plan["images"].items()):
            meta = json.loads((cache / f"{item['key']}.json").read_text(encoding="utf-8"))
            if "error" in meta:
                index["excluded"][sha] = meta["error"]
                continue
            quality = for_cutoffs(meta["quality"], cutoffs_of(item)) if item["recipe"] == "base_alpha" \
                else meta["quality"]
            reason = verdict(item["recipe"], quality, floors)
            report[sha] = {"recipe": item["recipe"], "width": meta["width"], **quality}
            if reason:
                index["excluded"][sha] = reason
                continue
            if item["recipe"] in ("base", "base_alpha") and item["key"] not in psnr_keys:
                psnr_keys.add(item["key"])
                base_psnr.append(meta["quality"]["psnr"])
            name = f"{sha}.{item['recipe']}.evt"
            if link_output:
                (target / name).unlink(missing_ok=True)
                os.link(cache / f"{item['key']}.evt", target / name)
            else:
                shutil.copyfile(cache / f"{item['key']}.evt", target / name)
            index["images"][sha] = {"file": name, "recipe": item["recipe"], "format": meta["format"],
                                    "width": meta["width"], "height": meta["height"],
                                    "mipmaps": meta["mipmaps"], "gpuBytes": meta["gpuBytes"],
                                    "rawBytes": meta["rawBytes"], "fileBytes": meta["fileBytes"],
                                    "sha256": meta["sha256"], "roles": item["roles"]}
        index["excluded"] = dict(sorted(index["excluded"].items()))
        wanted = {entry["file"] for entry in index["images"].values()}
        stale = [p for p in target.glob("*.evt") if p.name not in wanted]
        for path in stale:
            path.unlink()
        (target / "index.json").write_text(json.dumps(index, indent=1, sort_keys=False) + "\n",
                                           encoding="utf-8", newline="\n")
        (target / "report.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8", newline="\n")
        reasons: dict[str, int] = {}
        for reason in index["excluded"].values():
            reasons[reason.split(":")[0]] = reasons.get(reason.split(":")[0], 0) + 1
        summary["directories"][str(target)] = {
            "sidecars": len(index["images"]), "excluded": reasons,
            "gpuMiB": round(sum(e["gpuBytes"] for e in index["images"].values()) / 1048576, 1),
            "fileMiB": round(sum(e["fileBytes"] for e in index["images"].values()) / 1048576, 1),
            "staleRemoved": len(stale)}
    if base_psnr:
        base_psnr.sort()
        median = base_psnr[len(base_psnr) // 2]
        summary["basePsnrMedian"] = median
        summary["basePsnrEncodes"] = len(base_psnr)
        # A set-level gate: meaningless on a handful of test images.
        if len(base_psnr) >= 20 and median < floors["base_psnr_median"]:
            raise BuildError(f"median base-colour PSNR {median} is under {floors['base_psnr_median']} dB")
    if prune:
        removed = 0
        for path in cache.glob("*.json"):
            if path.stem not in used_keys:
                path.unlink()
                (cache / f"{path.stem}.evt").unlink(missing_ok=True)
                removed += 1
        summary["pruned"] = removed
        extracted = {record["path"].name for record in found.values()
                     if record["path"].parent == (cache / EMBEDDED_DIR)}
        for path in (cache / EMBEDDED_DIR).glob("*"):
            if path.is_file() and path.name not in extracted:
                path.unlink()
    summary["seconds"] = round(time.time() - started, 1)
    return summary


def sidecar_target(maps_roots: list[Path], source_dir: Path, out_root: Path | None) -> Path:
    boundary = out_root.resolve() if out_root else source_dir.resolve()
    target = (boundary / source_dir.relative_to(common_root(maps_roots, source_dir)) / SIDECAR_DIR
              if out_root else boundary / SIDECAR_DIR)
    if not target.resolve().is_relative_to(boundary):
        raise BuildError(f"resolved sidecar output escapes its destination root: {target}")
    return target


def scenery_target(source_dir: Path, scenery_out_root: Path | None) -> Path:
    """A scenery GLB directory's vram/: beside the GLBs, or below scenery_out_root mirroring SCENERY_ROOT."""
    if scenery_out_root is None:
        return source_dir / SIDECAR_DIR
    boundary = scenery_out_root.resolve()
    try:
        relative = source_dir.resolve().relative_to(SCENERY_ROOT.resolve())
    except ValueError as error:
        raise BuildError(f"scenery directory {source_dir} is outside {SCENERY_ROOT}") from error
    target = boundary / relative / SIDECAR_DIR
    if not target.resolve().is_relative_to(boundary):
        raise BuildError(f"resolved sidecar output escapes its destination root: {target}")
    return target


def common_root(maps_roots: list[Path], source_dir: Path) -> Path:
    return _containing_root([root.resolve() for root in maps_roots], source_dir)


def _containing_root(resolved_roots: list[Path], source_dir: Path) -> Path:
    """Boundary check after canonicalization, without resolving each root per image."""
    for root in resolved_roots:
        try:
            source_dir.relative_to(root)
            return root
        except ValueError:
            continue
    raise BuildError(f"{source_dir} is outside every --maps root")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--maps", type=Path, action="append",
                        help="map tree to scan for world.json (default <repo>/eloria-assets/maps); repeatable")
    parser.add_argument("--manifest", type=Path, action="append", default=[],
                        help="prepare only this manifest's declared scene leaves and prototypes; repeatable; "
                             "requires separate --out-root, with --maps still containing all dependencies")
    parser.add_argument("--scope-group", action="append", default=[],
                        help="select current registry map manifests from a geometry-cache-scope group "
                             "(for example landfall_continent); repeatable; map manifests only")
    parser.add_argument("--out-root", type=Path,
                        help="write <out-root>/<image dir relative to its --maps root>/vram instead of beside the images")
    parser.add_argument("--cache", type=Path, default=REPO / ".vram-encode-cache",
                        help="encode cache, a git-ignored directory (default <repo>/.vram-encode-cache)")
    parser.add_argument("--godot", help="Godot 4.7.2 editor binary (default: ELORIA_GODOT, the checkout's, PATH)")
    parser.add_argument("--procs", type=int, default=max(1, min(8, (os.cpu_count() or 2) // 2)))
    parser.add_argument("--no-prune", action="store_true", help="keep cache entries this run did not use")
    parser.add_argument("--link-output", action="store_true", help="hard-link sidecars into a disposable runner stage")
    parser.add_argument("--cache-budget-bytes", type=int, help="runner allowance for cached encodes and quality scratch")
    parser.add_argument("--floors", help="JSON object overriding quality floors (tests)")
    parser.add_argument("--skip-dir", action="append", default=[],
                        help="image directory (relative to a --maps root) to leave un-encoded; repeatable. "
                             "A pool whose images the client can afford to decode costs download size "
                             "it does not need to spend.")
    parser.add_argument("--unskip-map", action="append", default=[],
                        help="map directory (relative to a --maps root, e.g. continent-v2/landfall_town) whose "
                             "images are planned even inside a --skip-dir directory; repeatable")
    parser.add_argument("--scenery-config", type=Path, action="append", default=[],
                        help="scenery config (an \"assets\" object of res:// GLB paths, e.g. "
                             "godot-client/data/world/town-scenery.json) whose GLBs' embedded images get sidecars "
                             "in the vram/ folder of each GLB's directory; repeatable")
    parser.add_argument("--scenery-out-root", type=Path,
                        help="write the scenery sidecars to <root>/<GLB dir relative to godot-client/assets/world>"
                             "/vram instead of beside the GLBs (required with --manifest/--scope-group)")
    options = parser.parse_args()
    try:
        manifests = [path.resolve() for path in options.manifest] + scope_group_manifests(options.scope_group)
        summary = build([p.resolve() for p in (options.maps or [REPO / "eloria-assets" / "maps"])],
                        options.out_root.resolve() if options.out_root else None,
                        options.cache.resolve(), find_godot(options.godot), options.procs,
                        prune=not options.no_prune, floors=json.loads(options.floors) if options.floors else None,
                        skip=options.skip_dir, link_output=options.link_output, cache_budget_bytes=options.cache_budget_bytes,
                        manifests=manifests if options.manifest or options.scope_group else None,
                        scenery_configs=[path.resolve() for path in options.scenery_config],
                        scenery_out_root=options.scenery_out_root.resolve() if options.scenery_out_root else None,
                        unskip=options.unskip_map)
    except BuildError as error:
        log(f"FAILED: {error}")
        return 1
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
