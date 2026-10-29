#!/usr/bin/env python3
"""Publish a map's repeated prop meshes once, and let every package name them.

Added 2026-10-13 for Eloria Client. Design: work-output/shared-prop-library-2026-10-13/DESIGN.md

    python eloria-assets/tools/shared_meshes.py --scan                 # what is duplicated
    python eloria-assets/tools/shared_meshes.py --apply --sets all     # externalise
    python eloria-assets/tools/shared_meshes.py --reconcile            # hashes back in step

2,053 MB of the shipped map geometry is byte-identical to geometry in another
map file: the same kit prop baked once per placement. Inside one file glTF
already shares a mesh across nodes (and the loader walks its collision shape
once and batches its instances), so the waste is entirely between files, where
glTF has no way to reference another file's mesh.

This tool is a post-bake pass over finished packages: the bake families
(continent-v2's publish_client.py, the nymara region builders,
build_four_gates.py) are unchanged in how they bake, and call publish_finish.py
afterwards to run this over what they wrote - which is the only thing that
keeps a republished map from arriving with every prop copied again. Running
this tool over the whole tree stays the way to catch what a scoped pass could
not see. It reads a package's GLBs, moves every mesh that appears in two or
more files into one content-addressed prototype file, and leaves the placement
behind as a node with the same name and transform:

    maps/_shared/meshes/<sha256>.glb     one prototype: its mesh, materials, images
    maps/_shared/meshes/index.json       sha -> {bytes, primitives, files, materials}

    chunk world.glb   node {"name": <unchanged>, "matrix": ..,
                            "extras": {"eloria": {"prototype": "<sha>"}}}  and no mesh
    chunk world.json  "externalMeshes": {"<relative uri>": "<sha256 of that file>"}

The name is what makes this safe: collision.nodeNames, navigation's surface
prefixes, the Walk_/Terrain_/Water_ conventions, the object material catalog,
the look pass and the lighting markers are all keyed on node names, so a
placement that keeps its name keeps every contract it had.

The prototype hash covers geometry and appearance only - accessor bytes,
primitive and material definitions, image bytes - and never a placement's
transform, node name or instance extras. Moving a tree therefore republishes
one chunk and leaves the library (and every other package's digest) alone.

Shared prototypes are immutable at runtime: the client's material passes must
not write to a pooled mesh or its materials (see the design, Client).

A placement without a mesh is also invisible to anything that walks
`node["mesh"]`, which is most of the Python that reads a finished package - the
continent audit's deck heights among them. `inline_prototypes` here is what the
readers use to see a package whole; `glb_reader.load` calls it, so a tool built
on the toolkit needs no change.
"""
from __future__ import annotations

import argparse
import base64
import functools
import hashlib
import json
import os
import struct
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# ELORIA_MAPS_ROOT lets the tests run the whole pass over a sandbox copy.
MAPS = Path(os.environ.get("ELORIA_MAPS_ROOT", REPO / "eloria-assets" / "maps"))
POOL = MAPS / "_shared" / "meshes"
INDEX = POOL / "index.json"
MANIFEST_KEY = "externalMeshes"
EXTRAS_KEY = "eloria"
PROTOTYPE_FIELD = "prototype"
SCHEMA = "eloria-shared-meshes-v1"
# A prototype must be worth a file: below this, a copy costs less than the
# directory entry, the request and the manifest line.
MIN_BYTES = 4096
GLB_MAGIC = 0x46546C67
# GitHub refuses a file over 100 MiB, as scene_io.PACKAGE_FILE_BYTES says.
PACKAGE_FILE_BYTES = 100 * 2 ** 20

