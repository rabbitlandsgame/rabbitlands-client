#!/usr/bin/env python3
"""Strip the RL hair and beard GLBs' embedded copies of the RL head maps for a package (AT-C0).

Added 2026-11-03 (wave 2, actor textures, chunk C0).

    python godot-client/tools/strip_rl_head_images.py strip APP_DIR BUILD_DIR [--receipt FILE]
    python godot-client/tools/strip_rl_head_images.py strip APP_DIR BUILD_DIR --dry-run

package_client.py runs it on the disposable build tree's godot-client/ before
the import (strip_rl_head_stage), the first of the package-time actor
transforms (wave-2 schedule 1.1 #6: RL image strip, attribute quantisation,
import, actor geometry cook, actor VRAM sidecars, export), so every later step
and the loose staging see the stripped bytes. The receipt is the build's
logs/rl-head-strip.json; after the export, check_rl_head_strip_pack proves
every removed copy's map is in the PCK. The command line strips an exported
stage's app/ instead and checks its PCK first. A developer checkout is never
touched, and files are replaced, never written in place, so a hard link (a
runner's source or a benchmark stage) never writes through.

Why. Each RL hairstyle and beard (app/assets/actors/native/rl_heads/{hair,beards})
carries its strand map as an embedded PNG, byte for byte the map that also ships
in the PCK under rl_head_textures/ (LOADED_IMAGE_FOLDERS). The game never samples
the embedded copy: RLHeadRig._assign_materials replaces every surface whose
material name the RL contract knows with RLHeadLibrary.material(), a shared
ShaderMaterial that load()s the imported map. GLTFDocument still decodes each
embedded PNG and uploads it as an RGBA8 texture with no mips, 4-32 MiB per drawn
style, up to about 37 ms of PNG decode each. On develop content (2026-11-03)
that is 61 images (84.1 MB of PNG, decoded one by one) in 42 of the 44 files,
stored as 68.7 MB: some files keep two images on one bufferView.

An embedded image is removed only when all of these hold (anything else is kept
and reported with its reason):

  1. its bytes' SHA-256 equals a map tracked under rl_head_textures/ at the
     packaged commit (that folder ships in the PCK);
  2. every material that samples it names, in its extras `texture`, a map with
     those same bytes;
  3. every such material is in the RL material contract: the names
     RLHeadLibrary.material() replaces, read from rl_head_library.gd at the
     packaged commit (MATERIAL_SHADERS, and MATERIAL_ROLES mapped onto it, each
     drawn by a SHADERS key). Names are matched exactly, as the runtime looks
     them up: a `_lod<k>` material the library does not list keeps its imported
     material, so its image stays;
  4. nothing else references the image or its textures (no extension, no node,
     no extras), and the file is a plain single-buffer GLB without extensions.

The build fails when an image would be removed while the map its material
names is not in the PCK as an import with every product it names.

Removal deletes the texture-info entries that sampled the image, its textures,
the samplers only they used and the image's bufferViews, re-indexes what stays,
and repacks the BIN chunk with 4-byte alignment. Every accessor's bytes, every
kept image's bytes and every other JSON field (materials and their extras,
alphaMode, nodes, meshes, skins, animations, scenes, asset) are then compared
with the original, on the written bytes re-read; any difference fails the
build. Nothing pins the RL GLB hashes in a catalog: the runtime hashes the
staged file it reads (CreaturePayload.source_sha256).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
from pathlib import Path, PurePosixPath

GLB_MAGIC = 0x46546C67  # "glTF"
JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942
# Folders under the stage's app/ (and the build tree's godot-client/) whose
# GLBs are stripped, non-recursively: RLHeadLibrary reads HAIR_DIR + name and
# BEARD_DIR + name only.
RL_GLB_DIRS = ("assets/actors/native/rl_heads/hair", "assets/actors/native/rl_heads/beards")
MAP_DIR = "assets/actors/native/rl_head_textures"
LIBRARY = "src/actors/rl_head/rl_head_library.gd"
MAP_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
RECEIPT_SCHEMA = 1


class StripError(RuntimeError):
    """The stage cannot be stripped safely; the package must not be built as it is."""


# --- the RL material contract -------------------------------------------------

def _gd_dictionary(text: str, name: str) -> str:
    """The body of `const <name> := { ... }` in GDScript source, braces excluded.

    `#` comments are left out of the body and braces inside strings or comments
    do not count, as GDScript reads them: a commented-out entry is not in the
    contract (a strip that counted it would leave that surface untextured).
    """
    match = re.search(r"^const\s+" + re.escape(name) + r"\s*(?::[^=]*)?:?=\s*\{", text, re.M)
    if not match:
        raise StripError(f"{LIBRARY}: const {name} not found; the RL material contract cannot be read")
    depth, index, body = 1, match.end(), []
    while index < len(text):
        char = text[index]
        if char == "#":
            end = text.find("\n", index)
            index = len(text) if end < 0 else end
            continue
        if char in "\"'":
            end = index + 1
            while end < len(text) and text[end] != char:
                if text[end] == "\n":
                    raise StripError(f"{LIBRARY}: const {name} has a string this tool cannot read")
                end += 2 if text[end] == "\\" else 1
            body.append(text[index:end + 1])
            index = end + 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return "".join(body)
        body.append(char)
        index += 1
    raise StripError(f"{LIBRARY}: const {name} is not closed")


def _gd_pairs(body: str, name: str, value: str) -> dict[str, str]:
    """`"key": <value>` pairs of a dictionary body; every line holding a key must parse."""
    if re.search(r"""[&^]["']""", body):
        # StringName/NodePath keys are not the String names material() looks up.
        raise StripError(f"{LIBRARY}: const {name} uses StringName or NodePath literals; "
                         "update strip_rl_head_images.py with the contract")
    pattern = re.compile(r'"([^"\\]+)"\s*:\s*' + value)
    pairs = {m.group(1): (m.group(2) if m.lastindex and m.lastindex >= 2 else "") for m in pattern.finditer(body)}
    keys = re.findall(r'"([^"\\]+)"\s*:', body)
    if not pairs or sorted(set(keys)) != sorted(pairs):
        raise StripError(f"{LIBRARY}: const {name} has entries this tool cannot read ({sorted(set(keys) - set(pairs))}); "
                         "update strip_rl_head_images.py with the contract")
    return pairs


