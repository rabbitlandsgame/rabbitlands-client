"""Plan/validate optional exact-variant native content; never launch Godot.

Run against an isolated disposable package project after its imports and map
sidecars match the final package. The caller owns engine scheduling. Source and
raw files remain present. Exact runtime imports/products are snapshotted only
inside an explicitly marked disposable cook project; authored trees stay out
of the preparation/export workflow.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import struct
import shutil
from urllib.parse import unquote

SCHEMA = 1
POLICY = "rabbitlands-native-prepared-v2"
FULL_KIT_A = {0: 114, 1: 106, 2: 0, 3: 117, 4: 171, 5: 184, 6: 192}
PILOT_WORLD = "eloria-assets/maps/nymara-regions/whitehorn_range/chunks/05_01/world.json"
PILOT_INTERIOR = "eloria-assets/maps/nymara-regions/interiors/amethyst_barrens_secrets/world.json"
HEX = re.compile(r"[0-9a-f]{64}\Z")
RUNTIME_IMPORT_POLICY = "actual-pck-runtime-imports-v1"
RUNTIME_IMPORT_MARKER = ".prepared-runtime-inputs.json"


class PreparedError(ValueError):
    pass


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def scoped(root: Path, relative: str) -> Path:
    value = PurePosixPath(relative)
    if "\\" in relative or ":" in relative or value.is_absolute():
        raise PreparedError(f"nonportable asset path: {relative}")
    actual = (root / relative).resolve()
    if not actual.is_relative_to(root.resolve()):
        raise PreparedError(f"asset escaped isolated root: {relative}")
    return actual


def logical(path: Path, repository: Path) -> str:
    value = path.resolve().relative_to(repository.resolve()).as_posix()
    if not value.startswith(("godot-client/", "eloria-assets/")):
        raise PreparedError(f"not an approved runtime scope: {value}")
    return value


class ExportView:
    """Exact selected runtime bytes. Directory metadata/MD5 is never evidence."""
    def __init__(self, stage: Path):
        from benchmark_asset_closure import pck_index
        self.stage = stage.resolve()
        self.pck = self.stage / "app/RabbitLands.pck"
        self.entries = {row["path"]: row for row in pck_index(self.pck)["entries"]}

    def read(self, name: str, maximum: int = 1 << 20) -> bytes:
        row = self.entries.get(name)
        if row is None or row["bytes"] > maximum:
            raise PreparedError(f"missing or oversized selected PCK input: {name}")
        with self.pck.open("rb") as stream:
            stream.seek(row["offset"])
            data = stream.read(row["bytes"])
        if len(data) != row["bytes"]:
            raise PreparedError(f"truncated selected PCK input: {name}")
        return data

    def copy(self, name: str, destination: Path) -> None:
        row = self.entries[name]
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self.pck.open("rb") as source, destination.open("wb") as target:
            source.seek(row["offset"])
            remaining = row["bytes"]
            while remaining:
                data = source.read(min(1 << 20, remaining))
                if not data:
                    raise PreparedError(f"truncated selected PCK input: {name}")
                target.write(data)
                remaining -= len(data)

    def runtime_hash(self, name: str) -> str:
        if name.startswith("eloria-assets/"):
            return digest(scoped(self.stage, name))
        if not name.startswith("godot-client/"):
            raise PreparedError(f"unknown runtime input scope: {name}")
        local = name.removeprefix("godot-client/")
        loose = scoped(self.stage / "app", local)
        row = self.entries.get(local)
        if row is None:
            if loose.is_file():
                return digest(loose)
            raise PreparedError(f"prepared runtime dependency not exported: {name}")
        hashing = hashlib.sha256()
        with self.pck.open("rb") as stream:
            stream.seek(row["offset"])
            remaining = row["bytes"]
            while remaining:
                data = stream.read(min(1 << 20, remaining))
                if not data:
                    raise PreparedError(f"truncated selected PCK input: {name}")
                hashing.update(data)
                remaining -= len(data)
        actual = hashing.hexdigest()
        if loose.is_file() and digest(loose) != actual:
            raise PreparedError(f"ambiguous loose/PCK input identity: {name}")
        return actual


def marked_project(project: Path) -> None:
    marker = project / ".prepared-cook-project.json"
    if not marker.is_file() or json.loads(marker.read_text(encoding="utf-8")).get("purpose") != "disposable-native-cook":
        raise PreparedError("only an explicitly marked disposable cook project may be modified")


def snapshot_runtime_imports(project: Path, stage: Path, targets: list[tuple[str, str]]) -> dict:
    """Copy only selected .import/actual products from an existing real PCK.

    Original full editor-import SHA and product SHA remain provenance. The
    cooker reads exact runtime bytes, including exporter changes and NUL. No
    predicted exporter serialization, new import, editor or engine is involved.
    """
    project = project.resolve()
    marked_project(project)
    marker = project / RUNTIME_IMPORT_MARKER
    if marker.exists():
        raise PreparedError("runtime input snapshot already exists; use it unchanged or prepare a fresh disposable project")
    remaps: set[str] = set()
    for _kind, source in targets:
        closure = Closure(project)
        closure.visit(scoped(project.parent, source))
        remaps.update(name for name in closure.files if name.endswith(".import"))
    view = ExportView(stage)
    payloads: dict[str, str] = {}
    provenance: dict[str, dict] = {}
    for name in sorted(remaps):
        local = name.removeprefix("godot-client/")
        original = scoped(project.parent, name)
        original_text = original.read_text(encoding="utf-8")
        raw = view.read(local)
        try:
            runtime_text = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise PreparedError(f"invalid actual runtime import record: {name}") from error
        products = set(re.findall(r'"(res://\.godot/imported/[^"\r\n\x00]+)"', runtime_text))
        original_products = set(re.findall(r'"(res://\.godot/imported/[^"\r\n\x00]+)"', original_text))
        if not products or not products.issubset(original_products):
            raise PreparedError(f"actual runtime remap has missing/foreign source product: {name}")
        names = [name, *("godot-client/" + product.removeprefix("res://") for product in sorted(products))]
        for dependency in names:
            actual = scoped(project.parent, dependency)
            if not actual.is_file():
                raise PreparedError(f"original selected import input missing: {dependency}")
            pck_name = dependency.removeprefix("godot-client/")
            if pck_name not in view.entries:
                raise PreparedError(f"selected actual runtime import product missing: {dependency}")
            runtime_sha = view.runtime_hash(dependency)
            payloads[dependency] = runtime_sha
            provenance[dependency] = {"path": dependency, "source_sha256": digest(actual),
                "sha256": runtime_sha, "view": RUNTIME_IMPORT_POLICY,
                "kind": "import-remap" if dependency.endswith(".import") else "import-product"}
            if dependency.endswith(".import"):
                image_source=Path(str(actual).removesuffix(".import"))
                if image_source.is_file():
                    provenance[dependency]["source_image"]={"path":logical(image_source,project.parent),
                        "sha256":digest(image_source)}
    # Validate all selected bytes/paths before mutating this disposable tree.
    records = [provenance[name] for name in sorted(provenance)]
    snapshot_id = hashlib.sha256(json.dumps(records, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    for name in sorted(payloads):
        target = scoped(project.parent, name)
        view.copy(name.removeprefix("godot-client/"), target)
        if digest(target) != payloads[name]:
            raise PreparedError(f"PCK input changed while snapshotting: {name}; discard the disposable project")
    result = {"schema_version": 1, "policy": RUNTIME_IMPORT_POLICY, "snapshot_id": snapshot_id,
              "records": records, "status": "exact-selected-runtime-bytes; no engine launched"}
    marker.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def runtime_import_provenance(project: Path, files: dict[str, str]) -> dict:
    remaps = {name for name in files if name.endswith(".import")}
    marker = project / RUNTIME_IMPORT_MARKER
    if not remaps:
        return {"policy": RUNTIME_IMPORT_POLICY, "records": []}
    if not marker.is_file():
        raise PreparedError("selected imported images require an actual-PCK runtime import snapshot before cooking")
    document = json.loads(marker.read_text(encoding="utf-8"))
    if document.get("schema_version") != 1 or document.get("policy") != RUNTIME_IMPORT_POLICY:
        raise PreparedError("unsupported runtime input snapshot")
    records = document.get("records", [])
    identity = hashlib.sha256(json.dumps(records, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if identity != document.get("snapshot_id"):
        raise PreparedError("runtime input snapshot metadata changed")
    selected = {row["path"]: row for row in records if row.get("path") in files}
    if not remaps.issubset(selected):
        raise PreparedError("selected remap is not covered by the actual runtime snapshot")
    for name, record in selected.items():
        if record.get("view") != RUNTIME_IMPORT_POLICY or not HEX.fullmatch(str(record.get("source_sha256", ""))) \
                or files[name] != record.get("sha256") or digest(scoped(project.parent, name)) != record["sha256"]:
            raise PreparedError(f"selected runtime import snapshot no longer matches: {name}")
    return {"policy": RUNTIME_IMPORT_POLICY, "snapshot_id": identity,
            "records": [selected[name] for name in sorted(selected)]}


def gltf(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    if path.suffix.lower() == ".gltf":
        return json.loads(raw), b""
    if len(raw) < 20 or raw[:4] != b"glTF":
        raise PreparedError(f"not a glTF 2 binary: {path}")
    magic, version, length = struct.unpack_from("<4sII", raw)
    if version != 2 or length != len(raw):
        raise PreparedError(f"invalid glTF envelope: {path}")
    offset, document, binary = 12, None, b""
    while offset < length:
        if offset + 8 > length:
            raise PreparedError(f"truncated glTF chunk: {path}")
        size, kind = struct.unpack_from("<II", raw, offset)
        offset += 8
        if offset + size > length:
            raise PreparedError(f"truncated glTF data: {path}")
        chunk = raw[offset:offset + size]
        if kind == 0x4E4F534A:
            if document is not None:
                raise PreparedError("duplicate JSON glTF chunk")
            document = json.loads(chunk.rstrip(b"\x00 "))
        elif kind == 0x004E4942:
            binary = chunk
        offset += size
    if not isinstance(document, dict):
        raise PreparedError(f"missing glTF document: {path}")
    return document, binary


class Closure:
    def __init__(self, project: Path):
        self.project = project.resolve()
        self.repository = self.project.parent
        self.files: dict[str, str] = {}
        self.images: list[dict] = []
        self._visited: set[Path] = set()
        retired=self.project/"data/assets/retired_procedural_models.json"
        policy=json.loads(retired.read_text(encoding="utf-8")) if retired.is_file() else {}
        self.retired_prototypes=set(policy.get("retiredMapPrototypes",[]))
        self.retired_paths={"godot-client/assets/"+name for name in policy.get("runtimePaths",[])}
        if retired.is_file(): self.add(retired)

    def add(self, path: Path, expected: str | None = None) -> None:
        name = logical(path, self.repository)
        if not path.is_file():
            raise PreparedError(f"runtime dependency missing: {name}")
        actual = digest(path)
        if expected is not None and actual != expected:
            raise PreparedError(f"declared runtime dependency changed: {name}")
        self.files[name] = actual

    def uri(self, base: Path, value: str) -> Path:
        if not value or value.startswith("data:"):
            raise PreparedError("embedded URI is not a filesystem dependency")
        relative = unquote(value)
        if PurePosixPath(relative).is_absolute() or "\\" in relative or ":" in relative:
            raise PreparedError(f"nonrelative runtime URI: {value}")
        actual = scoped(self.repository, logical(base, self.repository) + "/" + relative)
        return actual

    def image(self, source: Path, index: int, spec: dict, doc: dict, binary: bytes) -> None:
        record = {"source": logical(source, self.repository), "index": index,
                  "mime": spec.get("mimeType", ""), "representation": "unchanged"}
        if "bufferView" in spec:
            view = doc.get("bufferViews", [])[int(spec["bufferView"])]
            if int(view.get("buffer", 0)) != 0 or not binary:
                raise PreparedError("embedded pilot image must use the GLB binary chunk")
            start, size = int(view.get("byteOffset", 0)), int(view["byteLength"])
            if min(start, size) < 0 or start + size > len(binary):
                raise PreparedError("embedded image view outside GLB")
            image = binary[start:start + size]
            record.update(storage="bufferView", bytes=size,
                          sha256=hashlib.sha256(image).hexdigest())
        elif str(spec.get("uri", "")).startswith("data:"):
            # The complete GLB/GLTF source is already hashed. Record this
            # explicitly; parsing/conversion of a data URI remains Godot-owned.
            record.update(storage="data-uri", source_covered=True)
        elif "uri" in spec:
            target = self.uri(source.parent, str(spec["uri"]))
            remap = Path(str(target) + ".import")
            if remap.is_file():
                self.add(remap)
                products = re.findall(r'"(res://\.godot/imported/[^"\r\n]+)"',
                                      remap.read_text(encoding="utf-8"))
                if not products:
                    raise PreparedError(f"texture import has no actual product: {remap}")
                for product in sorted(set(products)):
                    self.add(scoped(self.project, product.removeprefix("res://")))
                record.update(storage="import-products", import_remap=logical(remap, self.repository),
                              products=sorted(set(products)))
            else:
                self.add(target)
                record.update(storage="loose-uri", path=logical(target, self.repository))
            self.sidecars(target)
        else:
            raise PreparedError("image has neither bufferView nor URI")
        self.images.append(record)

    def sidecars(self, source: Path) -> None:
        index = source.parent / "vram/index.json"
        if not index.is_file():
            return
        self.add(index)
        document = json.loads(index.read_text(encoding="utf-8"))
        if document.get("schema") != 1 or document.get("recipeVersion") != 1:
            raise PreparedError(f"unknown sidecar recipe: {index}")
        if not source.is_file():
            return  # Imported URI image; its import products are the input.
        entry = document.get("images", {}).get(digest(source))
        if entry is None:
            return
        pool = str(entry.get("pool", "."))
        filename = str(entry.get("file", ""))
        if not filename or PurePosixPath(filename).name != filename:
            raise PreparedError("invalid sidecar filename")
        target = self.uri(source.parent, pool + "/vram/" + filename)
        self.add(target, str(entry.get("sha256", "")))

    def visit(self, path: Path) -> None:
        path = path.resolve()
        if logical(path,self.repository) in self.retired_paths:
            raise PreparedError("retired target is not a preparation source")
        if path in self._visited:
            return
        self._visited.add(path)
        self.add(path)
        if path.suffix.lower() in {".glb", ".gltf"}:
            doc, binary = gltf(path)
            for index, image in enumerate(doc.get("images", [])):
                self.image(path, index, image, doc, binary)
            for buffer in doc.get("buffers", []):
                uri = str(buffer.get("uri", ""))
                if uri and not uri.startswith("data:"):
                    self.add(self.uri(path.parent, uri))
        elif path.name == "world.json":
            doc = json.loads(path.read_text(encoding="utf-8"))
            if "streamingChunks" in doc:
                raise PreparedError("cook child packages, never a partially resident territory")
            self.visit(self.uri(path.parent, str(doc["asset"]["glb"])))
            for section in ("externalResources", "externalMeshes"):
                for uri, expected in sorted(doc.get(section, {}).items()):
                    if section == "externalMeshes" and PurePosixPath(uri).stem in self.retired_prototypes:
                        continue
                    dependency = self.uri(path.parent, uri)
                    self.add(dependency, expected)
                    if section == "externalMeshes":
                        self.visit(dependency)
                    else:
                        self.sidecars(dependency)
            # The mesh pool's image/index policy also affects canonical
            # prototype material references, even when the manifest uses none.
            for uri in doc.get("externalMeshes", {}):
                if PurePosixPath(uri).stem in self.retired_prototypes:
                    continue
                index = self.uri(path.parent, uri).parent / "index.json"
                if index.is_file():
                    self.add(index)


def resolve_equipped_actor(project: Path) -> list[str]:
    models = json.loads((project / "data/actors/models.json").read_text(encoding="utf-8"))
    equipment = json.loads((project / "data/actors/equipment.json").read_text(encoding="utf-8"))
    body = models["models"]["luminous_male"]
    paths = [body["scene"], body["animationLibrary"], body["hairStyles"][4]]
    groups = equipment.get("fitGroups", {}).get("luminous_male", [])
    for slot, item in FULL_KIT_A.items():
        key = f"{slot}:{item}"
        # Resolve the same explicit catalog fit precedence as Main. No
        # composite actor is baked and no compatibility identifier changes.
        aliases = equipment.get("aliases", {})
        seen: set[str] = set()
        while key in aliases:
            if key in seen:
                raise PreparedError("equipment alias cycle")
            seen.add(key)
            key = str(aliases[key])
        config = dict(equipment["models"][key])
        variants = config.get("variants", {})
        for group in groups:
            if group in variants:
                config.update(variants[group])
                break
        paths.append(config["scene"])
    return list(dict.fromkeys("godot-client/" + p.removeprefix("res://") for p in paths))


def pilot(project: Path, chunk: str = PILOT_WORLD) -> list[tuple[str, str]]:
    manifest = json.loads(scoped(project.parent, chunk).read_text(encoding="utf-8"))
    retired=Closure(project).retired_prototypes
    prototypes = sorted(uri for uri in manifest.get("externalMeshes", {}) if PurePosixPath(uri).stem not in retired)
    if not prototypes:
        raise PreparedError("pilot chunk must exercise a shared prototype")
    prototype = logical(scoped(project.parent, str(PurePosixPath(chunk).parent / prototypes[0])), project.parent)
    return [("world", chunk), ("mesh", prototype), ("world", PILOT_INTERIOR),
            ("scene", "godot-client/assets/world/interactives/storage.glb"),
            *[("scene", source) for source in resolve_equipped_actor(project)]]


def pilot_qualification_plan(project: Path, chunk: str = PILOT_WORLD) -> dict:
    """Exact sources and a geometrically selected point, never a grounding claim."""
    source=scoped(project.parent,chunk)
    document=json.loads(source.read_text(encoding="utf-8"))
    parent=source.parent.parent.parent/"world.json"
    territory=json.loads(parent.read_text(encoding="utf-8"))
    relative=source.relative_to(parent.parent).as_posix()
    entries=[row for row in territory.get("streamingChunks",{}).get("chunks",[]) if row.get("manifest")==relative]
    if len(entries)!=1 or territory.get("streamingChunks",{}).get("coordinateSpace")!="territory-local":
        raise PreparedError("pilot must have one exact territory-local selector entry")
    entry=entries[0]
    bounds=entry["bounds"]
    point=[(float(a)+float(b))/2 for a,b in zip(bounds["min"],bounds["max"])]
    coordinate=territory.get("coordinateTransform",{})
    origin=coordinate.get("origin",[0,0,0]);server_origin=coordinate.get("serverOrigin",[0,0])
    scale=float(coordinate.get("metresPerTile",1))
    if not math.isfinite(scale) or scale<=0:raise PreparedError("finite positive coordinate scale required")
    local_z=(point[2]-float(origin[2]))/scale
    tile=[math.floor((point[0]-float(origin[0]))/scale+float(server_origin[0])),
          math.floor((-local_z if coordinate.get("invertServerY",True) else local_z)+float(server_origin[1]))]
    tile_point=[float(origin[0])+(tile[0]+.5-float(server_origin[0]))*scale,
                float(coordinate.get("walkingHeight",origin[1])),
                float(origin[2])+(-1 if coordinate.get("invertServerY",True) else 1)*(tile[1]+.5-float(server_origin[1]))*scale]
    if not all(float(bounds["min"][axis])<=tile_point[axis]<=float(bounds["max"][axis]) for axis in (0,2)):
        raise PreparedError("pilot tile center escaped selected chunk horizontal bounds")
    targets=[{"kind":kind,"source":target,"required_consumed_entry":True} for kind,target in pilot(project,chunk)]
    return {"schema_version":1,"status":"source-planned; runtime grounding/selection still required",
        "territory_asset_id":territory["asset"]["id"],"territory_manifest":logical(parent,project.parent),
        "chunk_id":entry["id"],"chunk_source":chunk,"selector_bounds":bounds,"territory_local_center":point,
        "server_tile":tile,"tile_center_local":tile_point,"required_targets":targets,
        "crowd_environment":{"RABBITLANDS_CROWD_BENCH_MAP":territory["asset"]["id"],
            "RABBITLANDS_CROWD_BENCH_CENTRE":",".join(str(value) for value in tile)},
        "equipped_actor_anchor":{"record":"_record(0,true,tile,FULL_KIT_A)","kind":1,"actor_type":1,
            "appearance":{},"equipment":FULL_KIT_A,"health":5000,"max_health":5000,"alive":True},
        "hatless_actor_anchor":{"kind":1,"actor_type":1,"appearance":{"hair":104},
            "equipment":{**FULL_KIT_A,3:0},"hairstyle_index":4,"head_part":3},
        "variant_matrix":[{"renderer":renderer,"texture":texture,"requires_exact_runtime_token":True}
            for renderer in ("gl_compatibility","forward_plus") for texture in ("full","half","quarter")],
        "acceptance":["actual selected/resident chunk ID and transform match",
            "positive exact consumed entry for every required target including the independent interior",
            "same exported asset closure for raw/prepared comparison",
            "collision/grounding/material/animation/skin/season/night/fade/cancellation/shutdown parity"],
        "limitations":["a geometric center is not proof of walkable terrain; readiness/grounding must pass",
            "the crowd route does not imply interior/storage/prototype/equipment coverage",
            "merge duplicate renderer variants only when the complete exact runtime identity is equal"]}


def write_job(project: Path, texture: str, output: str, targets: list[tuple[str, str]], path: Path,
              user_root: Path) -> None:
    if not targets:
        raise PreparedError("at least one explicit target is required")
    if texture not in {"full", "half", "quarter"}:
        raise PreparedError("explicit texture quality required")
    destination = scoped(project, output.removeprefix("res://"))
    if not output.startswith("res://prepared-content/") or destination == project / "prepared-content":
        raise PreparedError("a disposable variant subfolder is required")
    marker = project / ".prepared-cook-project.json"
    if not marker.is_file() or json.loads(marker.read_text(encoding="utf-8")).get("purpose") != "disposable-native-cook":
        raise PreparedError("package coordinator must mark this as a disposable cook project")
    if user_root.exists() and any(user_root.iterdir()):
        raise PreparedError("cook user root must be fresh and empty")
    # Current project declares this Windows custom user directory. Other
    # platforms need their own tested isolation mapping, not an assumed flag.
    expected_user = user_root.resolve() / "Godot/app_userdata/Eloria"
    result = []
    for kind, source in targets:
        closure = Closure(project)
        closure.visit(scoped(project.parent, source))
        result.append({"kind": kind, "source": source,
                       "inputs": [{"path": key, "sha256": value} for key, value in sorted(closure.files.items())],
                       "source_images": closure.images,
                       "runtime_import_snapshot": runtime_import_provenance(project, closure.files)})
    job = {"schema_version": SCHEMA, "texture_quality": texture, "output": output, "targets": result,
           "expected_user_directory": str(expected_user),
           "required_environment": {"APPDATA": str(user_root.resolve()), "XDG_DATA_HOME": str(user_root.resolve())},
           "required_runtime": "Windows fresh isolated APPDATA; exact target renderer/format mask; serial coordinator"}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(job, indent=2) + "\n", encoding="utf-8")


def entry_metadata(entry: dict) -> dict:
    """Decode for inspection only; keep metadata_json byte-for-byte unchanged."""
    if "metadata" in entry or not isinstance(entry.get("metadata_json"), str):
        raise PreparedError("authoritative metadata_json String required without decoded metadata alias")
    try:
        def reject_constant(value):
            raise ValueError(f"non-finite JSON value: {value}")
        metadata = json.loads(entry["metadata_json"], parse_constant=reject_constant)
    except (ValueError, TypeError) as error:
        raise PreparedError("invalid authoritative prepared metadata JSON") from error
    if not isinstance(metadata, dict):
        raise PreparedError("authoritative prepared metadata must decode to an object")
    return metadata


def runtime_import_metadata(entry: dict) -> dict:
    provenance = entry_metadata(entry).get("runtime_import_snapshot", {})
    if not isinstance(provenance, dict):
        raise PreparedError("invalid runtime import provenance metadata")
    return provenance


def merge_catalogs(project: Path, catalogs: list[Path], output: Path) -> dict:
    expected = project / "prepared-content/index.json"
    if output.resolve() != expected.resolve():
        raise PreparedError("merged index must live at project/prepared-content/index.json")
    entries, identities = [], set()
    for path in catalogs:
        catalog = json.loads(path.read_text(encoding="utf-8"))
        if catalog.get("schema_version") != SCHEMA or catalog.get("policy") != POLICY:
            raise PreparedError(f"unknown catalog: {path}")
        for entry in catalog["entries"]:
            entry_metadata(entry)
            key = tuple(entry[field] for field in ("kind", "source", "source_digest", "texture_token"))
            if key in identities:
                raise PreparedError(f"duplicate exact variant: {key}")
            identities.add(key)
            if not HEX.fullmatch(str(entry.get("entry_id", ""))):
                raise PreparedError("invalid entry id")
            for item in entry["inputs"]:
                if digest(scoped(project.parent, item["path"])) != item["sha256"]:
                    raise PreparedError(f"input changed after cooking: {item['path']}")
            payloads = set()
            for item in entry["payloads"]:
                name = item["path"]
                target = scoped(project, name.removeprefix("res://"))
                if not name.startswith("res://prepared-content/") or target.suffix not in {".scn", ".res"} \
                        or target.stem != item["sha256"] or digest(target) != item["sha256"]:
                    raise PreparedError(f"payload changed or unscoped: {name}")
                payloads.add(name)
            if entry["resource"] not in payloads:
                raise PreparedError("primary resource missing from closure")
            entries.append(entry)
    result = {"schema_version": SCHEMA, "policy": POLICY,
              "qualification": "pending_exported_parity", "entries": entries}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"entries": len(entries), "index_sha256": digest(output), "qualification": result["qualification"]}


def install_generation(index: Path, project: Path, stage: Path) -> dict:
    """Copy only declared native payloads into a disposable export project.

    Validate raw-map inputs against the *staged* sidecar generation. Validate
    project inputs again against actual exported PCK/loose bytes after export.
    """
    index=index.resolve()
    source=index.parent
    document=json.loads(index.read_text(encoding="utf-8"))
    if document.get("schema_version")!=SCHEMA or document.get("policy")!=POLICY \
            or not isinstance(document.get("entries"),list) or not document["entries"]:
        raise PreparedError("complete supported prepared catalog required")
    destination=project.resolve()/"prepared-content"
    if destination.exists():
        raise PreparedError("fresh disposable prepared-content destination required")
    payloads={}
    variants=set()
    view=ExportView(stage)
    for entry in document["entries"]:
        variant=tuple(entry[field] for field in ("kind","source","source_digest","texture_token"))
        if variant in variants: raise PreparedError("duplicate prepared variant")
        variants.add(variant)
        if entry.get("kind") not in {"world","mesh","scene"} or not HEX.fullmatch(str(entry.get("entry_id",""))):
            raise PreparedError("invalid prepared target")
        inputs=entry.get("inputs")
        if not isinstance(inputs,list) or not inputs or entry["source"] not in {row.get("path") for row in inputs}:
            raise PreparedError("source missing from prepared input closure")
        for row in inputs:
            name=row["path"]
            if not name.startswith(("godot-client/","eloria-assets/")) or view.runtime_hash(name)!=row["sha256"]:
                raise PreparedError(f"prepared input differs from target package: {name}")
        provenance=runtime_import_metadata(entry)
        imported={row["path"] for row in inputs if row["path"].endswith(".import")}
        records=provenance.get("records",[])
        if imported and (provenance.get("policy")!=RUNTIME_IMPORT_POLICY \
                or not imported.issubset({row.get("path") for row in records})):
            raise PreparedError("prepared import remap lacks actual runtime/source provenance")
        input_hashes={row["path"]:row["sha256"] for row in inputs}
        for row in records:
            name=row.get("path","")
            if row.get("view")!=RUNTIME_IMPORT_POLICY or input_hashes.get(name)!=row.get("sha256") \
                    or not HEX.fullmatch(str(row.get("source_sha256",""))) \
                    or digest(scoped(project.parent,name))!=row["source_sha256"]:
                raise PreparedError(f"original import provenance differs from target build: {name}")
            image=row.get("source_image")
            if image is not None and (not isinstance(image,dict) \
                    or not HEX.fullmatch(str(image.get("sha256",""))) \
                    or digest(scoped(project.parent,image.get("path","")))!=image["sha256"]):
                raise PreparedError(f"original imported image provenance differs from target build: {name}")
        own_payloads=set()
        for row in entry.get("payloads",[]):
            name=row["path"]
            if not name.startswith("res://prepared-content/"): raise PreparedError("unscoped native payload")
            relative=name.removeprefix("res://prepared-content/")
            path=scoped(source,relative)
            if path.suffix not in {".scn",".res"} or path.stem!=row["sha256"] or digest(path)!=row["sha256"]:
                raise PreparedError(f"invalid prepared payload: {name}")
            if name in payloads and payloads[name]!=row["sha256"]: raise PreparedError("conflicting native payload")
            payloads[name]=row["sha256"]
            own_payloads.add(name)
        if entry.get("resource") not in own_payloads: raise PreparedError("missing native primary")
    # No destination mutation occurs until all source and payload bytes pass.
    destination.mkdir(parents=True)
    for name in sorted(payloads):
        relative=name.removeprefix("res://prepared-content/")
        target=scoped(destination,relative)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(scoped(source,relative),target)
    shutil.copyfile(index,destination/"index.json")
    return {"entries":len(document["entries"]),"payloads":len(payloads),"index_sha256":digest(index)}


def check_export(index: Path, stage: Path) -> dict:
    """Require native payload AND input identities from actual PCK/loose data."""
    document=json.loads(index.read_text(encoding="utf-8"))
    runtime_hash=ExportView(stage).runtime_hash
    if runtime_hash("godot-client/prepared-content/index.json")!=digest(index):
        raise PreparedError("exporter rewrote the prepared index")
    verified=set()
    for entry in document["entries"]:
        provenance=runtime_import_metadata(entry)
        imported={row["path"] for row in entry["inputs"] if row["path"].endswith(".import")}
        records=provenance.get("records",[])
        if not isinstance(records,list) or any(not isinstance(row,dict) for row in records) \
                or (imported and (provenance.get("policy")!=RUNTIME_IMPORT_POLICY \
                or not imported.issubset({row.get("path") for row in records}))):
            raise PreparedError("exported import remap lacks authoritative runtime/source provenance")
        for row in entry["inputs"]:
            identity=(row["path"],row["sha256"])
            if identity not in verified and runtime_hash(row["path"])!=row["sha256"]:
                raise PreparedError(f"actual exported prepared input differs: {row['path']}")
            verified.add(identity)
        for row in entry["payloads"]:
            name="godot-client/"+row["path"].removeprefix("res://")
            identity=(name,row["sha256"])
            if identity not in verified and runtime_hash(name)!=row["sha256"]:
                raise PreparedError(f"actual native payload differs: {name}")
            verified.add(identity)
    return {"verified_runtime_files":len(verified),"status":"complete","estimate_kind":"content identity only"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan-pilot")
    plan.add_argument("--texture", required=True, choices=["full", "half", "quarter"])
    plan.add_argument("--variant", required=True)
    plan.add_argument("--chunk", default=PILOT_WORLD)
    plan.add_argument("--job", required=True, type=Path)
    plan.add_argument("--user-root", required=True, type=Path)
    snapshot = sub.add_parser("snapshot-runtime-imports")
    snapshot.add_argument("--stage", required=True, type=Path)
    snapshot.add_argument("--chunk", default=PILOT_WORLD)
    describe=sub.add_parser("describe-pilot")
    describe.add_argument("--chunk",default=PILOT_WORLD)
    merge = sub.add_parser("merge")
    merge.add_argument("catalogs", nargs="+", type=Path)
    args = parser.parse_args()
    project = args.project.resolve()
    if not (project / "project.godot").is_file() or not (project.parent / "eloria-assets").is_dir():
        raise PreparedError("expected a complete isolated client package project")
    if args.command == "describe-pilot":
        print(json.dumps(pilot_qualification_plan(project,args.chunk),indent=2,sort_keys=True))
    elif args.command == "snapshot-runtime-imports":
        print(json.dumps(snapshot_runtime_imports(project, args.stage, pilot(project,args.chunk))))
    elif args.command == "plan-pilot":
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", args.variant):
            raise PreparedError("simple variant directory name required")
        write_job(project, args.texture, f"res://prepared-content/{args.variant}", pilot(project, args.chunk), args.job, args.user_root)
        print(json.dumps({"job": str(args.job), "status": "planned; no engine launched"}))
    else:
        print(json.dumps(merge_catalogs(project, args.catalogs, project / "prepared-content/index.json")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
