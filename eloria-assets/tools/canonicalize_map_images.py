#!/usr/bin/env python3
"""Deduplicate byte-identical map images without changing texture delivery policy.

Plan against the CURRENT combined checkout, after geometry consolidation::

    python eloria-assets/tools/canonicalize_map_images.py --plan .local/images/plan.json
    python eloria-assets/tools/canonicalize_map_images.py --apply .local/images/plan.json \
        --recovery .local/images/recovery

The ignored plan stages JSON-only GLB rewrites, preserving every non-JSON chunk
byte, plus literal/resource/hash updates. Original policy directories remain explicit
in image extras and manifest/index policy collections. Apply checks every scanned input SHA,
backs up all affected originals, verifies the complete graph and original
sidecar planning policy, then removes duplicate images. A failure restores the
originals. No decoder, encoder, GPU, Godot import or geometry builder is invoked.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import shutil
import struct
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "godot-client" / "tools"))
import build_vram_textures as vram

SCHEMA = "rabbitlands-map-image-canonicalization-v1"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
TEXT_SUFFIXES = {".json", ".gltf", ".gd", ".tscn", ".tres", ".cfg", ".py", ".md",
                 ".txt", ".toml", ".yaml", ".yml", ".html", ".js", ".css", ".svg"}
QUOTED = re.compile(r'''(["'])([^"'\r\n]+)\1''')
SHA = re.compile(r"^[0-9a-f]{64}$")
RELEASE_SKIP = ["_shared/images"]
RELEASE_UNSKIP = ["continent-v2/landfall_town"]


class CanonicalizationError(ValueError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inside(root: Path, relative: str) -> Path:
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()):
        raise CanonicalizationError(f"path escapes checkout: {relative}")
    return path


def tracked_files(root: Path) -> list[str]:
    result = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                            cwd=root, check=True, capture_output=True)
    return sorted({name for name in result.stdout.decode("utf-8").split("\0")
                   if name and (root / name).is_file()})


def ignored(root: Path, directory: Path) -> None:
    relative = directory.resolve().relative_to(root.resolve()).as_posix()
    result = subprocess.run(["git", "check-ignore", "-q", "--", relative + "/"], cwd=root)
    if result.returncode:
        raise CanonicalizationError(f"local stage/recovery must be Git-ignored: {relative}")


def resolve_reference(owner: str, value: str, base: str | None = None) -> tuple[str, str] | None:
    """Lexical resolution avoids an expensive filesystem realpath per material URI."""
    if not isinstance(value, str) or not value or "\0" in value or "\n" in value:
        return None
    value = value.replace("\\", "/")
    if value.startswith("res://../"):
        target, kind = value[9:], "res-parent"
    elif value.startswith("res://"):
        target, kind = "godot-client/" + value[6:], "res"
    elif value.startswith(("eloria-assets/", "godot-client/")):
        target, kind = value, "root"
    elif ":" in value or value.startswith("/") or "?" in value or "#" in value:
        return None
    else:
        target, kind = posixpath.join(base or posixpath.dirname(owner), value), "relative"
    target = posixpath.normpath(target)
    if target == ".." or target.startswith("../"):
        return None
    return target, kind


def rebase(owner: str, value: str, aliases: dict[str, str], base: str | None = None) -> str:
    resolved = resolve_reference(owner, value, base)
    if resolved is None or resolved[0] not in aliases:
        return value
    target, kind = aliases[resolved[0]], resolved[1]
    if kind == "res-parent":
        return "res://../" + target
    if kind == "res":
        if not target.startswith("godot-client/"):
            return "res://../" + target
        return "res://" + target[len("godot-client/"):]
    if kind == "root":
        return target
    return posixpath.relpath(target, base or posixpath.dirname(owner) or ".")


def document_base(owner: str, document: object) -> str:
    if owner.endswith("/world.json") and isinstance(document, dict):
        glb = document.get("asset", {}).get("glb", "world.glb")
        resolved = resolve_reference(owner, str(glb))
        if resolved:
            return posixpath.dirname(resolved[0])
    return posixpath.dirname(owner)


POLICY_DIRECTORY_EXTRA = "rl_texture_policy_directory"
POLICY_COLLECTION = "externalImagePolicies"

def _policy_uri(owner: str, descriptor: dict) -> str:
    extras = descriptor.get("extras", {})
    if isinstance(extras, dict) and POLICY_DIRECTORY_EXTRA in extras:
        uri = extras[POLICY_DIRECTORY_EXTRA]
        resolved = resolve_reference(owner, uri) if isinstance(uri, str) else None
        if not resolved or not resolved[0].startswith("eloria-assets/maps/") or ":" in uri or "%" in uri or "\\" in uri:
            raise CanonicalizationError(f"unsafe image policy in {owner}: {uri!r}")
        return uri
    resolved = resolve_reference(owner, str(descriptor.get("uri", "")))
    if not resolved: raise CanonicalizationError(f"unresolvable image in {owner}")
    return posixpath.relpath(posixpath.dirname(resolved[0]), posixpath.dirname(owner))


def annotate_policies(owner: str, document: object, aliases: dict[str, str]) -> object:
    document = json.loads(json.dumps(document))
    touched = set(aliases) | set(aliases.values())
    material_policies = defaultdict(set)
    descriptor_policies = defaultdict(set)
    def images(value):
        if isinstance(value, dict):
            for image in value.get("images", []) if isinstance(value.get("images"), list) else []:
                if not isinstance(image, dict) or not isinstance(image.get("uri"), str): continue
                resolved = resolve_reference(owner, image["uri"])
                explicit = isinstance(image.get("extras"), dict) and POLICY_DIRECTORY_EXTRA in image["extras"]
                if resolved and (resolved[0] in touched or explicit):
                    policy = _policy_uri(owner, image)
                    extras = image.setdefault("extras", {})
                    if not isinstance(extras, dict): raise CanonicalizationError(f"invalid image extras in {owner}")
                    extras[POLICY_DIRECTORY_EXTRA] = policy
                    material_policies[rebase(owner, image["uri"], aliases)].add(policy)
                if resolved:
                    descriptor_policies[rebase(owner, image["uri"], aliases)].add(isinstance(image.get("extras"), dict) and POLICY_DIRECTORY_EXTRA in image["extras"])
            for child in value.values(): images(child)
        elif isinstance(value, list):
            for child in value: images(child)
    images(document)
    if any(True in values and False in values for values in descriptor_policies.values()):
        raise CanonicalizationError(f"ambiguous original image policy in {owner}; restore missing descriptor extras")
    def collection(resources, previous, base):
        result = defaultdict(set)
        if not isinstance(previous, dict): raise CanonicalizationError(f"invalid policy collection in {owner}")
        if set(previous) - set(resources): raise CanonicalizationError(f"unknown image policy keys in {owner}")
        for uri in resources:
            resolved = resolve_reference(owner, uri, base)
            new_uri = rebase(owner, uri, aliases, base)
            if uri in previous:
                values = previous[uri]
                if not isinstance(values, list) or not values: raise CanonicalizationError(f"invalid policy collection in {owner}: {uri}")
                for value in values:
                    policy = resolve_reference(owner, value, base) if isinstance(value, str) else None
                    if not policy or not policy[0].startswith("eloria-assets/maps/") or ":" in value or "%" in value or "\\" in value:
                        raise CanonicalizationError(f"unsafe image policy in {owner}: {value!r}")
                    result[new_uri].add(value)
            elif new_uri in material_policies:
                result[new_uri].update(material_policies[new_uri])
            elif resolved and resolved[0] in touched:
                result[new_uri].add(posixpath.relpath(posixpath.dirname(resolved[0]), base))
        return {uri: sorted(values) for uri, values in sorted(result.items())}
    if isinstance(document, dict):
        resources = document.get("externalResources")
        if isinstance(resources, dict):
            policies = collection(resources, document.get(POLICY_COLLECTION, {}), document_base(owner, document))
            if policies: document[POLICY_COLLECTION] = policies
        prototypes = document.get("prototypes", {})
        if isinstance(prototypes, dict):
            for entry in prototypes.values():
                if isinstance(entry, dict) and isinstance(entry.get("images"), dict):
                    policies = collection(entry["images"], entry.get("imagePolicies", {}), posixpath.dirname(owner))
                    if policies: entry["imagePolicies"] = policies
        if owner.endswith("/roads.json") and material_policies:
            previous = document.get(POLICY_COLLECTION, {})
            for uri, values in previous.items(): material_policies[rebase(owner, uri, aliases)].update(values)
            document[POLICY_COLLECTION] = {uri: sorted(values) for uri, values in sorted(material_policies.items())}
    return document


def rewrite_document(owner: str, document: object, aliases: dict[str, str]) -> object:
    document = annotate_policies(owner, document, aliases)
    resource_base = document_base(owner, document)

    def walk(value: object, base: str) -> object:
        if isinstance(value, dict):
            out = {}
            for key, item in value.items():
                new_key = rebase(owner, key, aliases, base)
                child_base = resource_base if key == "externalResources" else base
                if key == "externalResources":
                    new_key = key
                converted = walk(item, child_base)
                if new_key in out and out[new_key] != converted:
                    raise CanonicalizationError(f"conflicting reference aliases in {owner}: {new_key}")
                out[new_key] = converted
            return out
        if isinstance(value, list):
            return [walk(item, base) for item in value]
        if isinstance(value, str):
            return rebase(owner, value, aliases, base)
        return value
    return walk(document, posixpath.dirname(owner))


def glb_parts(path: Path) -> tuple[dict, bytes]:
    """Keep all non-JSON chunks, external-buffer URIs and padding exactly intact."""
    data = path.read_bytes()
    if len(data) < 20:
        raise CanonicalizationError(f"short GLB: {path}")
    magic, version, length, json_length, kind = struct.unpack_from("<4sIII4s", data)
    if magic != b"glTF" or version != 2 or length != len(data) or kind != b"JSON":
        raise CanonicalizationError(f"invalid GLB: {path}")
    end = 20 + json_length
    if end > len(data) or json_length % 4:
        raise CanonicalizationError(f"invalid GLB JSON span: {path}")
    return json.loads(data[20:end]), data[end:]


def glb_bytes(document: dict, rest: bytes) -> bytes:
    raw = json.dumps(document, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    raw += b" " * (-len(raw) % 4)
    return struct.pack("<4sIII4s", b"glTF", 2, 20 + len(raw) + len(rest), len(raw), b"JSON") + raw + rest


def policy_inventory(root: Path) -> dict[str, dict]:
    public_inputs = {root / name for name in tracked_files(root) if name.endswith("/world.json") or (name.startswith("eloria-assets/maps/_shared/meshes/") and name.endswith(".glb"))}
    try:
        found = vram.inventory([(root / "eloria-assets/maps").resolve()], input_files=public_inputs)
    except vram.BuildError as error:
        if "undeclared" not in str(error):
            raise
        raise CanonicalizationError(
            "Original texture policy metadata is missing or inconsistent. Repair externalImagePolicies "
            "from the owning GLB descriptors, or prototype imagePolicies via shared_meshes.reconcile(); "
            "refusing to infer original policy from the canonical pixel directory. " + str(error)) from error
    return {directory.resolve().relative_to(root.resolve()).as_posix() + "|" + sha:
            {"sha256": sha, "source": record["path"].resolve().relative_to(root.resolve()).as_posix(),
             **vram.delivery_policy(record, directory, RELEASE_SKIP, RELEASE_UNSKIP)}
            for (directory, sha), record in found.items()}


def candidate_image(name: str) -> bool:
    return name.startswith("eloria-assets/maps/") and ("/shared-assets/" in name or "/_shared/images/" in name) and Path(name).suffix.lower() in IMAGE_SUFFIXES


def unplanned(sha: str) -> dict:
    return {"sha256": sha, "recipe": None, "reason": "not_planned", "roles": [],
            "rolePairs": [], "cutoffs": []}


def choose_aliases(root: Path, images: list[str], policies: dict[str, dict]) -> tuple[dict, list, dict]:
    by_bytes, by_policy = defaultdict(list), defaultdict(list)
    for relative in images:
        path = inside(root, relative)
        sha = file_sha(path)
        row = {"path": relative, "sha256": sha, "bytes": path.stat().st_size}
        by_bytes[sha].append(row)
        by_policy[sha].append(row)
    aliases, deletions = {}, []
    def preference(row):
        name = row["path"]
        # Prefer an existing copy, never move raw-only contents into an enabled folder.
        pool = 0 if "/nymara-regions/_continent/shared-assets/" in name else 1 if "/continent-v2/_continent_v2/shared-assets/" in name else 2
        return pool, name
    for group in by_policy.values():
        canonical = min(group, key=preference)["path"]
        for row in group:
            if row["path"] != canonical:
                aliases[row["path"]] = canonical
                deletions.append({**row, "canonical": canonical})
    summary = {"images": len(images), "imageBytes": sum(row["bytes"] for group in by_bytes.values() for row in group),
               "unrestrictedDuplicateBytes": sum(group[0]["bytes"] * (len(group) - 1) for group in by_bytes.values()),
               "safeDuplicateBytes": sum(row["bytes"] for row in deletions),
               "safeDuplicateFiles": len(deletions),
               "policyMode": "preserved-original-directory"}
    return dict(sorted(aliases.items())), sorted(deletions, key=lambda row: row["path"]), summary


def refresh_hash_links(owner: str, document: object, hashes: dict[str, str],
                       sizes: dict[str, int], original_hashes: dict[str, str]) -> object:
    """Refresh live file references, not historical source/provenance SHA tokens."""
    resource_base = document_base(owner, document)
    def walk(value, base, field=""):
        if isinstance(value, list):
            return [walk(item, base, field) for item in value]
        if not isinstance(value, dict):
            return value
        out = {key: walk(item, resource_base if key == "externalResources" else base, key)
               for key, item in value.items()}
        # Dictionaries such as externalResources, externalMeshes and road resources.
        for uri, declared in list(out.items()):
            resolved = resolve_reference(owner, uri, base)
            if isinstance(declared, str) and SHA.fullmatch(declared) and resolved:
                target = resolved[0]
                if field in {"externalResources", "externalMeshes", "resources", "images"} and target in hashes and hashes[target] != original_hashes[target]:
                    if declared not in {original_hashes[target], hashes[target]}:
                        raise CanonicalizationError(f"stale file hash in {owner}: {uri}")
                    out[uri] = hashes[target]
        # A file+sha256 record (roadGround, field mip, glTF asset, map index, ...).
        if isinstance(out.get("sha256"), str):
            targets = []
            for key in ("metadata", "file", "path", "uri", "texture", "glb", "manifest"):
                if isinstance(out.get(key), str):
                    resolved = resolve_reference(owner, out[key], base)
                    if resolved and resolved[0] in hashes:
                        targets.append(resolved[0])
            matches = [target for target in targets if out["sha256"] in {original_hashes[target], hashes[target]}]
            if len(set(matches)) == 1:
                target = matches[0]
                out["sha256"] = hashes[target]
                if "bytes" in out:
                    out["bytes"] = sizes[target]
        return out
    result = walk(document, posixpath.dirname(owner))
    if isinstance(result, dict) and isinstance(result.get("prototypes"), dict):
        for stem, record in result["prototypes"].items():
            target = posixpath.join(posixpath.dirname(owner), stem + ".glb")
            if target in hashes and isinstance(record, dict):
                if record.get("sha256") not in {original_hashes[target], hashes[target]}:
                    raise CanonicalizationError(f"stale prototype hash in {owner}: {stem}")
                record["sha256"], record["bytes"] = hashes[target], sizes[target]
    if isinstance(result, dict) and isinstance(result.get("mapMeshCopies"), dict):
        for target, record in result["mapMeshCopies"].items():
            if target in hashes and hashes[target] != original_hashes[target] and isinstance(record, dict):
                if record.get("sha256") not in {original_hashes[target], hashes[target]}:
                    raise CanonicalizationError(f"stale retirement binding in {owner}: {target}")
                record["sha256"] = hashes[target]
    if owner.endswith("/world.json") and isinstance(result, dict):
        resolved = resolve_reference(owner, str(result.get("asset", {}).get("glb", "world.glb")))
        if resolved and resolved[0] in sizes and isinstance(result.get("performance"), dict):
            if "glbBytes" in result["performance"]:
                result["performance"]["glbBytes"] = sizes[resolved[0]]
    return result


def verify_graph(root: Path, files: list[str], aliases: dict[str, str], stage: Path | None = None) -> None:
    """All image-bearing literals in every tracked text/GLB resolve after deletion."""
    removed = set(aliases)
    canonical = set(aliases.values())
    names = set(files) - removed
    def verify(owner, value, base=None):
        if isinstance(value, dict):
            for key, item in value.items():
                verify(owner, key, base)
                verify(owner, item, document_base(owner, document) if key == "externalResources" else base)
        elif isinstance(value, list):
            for item in value:
                verify(owner, item, base)
        elif isinstance(value, str):
            resolved = resolve_reference(owner, value, base)
            if resolved and resolved[0] in removed:
                raise CanonicalizationError(f"dangling removed-image reference in {owner}: {value}")
            # Only validate dependencies touched by this pass: older authoring
            # records can deliberately name archived/non-runtime source inputs.
            if resolved and resolved[0] in canonical and resolved[0] not in names:
                raise CanonicalizationError(f"canonical image is absent: {resolved[0]}")
    for relative in files:
        if relative in removed:
            continue
        path = stage / relative if stage and (stage / relative).is_file() else root / relative
        suffix = path.suffix.lower()
        if suffix == ".glb":
            document, _ = glb_parts(path)
            verify(relative, document)
        elif suffix in {".json", ".gltf"}:
            try:
                document = json.loads(path.read_text(encoding="utf-8-sig"))
            except (UnicodeError, ValueError):
                continue
            # world externalResources are relative to asset.glb, which may be in a child directory.
            verify(relative, document)
            if isinstance(document, dict) and "externalResources" in document:
                verify(relative, document["externalResources"], document_base(relative, document))
        elif suffix in TEXT_SUFFIXES:
            try:
                text = path.read_text(encoding="utf-8-sig")
            except UnicodeError:
                continue
            for match in QUOTED.finditer(text):
                verify(relative, match[2])


def make_plan(root: Path, plan_path: Path, *, files: list[str] | None = None,
              images: list[str] | None = None, policies: dict[str, dict] | None = None) -> dict:
    root = root.resolve();plan_path = plan_path.resolve();files = tracked_files(root) if files is None else sorted(files)
    if plan_path.exists() or plan_path.with_suffix("").exists():
        raise CanonicalizationError("use a fresh plan path; existing plans and stages are never overwritten")
    images = images if images is not None else [name for name in files if candidate_image(name)]
    if any(name not in files or not name.startswith("eloria-assets/maps/") for name in images):
        raise CanonicalizationError("selected images must be existing tracked map files")
    policies = policy_inventory(root) if policies is None else policies
    aliases, deletes, summary = choose_aliases(root, sorted(set(images)), policies)
    stage = plan_path.with_suffix("") / "stage";stage.mkdir(parents=True)
    inputs, hashes, sizes, documents = {}, {}, {}, {}
    changes = {}
    def remember(name, raw):
        inputs[name] = digest(raw);hashes[name] = inputs[name];sizes[name] = len(raw)
    def publish(name, raw, kind, **proof):
        target = inside(stage, name);target.parent.mkdir(parents=True, exist_ok=True);target.write_bytes(raw)
        hashes[name], sizes[name] = digest(raw), len(raw)
        changes[name] = {"path": name, "before": inputs[name], "after": hashes[name], "bytes": len(raw), "kind": kind, **proof}
    for name in files:
        suffix = Path(name).suffix.lower()
        if suffix not in TEXT_SUFFIXES | {".glb"} and name not in images:
            continue
        path = inside(root, name);raw = path.read_bytes();remember(name, raw)
        if suffix == ".glb":
            document, rest = glb_parts(path)
            converted = rewrite_document(name, document, aliases)
            if converted != document:
                output = glb_bytes(converted, rest)
                publish(name, output, "glb-json", nonJsonSha256=digest(rest))
        elif suffix in {".json", ".gltf"}:
            try:
                documents[name] = rewrite_document(name, json.loads(raw.decode("utf-8-sig")), aliases)
            except (UnicodeError, json.JSONDecodeError):
                continue
        elif suffix in TEXT_SUFFIXES:
            try:
                text = raw.decode("utf-8")
            except UnicodeError:
                continue
            converted = QUOTED.sub(lambda match: match[1] + rebase(name, match[2], aliases) + match[1], text)
            if converted != text:
                publish(name, converted.encode("utf-8"), "text-literals")
    for policy in policies.values():
        source = policy["source"]
        actual = inputs.get(source) or file_sha(inside(root, source))
        if actual != policy["sha256"]:
            raise CanonicalizationError(f"image differs from declared source hash: {source}")
        if source not in inputs:
            inputs[source] = hashes[source] = actual
            sizes[source] = inside(root, source).stat().st_size
    originals = dict(inputs)
    # Child metadata hashes precede parents; no circular file hash fixpoints are accepted.
    for iteration in range(16):
        advanced = False
        for name, document in list(documents.items()):
            refreshed = refresh_hash_links(name, document, hashes, sizes, originals)
            raw = (json.dumps(refreshed, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
            original_document = json.loads((root / name).read_text(encoding="utf-8-sig"))
            if refreshed != original_document:
                if digest(raw) != hashes[name]:
                    publish(name, raw, "json-references")
                    advanced = True
            documents[name] = refreshed
        if not advanced:
            break
    else:
        raise CanonicalizationError("cyclic or unstable JSON hash dependencies")
    verify_graph(root, files, aliases, stage)
    for item in changes.values():
        if item["kind"] == "glb-json":
            before_doc, before_rest = glb_parts(root / item["path"])
            after_doc, after_rest = glb_parts(stage / item["path"])
            if before_rest != after_rest or rewrite_document(item["path"], before_doc, aliases) != after_doc:
                raise CanonicalizationError(f"non-reference GLB change: {item['path']}")
    plan = {"schema": SCHEMA, "root": str(root), "stage": str(stage), "summary": summary,
            "releasePolicy": {"skip": RELEASE_SKIP, "unskip": RELEASE_UNSKIP},
            "files": files, "inputs": inputs, "aliases": aliases, "deletes": deletes,
            "changes": list(changes.values()), "policies": policies}
    plan_path.parent.mkdir(parents=True, exist_ok=True);plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    return plan


def apply_plan(root: Path, plan_path: Path, recovery: Path, *, verify_policy=True) -> dict:
    root=root.resolve();plan=json.loads(plan_path.read_text(encoding="utf-8"));stage=Path(plan["stage"])
    if plan.get("schema") != SCHEMA or Path(plan.get("root", "")).resolve() != root:
        raise CanonicalizationError("plan schema/root mismatch")
    if recovery.exists():
        raise CanonicalizationError("use a fresh recovery directory")
    for relative, expected in plan["inputs"].items():
        if file_sha(inside(root, relative)) != expected:
            raise CanonicalizationError(f"stale plan input: {relative}")
    for item in plan["changes"]:
        if file_sha(inside(stage, item["path"])) != item["after"]:
            raise CanonicalizationError(f"corrupt staged file: {item['path']}")
    affected = sorted({item["path"] for item in plan["changes"] + plan["deletes"]})
    recovery.mkdir(parents=True)
    for relative in affected:
        backup=inside(recovery,relative);backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(inside(root,relative),backup)
    (recovery/"receipt.json").write_text(json.dumps({"schema":SCHEMA,"planSha256":file_sha(plan_path),"paths":affected},indent=2)+"\n")
    try:
        for item in plan["changes"]:
            shutil.copyfile(inside(stage,item["path"]),inside(root,item["path"]))
        verify_graph(root,plan["files"],plan["aliases"])
        if verify_policy:
            current=policy_inventory(root)
            expected_records = {}
            for key, before in plan["policies"].items():
                expected = dict(before)
                expected["source"] = plan["aliases"].get(expected["source"], expected["source"])
                expected_records[key] = expected
            if current != expected_records:
                changed = sorted(key for key in set(current) | set(expected_records) if current.get(key) != expected_records.get(key))
                raise CanonicalizationError("texture policy changed: " + ", ".join(changed[:8]))
        # Delete last, only after graph, source hashes and policy have passed.
        for item in plan["deletes"]:
            if file_sha(inside(root,item["canonical"])) != item["sha256"]:
                raise CanonicalizationError(f"canonical image changed: {item['canonical']}")
            inside(root,item["path"]).unlink()
        verify_graph(root,plan["files"],plan["aliases"])
    except Exception:
        for relative in affected:
            shutil.copy2(inside(recovery,relative),inside(root,relative))
        raise
    return plan["summary"]


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=REPO)
    group=parser.add_mutually_exclusive_group(required=True);group.add_argument("--plan",type=Path);group.add_argument("--apply",type=Path)
    parser.add_argument("--recovery",type=Path);parser.add_argument("--images-from",type=Path,help="package selection JSON with files:[{path,...}] to limit candidate images")
    options=parser.parse_args();root=options.root.resolve()
    try:
        if options.plan:
            ignored(root,options.plan.parent)
            images=None
            if options.images_from:
                rows=json.loads(options.images_from.read_text(encoding="utf-8"))["files"]
                images=[row["path"] for row in rows if candidate_image(row["path"])]
            plan=make_plan(root,options.plan,images=images);summary=plan["summary"]
        else:
            if options.recovery is None:
                raise CanonicalizationError("--apply requires an ignored --recovery directory")
            ignored(root,options.recovery);summary=apply_plan(root,options.apply,options.recovery)
        print(json.dumps(summary,indent=2));return 0
    except (CanonicalizationError,OSError,ValueError,subprocess.CalledProcessError) as error:
        print(f"image canonicalization: {error}",file=sys.stderr);return 1


if __name__ == "__main__":
    raise SystemExit(main())