SETS = {
    "continent-v2": MAPS / "continent-v2",
    "nymara-regions": MAPS / "nymara-regions",
    "four-gates": MAPS / "four-gates",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --- GLB ---------------------------------------------------------------------

def read_glb(path: Path) -> tuple[dict, bytes]:
    data = path.read_bytes()
    magic, _, _ = struct.unpack_from("<III", data, 0)
    if magic != GLB_MAGIC:
        raise ValueError(f"not a GLB: {path}")
    json_length, _ = struct.unpack_from("<II", data, 12)
    document = json.loads(data[20:20 + json_length])
    offset = 20 + json_length
    binary = b""
    if offset < len(data):
        length, _ = struct.unpack_from("<II", data, offset)
        binary = data[offset + 8:offset + 8 + length]
    buffers = document.get("buffers", [])
    if len(buffers) > 1 or any("uri" in buffer for buffer in buffers):
        binary = _flatten_buffers(path, document, binary)
    return document, binary


def _flatten_buffers(path: Path, document: dict, first: bytes) -> bytes:
    """Fold a GLB's external buffers into one, and rebase its views onto it.

    A region master past 90 MiB continues in sibling `.part<n>.<sha>.bin` files
    (scene_io.dump_glb), which are standard glTF external buffers. Everything
    downstream here reads a view's bytes as an offset into one binary, so a
    view in part 1 would otherwise be read from part 0 at a part-local offset:
    the wrong bytes, silently.
    """
    loaded = [first]
    for buffer in document["buffers"][1:]:
        uri = buffer.get("uri", "")
        if uri.startswith("data:"):
            loaded.append(base64.b64decode(uri.split(",", 1)[1]))
            continue
        if not uri:
            raise ValueError(f"{path}: buffer {len(loaded)} has no uri and is not the GLB's own")
        part = path.parent / uri
        if not part.is_file():
            raise ValueError(f"{path}: buffer file {uri} is missing")
        loaded.append(part.read_bytes())
    packed = bytearray()
    for view in document["bufferViews"]:
        start = view.get("byteOffset", 0)
        data = loaded[view.get("buffer", 0)][start:start + view["byteLength"]]
        packed.extend(b"\0" * ((-len(packed)) % 4))
        view["buffer"] = 0
        view["byteOffset"] = len(packed)
        packed.extend(data)
    document["buffers"] = [{"byteLength": len(packed)}]
    return bytes(packed)


def write_package_glb(path: Path, data: bytes) -> None:
    """Write a package GLB, and drop the part files it no longer continues in.

    The passes here always write a self-contained GLB, so a master that was
    split leaves its parts behind as orphans - which the packager would ship
    and `git` would keep. A file that cannot be made to fit without them is an
    error rather than an unpushable commit.
    """
    if len(data) > PACKAGE_FILE_BYTES:
        raise ValueError(f"{path}: {len(data)} bytes exceeds the {PACKAGE_FILE_BYTES}-byte file limit; "
                         "it needs re-splitting through scene_io.dump_glb")
    path.write_bytes(data)
    for stale in path.parent.glob(f"{path.stem}.part*.bin"):
        stale.unlink()


def write_glb(document: dict, binary: bytes) -> bytes:
    text = json.dumps(document, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    text += b" " * ((-len(text)) % 4)
    binary = binary + b"\0" * ((-len(binary)) % 4)
    chunks = struct.pack("<II", len(text), 0x4E4F534A) + text
    if binary:
        chunks += struct.pack("<II", len(binary), 0x004E4942) + binary
    return struct.pack("<III", GLB_MAGIC, 2, 12 + len(chunks)) + chunks


def view_bytes(document: dict, binary: bytes, index: int) -> bytes:
    view = document["bufferViews"][index]
    start = view.get("byteOffset", 0)
    return binary[start:start + view["byteLength"]]


def accessor_bytes(document: dict, binary: bytes, index: int) -> bytes:
    accessor = document["accessors"][index]
    if "bufferView" not in accessor:
        return b""
    widths = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
    counts = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}
    view = document["bufferViews"][accessor["bufferView"]]
    element = widths[accessor["componentType"]] * counts[accessor["type"]]
    stride = view.get("byteStride", element)
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    length = stride * (accessor["count"] - 1) + element if accessor["count"] else 0
    return binary[start:start + length]


# --- canonical identity ------------------------------------------------------

def _image_identity(document: dict, binary: bytes, index: int, source: Path) -> str:
    """An image by its bytes, wherever they live, so two packages agree."""
    image = document["images"][index]
    if "bufferView" in image:
        return sha256(view_bytes(document, binary, image["bufferView"]))
    uri = image.get("uri", "")
    if uri.startswith("data:"):
        return sha256(uri.encode())
    path = (source.parent / uri).resolve()
    return sha256(path.read_bytes()) if path.is_file() else "missing:" + uri


def _texture_identity(document: dict, binary: bytes, info, source: Path, cache: dict):
    if not isinstance(info, dict) or "index" not in info:
        return None
    texture = document["textures"][info["index"]]
    out = {k: v for k, v in info.items() if k != "index"}
    image = texture.get("source")
    if image is not None:
        if image not in cache:
            cache[image] = _image_identity(document, binary, image, source)
        out["image"] = cache[image]
    if "sampler" in texture:
        out["sampler"] = document.get("samplers", [])[texture["sampler"]]
    return out


def _material_identity(document: dict, binary: bytes, index, source: Path, cache: dict):
    """A material with every texture replaced by the bytes it shows, name dropped."""
    if index is None:
        return None
    material = json.loads(json.dumps(document["materials"][index]))
    material.pop("name", None)

    def walk(node):
        if isinstance(node, dict):
            for key, value in list(node.items()):
                if isinstance(value, dict) and key.endswith("Texture") and "index" in value:
                    node[key] = _texture_identity(document, binary, value, source, cache)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(material)
    return material


def mesh_identity(document: dict, binary: bytes, mesh_index: int, source: Path,
                  cache: dict) -> tuple[str, int]:
    """The sha of a mesh's geometry and appearance, and the bytes it occupies.

    Excludes the mesh's own name and the nodes that place it, so the same prop
    in two packages hashes the same and a moved placement changes nothing.
    """
    mesh = document["meshes"][mesh_index]
    digest = hashlib.sha256()
    digest.update(SCHEMA.encode())
    size = 0
    for primitive in mesh["primitives"]:
        digest.update(b"\x00primitive")
        for semantic in sorted(primitive["attributes"]):
            accessor_index = primitive["attributes"][semantic]
            accessor = document["accessors"][accessor_index]
            data = accessor_bytes(document, binary, accessor_index)
            size += len(data)
            digest.update(semantic.encode())
            digest.update(struct.pack("<III", accessor["componentType"], accessor["count"],
                                      1 if accessor.get("normalized") else 0))
            digest.update(accessor["type"].encode())
            digest.update(data)
        if "indices" in primitive:
            data = accessor_bytes(document, binary, primitive["indices"])
            size += len(data)
            digest.update(b"indices")
            digest.update(struct.pack("<I", document["accessors"][primitive["indices"]]["componentType"]))
            digest.update(data)
        digest.update(b"mode%d" % primitive.get("mode", 4))
        if primitive.get("targets"):
            for target in primitive["targets"]:
                for semantic in sorted(target):
                    digest.update(semantic.encode())
                    digest.update(accessor_bytes(document, binary, target[semantic]))
        material = _material_identity(document, binary, primitive.get("material"), source, cache)
        digest.update(json.dumps(material, sort_keys=True, separators=(",", ":")).encode())
    if mesh.get("weights"):
        digest.update(json.dumps(mesh["weights"], separators=(",", ":")).encode())
    return digest.hexdigest(), size


# --- package walking ---------------------------------------------------------

def package_glbs(root: Path) -> list[Path]:
    """Every map GLB under `root` that a package ships (not sources or LODs)."""
    out = []
    for path in sorted(root.rglob("*.glb")):
        parts = {p.lower() for p in path.relative_to(root).parts[:-1]}
        if parts & {"source", "sources", "references", "captures", "godot-captures", "qa", "work", ".local"}:
            continue
        if path.name.startswith("world-lod") or path.parent.name == "meshes":
            continue
        out.append(path)
    return out


def manifest_for(glb: Path) -> Path | None:
    for name in (glb.with_suffix(".json").name, "world.json"):
        candidate = glb.parent / name
        if candidate.is_file():
            return candidate
    return None


def survey(roots: list[Path]) -> dict:
    """Every mesh in every package, by identity: where it is and what it costs."""
    meshes: dict[str, dict] = defaultdict(lambda: {"bytes": 0, "files": set(), "uses": 0})
    for root in roots:
        for glb in package_glbs(root):
            document, binary = read_glb(glb)
            cache: dict = {}
            users = defaultdict(int)
            for node in document.get("nodes", []):
                if "mesh" in node:
                    users[node["mesh"]] += 1
            for index in range(len(document.get("meshes", []))):
                identity, size = mesh_identity(document, binary, index, glb, cache)
                entry = meshes[identity]
                entry["bytes"] = size
                entry["files"].add(glb)
                entry["uses"] += max(1, users.get(index, 0))
    return meshes


def _collect(document: dict, binary: bytes, mesh_index: int, source: Path) -> tuple[dict, bytes]:
    """A standalone GLB holding one mesh: its accessors, materials and images.

    Image URIs are rewritten relative to the pool, so a prototype points at the
    same shared image file the package pointed at.
    """
    out: dict = {"asset": {"version": "2.0", "generator": "eloria shared_meshes"},
                 "scenes": [{"nodes": [0]}], "scene": 0,
                 "nodes": [{"name": "prototype", "mesh": 0}], "meshes": [], "accessors": [],
                 "bufferViews": [], "materials": [], "textures": [], "images": [], "samplers": []}
    packed = bytearray()
    view_map: dict[int, int] = {}
    accessor_map: dict[int, int] = {}
    material_map: dict[int, int] = {}
    texture_map: dict[int, int] = {}
    image_map: dict[int, int] = {}
    sampler_map: dict[int, int] = {}

    def add_view(index: int) -> int:
        if index not in view_map:
            data = view_bytes(document, binary, index)
            packed.extend(b"\0" * ((-len(packed)) % 4))
            view = {k: v for k, v in document["bufferViews"][index].items()
                    if k in ("byteStride", "target")}
            view.update(buffer=0, byteOffset=len(packed), byteLength=len(data))
            packed.extend(data)
            out["bufferViews"].append(view)
            view_map[index] = len(out["bufferViews"]) - 1
        return view_map[index]

    def add_accessor(index: int) -> int:
        if index not in accessor_map:
            accessor = dict(document["accessors"][index])
            if "bufferView" in accessor:
                accessor["bufferView"] = add_view(accessor["bufferView"])
            out["accessors"].append(accessor)
            accessor_map[index] = len(out["accessors"]) - 1
        return accessor_map[index]

    def add_image(index: int) -> int:
        if index not in image_map:
            image = dict(document["images"][index])
            if "bufferView" in image:
                image["bufferView"] = add_view(image["bufferView"])
            elif "uri" in image and not image["uri"].startswith("data:"):
                target = (source.parent / image["uri"]).resolve()
                image["uri"] = os.path.relpath(target, POOL).replace("\\", "/")
            out["images"].append(image)
            image_map[index] = len(out["images"]) - 1
        return image_map[index]

    def add_texture(index: int) -> int:
        if index not in texture_map:
            texture = dict(document["textures"][index])
            if "source" in texture:
                texture["source"] = add_image(texture["source"])
            if "sampler" in texture:
                sampler = texture["sampler"]
                if sampler not in sampler_map:
                    out["samplers"].append(dict(document["samplers"][sampler]))
                    sampler_map[sampler] = len(out["samplers"]) - 1
                texture["sampler"] = sampler_map[sampler]
            out["textures"].append(texture)
            texture_map[index] = len(out["textures"]) - 1
        return texture_map[index]

    def remap_textures(node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, dict) and key.endswith("Texture") and "index" in value:
                    value["index"] = add_texture(value["index"])
                else:
                    remap_textures(value)
        elif isinstance(node, list):
            for item in node:
                remap_textures(item)

    def add_material(index: int) -> int:
        if index not in material_map:
            material = json.loads(json.dumps(document["materials"][index]))
            remap_textures(material)
            out["materials"].append(material)
            material_map[index] = len(out["materials"]) - 1
        return material_map[index]

    mesh = json.loads(json.dumps(document["meshes"][mesh_index]))
    mesh.pop("name", None)
    for primitive in mesh["primitives"]:
        primitive["attributes"] = {k: add_accessor(v) for k, v in sorted(primitive["attributes"].items())}
        if "indices" in primitive:
            primitive["indices"] = add_accessor(primitive["indices"])
        if "material" in primitive:
            primitive["material"] = add_material(primitive["material"])
        for target in primitive.get("targets", []):
            for semantic in list(target):
                target[semantic] = add_accessor(target[semantic])
    out["meshes"].append(mesh)
    packed.extend(b"\0" * ((-len(packed)) % 4))
    out["buffers"] = [{"byteLength": len(packed)}]
    for key in ("materials", "textures", "images", "samplers"):
        if not out[key]:
            del out[key]
    for extension in ("extensionsUsed", "extensionsRequired"):
        if document.get(extension):
            out[extension] = document[extension]
    return out, bytes(packed)


def _prune(document: dict, binary: bytes) -> tuple[dict, bytes]:
    """Drop what nothing references any more and repack, as strip_unused_glb_data does."""
    used_accessors: set[int] = set()
    used_materials: set[int] = set()
    for mesh in document.get("meshes", []):
        for primitive in mesh["primitives"]:
            used_accessors.update(primitive["attributes"].values())
            if "indices" in primitive:
                used_accessors.add(primitive["indices"])
            if "material" in primitive:
                used_materials.add(primitive["material"])
            for target in primitive.get("targets", []):
                used_accessors.update(target.values())
    for animation in document.get("animations", []):
        for sampler in animation["samplers"]:
            used_accessors.update((sampler["input"], sampler["output"]))
    for skin in document.get("skins", []):
        if "inverseBindMatrices" in skin:
            used_accessors.add(skin["inverseBindMatrices"])

    used_textures: set[int] = set()

    def walk(node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, dict) and key.endswith("Texture") and "index" in value:
                    used_textures.add(value["index"])
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for index in sorted(used_materials):
        walk(document["materials"][index])
    used_images = {document["textures"][t].get("source") for t in used_textures}
    used_images.discard(None)

    used_views = {document["accessors"][a]["bufferView"] for a in used_accessors
                  if "bufferView" in document["accessors"][a]}
    used_views |= {document["images"][i]["bufferView"] for i in used_images
                   if "bufferView" in document["images"][i]}

    view_map = {old: new for new, old in enumerate(sorted(used_views))}
    accessor_map = {old: new for new, old in enumerate(sorted(used_accessors))}
    material_map = {old: new for new, old in enumerate(sorted(used_materials))}
    texture_map = {old: new for new, old in enumerate(sorted(used_textures))}
    image_map = {old: new for new, old in enumerate(sorted(used_images))}

    packed = bytearray()
    views = []
    for old in sorted(used_views):
        data = view_bytes(document, binary, old)
        packed.extend(b"\0" * ((-len(packed)) % 4))
        view = dict(document["bufferViews"][old])
        view.update(buffer=0, byteOffset=len(packed), byteLength=len(data))
        views.append(view)
        packed.extend(data)
    packed.extend(b"\0" * ((-len(packed)) % 4))

    accessors = []
    for old in sorted(used_accessors):
        accessor = dict(document["accessors"][old])
        if "bufferView" in accessor:
            accessor["bufferView"] = view_map[accessor["bufferView"]]
        accessors.append(accessor)
    materials = []
    for old in sorted(used_materials):
        material = json.loads(json.dumps(document["materials"][old]))

        def remap(node) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    if isinstance(value, dict) and key.endswith("Texture") and "index" in value:
                        value["index"] = texture_map[value["index"]]
                    else:
                        remap(value)
            elif isinstance(node, list):
                for item in node:
                    remap(item)

        remap(material)
        materials.append(material)
    textures = []
    for old in sorted(used_textures):
        texture = dict(document["textures"][old])
        if "source" in texture:
            texture["source"] = image_map[texture["source"]]
        textures.append(texture)
    images = []
    for old in sorted(used_images):
        image = dict(document["images"][old])
        if "bufferView" in image:
            image["bufferView"] = view_map[image["bufferView"]]
        images.append(image)

    for mesh in document.get("meshes", []):
        for primitive in mesh["primitives"]:
            primitive["attributes"] = {k: accessor_map[v] for k, v in primitive["attributes"].items()}
            if "indices" in primitive:
                primitive["indices"] = accessor_map[primitive["indices"]]
            if "material" in primitive:
                primitive["material"] = material_map[primitive["material"]]
            for target in primitive.get("targets", []):
                for semantic in list(target):
                    target[semantic] = accessor_map[target[semantic]]
    for animation in document.get("animations", []):
        for sampler in animation["samplers"]:
            sampler["input"] = accessor_map[sampler["input"]]
            sampler["output"] = accessor_map[sampler["output"]]
    for skin in document.get("skins", []):
        if "inverseBindMatrices" in skin:
            skin["inverseBindMatrices"] = accessor_map[skin["inverseBindMatrices"]]

    document["accessors"] = accessors
    document["bufferViews"] = views
    for key, value in (("materials", materials), ("textures", textures), ("images", images)):
        if value:
            document[key] = value
        else:
            document.pop(key, None)
    document["buffers"] = [{"byteLength": len(packed)}] if packed else []
    return document, bytes(packed)


@functools.lru_cache(maxsize=256)
def _prototype(path: Path) -> tuple[dict, bytes]:
    return read_glb(path)


def inline_prototypes(path: Path, document: dict, binary: bytes) -> tuple[dict, bytes]:
    """Put a shared package's pooled meshes back into the document that places them.

    A placement that names a prototype carries no mesh of its own, so a reader
    that walks `node["mesh"]` sees nothing where the package draws a tree: the
    continent audit's deck heights, a package's vertex counts, a test's
    triangles. This is the Python counterpart of the client's
    WorldLoader._resolve_shared_meshes - the geometry comes back as a mesh on
    the node that placed it, so a reader works whether the package shares its
    props or not.

    The pool is read, never written. A prototype's image URIs are rewritten
    relative to the file being read, since they were written relative to the
    pool.

    The placement's pool reference goes once its mesh is back, as
    apply_to_file's inverse: a node carrying both would be drawn twice by the
    client if a tool wrote the document out again, and a reader that expands
    references itself would add the prop a second time.
    """
    placements = [node for node in document.get("nodes", [])
                  if PROTOTYPE_FIELD in (node.get("extras", {}).get(EXTRAS_KEY) or {})]
    if not placements:
        return document, binary
    packed = bytearray(binary)
    meshes: dict[str, int] = {}
    for node in placements:
        identity = node["extras"][EXTRAS_KEY][PROTOTYPE_FIELD]
        if identity not in meshes:
            source, body = _prototype((POOL / f"{identity}.glb").resolve())
            meshes[identity] = _merge(path, document, packed, source, body)
        node["mesh"] = meshes[identity]
        extras = node["extras"]
        extras[EXTRAS_KEY].pop(PROTOTYPE_FIELD)
        if not extras[EXTRAS_KEY]:
            extras.pop(EXTRAS_KEY)
        if not extras:
            node.pop("extras")
    document["buffers"] = [{"byteLength": len(packed)}]
    return document, bytes(packed)


def _merge(path: Path, document: dict, packed: bytearray, source: dict, body: bytes) -> int:
    """Copy one prototype's mesh and everything it references. Its mesh index."""
    def add(key: str, value: dict) -> int:
        document.setdefault(key, []).append(value)
        return len(document[key]) - 1

    def add_view(index: int) -> int:
        data = view_bytes(source, body, index)
        packed.extend(b"\0" * ((-len(packed)) % 4))
        view = {k: v for k, v in source["bufferViews"][index].items() if k in ("byteStride", "target")}
        view.update(buffer=0, byteOffset=len(packed), byteLength=len(data))
        packed.extend(data)
        return add("bufferViews", view)

    def add_accessor(index: int) -> int:
        accessor = dict(source["accessors"][index])
        if "bufferView" in accessor:
            accessor["bufferView"] = add_view(accessor["bufferView"])
        return add("accessors", accessor)

    images: dict[int, int] = {}
    samplers: dict[int, int] = {}
    textures: dict[int, int] = {}

    def add_image(index: int) -> int:
        if index not in images:
            image = dict(source["images"][index])
            if "bufferView" in image:
                image["bufferView"] = add_view(image["bufferView"])
            elif "uri" in image and not image["uri"].startswith("data:"):
                target = (POOL / image["uri"]).resolve()
                image["uri"] = os.path.relpath(target, path.parent).replace(os.sep, "/")
            images[index] = add("images", image)
        return images[index]

    def add_texture(index: int) -> int:
        if index not in textures:
            texture = dict(source["textures"][index])
            if "source" in texture:
                texture["source"] = add_image(texture["source"])
            if "sampler" in texture:
                if texture["sampler"] not in samplers:
                    samplers[texture["sampler"]] = add("samplers", dict(source["samplers"][texture["sampler"]]))
                texture["sampler"] = samplers[texture["sampler"]]
            textures[index] = add("textures", texture)
        return textures[index]

    def remap(node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, dict) and key.endswith("Texture") and "index" in value:
                    value["index"] = add_texture(value["index"])
                else:
                    remap(value)
        elif isinstance(node, list):
            for item in node:
                remap(item)

    mesh = json.loads(json.dumps(source["meshes"][0]))
    for primitive in mesh["primitives"]:
        primitive["attributes"] = {k: add_accessor(v) for k, v in sorted(primitive["attributes"].items())}
        if "indices" in primitive:
            primitive["indices"] = add_accessor(primitive["indices"])
        if "material" in primitive:
            material = json.loads(json.dumps(source["materials"][primitive["material"]]))
            remap(material)
            primitive["material"] = add("materials", material)
        for target in primitive.get("targets", []):
            for semantic in list(target):
                target[semantic] = add_accessor(target[semantic])
    for key in ("extensionsUsed", "extensionsRequired"):
        if source.get(key):
            document[key] = sorted(set(document.get(key, [])) | set(source[key]))
    return add("meshes", mesh)


def manifest_indent(text: str) -> int:
    """The indentation the file already uses, so a rewrite is not a reformat.

    The bake families disagree - the nymara publishers write two spaces and
    continent-v2 one - and a pass that rewrote a manifest at its own preference
    turned a two-line change into a whole-file diff.
    """
    for line in text.split("\n")[1:]:
        body = line.lstrip(" ")
        if body and not body.startswith("}"):
            return len(line) - len(body)
    return 2


def write_manifest(path: Path, manifest: dict, text: str) -> None:
    """Rewrite a manifest in the shape it was found in."""
    rendered = json.dumps(manifest, indent=manifest_indent(text), ensure_ascii=False) + "\n"
    if "\r\n" in text:
        rendered = rendered.replace("\n", "\r\n")
    path.write_bytes(rendered.encode("utf-8"))


def _index_entry(prototype: dict, data: bytes) -> dict:
    """What the pool's index records about one prototype.

    `images` is the point of it: the client needs a prototype's external images
    keyed exactly as the prototype's glTF names them, so the map image
    extension can prepare them (sidecar or pooled) instead of letting
    GLTFDocument hand them to ResourceLoader - which, outside the editor, reads
    them back off the GPU and deadlocks a worker the main thread is joining.
    """
    images = {}
    for image in prototype.get("images", []):
        uri = image.get("uri", "")
        if uri and not uri.startswith("data:"):
            path = (POOL / uri).resolve()
            if path.is_file():
                images[uri] = sha256(path.read_bytes())
    return {"bytes": len(data), "sha256": sha256(data),
            "primitives": len(prototype["meshes"][0]["primitives"]),
            "images": images}


def apply_to_file(glb: Path, shared: dict, index: dict, dry_run: bool) -> dict:
    """Move this file's shared meshes into the pool and leave placements behind."""
    document, binary = read_glb(glb)
    cache: dict = {}
    identities = {i: mesh_identity(document, binary, i, glb, cache)[0]
                  for i in range(len(document.get("meshes", [])))}
    moving = {i: identity for i, identity in identities.items() if identity in shared}
    if not moving:
        return {"moved": 0, "bytes": 0}

    written = 0
    for mesh_index, identity in sorted(moving.items()):
        target = POOL / f"{identity}.glb"
        if not target.exists():
            prototype, prototype_binary = _collect(document, binary, mesh_index, glb)
            data = write_glb(prototype, prototype_binary)
            if not dry_run:
                POOL.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            written += 1
            index[identity] = _index_entry(prototype, data)
        elif identity not in index:
            data = target.read_bytes()
            index[identity] = _index_entry(read_glb(target)[0], data)

    placements = 0
    for node in document.get("nodes", []):
        mesh_index = node.get("mesh")
        if mesh_index in moving:
            node.pop("mesh", None)
            extras = node.setdefault("extras", {}).setdefault(EXTRAS_KEY, {})
            extras[PROTOTYPE_FIELD] = moving[mesh_index]
            placements += 1

    before = glb.stat().st_size
    keep = [i for i in range(len(document.get("meshes", []))) if i not in moving]
    mesh_map = {old: new for new, old in enumerate(keep)}
    document["meshes"] = [document["meshes"][i] for i in keep]
    for node in document.get("nodes", []):
        if "mesh" in node:
            node["mesh"] = mesh_map[node["mesh"]]
    document, binary = _prune(document, binary)
    data = write_glb(document, binary)
    if not dry_run:
        write_package_glb(glb, data)

    # Every prototype the file places, not only the ones moved now: a file
    # shared before that gains another repeated prop keeps its old placements,
    # and a reference the manifest stops naming draws nothing in the client and
    # is not shipped by the packager.
    placed = {(node.get("extras", {}).get(EXTRAS_KEY) or {}).get(PROTOTYPE_FIELD)
              for node in document.get("nodes", [])} - {None}
    manifest_path = manifest_for(glb)
    if manifest_path and not dry_run:
        text = manifest_path.read_bytes().decode("utf-8")
        manifest = json.loads(text)
        named = manifest.get(MANIFEST_KEY) if isinstance(manifest.get(MANIFEST_KEY), dict) else {}
        uris = {}
        for identity in sorted(placed):
            uri = os.path.relpath(POOL / f"{identity}.glb", glb.parent).replace("\\", "/")
            uris[uri] = index[identity]["sha256"] if identity in index else named.get(uri) \
                or sha256((POOL / f"{identity}.glb").read_bytes())
        manifest[MANIFEST_KEY] = uris
        write_manifest(manifest_path, manifest, text)
    return {"moved": len(moving), "placements": placements, "written": written,
            "bytes": before - len(data), "manifest": bool(manifest_path)}


def reconcile(dry_run: bool = False, prototypes: set | None = None,
              manifests: list | None = None) -> list[str]:
    """Refresh every manifest's externalMeshes sha from the pool files.

    A manifest records the prototype FILE's sha256, so anything that rewrites a
    prototype - shared_images.py moving its textures into the image pool, a
    later pass of this tool - leaves every manifest that names it recording the
    old bytes, and the packager refuses the build. This puts them back in step.
    """
    digests: dict[str, str] = {}
    updated = []
    # The pool's own index records each prototype's sha and size too, and the
    # packager refuses a package where it disagrees with the file.
    if INDEX.is_file():
        index = json.loads(INDEX.read_text(encoding="utf-8"))
        pool = index.get("prototypes", {})
        changed = False
        # `prototypes` scopes this to the ones a publisher just wrote; without
        # it every prototype in the pool is read back and checked.
        for identity, entry in pool.items() if prototypes is None else (
                (i, pool[i]) for i in sorted(prototypes) if i in pool):
            target = POOL / f"{identity}.glb"
            if not target.is_file():
                continue
            data = target.read_bytes()
            if entry.get("sha256") != sha256(data) or entry.get("bytes") != len(data):
                entry["sha256"] = sha256(data)
                entry["bytes"] = len(data)
                changed = True
        if changed and not dry_run:
            write_manifest(INDEX, index, INDEX.read_bytes().decode("utf-8"))
        if changed:
            updated.append(repo_relative(INDEX))
    candidates = sorted(MAPS.rglob("*.json")) if manifests is None else [Path(m) for m in manifests]
    for manifest_path in candidates:
        if manifest_path.parent == POOL or "_shared" in manifest_path.parts or not manifest_path.is_file():
            continue
        raw = manifest_path.read_bytes()
        if MANIFEST_KEY.encode() not in raw:
            continue
        text = raw.decode("utf-8")
        manifest = json.loads(text)
        entries = manifest.get(MANIFEST_KEY)
        if not isinstance(entries, dict) or not entries:
            continue
        changed = False
        for uri in list(entries):
            target = (manifest_path.parent / uri).resolve()
            if not target.is_file():
                continue
            key = str(target)
            if key not in digests:
                digests[key] = sha256(target.read_bytes())
            if entries[uri] != digests[key]:
                entries[uri] = digests[key]
                changed = True
        if not changed:
            continue
        updated.append(repo_relative(manifest_path))
        if dry_run:
            continue
        write_manifest(manifest_path, manifest, text)
    return updated


def repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(MAPS).as_posix()
    except ValueError:
        return str(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--reconcile", action="store_true",
                        help="refresh manifest externalMeshes hashes from the pool files")
    parser.add_argument("--scan", action="store_true", help="report duplication, write nothing")
    parser.add_argument("--apply", action="store_true", help="externalise prototypes and rewrite packages")
    parser.add_argument("--dry-run", action="store_true", help="with --apply: write nothing")
    parser.add_argument("--sets", default="all", help="comma list of %s, or all" % ",".join(SETS))
    parser.add_argument("--min-bytes", type=int, default=MIN_BYTES)
    options = parser.parse_args()
    names = list(SETS) if options.sets == "all" else [s for s in options.sets.split(",") if s]
    roots = [SETS[n] for n in names]

    if options.reconcile:
        updated = reconcile(options.dry_run)
        print(f"{'would update' if options.dry_run else 'updated'} {len(updated)} manifests whose "
              f"externalMeshes hashes had fallen behind the pool")
        for path in updated[:10]:
            print("  " + path)
        if not options.apply and not options.scan:
            return 0

    meshes = survey(roots)
    shared = {k: v for k, v in meshes.items() if len(v["files"]) > 1 and v["bytes"] >= options.min_bytes}
    total = sum(v["bytes"] * len(v["files"]) for v in meshes.values())
    keep = sum(v["bytes"] for v in shared.values())
    drop = sum(v["bytes"] * (len(v["files"]) - 1) for v in shared.values())
    print(f"{len(meshes)} distinct meshes in {len(set().union(*(v['files'] for v in meshes.values())))} files, "
          f"{total / 1e6:.0f} MB as shipped")
    print(f"{len(shared)} prototypes appear in more than one file: {keep / 1e6:.0f} MB published once, "
          f"{drop / 1e6:.0f} MB of copies removed")
    biggest = sorted(shared.items(), key=lambda kv: -kv[1]["bytes"] * (len(kv[1]["files"]) - 1))[:8]
    for identity, entry in biggest:
        example = sorted(entry["files"])[0].relative_to(MAPS)
        print(f"  {entry['bytes'] * (len(entry['files']) - 1) / 1e6:7.1f} MB  in {len(entry['files']):4d} files  "
              f"{entry['bytes'] / 1e6:5.2f} MB each  {identity[:12]}  e.g. {example}")
    if not options.apply:
        return 0

    index = json.loads(INDEX.read_text(encoding="utf-8")).get("prototypes", {}) if INDEX.is_file() else {}
    files = [glb for root in roots for glb in package_glbs(root)]
    moved = saved = touched = 0
    for position, glb in enumerate(files, 1):
        result = apply_to_file(glb, shared, index, options.dry_run)
        if result["moved"]:
            touched += 1
            moved += result["moved"]
            saved += result["bytes"]
        if position % 100 == 0 or position == len(files):
            print(f"  [{position}/{len(files)}] {touched} files rewritten, {saved / 1e6:.0f} MB removed",
                  flush=True)
    if not options.dry_run:
        POOL.mkdir(parents=True, exist_ok=True)
        INDEX.write_text(json.dumps({"schema": SCHEMA, "prototypes": dict(sorted(index.items()))},
                                    indent=2) + "\n", encoding="utf-8")
    pool_bytes = sum(entry["bytes"] for entry in index.values())
    print(f"{'would move' if options.dry_run else 'moved'} {moved} mesh references out of {touched} files; "
          f"packages {saved / 1e6:.0f} MB smaller, pool {len(index)} prototypes / {pool_bytes / 1e6:.0f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