def read_contract(library_text: str) -> dict[str, str]:
    """{material name: shader kind} for every name RLHeadLibrary.material() replaces.

    material() looks a name up exactly: role = MATERIAL_ROLES.get(name, name),
    kind = MATERIAL_SHADERS.get(role); an empty kind returns null and the
    surface keeps its imported material (RLHeadRig._assign_materials).
    """
    shaders = _gd_pairs(_gd_dictionary(library_text, "SHADERS"), "SHADERS", r"(preload)\(")
    roles_to_kind = _gd_pairs(_gd_dictionary(library_text, "MATERIAL_SHADERS"), "MATERIAL_SHADERS", r'"([^"\\]+)"')
    explicit = _gd_pairs(_gd_dictionary(library_text, "MATERIAL_ROLES"), "MATERIAL_ROLES", r'"([^"\\]+)"')
    unknown = sorted(kind for kind in roles_to_kind.values() if kind not in shaders)
    if unknown:
        raise StripError(f"{LIBRARY}: MATERIAL_SHADERS draws with {unknown}, which SHADERS does not hold")
    contract = {name: roles_to_kind[name] for name in roles_to_kind if name not in explicit}
    for name, role in explicit.items():
        if role in roles_to_kind:
            contract[name] = roles_to_kind[role]
    return dict(sorted(contract.items()))


# --- GLB bytes -------------------------------------------------------------------

