#!/usr/bin/env python3
"""Plan/apply byte-identical scenery image externalization with full proofs.

This keeps ordinary GLBs and exact accessor/view payloads. It never re-encodes
images or changes vertex data. Plans are made against the *current* source tree;
apply refuses changed inputs and retains exact originals in ignored recovery.
"""
from __future__ import annotations
import argparse
import copy
import json
import os
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "godot-client/tools"))
from scenery_image_sources import (SCHEMA, KEY, POLICY, ELIGIBLE, glb_chunks, sha, validate)


def encode(document: dict, binary: bytes) -> bytes:
    text = json.dumps(document, separators=(",", ":"), ensure_ascii=False).encode()
    text += b" " * (-len(text) % 4)
    binary += b"\0" * (-len(binary) % 4)
    body = struct.pack("<I4s", len(text), b"JSON") + text
    if binary:
        body += struct.pack("<I4s", len(binary), b"BIN\0") + binary
    return struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body


def image_type(data: bytes) -> tuple[str, str]:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png", "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg", "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp", "image/webp"
    raise ValueError("unsupported encoded scenery image")


def relative(path: Path, base: Path) -> str:
    return os.path.relpath(path, base).replace("\\", "/")


def _view_references(value, result: set[int]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "bufferView":
                if type(child) is not int:
                    raise ValueError("noninteger bufferView reference")
                result.add(child)
            else:
                _view_references(child, result)
    elif isinstance(value, list):
        for child in value:
            _view_references(child, result)


def _remap_views(value, mapping: dict[int, int]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "bufferView":
                value[key] = mapping[child]
            else:
                _remap_views(child, mapping)
    elif isinstance(value, list):
        for child in value:
            _remap_views(child, mapping)


def transform(root: Path, glb: Path, canonical: dict[str, Path]) -> tuple[bytes, dict[Path, bytes], dict]:
    document, binary = glb_chunks(glb)
    if KEY in document.get("extras", {}):
        validate(root, glb, document)
        return glb.read_bytes(), {}, {"already_externalized": True}
    images = document.get("images", [])
    embedded = [item for item in images if "bufferView" in item]
    if not embedded:
        return glb.read_bytes(), {}, {"unchanged_uri_images": len(images)}
    buffers = document.get("buffers", [])
    if len(buffers) != 1 or "uri" in buffers[0]:
        raise ValueError(f"only ordinary single-BIN scenery is supported: {glb}")
    if any(name in document.get("extensionsUsed", []) for name in
           ("EXT_meshopt_compression", "KHR_draco_mesh_compression")):
        raise ValueError("compressed geometry is outside this byte-identical pass")
    before = copy.deepcopy(document)
    original_views = before.get("bufferViews", [])
    generated, resources, policies, image_proof = {}, {}, {}, []
    removable = set()
    for index, image in enumerate(images):
        original = copy.deepcopy(image)
        if "bufferView" in image:
            view_index = image.pop("bufferView")
            view = original_views[view_index]
            if view.get("buffer", 0) != 0:
                raise ValueError("image references an external buffer")
            start, length = view.get("byteOffset", 0), view["byteLength"]
            payload = binary[start:start + length]
            if len(payload) != length:
                raise ValueError("image span outside BIN")
            digest = sha(payload)
            suffix, mime = image_type(payload)
            destination = canonical.get(digest, root / "eloria-assets/world/_shared/images" / (digest + suffix))
            if digest not in canonical:
                generated[destination] = payload
            image["uri"] = relative(destination, glb.parent)
            image["mimeType"] = mime
            removable.add(view_index)
            eligible = True
        else:
            uri = image.get("uri", "")
            if not uri or uri.startswith("data:"):
                raise ValueError("mixed data URI scenery needs explicit support")
            destination = (glb.parent / uri).resolve()
            payload = destination.read_bytes()
            digest = sha(payload)
            eligible = False
        image.setdefault("extras", {})[POLICY] = "."
        image["extras"][ELIGIBLE] = eligible
        resources[image["uri"]] = digest
        policies[image["uri"]] = ["."]
        image_proof.append({"index": index, "source_sha256": digest, "bytes": len(payload),
                            "uri": image["uri"], "sidecar_eligible": eligible,
                            "original_descriptor": original})
    # A view used outside image descriptors is retained even if it also happens
    # to carry an image. All non-image references and view bytes stay exact.
    nonimages = copy.deepcopy(before)
    nonimages.pop("images", None)
    used = set()
    _view_references(nonimages, used)
    removable -= used
    kept, mapping, output = [], {}, bytearray()
    for index, view in enumerate(original_views):
        if index in removable:
            continue
        if view.get("buffer", 0) != 0:
            raise ValueError("external scenery bufferView unsupported")
        output.extend(b"\0" * (-len(output) % 4))
        start, count = view.get("byteOffset", 0), view["byteLength"]
        raw = binary[start:start + count]
        if len(raw) != count:
            raise ValueError("retained view outside BIN")
        new = copy.deepcopy(view)
        new["byteOffset"] = len(output)
        output.extend(raw)
        mapping[index] = len(kept)
        kept.append(new)
    _remap_views(document, mapping)
    document["bufferViews"] = kept
    document["buffers"][0]["byteLength"] = len(output)
    document.setdefault("extras", {})[KEY] = {"schema": SCHEMA, "mipPolicy": "full",
                                              "resources": resources, "imagePolicies": policies}
    # Prove schema/scope without IO for generated files, then independently
    # compare all retained view bytes, accessors, materials and texture slots.
    validate(root, glb, document, verify_bytes=False)
    for old, new in mapping.items():
        a, b = original_views[old], kept[new]
        if binary[a.get("byteOffset", 0):a.get("byteOffset", 0) + a["byteLength"]] != output[b["byteOffset"]:b["byteOffset"] + b["byteLength"]]:
            raise AssertionError("retained bufferView changed")
    reverse = copy.deepcopy(document)
    _remap_views(reverse, {new: old for old, new in mapping.items()})
    for key in ("accessors", "meshes", "materials", "textures", "samplers", "nodes", "scenes", "animations", "skins"):
        if reverse.get(key) != before.get(key):
            raise AssertionError(f"semantic field changed: {key}")
    return encode(document, bytes(output)), generated, {
        "image_records": image_proof, "buffer_view_map": mapping,
        "removed_image_only_views": sorted(removable), "retained_view_payloads_byte_identical": True,
        "accessor_material_sampler_scene_semantics_exact": True}


def current_metadata(root: Path, model_changes: list[dict]) -> dict[Path, bytes]:
    """Refresh only current outputs; original generation/source receipts stay historical."""
    models = {row["path"]: row for row in model_changes if "proof" in row}
    outputs = {}

    def equivalence(row):
        return {"schema": "rabbitlands-scenery-image-equivalence-v1",
                "inputSha256": row["before_sha256"], "outputSha256": row["after_sha256"],
                "encodedImageBytesIdentical": True, "retainedBufferViewsByteIdentical": True,
                "accessorMaterialSamplerSceneSemanticsExact": True,
                "imageSchema": SCHEMA}

    reused = root / "eloria-assets/source/world_objects/underground/reused-scenery.json"
    if reused.is_file():
        data = json.loads(reused.read_text(encoding="utf-8-sig"))
        changed = False
        for asset in data.get("assets", []):
            row = models.get(asset.get("output"))
            if row is None:
                continue
            asset["sha256"] = row["after_sha256"]
            asset["images"] = [{"sha256": image["source_sha256"], "bytes": image["bytes"], "uri": image["uri"]}
                               for image in row["proof"]["image_records"]]
            asset["sourceBinaryPrefixPreserved"] = False
            asset["storageEquivalence"] = equivalence(row)
            changed = True
        if changed:
            outputs[reused] = (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode()
    storage = root / "eloria-assets/source/world_objects/storage/provenance.json"
    storage_row = models.get("godot-client/assets/world/interactives/storage.glb")
    if storage.is_file() and storage_row is not None:
        data = json.loads(storage.read_text(encoding="utf-8-sig"))
        data["model"]["sha256"] = storage_row["after_sha256"]
        data["model"]["storageEquivalence"] = equivalence(storage_row)
        outputs[storage] = (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode()
    objects = root / "godot-client/data/world/objects.json"
    if objects.is_file():
        data = json.loads(objects.read_text(encoding="utf-8-sig"))
        changed = False

        def visit(value):
            nonlocal changed
            if isinstance(value, dict):
                scene = value.get("scene", "")
                if isinstance(scene, str) and scene.startswith("res://") and "sha256" in value:
                    row = models.get("godot-client/" + scene[6:])
                    if row is not None:
                        value["sha256"] = row["after_sha256"]
                        changed = True
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
        visit(data)
        if changed:
            outputs[objects] = (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode()
    return outputs


def plan(root: Path, shipping_list: Path, stage: Path) -> dict:
    root, stage = root.resolve(), stage.resolve()
    if stage.exists() and any(stage.iterdir()):
        raise ValueError("stage must be new or empty")
    stage.mkdir(parents=True, exist_ok=True)
    selected = json.loads(shipping_list.read_text(encoding="utf-8-sig"))["files"]
    canonical = {}
    inputs = {}
    for item in selected:
        path = root / item["path"]
        if item["path"].startswith("eloria-assets/maps/") and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            raw = path.read_bytes()
            if len(raw) != item["bytes"]:
                raise ValueError(f"shipping image changed: {path}")
            canonical.setdefault(sha(raw), path)
    models = sorted((root / "godot-client/assets/world").rglob("*.glb"))
    changes, pool = [], {}
    for glb in models:
        if ".local" in glb.relative_to(root).parts:
            continue
        source = glb.read_bytes()
        inputs[glb.relative_to(root).as_posix()] = sha(source)
        result, generated, proof = transform(root, glb, canonical)
        for destination, raw in generated.items():
            if destination.exists() and destination.read_bytes() != raw:
                raise ValueError(f"world pool content collision: {destination}")
            if not destination.exists():
                pool[destination] = raw
        if result == source:
            continue
        target = stage / "files" / glb.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(result)
        changes.append({"path": glb.relative_to(root).as_posix(), "before_sha256": sha(source),
                        "after_sha256": sha(result), "before_bytes": len(source), "after_bytes": len(result),
                        "proof": proof})
        for record in proof["image_records"]:
            destination = (glb.parent / record["uri"]).resolve()
            if destination.exists():
                inputs[destination.relative_to(root).as_posix()] = record["source_sha256"]
    for destination, raw in sorted(pool.items()):
        target = stage / "files" / destination.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        changes.append({"path": destination.relative_to(root).as_posix(), "before_sha256": None,
                        "after_sha256": sha(raw), "before_bytes": 0, "after_bytes": len(raw), "kind": "new_image"})
    for path, raw in current_metadata(root, changes).items():
        old = path.read_bytes()
        name = path.relative_to(root).as_posix()
        inputs[name] = sha(old)
        target = stage / "files" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        changes.append({"path": name, "before_sha256": sha(old), "after_sha256": sha(raw),
                        "before_bytes": len(old), "after_bytes": len(raw), "kind": "current_metadata"})
    result = {"schema": "rabbitlands-scenery-image-plan-v1", "root": str(root), "stage": str(stage),
              "shipping_list_sha256": sha(shipping_list.read_bytes()), "inputs": inputs, "changes": changes,
              "models_checked": len([p for p in models if ".local" not in p.relative_to(root).parts]),
              "new_image_count": len(pool), "new_image_bytes": sum(map(len, pool.values())),
              "net_saved_bytes": sum(row["before_bytes"] - row["after_bytes"] for row in changes)}
    (stage / "plan.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def apply(plan_path: Path, recovery: Path) -> dict:
    record = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    root, stage, recovery = Path(record["root"]), Path(record["stage"]), recovery.resolve()
    if not recovery.is_relative_to(root / ".local") or recovery.exists():
        raise ValueError("recovery must be a new ignored repository .local directory")
    for name, expected in record["inputs"].items():
        if sha((root / name).read_bytes()) != expected:
            raise ValueError(f"source changed since plan: {name}")
    for row in record["changes"]:
        target = root / row["path"]
        staged = stage / "files" / row["path"]
        if sha(staged.read_bytes()) != row["after_sha256"]:
            raise ValueError(f"staged output changed: {row['path']}")
        if row["before_sha256"] is None and target.exists():
            raise ValueError(f"new destination already exists: {target}")
    recovery.mkdir(parents=True)
    # Recovery is complete and verified before the first source mutation.
    for row in record["changes"]:
        if row["before_sha256"] is not None:
            old = (root / row["path"]).read_bytes()
            backup = recovery / row["path"]
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(old)
            if sha(backup.read_bytes()) != row["before_sha256"]:
                raise ValueError("recovery verification failed")
    for row in record["changes"]:
        target = root / row["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".scenery-image-tmp")
        temporary.write_bytes((stage / "files" / row["path"]).read_bytes())
        temporary.replace(target)
    for row in record["changes"]:
        if row.get("kind") not in {"new_image", "current_metadata"}:
            validate(root, root / row["path"])
    receipt = {"schema": record["schema"], "plan_sha256": sha(plan_path.read_bytes()),
               "net_saved_bytes": record["net_saved_bytes"], "changed_files": len(record["changes"]),
               "all_external_source_hashes_verified": True}
    (recovery / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    planner = commands.add_parser("plan")
    planner.add_argument("--root", type=Path, required=True)
    planner.add_argument("--shipping-list", type=Path, required=True)
    planner.add_argument("--stage", type=Path, required=True)
    installer = commands.add_parser("apply")
    installer.add_argument("--plan", type=Path, required=True)
    installer.add_argument("--recovery", type=Path, required=True)
    options = parser.parse_args()
    result = plan(options.root, options.shipping_list, options.stage) if options.command == "plan" else apply(options.plan, options.recovery)
    print(json.dumps({key: value for key, value in result.items() if key not in {"inputs", "changes"}}, indent=2))


if __name__ == "__main__":
    main()
