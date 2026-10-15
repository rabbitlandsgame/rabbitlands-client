#!/usr/bin/env python3
"""Cap the resolution of actor textures and re-encode them compactly.

Added 2026-09-16 for Eloria Client.

    python tools/shrink_actor_textures.py --dry-run
    python tools/shrink_actor_textures.py --archive ../../archive/fullres-textures-2026-09-16

Actor textures arrived from generation at 2048 px and as PNG, which is several
times what the game camera can show: they were 1.7 GB of a 6.6 GB install.
This tool touches four sets:

  equipment   equipment/textures/*, the shared textures the equipment and
              variant GLBs reference by URI, plus images embedded in
              equipment GLBs
  races       images embedded in races/*.glb
  creatures   images embedded in creatures/*.glb
  hair        images embedded in hair/**/*.glb

Each image is scaled down to its set's cap (never up) and re-encoded: JPEG for
anything without real alpha, PNG otherwise. Alpha in a normal, metallic-
roughness or occlusion map carries nothing in glTF and is dropped; alpha in a
base colour map is kept. An image is only replaced when that saves at least
10%, so running the tool again changes nothing.

Race bodies are the exception: every image in a race GLB is scaled by one
factor, and the race's face mask (face_masks/*.png) with it, because the mask
is a pixel map over the head atlas whose eye, brow and scalp crops are fixed
fractions of it (tests/test_face_texture_mapping.py checks the alignment).

What moves with the bytes:
  * equipment/textures names are content hashes (canonical_<sha256>.<ext>,
    from eloria-assets/tools/pack_canonical_equipment.py), so a re-encoded
    texture is renamed to its new hash and every GLB URI is rewritten;
  * GLB binary chunks are rebuilt with the geometry views byte-identical
    (checked after writing);
  * build records that pin a changed file's sha256 - native_asset_catalog,
    the creature expansion list, face mappings, skin palettes - are updated
    to the new hash, and a "bytes" beside it to the new size. Only
    godot-client/data and godot-client/assets are rewritten; evidence under
    eloria-assets/qa keeps its historical hashes.

Before anything is written, every original is copied to --archive at its
repository path, with manifest.json recording old and new hash and path.
Restoring is copying the archive back over the tree (and deleting the
renamed textures), or reverting the commit.

Regenerating an asset through its pipeline brings back a full-size texture;
run this again afterwards.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

CLIENT = Path(__file__).resolve().parents[1]
REPO = CLIENT.parent
NATIVE = CLIENT / "assets" / "actors" / "native"
EQUIPMENT = NATIVE / "equipment"
SHARED_TEXTURES = EQUIPMENT / "textures"

# Races cap at 2048 since the 2026-10 race rebase: every race GLB carries the
# Human body's 2048 TintableAtlas and race skin, and three race heads (with
# their face masks) are 2048. A 1024 cap would halve all sixteen, head atlases
# and masks included, by the one shared factor.
DEFAULT_CAPS = {"equipment": 1024, "races": 2048, "creatures": 1024, "hair": 512}
MIN_SAVING = 0.10
MIN_BYTES = 64_000  # palette thumbnails and flat masks are not worth touching
COLOUR_QUALITY = 88
DATA_QUALITY = 92  # normals and packed channels: less loss, no chroma subsampling
DATA_ROLES = {"normal", "mr", "occlusion"}
RECORD_ROOTS = ("godot-client/data", "godot-client/assets")
SHA = re.compile(r"[0-9a-f]{64}")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def repo_path(path: Path) -> str:
    return path.resolve().relative_to(REPO).as_posix()


# --- GLB --------------------------------------------------------------------

def read_glb(path: Path) -> tuple[dict, bytes]:
    data = path.read_bytes()
    magic, _, _ = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67:
        raise ValueError(f"not a GLB: {path}")
    json_length, json_type = struct.unpack_from("<II", data, 12)
    document = json.loads(data[20:20 + json_length])
    binary = b""
    offset = 20 + json_length
    if offset < len(data):
        bin_length, _ = struct.unpack_from("<II", data, offset)
        binary = data[offset + 8:offset + 8 + bin_length]
    return document, binary


def write_glb(document: dict, binary: bytes) -> bytes:
    text = json.dumps(document, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    text += b" " * ((-len(text)) % 4)
    binary += b"\0" * ((-len(binary)) % 4)
    chunks = struct.pack("<II", len(text), 0x4E4F534A) + text
    if binary:
        chunks += struct.pack("<II", len(binary), 0x004E4942) + binary
    return struct.pack("<III", 0x46546C67, 2, 12 + len(chunks)) + chunks


def view_bytes(document: dict, binary: bytes, index: int) -> bytes:
    view = document["bufferViews"][index]
    start = view.get("byteOffset", 0)
    return binary[start:start + view["byteLength"]]


def image_roles(document: dict) -> dict[int, set[str]]:
    """Which material slots use each image, and the base colour alpha mode."""
    roles: dict[int, set[str]] = defaultdict(set)
    textures = document.get("textures", [])

    def note(info, role):
        if info and info.get("index") is not None and info["index"] < len(textures):
            source = textures[info["index"]].get("source")
            if source is not None:
                roles[source].add(role)

    for material in document.get("materials", []):
        pbr = material.get("pbrMetallicRoughness", {})
        note(pbr.get("baseColorTexture"), "base")
        note(pbr.get("metallicRoughnessTexture"), "mr")
        note(material.get("normalTexture"), "normal")
        note(material.get("occlusionTexture"), "occlusion")
        note(material.get("emissiveTexture"), "emissive")
        for extension in material.get("extensions", {}).values():
            for key, value in extension.items():
                if isinstance(value, dict) and "index" in value:
                    note(value, "extension:" + key)
    return roles


def rebuild_binary(document: dict, binary: bytes, replacements: dict[int, bytes]) -> bytes:
    """Lay out every buffer view again, swapping in replaced image bytes."""
    views = document["bufferViews"]
    if any(view.get("buffer", 0) != 0 for view in views) or len(document.get("buffers", [])) > 1:
        raise ValueError("only single-buffer GLBs are supported")
    packed = bytearray()
    for index, view in enumerate(views):
        packed.extend(b"\0" * ((-len(packed)) % 4))
        data = replacements.get(index, view_bytes(document, binary, index))
        view["byteOffset"] = len(packed)
        view["byteLength"] = len(data)
        packed.extend(data)
    packed.extend(b"\0" * ((-len(packed)) % 4))
    document["buffers"][0]["byteLength"] = len(packed)
    return bytes(packed)


# --- images -------------------------------------------------------------------

def has_real_alpha(image: Image.Image) -> bool:
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        alpha = np.asarray(image.convert("RGBA").getchannel("A"))
        return bool((alpha < 250).any())
    return False


def shrink_image(encoded: bytes, cap: int, roles: set[str],
                 scale: float | None = None) -> tuple[bytes, str] | None:
    """Return (bytes, mime) for a smaller encoding, or None to keep the original.

    A fixed `scale` is applied whatever the saving: images that must stay in
    proportion to each other cannot be skipped one by one.
    """
    forced = scale is not None
    if len(encoded) < MIN_BYTES and not forced:
        return None
    image = Image.open(io.BytesIO(encoded))
    image.load()
    data_only = bool(roles) and roles <= DATA_ROLES
    keep_alpha = has_real_alpha(image) and not data_only
    if scale is None:
        scale = min(1.0, cap / max(image.size))
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    image = image.convert("RGBA" if keep_alpha else "RGB")
    if size != image.size:
        image = image.resize(size, Image.LANCZOS)
    out = io.BytesIO()
    if keep_alpha:
        image.save(out, "PNG", optimize=True)
        mime = "image/png"
    elif data_only:
        image.save(out, "JPEG", quality=DATA_QUALITY, subsampling=0, optimize=True)
        mime = "image/jpeg"
    else:
        image.save(out, "JPEG", quality=COLOUR_QUALITY, optimize=True)
        mime = "image/jpeg"
    result = out.getvalue()
    if len(result) > len(encoded) * (1 - MIN_SAVING) and not forced:
        return None
    return result, mime


# --- work units -----------------------------------------------------------------

def shrink_embedded(task: tuple[str, int, bool]) -> dict | None:
    """Rewrite one GLB's embedded images. Returns a change record or None.

    `uniform` scales every image by one factor, the one that brings the
    largest down to the cap. Race bodies need it: a face mask is a pixel map
    over the head atlas, and its eye, brow and scalp crops are fixed fractions
    of the mask (faceAppearance.groups.uvScale), so all of them must shrink
    together or not at all.
    """
    path_text, cap, uniform = task
    path = Path(path_text)
    original = path.read_bytes()
    document, binary = read_glb(path)
    roles = image_roles(document)
    embedded = [(i, im["bufferView"]) for i, im in enumerate(document.get("images", []))
                if im.get("bufferView") is not None]
    factor = None
    if uniform and embedded:
        largest = max(max(Image.open(io.BytesIO(view_bytes(document, binary, v))).size)
                      for _, v in embedded)
        if largest <= cap:
            return None
        factor = cap / largest
    replacements: dict[int, bytes] = {}
    for index, image in enumerate(document.get("images", [])):
        view = image.get("bufferView")
        if view is None:
            continue
        result = shrink_image(view_bytes(document, binary, view), cap, roles.get(index, set()), factor)
        if result:
            replacements[view] = result[0]
            image["mimeType"] = result[1]
    if not replacements:
        return None
    before = {i: view_bytes(document, binary, i) for i in range(len(document["bufferViews"]))
              if i not in replacements}
    new_binary = rebuild_binary(document, binary, replacements)
    for index, data in before.items():
        if view_bytes(document, new_binary, index) != data:
            raise ValueError(f"geometry view {index} changed in {path}")
    return {"path": path_text, "data": write_glb(document, new_binary), "factor": factor,
            "old_sha": sha256(original), "old_bytes": len(original), "images": len(replacements)}


def shrink_face_masks(results: list[dict]) -> list[dict]:
    """Scale each race's face mask by the factor its model's images got."""
    factors = {os.path.normpath(r["path"]): r["factor"] for r in results if r.get("factor")}
    models = json.loads((CLIENT / "data/actors/models.json").read_bytes())["models"]
    masks = []
    for config in models.values():
        mask = config.get("faceAppearance", {}).get("mask")
        scene = os.path.normpath(CLIENT / str(config.get("scene", "")).removeprefix("res://"))
        if not mask or scene not in factors:
            continue
        path = CLIENT / mask.removeprefix("res://")
        encoded = path.read_bytes()
        image = Image.open(io.BytesIO(encoded))
        image.load()
        size = (round(image.width * factors[scene]), round(image.height * factors[scene]))
        out = io.BytesIO()
        # Max-pool rather than average: the brow and iris regions are strokes
        # one or two texels wide, and averaging fades them below what the face
        # shader reads as painted.
        step = round(1 / factors[scene])
        pixels = np.asarray(image)
        if abs(step * factors[scene] - 1) < 1e-9 and pixels.shape[0] % step == 0 and pixels.shape[1] % step == 0:
            pooled = pixels.reshape(pixels.shape[0] // step, step, pixels.shape[1] // step, step, -1).max(axis=(1, 3))
            Image.fromarray(pooled.squeeze(-1) if pooled.shape[-1] == 1 else pooled, image.mode).save(out, "PNG", optimize=True)
        else:
            from PIL import ImageFilter
            image.filter(ImageFilter.MaxFilter(2 * math.ceil(1 / factors[scene]) - 1)).resize(
                size, Image.BOX).save(out, "PNG", optimize=True)
        masks.append({"path": str(path), "data": out.getvalue(), "old_sha": sha256(encoded),
                      "old_bytes": len(encoded), "set": "face masks", "images": 1})
    return masks


def shrink_shared(task: tuple[str, int, list[str]]) -> dict | None:
    path_text, cap, roles = task
    path = Path(path_text)
    encoded = path.read_bytes()
    result = shrink_image(encoded, cap, set(roles))
    if not result:
        return None
    data, mime = result
    suffix = ".jpg" if mime == "image/jpeg" else ".png"
    name = path.name
    if name.startswith("canonical_"):
        name = "canonical_" + sha256(data) + suffix
    else:
        name = path.stem + suffix
    return {"path": path_text, "new_path": str(path.with_name(name)), "data": data,
            "old_sha": sha256(encoded), "old_bytes": len(encoded)}


def tracked(*pathspecs: str) -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z", "--", *pathspecs], cwd=REPO,
                         capture_output=True, check=True).stdout.decode("utf-8")
    # Deleted-but-tracked paths are skipped: a rename leaves the old name in the index.
    return [REPO / p for p in out.split("\0") if p and (REPO / p).is_file()]


def shared_texture_users() -> tuple[dict[str, list[Path]], dict[str, set[str]]]:
    """Map each shared texture to the GLBs that reference it, and its roles."""
    users: dict[str, list[Path]] = defaultdict(list)
    roles: dict[str, set[str]] = defaultdict(set)
    for glb in tracked("godot-client/assets/actors/native/equipment/*.glb",
                       "godot-client/assets/actors/native/equipment/**/*.glb"):
        document, _ = read_glb(glb)
        image_role = image_roles(document)
        for index, image in enumerate(document.get("images", [])):
            uri = image.get("uri")
            if uri and not uri.startswith("data:"):
                target = os.path.normpath(glb.parent / uri)
                users[target].append(glb)
                roles[target] |= image_role.get(index, set())
    return users, roles


# --- main -------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--archive", type=Path, help="where originals are copied before any write")
    parser.add_argument("--dry-run", action="store_true", help="report savings without writing")
    parser.add_argument("--sets", default=",".join(DEFAULT_CAPS), help="comma list of sets")
    for name, cap in DEFAULT_CAPS.items():
        parser.add_argument(f"--{name}-cap", type=int, default=cap)
    parser.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    options = parser.parse_args()
    if not options.dry_run and not options.archive:
        parser.error("--archive is required unless --dry-run")
    sets = [s for s in options.sets.split(",") if s]
    caps = {name: getattr(options, f"{name}_cap") for name in DEFAULT_CAPS}

    embedded_tasks: list[tuple[str, int, str]] = []
    globs = {"races": ["races/*.glb"], "creatures": ["creatures/*.glb"],
             "hair": ["hair/*.glb", "hair/**/*.glb"],
             "equipment": ["equipment/*.glb", "equipment/**/*.glb"]}
    for name in sets:
        for pattern in globs[name]:
            for glb in tracked(f"godot-client/assets/actors/native/{pattern}"):
                embedded_tasks.append((str(glb), caps[name], name))
    embedded_tasks = list({t[0]: t for t in embedded_tasks}.values())

    results: list[dict] = []
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    with ProcessPoolExecutor(options.jobs) as pool:
        for (path, _, name), record in zip(embedded_tasks, pool.map(
                shrink_embedded, [(p, c, n == "races") for p, c, n in embedded_tasks], chunksize=4)):
            if record:
                record["set"] = name
                results.append(record)
                totals[name][0] += record["old_bytes"]
                totals[name][1] += len(record["data"])
                totals[name][2] += 1

        shared: list[dict] = []
        users: dict[str, list[Path]] = {}
        if "equipment" in sets:
            users, roles = shared_texture_users()
            # Listed from disk, so textures an uncommitted earlier run renamed count.
            textures = sorted(p for p in SHARED_TEXTURES.iterdir() if p.suffix in (".jpg", ".png"))
            tasks = [(os.path.normpath(t), caps["equipment"], sorted(roles.get(os.path.normpath(t), set())))
                     for t in textures]
            for record in pool.map(shrink_shared, tasks, chunksize=2):
                if record:
                    shared.append(record)
                    totals["equipment textures"][0] += record["old_bytes"]
                    totals["equipment textures"][1] += len(record["data"])
                    totals["equipment textures"][2] += 1

    for name, (before, after, count) in totals.items():
        print(f"{name:20s} {count:5d} files  {before / 1e6:9.1f} MB -> {after / 1e6:8.1f} MB")
    saved = sum(b - a for b, a, _ in totals.values())
    print(f"{'total saving':20s}             {saved / 1e6:9.1f} MB")
    if options.dry_run:
        return 0

    # Equipment GLBs whose URIs move. A GLB can also have had embedded images
    # replaced above; rewrite on top of that result.
    renames = {r["path"]: r["new_path"] for r in shared}
    pending = {r["path"]: r["data"] for r in results}
    for glb in sorted({g for r in shared for g in users.get(r["path"], [])}):
        key = str(glb)
        original = glb.read_bytes()
        document, binary = read_glb_bytes(pending.get(key, original))
        data = rewrite_document_uris(document, binary, glb, renames)
        if key in pending:
            next(r for r in results if r["path"] == key)["data"] = data
        else:
            results.append({"path": key, "data": data, "old_sha": sha256(original),
                            "old_bytes": len(original), "set": "equipment uris", "images": 0})

    results += shrink_face_masks(results)

    archive = options.archive.resolve()
    manifest_path = archive / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    changes = results + shared
    for record in changes:
        source = Path(record["path"])
        relative = repo_path(source)
        target = archive / relative
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        if sha256(target.read_bytes()) != record["old_sha"] and relative not in manifest:
            raise SystemExit(f"archive copy of {relative} does not match the file being replaced")

    # Hashes and sizes records may still hold from an earlier run, before this
    # one replaces them in the manifest.
    earlier = {path: (entry.get("newSha256"), entry.get("newBytes")) for path, entry in manifest.items()}

    # Write. Shared textures first, so no GLB ever points at a missing file.
    for record in shared:
        new_path = Path(record["new_path"])
        new_path.write_bytes(record["data"])
        if new_path.resolve() != Path(record["path"]).resolve():
            Path(record["path"]).unlink()
        entry = manifest.setdefault(repo_path(Path(record["path"])),
                                    {"sha256": record["old_sha"], "bytes": record["old_bytes"]})
        entry.update({"replacedBy": repo_path(new_path), "newSha256": sha256(record["data"]),
                      "newBytes": len(record["data"])})
    for record in results:
        path = Path(record["path"])
        path.write_bytes(record["data"])
        entry = manifest.setdefault(repo_path(path), {"sha256": record["old_sha"], "bytes": record["old_bytes"]})
        entry.update({"newSha256": sha256(record["data"]), "newBytes": len(record["data"])})
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    updated = update_records(*records_from_manifest(manifest, earlier))
    print(f"wrote {len(results)} GLBs and {len(shared)} shared textures; "
          f"updated hash records in {len(updated)} files")
    for path in updated:
        print("  " + path)
    return 0


def read_glb_bytes(data: bytes) -> tuple[dict, bytes]:
    json_length, _ = struct.unpack_from("<II", data, 12)
    document = json.loads(data[20:20 + json_length])
    offset = 20 + json_length
    binary = b""
    if offset < len(data):
        bin_length, _ = struct.unpack_from("<II", data, offset)
        binary = data[offset + 8:offset + 8 + bin_length]
    return document, binary


def rewrite_document_uris(document: dict, binary: bytes, glb: Path, renames: dict[str, str]) -> bytes:
    for image in document.get("images", []):
        uri = image.get("uri")
        if not uri or uri.startswith("data:"):
            continue
        target = os.path.normpath(glb.parent / uri)
        if target in renames:
            new = Path(renames[target])
            image["uri"] = os.path.relpath(new, glb.parent).replace("\\", "/")
            image["mimeType"] = "image/jpeg" if new.suffix == ".jpg" else "image/png"
    return write_glb(document, binary)


def records_from_manifest(manifest: dict, earlier: dict) -> tuple[dict, dict, dict]:
    """Every hash, size and name a record could hold, mapped to what is on disk now.

    Built from the whole archive manifest rather than this run's changes, so a
    record left at the original hash, or at the hash an earlier run wrote, is
    brought up to date either way.
    """
    hash_map: dict[str, tuple[str, int]] = {}
    sizes: dict[str, tuple[set[int], int]] = {}
    renamed: dict[str, str] = {}
    for path, entry in manifest.items():
        current = REPO / entry.get("replacedBy", path)
        if not current.is_file():
            continue
        data = current.read_bytes()
        now = (sha256(data), len(data))
        olds = {entry["sha256"]: entry["bytes"]}
        previous_sha, previous_bytes = earlier.get(path, (None, None))
        if previous_sha:
            olds[previous_sha] = previous_bytes
        for old_sha, old_bytes in olds.items():
            if old_sha != now[0]:
                hash_map[old_sha] = (now[0], old_bytes, now[1])
        sizes[path] = ({b for b in olds.values() if b is not None}, now[1])
        if "replacedBy" in entry:
            renamed[path] = entry["replacedBy"]
    return hash_map, renamed, sizes


def update_records(hash_map: dict[str, tuple[str, int, int]], renamed: dict[str, str],
                   paths: dict[str, tuple[set[int], int]]) -> list[str]:
    """Point build records at the new hashes, sizes and texture names.

    Edits the text in place rather than re-serialising, so a record's diff is
    the values that changed. A "bytes" is updated inside the innermost JSON
    object that names the file, by its hash or by its repository path.
    """
    updated = []
    names = {Path(old).name: Path(new).name for old, new in renamed.items()}
    sizes = {old: new for old, (_, _, new) in hash_map.items()}
    old_sizes = {old: {size} for old, (_, size, _) in hash_map.items()}
    innermost = re.compile(r"\{[^{}]*\}")
    bytes_field = re.compile(r'("(?:bytes|byteLength|size)"\s*:\s*)(\d+)')
    for path in tracked(*[f"{root}/**/*.json" for root in RECORD_ROOTS],
                        *[f"{root}/*.json" for root in RECORD_ROOTS]):
        # newline="" keeps CRLF checkouts CRLF; universal newlines would rewrite them.
        text = path.read_bytes().decode("utf-8")
        new_text = text
        if any(p in text for p in paths) or any(h in text for h in hash_map):
            def fix_object(match):
                block = match.group(0)
                olds = [h for h in SHA.findall(block) if h in hash_map]
                named = [p for p in paths if f'"{p}"' in block]
                if len(olds) == 1:
                    old_size, new_size = old_sizes[olds[0]], sizes[olds[0]]
                elif len(named) == 1:
                    old_size, new_size = paths[named[0]]
                else:
                    return block
                return bytes_field.sub(
                    lambda m: m.group(1) + (str(new_size) if int(m.group(2)) in old_size else m.group(2)),
                    block)
            new_text = innermost.sub(fix_object, new_text)
            for old, (new, _, _) in hash_map.items():
                new_text = new_text.replace(old, new)
        for old, new in names.items():
            new_text = new_text.replace(old, new)
        if new_text != text:
            path.write_bytes(new_text.encode("utf-8"))
            updated.append(repo_path(path))
    return updated


if __name__ == "__main__":
    sys.exit(main())