def read_glb(data: bytes) -> tuple[dict, bytes]:
    """(JSON document, BIN chunk) of a GLB; refuses anything but JSON then at most one BIN chunk."""
    if len(data) < 20:
        raise ValueError("too short for a GLB")
    magic, version, length = struct.unpack_from("<III", data, 0)
    if magic != GLB_MAGIC or version != 2 or length != len(data):
        raise ValueError("not a version 2 GLB of its stated length")
    json_length, json_type = struct.unpack_from("<II", data, 12)
    if json_type != JSON_CHUNK or 20 + json_length > len(data):
        raise ValueError("first chunk is not JSON")
    document = json.loads(data[20:20 + json_length].decode("utf-8"))
    if not isinstance(document, dict):
        raise ValueError("the JSON chunk is not an object")
    offset = 20 + json_length
    binary = b""
    if offset < len(data):
        if offset + 8 > len(data):
            raise ValueError("truncated chunk header")
        bin_length, bin_type = struct.unpack_from("<II", data, offset)
        if bin_type != BIN_CHUNK or offset + 8 + bin_length > len(data):
            raise ValueError("second chunk is not BIN")
        binary = data[offset + 8:offset + 8 + bin_length]
        if offset + 8 + bin_length != len(data):
            raise ValueError("chunks after BIN")
    return document, binary


def write_glb(document: dict, binary: bytes) -> bytes:
    payload = json.dumps(document, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    payload += b" " * ((-len(payload)) % 4)
    chunks = struct.pack("<II", len(payload), JSON_CHUNK) + payload
    if binary:
        padded = binary + b"\0" * ((-len(binary)) % 4)
        chunks += struct.pack("<II", len(padded), BIN_CHUNK) + padded
    return struct.pack("<III", GLB_MAGIC, 2, 12 + len(chunks)) + chunks


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _view_bytes(document: dict, binary: bytes, index: int) -> bytes:
    view = document["bufferViews"][index]
    start = view.get("byteOffset", 0)
    return binary[start:start + view["byteLength"]]


COMPONENT_BYTES = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
TYPE_COUNT = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}


def _accessor_bytes(document: dict, binary: bytes, index: int) -> tuple[bytes, ...]:
    """The bytes an accessor reads: its elements, and a sparse block's indices and values."""
    accessor = document["accessors"][index]
    element = COMPONENT_BYTES[accessor["componentType"]] * TYPE_COUNT[accessor["type"]]
    parts: list[bytes] = []
    if "bufferView" in accessor:
        view = document["bufferViews"][accessor["bufferView"]]
        stride = view.get("byteStride", element)
        start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
        count = accessor["count"]
        data = binary[start:start + (stride * (count - 1) + element if count else 0)]
        if stride != element:  # only the elements: stride padding is not read
            data = b"".join(data[i * stride:i * stride + element] for i in range(count))
        parts.append(data)
    sparse = accessor.get("sparse")
    if sparse:
        count = sparse["count"]
        for key, size in (("indices", COMPONENT_BYTES[sparse["indices"].get("componentType", 5125)]),
                          ("values", element)):
            block = sparse[key]
            start = document["bufferViews"][block["bufferView"]].get("byteOffset", 0) + block.get("byteOffset", 0)
            parts.append(binary[start:start + size * count])
    return tuple(parts)


# --- references ----------------------------------------------------------------------

def _texture_infos(value, path: tuple = ()):
    """(path, textureInfo) for every `...Texture`/`...texture` object with an integer index under `value`."""
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(child, dict) and key.lower().endswith("texture") and isinstance(child.get("index"), int):
                yield path + (key,), child
            yield from _texture_infos(child, path + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _texture_infos(child, path + (index,))


def _keyed(value, name: str, path: tuple = ()):
    """(path, value) of every `name` key under `value`."""
    if isinstance(value, dict):
        for key, child in value.items():
            if key == name:
                yield path + (key,), child
            yield from _keyed(child, name, path + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _keyed(child, name, path + (index,))


def _structure_problem(document: dict, binary: bytes) -> str | None:
    """Why this file is not a GLB the strip can rewrite safely, or None."""
    if document.get("extensionsUsed") or document.get("extensionsRequired") or "extensions" in document:
        return "the file uses glTF extensions"
    for path, _ in _keyed(document, "extensions"):
        return f"an extension at {'/'.join(map(str, path[:-1]))}"
    buffers = document.get("buffers", [])
    if len(buffers) > 1 or any("uri" in b for b in buffers):
        return "more than the one embedded buffer"
    if buffers and buffers[0].get("byteLength", 0) > len(binary):
        return "the BIN chunk is shorter than its buffer"
    for view in document.get("bufferViews", []):
        if view.get("buffer", 0) != 0:
            return "a bufferView outside the embedded buffer"
    for path, _ in _keyed(document, "bufferView"):
        if path[0] not in ("accessors", "images"):
            return f"a bufferView named at {'/'.join(map(str, path))}"
    return None


def plan_document(document: dict, binary: bytes, maps: dict[str, list[str]],
                  contract: dict[str, str]) -> tuple[dict[int, dict], dict[int, dict]]:
    """({image: why it goes}, {image: why it stays}) for one GLB's embedded images.

    `maps` is {sha256: [map file names with those bytes]} of the tracked
    rl_head_textures images; `contract` comes from read_contract.
    """
    images = document.get("images", [])
    remove: dict[int, dict] = {}
    keep: dict[int, dict] = {}
    if not images:
        return remove, keep
    problem = _structure_problem(document, binary)
    textures = document.get("textures", [])
    materials = document.get("materials", [])
    # Who samples each texture: material texture-infos outside extras, and
    # anything else that names a texture (extras, nodes, ...).
    material_uses: dict[int, list[tuple[int, tuple]]] = {}
    other_uses: dict[int, list[str]] = {}
    for path, info in _texture_infos(document):
        index = info["index"]
        if path[0] == "materials" and "extras" not in path:
            material_uses.setdefault(index, []).append((path[1], path[2:]))
        else:
            other_uses.setdefault(index, []).append("/".join(map(str, path)))
    for image_index, image in enumerate(images):
        record: dict = {"image": image_index}
        if "bufferView" not in image:
            keep[image_index] = {**record, "reason": "not embedded (uri)"}
            continue
        if problem:
            keep[image_index] = {**record, "reason": problem}
            continue
        data = _view_bytes(document, binary, image["bufferView"])
        sha = _sha(data)
        record.update({"sha256": sha, "bytes": len(data)})
        names = maps.get(sha)
        if not names:
            keep[image_index] = {**record, "reason": "no tracked rl_head_textures map has these bytes"}
            continue
        record["maps"] = sorted(names)
        own = [t for t, texture in enumerate(textures) if texture.get("source") == image_index]
        reasons: list[str] = []
        used_by: list[str] = []
        named: set[str] = set()
        # Another image on the same view is fine (strip_document keeps a view a
        # kept image names); accessor data on it is not.
        if any(value == image["bufferView"] for path, value in _keyed(document, "bufferView")
               if path[0] == "accessors"):
            reasons.append("its bufferView holds accessor data")
        for texture_index in own:
            texture = textures[texture_index]
            if set(texture) - {"source", "sampler", "name", "extras"} or texture.get("extras"):
                reasons.append(f"texture {texture_index} carries more than source/sampler/name")
            for where in other_uses.get(texture_index, []):
                reasons.append(f"texture {texture_index} is referenced at {where}")
            for material_index, _ in material_uses.get(texture_index, []):
                material = materials[material_index] if material_index < len(materials) else {}
                name = str(material.get("name", ""))
                extras = material.get("extras") if isinstance(material.get("extras"), dict) else {}
                texture_name = extras.get("texture")
                if name not in contract:
                    reasons.append(f"material {material_index} {name!r} is outside the RL material contract")
                elif not isinstance(texture_name, str) or texture_name not in names:
                    reasons.append(f"material {material_index} {name!r} names {texture_name!r} in extras.texture, "
                                   f"not a map with these bytes ({', '.join(sorted(names))})")
                else:
                    named.add(texture_name)
                    used_by.append(name)
        if not used_by and not reasons:
            reasons.append("no material samples it")
        if reasons:
            keep[image_index] = {**record, "reason": "; ".join(dict.fromkeys(reasons))}
            continue
        remove[image_index] = {**record, "textures": own, "materials": sorted(set(used_by)), "named": sorted(named)}
    return remove, keep


# --- rewriting ------------------------------------------------------------------------

def _gone_views(document: dict, remove: set[int]) -> set[int]:
    """The bufferViews only the `remove` images name."""
    removed = {document["images"][i]["bufferView"] for i in remove}
    named_elsewhere = {value for path, value in _keyed(document, "bufferView")
                       if not (path[0] == "images" and path[1] in remove)}
    return removed - named_elsewhere


def strip_document(document: dict, binary: bytes, remove: set[int]) -> tuple[dict, bytes]:
    """A copy of the document without `remove` (image indices), their textures, the
    texture-infos sampling them, samplers only they used and their bufferViews."""
    doc = json.loads(json.dumps(document))
    images = doc.get("images", [])
    textures = doc.get("textures", [])
    gone_textures = {t for t, texture in enumerate(textures) if texture.get("source") in remove}
    kept_textures = [t for t in range(len(textures)) if t not in gone_textures]
    texture_map = {old: new for new, old in enumerate(kept_textures)}
    # Texture-infos: drop the removed ones, re-index the rest (materials only;
    # plan_document refused images whose textures anything else names).
    for material in doc.get("materials", []):
        infos = [(path, info) for path, info in _texture_infos({k: v for k, v in material.items() if k != "extras"})]
        for path, info in infos:
            parent = material
            for key in path[:-1]:
                parent = parent[key]
            if info["index"] in gone_textures:
                # An emptied pbrMetallicRoughness stays as {}: the defaults, as before.
                del parent[path[-1]]
            else:
                info["index"] = texture_map[info["index"]]
    samplers = doc.get("samplers", [])
    used_samplers_before = {t.get("sampler") for t in textures if "sampler" in t}
    used_samplers_after = {textures[t].get("sampler") for t in kept_textures if "sampler" in textures[t]}
    gone_samplers = {s for s in used_samplers_before - used_samplers_after if isinstance(s, int)}
    kept_samplers = [s for s in range(len(samplers)) if s not in gone_samplers]
    sampler_map = {old: new for new, old in enumerate(kept_samplers)}
    kept_images = [i for i in range(len(images)) if i not in remove]
    image_map = {old: new for new, old in enumerate(kept_images)}
    new_textures = []
    for old in kept_textures:
        texture = textures[old]
        if "source" in texture:
            texture["source"] = image_map[texture["source"]]
        if "sampler" in texture:
            texture["sampler"] = sampler_map[texture["sampler"]]
        new_textures.append(texture)
    # bufferViews: those only removed images name go; every other view stays,
    # including views nothing names (not this tool's business).
    views = doc.get("bufferViews", [])
    gone_views = _gone_views(doc, remove)
    kept_views = [v for v in range(len(views)) if v not in gone_views]
    view_map = {old: new for new, old in enumerate(kept_views)}
    packed = bytearray()
    new_views = []
    for old in kept_views:
        packed.extend(b"\0" * ((-len(packed)) % 4))
        view = dict(views[old], byteOffset=len(packed))
        packed.extend(_view_bytes(document, binary, old))
        new_views.append(view)
    packed.extend(b"\0" * ((-len(packed)) % 4))
    for path, value in list(_keyed(doc, "bufferView")):
        if path[0] == "images" and path[1] in remove:
            continue
        parent = doc
        for key in path[:-1]:
            parent = parent[key]
        parent["bufferView"] = view_map[value]
    for key, values in (("images", [images[i] for i in kept_images]), ("textures", new_textures),
                        ("samplers", [samplers[s] for s in kept_samplers]), ("bufferViews", new_views)):
        if values:
            doc[key] = values
        else:
            doc.pop(key, None)
    if doc.get("buffers"):
        doc["buffers"][0]["byteLength"] = len(packed)
    return doc, bytes(packed)


def _without_texture_data(document: dict) -> dict:
    """The document with what a strip may change taken out, for comparison."""
    doc = json.loads(json.dumps(document))
    for key in ("images", "textures", "samplers", "bufferViews", "buffers"):
        doc.pop(key, None)
    for material in doc.get("materials", []):
        for path, _ in list(_texture_infos({k: v for k, v in material.items() if k != "extras"})):
            parent = material
            for key in path[:-1]:
                parent = parent[key]
            parent.pop(path[-1], None)
    for accessor in doc.get("accessors", []):
        accessor.pop("bufferView", None)
        for block in ("indices", "values"):
            if isinstance(accessor.get("sparse", {}).get(block), dict):
                accessor["sparse"][block].pop("bufferView", None)
    return doc


def _texture_identity(document: dict, binary: bytes, index: int) -> tuple:
    texture = document["textures"][index]
    image = document["images"][texture["source"]] if "source" in texture else {}
    data = _view_bytes(document, binary, image["bufferView"]) if "bufferView" in image else image.get("uri")
    sampler = document.get("samplers", [])[texture["sampler"]] if "sampler" in texture else None
    meta = {k: v for k, v in image.items() if k != "bufferView"}
    return (data, json.dumps(meta, sort_keys=True), json.dumps(sampler, sort_keys=True),
            json.dumps({k: v for k, v in texture.items() if k not in ("source", "sampler")}, sort_keys=True))


def verify(original: dict, original_bin: bytes, stripped: dict, stripped_bin: bytes, remove: set[int]) -> None:
    """Raise StripError unless `stripped` is `original` minus exactly the removed images' data."""
    if _without_texture_data(original) != _without_texture_data(stripped):
        raise StripError("a JSON field other than the removed images' texture data changed")
    accessors = original.get("accessors", [])
    if len(accessors) != len(stripped.get("accessors", [])):
        raise StripError("the accessor count changed")
    for index in range(len(accessors)):
        if _accessor_bytes(original, original_bin, index) != _accessor_bytes(stripped, stripped_bin, index):
            raise StripError(f"accessor {index}'s bytes changed")
    kept = [i for i in range(len(original.get("images", []))) if i not in remove]
    new_images = stripped.get("images", [])
    if len(kept) != len(new_images):
        raise StripError("the kept image count is wrong")
    for new, old in enumerate(kept):
        before, after = original["images"][old], new_images[new]
        if {k: v for k, v in before.items() if k != "bufferView"} != {k: v for k, v in after.items() if k != "bufferView"}:
            raise StripError(f"image {old}'s fields changed")
        if "bufferView" in before and _view_bytes(original, original_bin, before["bufferView"]) \
                != _view_bytes(stripped, stripped_bin, after["bufferView"]):
            raise StripError(f"image {old}'s bytes changed")
    gone = {t for t, texture in enumerate(original.get("textures", [])) if texture.get("source") in remove}
    for material_index, material in enumerate(original.get("materials", [])):
        before = dict(_texture_infos({k: v for k, v in material.items() if k != "extras"}))
        after = dict(_texture_infos({k: v for k, v in stripped["materials"][material_index].items() if k != "extras"}))
        expected = {path for path, info in before.items() if info["index"] not in gone}
        if set(after) != expected:
            raise StripError(f"material {material_index}'s texture slots are not the expected ones")
        for path in expected:
            old, new = before[path], after[path]
            if {k: v for k, v in old.items() if k != "index"} != {k: v for k, v in new.items() if k != "index"} \
                    or _texture_identity(original, original_bin, old["index"]) \
                    != _texture_identity(stripped, stripped_bin, new["index"]):
                raise StripError(f"material {material_index} samples a different texture at {'/'.join(map(str, path))}")
    for view in stripped.get("bufferViews", []):
        if view.get("byteOffset", 0) % 4 or view.get("byteOffset", 0) + view["byteLength"] > len(stripped_bin):
            raise StripError("a repacked bufferView is misaligned or out of range")
    if stripped.get("buffers") and stripped["buffers"][0]["byteLength"] != len(stripped_bin):
        raise StripError("the buffer length does not match the repacked BIN chunk")


def strip_glb(data: bytes, maps: dict[str, list[str]], contract: dict[str, str]) -> tuple[bytes | None, dict]:
    """(new GLB bytes or None when nothing goes, {removed, kept}) for one GLB's bytes."""
    try:
        document, binary = read_glb(data)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return None, {"removed": [], "kept": [{"reason": f"unreadable GLB: {error}"}]}
    remove, keep = plan_document(document, binary, maps, contract)
    result = {"removed": [remove[i] for i in sorted(remove)], "kept": [keep[i] for i in sorted(keep)]}
    if not remove:
        return None, result
    # Two images may share one bufferView (an exporter's dedupe): each is
    # decoded and uploaded on its own at runtime, but its bytes are stored once.
    result["embedded_bytes_removed"] = sum(document["bufferViews"][v]["byteLength"]
                                           for v in _gone_views(document, set(remove)))
    stripped, stripped_bin = strip_document(document, binary, set(remove))
    try:
        written = write_glb(stripped, stripped_bin)
    except ValueError as error:  # a NaN/Infinity the original JSON spelled non-standardly
        return None, {"removed": [], "kept": [{**remove[i], "reason": f"JSON not rewritable: {error}"}
                                             for i in sorted(remove)] + result["kept"]}
    reread, reread_bin = read_glb(written)
    verify(document, binary, reread, reread_bin, set(remove))
    return written, result


# --- the stage ------------------------------------------------------------------------

def tracked_maps(build_dir: Path) -> dict[str, list[str]]:
    """{sha256: [file names]} of the images tracked under rl_head_textures/ at the build tree's commit."""
    folder = "godot-client/" + MAP_DIR
    listing = subprocess.run(["git", "-C", str(build_dir), "ls-files", "-z", "--", folder],
                             check=True, capture_output=True).stdout.decode("utf-8")
    maps: dict[str, list[str]] = {}
    for relative in filter(None, listing.split("\0")):
        path = PurePosixPath(relative)
        if path.parent.as_posix() == folder and path.suffix.lower() in MAP_SUFFIXES:
            maps.setdefault(_sha((build_dir / relative).read_bytes()), []).append(path.name)
    return maps


def _replace(target: Path, data: bytes) -> None:
    """Write a new file over `target`: a staged hard link to the build tree is
    unlinked by the rename, so the build tree's file never changes."""
    temporary = target.with_name(target.name + ".rl-strip.tmp")
    temporary.write_bytes(data)
    os.replace(temporary, target)


def strip_stage(app_dir: Path, build_dir: Path, *, receipt: Path | None = None, pck_has=None,
                budget=None, dry_run: bool = False, maps: dict[str, list[str]] | None = None,
                contract: dict[str, str] | None = None, log=None) -> dict:
    """Strip every RL hair/beard GLB under `app_dir`; returns (and writes) the receipt.

    `app_dir` holds assets/ as the game reads it: a stage's app/, or the build
    tree's godot-client/ before the import (package_client).
    `pck_has(local_path)` says whether a map ("assets/actors/native/rl_head_textures/x.png")
    is (or, before the export, will be) in the PCK as a complete import; it is
    required unless `dry_run`.
    `budget(phase, additional_bytes)` is the runner's storage check: replacing a
    hard-linked copy costs its new size in fresh disk.
    """
    if pck_has is None and not dry_run:
        raise StripError("the RL maps' PCK copies must be checked before their embedded copies are removed")
    if contract is None:
        contract = read_contract((build_dir / "godot-client" / LIBRARY).read_text(encoding="utf-8"))
    if maps is None:
        maps = tracked_maps(build_dir)
    files: list[dict] = []
    writes: list[tuple[Path, bytes]] = []
    missing: list[str] = []
    for folder in RL_GLB_DIRS:
        for path in sorted((app_dir / folder).glob("*.glb")):
            if not path.is_file():
                continue
            data = path.read_bytes()
            new, result = strip_glb(data, maps, contract)
            row = {"path": path.relative_to(app_dir).as_posix(),
                   "before": {"sha256": _sha(data), "bytes": len(data)},
                   "after": {"sha256": _sha(new), "bytes": len(new)} if new is not None else None, **result}
            files.append(row)
            if new is None:
                continue
            for removed in result["removed"]:
                for name in removed["named"]:
                    if pck_has is not None and not pck_has(f"{MAP_DIR}/{name}"):
                        missing.append(f"{row['path']} image {removed['image']} -> {MAP_DIR}/{name}")
            writes.append((path, new))
    if missing:
        raise StripError(f"{len(missing)} RL maps would lose their only shipped copy (not imported in the PCK):\n  "
                         + "\n  ".join(sorted(set(missing))[:40]))
    shared = sum(len(new) for path, new in writes if path.stat().st_nlink > 1)
    if budget and writes and not dry_run:
        budget("before the RL head image strip", shared)
    if not dry_run:
        for path, new in writes:
            _replace(path, new)
    removed = [image for row in files for image in row["removed"]]
    kept = [image for row in files for image in row["kept"]]
    totals = {"files": len(files), "changed": len(writes), "images_removed": len(removed),
              "image_bytes_removed": sum(image["bytes"] for image in removed),
              "embedded_bytes_removed": sum(row.get("embedded_bytes_removed", 0) for row in files),
              "bytes_before": sum(row["before"]["bytes"] for row in files),
              "bytes_after": sum((row["after"] or row["before"])["bytes"] for row in files),
              "images_kept": len(kept), "dry_run": dry_run}
    totals["bytes_removed"] = totals["bytes_before"] - totals["bytes_after"]
    document = {"schema": RECEIPT_SCHEMA, "tool": "tools/strip_rl_head_images.py", "contract": contract,
                "totals": totals, "files": files}
    if receipt is not None:
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    (log or print)(f"{'would strip' if dry_run else 'stripped'} {len(removed)} embedded RL head map copies "
        f"({totals['image_bytes_removed'] / 1e6:.1f} MB of images, {totals['bytes_removed'] / 1e6:.1f} MB of files) "
        f"from {len(writes)} of {len(files)} RL hair and beard GLBs; "
        f"{len(kept)} images kept" + (f" (see {receipt.name})" if receipt is not None and kept else ""))
    return document


def _pck_checker(pck: Path, project: Path):
    """pck_has for the command line: the packager's PCK reader and import products."""
    import package_client  # imported here only: package_client imports this module

    packed = package_client.pck_paths(pck)

    def pck_has(local: str) -> bool:
        sidecar = project / (local + ".import")
        products = package_client.exported_import_products(sidecar) if sidecar.is_file() else []
        return local + ".import" in packed and bool(products) and all(p in packed for p in products)
    return pck_has


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    strip = commands.add_parser("strip", help="strip a stage's RL hair and beard GLBs in place")
    strip.add_argument("app_dir", type=Path, help="the stage's app/ folder (with RabbitLands.pck)")
    strip.add_argument("build_dir", type=Path, help="the build worktree at the packaged commit")
    strip.add_argument("--receipt", type=Path, help="where to write the JSON receipt")
    strip.add_argument("--dry-run", action="store_true", help="report only; write no GLB (no PCK needed)")
    options = parser.parse_args(argv)
    checker = None
    if not options.dry_run:
        pck = options.app_dir / "RabbitLands.pck"
        if not pck.is_file():
            parser.error(f"{pck} is missing: the maps' PCK copies cannot be checked (use --dry-run to report only)")
        checker = _pck_checker(pck, options.build_dir / "godot-client")
    try:
        strip_stage(options.app_dir, options.build_dir, receipt=options.receipt, pck_has=checker,
                    dry_run=options.dry_run)
    except StripError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
