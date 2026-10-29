"""Ship the complete lean world cache without retaining player-profile paths.

The runtime writer owns native serialization. This module only copies verified
native bytes and rewrites the documented JSON cache-path fields. A persistent
producer/engine namespace lets the runtime reuse unchanged entries instead of
serializing new opaque resource IDs on every release. No texture tiers or image
pixels are added to this geometry/collision/paving generation.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil

import map_geometry_cache as geometry

SCHEMA = 1
POLICY = "rabbitlands-installed-world-v1"
DESCRIPTOR = "data/maps/prepared-world.json"
BUILD_OWNER = ".prepared-world-owner.json"
HASH = re.compile(r"[0-9a-f]{64}\Z")
PLATFORMS = {"windows": "Windows", "linux": "Linux", "macos": "macOS"}
NAMESPACES = {"geometry": "map-geometry-cache", "collision": "map-collision-cache",
              "paving": "map-paving-cache"}


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def data_digest(value):
    # Matches Godot JSON.stringify(value,"",true,true) for these string arrays.
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False) + "\n").encode()
    if path.is_file() and path.read_bytes() == raw:
        return
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(raw)
    temporary.replace(path)


def portable(value):
    require(isinstance(value, str) and value and not any(c in value for c in "\\:%\0"),
            "World cache path is not a plain portable relative path")
    path = PurePosixPath(value)
    require(not path.is_absolute() and not any(p in {".", ".."} for p in path.parts)
            and path.as_posix() == value, "World cache path escaped its catalog")
    return path


def regular(root, relative):
    path = Path(root) / portable(relative)
    require(path.is_file() and not path.is_symlink() and not path.is_junction()
            and path.resolve().is_relative_to(Path(root).resolve()),
            "World cache file is missing or linked outside its root: " + str(path))
    for parent in path.parents:
        if parent == Path(root):
            break
        require(not parent.is_symlink() and not parent.is_junction(), "Linked world cache directory")
    return path


def producer_inputs(project):
    """World construction scripts, excluding unrelated app/UI/release identity.

    World scripts use both global classes and explicit preloads. Include that
    bounded directory and follow its explicit actor/runtime/shader dependencies
    instead of pretending a preload-only graph covers global-class references.
    """
    project = Path(project).resolve()
    pending = list((project / "src/world").rglob("*.gd"))
    pending += [project / "src/actors/glb_scene_cache.gd"]
    pending += [project / "tools/map_geometry_cache.py", project / "tools/release_world_preparation.py"]
    found = {}
    pattern = re.compile(r'[\"\'](res://[^\"\']+\.(?:gd|gdshader|gdshaderinc))[\"\']')
    while pending:
        path = pending.pop().resolve()
        require(path.is_relative_to(project) and path.is_file(),
                "World producer dependency is missing: " + str(path))
        source = "res://" + path.relative_to(project).as_posix()
        if source in found:
            continue
        found[source] = digest(path)
        if path.suffix in {".gd", ".gdshader", ".gdshaderinc"}:
            pending.extend(project / match[6:] for match in pattern.findall(path.read_text(encoding="utf-8")))
    return dict(sorted(found.items()))


def capture(project):
    """Call before disposable source retirement; retain the exact full scope."""
    project = Path(project).resolve()
    result = geometry.plan(project)
    result["producer_inputs"] = producer_inputs(project)
    result["producer_sha256"] = data_digest(result["producer_inputs"])
    return result


def selected_source_inputs(project, plan):
    project = Path(project).resolve()
    return {geometry.source_path(project, row["source"]).relative_to(project.parent).as_posix(): row["sha256"]
            for row in plan["source_closure"]}


def runtime_name(source):
    require(isinstance(source, str) and source, "Invalid world source path")
    value = "godot-client/" + source[6:] if source.startswith("res://") else source
    require(not any(c in value for c in "\\:%\0"), "Invalid world source path")
    name = posixpath.normpath(value)
    require(name.startswith(("godot-client/", "eloria-assets/")), "World source escaped runtime roots")
    require(source.startswith("res://") or name == source, "World source is not canonical")
    return name


def target_key(row):
    return row["kind"] + "|" + runtime_name(row["source"])


def source_file(project, source):
    return geometry.allowed_path(Path(project), Path(project).parent / runtime_name(source))


def _verify_inputs(project, entry, verified, runtime_view=None):
    rows = entry.get("inputs")
    require(isinstance(rows, list) and rows, "World entry has no source closure")
    for row in rows:
        require(isinstance(row, dict) and HASH.fullmatch(str(row.get("sha256", ""))),
                "World entry source digest is malformed")
        source, expected = row.get("path"), row["sha256"]
        if source not in verified:
            verified[source] = (runtime_view.runtime_hash(runtime_name(source)) if runtime_view is not None
                                else digest(source_file(project, source)))
        require(verified[source] == expected, "World entry source changed: " + str(source))


def _metadata(user, kind, policy, key):
    source = key.split("|", 1)[1]
    identity = data_digest(key.split("|", 1)) if kind == "geometry" else data_digest(source)
    relative = f"{NAMESPACES[kind]}/{policy}/entries/{identity}.json"
    return regular(user, relative), f"{kind}/{policy}/entries/{identity}.json"


def _copy(source, target, *, links=False):
    target.parent.mkdir(parents=True, exist_ok=True)
    require(not target.exists(), "World output must be fresh: " + str(target))
    if links:
        try:
            os.link(source, target)
        except OSError as error:
            if error.errno != 18 and getattr(error, "winerror", None) != 17:
                raise
            shutil.copyfile(source, target)
    else:
        shutil.copyfile(source, target)


def collect(project, plan, report, output, *, links=False):
    """Translate one successful runtime generation; never rewrite native bytes."""
    project, output = Path(project).resolve(), Path(output).resolve()
    meta = report.get("release_metadata", {})
    expected = sorted(target_key(row) for row in plan["targets"])
    require(report.get("ok") is True and meta.get("scope_complete") is True
            and meta.get("target_keys") == expected, "World cook did not complete the exact production scope")
    collision_keys = sorted(target_key(row) for row in plan["targets"]
                            if row["kind"] == "world" and "__chunk_" in row["id"])
    require(meta.get("collision_target_keys") == collision_keys
            and isinstance(meta.get("paving_target_keys"), list)
            and meta["paving_target_keys"] == sorted(set(meta["paving_target_keys"]))
            and set(meta["paving_target_keys"]).issubset(collision_keys),
            "World cook collision/paving coverage differs from its scope")
    policies = {kind: meta.get(kind + "_policy") for kind in NAMESPACES}
    require(all(isinstance(p, str) and HASH.fullmatch(p) for p in policies.values()),
            "World cook policies are missing")
    require(meta.get("renderer") == "forward_plus" and meta.get("platform") in PLATFORMS.values()
            and isinstance(meta.get("engine"), dict), "World cook compatibility is missing")
    compatibility = data_digest([POLICY, *policies.values(), meta["platform"]])
    geometry_root = f"res://prepared-world/{compatibility}/geometry/{policies['geometry']}"
    require(meta.get("geometry_root") == geometry_root, "World cook has no stable installed native namespace")
    require(not output.exists(), "World catalog output must be fresh")
    output.mkdir(parents=True)
    user = Path(meta["user_data_path"]).resolve()
    files, targets, checked_inputs = {}, {}, {}

    def blob(value, kind, expected_sha):
        prefix = (geometry_root + "/blobs/" if kind == "geometry"
                  else f"user://{NAMESPACES[kind]}/{policies[kind]}/blobs/")
        require(isinstance(value, str) and value.startswith(prefix), "World metadata contains a foreign blob")
        name = value[len(prefix):]
        require("/" not in name and HASH.fullmatch(expected_sha)
                and name.split(".", 1)[0] == expected_sha
                and name.rsplit(".", 1)[-1] in ({"scn", "res"} if kind == "geometry" else {"rlc"} if kind == "collision" else {"res"}),
                "World blob is not content-addressed")
        relative = f"{kind}/{policies[kind]}/blobs/{name}"
        source = regular(project, value[6:]) if kind == "geometry" else regular(user, value[7:])
        if relative not in files:
            require(digest(source) == expected_sha, "World blob changed after cooking")
            _copy(source, output / relative, links=links)
            files[relative] = {"sha256": expected_sha, "bytes": source.stat().st_size}
        return relative

    for key in expected:
        kind, source = key.split("|", 1)
        paths = {}
        for cache_kind, policy in policies.items():
            if cache_kind != "geometry" and key not in meta.get(cache_kind + "_target_keys", []):
                continue
            if cache_kind == "geometry":
                identity = data_digest([kind, source])
                original = regular(project, geometry_root[6:] + "/entries/" + identity + ".json")
                relative = f"geometry/{policy}/entries/{identity}.json"
            else:
                original, relative = _metadata(user, cache_kind, policy, key)
            entry = geometry.read_json(original)
            require(entry.get("policy") == policy and entry.get("source") == source
                    and entry.get("schema") == (meta.get("geometry_schema") if cache_kind == "geometry" else 1)
                    and HASH.fullmatch(str(entry.get("source_digest", "")))
                    and (cache_kind != "geometry" or entry.get("kind") == kind),
                    "World entry identity differs from its scope")
            _verify_inputs(project, entry, checked_inputs)
            entry = copy.deepcopy(entry)
            if cache_kind == "geometry":
                payloads = entry.get("payloads", {})
                require(isinstance(payloads, dict) and entry.get("primary") in payloads,
                        "World geometry primary is undeclared")
                aliases = {path: blob(path, cache_kind, sha) for path, sha in payloads.items()}
                entry["primary"] = aliases[entry["primary"]]
                entry["payloads"] = {aliases[path]: sha for path, sha in payloads.items()}
                require(isinstance(entry.get("shared_meshes", {}), dict)
                        and set(entry.get("shared_meshes", {})).issubset(payloads), "World shared mesh table is malformed")
                entry["shared_meshes"] = {aliases[path]: sha for path, sha in entry.get("shared_meshes", {}).items()}
            elif cache_kind == "collision":
                entry["blob"] = blob(entry.get("blob"), cache_kind, entry.get("sha256", ""))
            else:
                require(isinstance(entry.get("meshes"), dict), "World paving table is malformed")
                for row in entry["meshes"].values():
                    row["blob"] = blob(row.get("blob"), cache_kind, row.get("sha256", ""))
            write_json(output / relative, entry)
            files[relative] = {"sha256": digest(output / relative), "bytes": (output / relative).stat().st_size}
            paths[cache_kind] = relative
        targets[key] = paths
    catalog = {"schema": SCHEMA, "policy": POLICY, "compatibility": compatibility,
               "platform": meta["platform"], "renderer": meta["renderer"], "engine": meta["engine"],
               "engine_executable_sha256": meta["engine_executable_sha256"],
               **{kind + "_policy": value for kind, value in policies.items()},
               "scope_sha256": meta["scope_sha256"], "registry_sha256": meta["registry_sha256"],
               "producer_sha256": plan["producer_sha256"], "target_keys": expected,
               "targets": targets, "files": dict(sorted(files.items()))}
    write_json(output / "catalog.json", catalog)
    return catalog


def validate(project, catalog_path, *, plan=None, platform=None, runtime_view=None):
    """Hash the complete portable installed generation, including source inputs."""
    project, catalog_path = Path(project).resolve(), Path(catalog_path).resolve()
    catalog = geometry.read_json(catalog_path)
    require(catalog.get("schema") == SCHEMA and catalog.get("policy") == POLICY,
            "Unsupported installed world catalog")
    policies = [catalog.get(kind + "_policy") for kind in NAMESPACES]
    require(all(isinstance(p, str) and HASH.fullmatch(p) for p in policies), "Invalid installed world policies")
    compatibility = data_digest([POLICY, *policies, catalog.get("platform")])
    require(catalog.get("compatibility") == compatibility and catalog.get("renderer") == "forward_plus"
            and isinstance(catalog.get("engine"), dict)
            and all(isinstance(catalog["engine"].get(k), str) for k in ("hash", "string")),
            "Invalid installed world compatibility")
    if platform is not None:
        require(catalog.get("platform") == PLATFORMS[platform], "Installed world catalog is for another platform")
    for field in ("scope_sha256", "registry_sha256", "producer_sha256", "engine_executable_sha256"):
        require(HASH.fullmatch(str(catalog.get(field, ""))), "Invalid installed world digest: " + field)
    source_hash = (lambda name: runtime_view.runtime_hash("godot-client/" + name)) if runtime_view else lambda name: digest(project / name)
    require(catalog["scope_sha256"] == source_hash(geometry.SCOPE)
            and catalog["registry_sha256"] == source_hash(geometry.REGISTRY),
            "Installed world scope or registry differs from this build")
    keys, targets, files = catalog.get("target_keys"), catalog.get("targets"), catalog.get("files")
    require(isinstance(keys, list) and keys and keys == sorted(set(keys))
            and isinstance(targets, dict) and set(keys) == set(targets)
            and isinstance(files, dict) and files, "Installed world target/file table is malformed")
    if plan is not None:
        expected = sorted(target_key(row) for row in plan["targets"])
        require(keys == expected and catalog["producer_sha256"] == plan["producer_sha256"],
                "Installed world catalog does not cover this producer and full scope")
    root, total = catalog_path.parent, 0
    for relative, row in files.items():
        path = regular(root, relative)
        require(isinstance(row, dict) and HASH.fullmatch(str(row.get("sha256", "")))
                and type(row.get("bytes")) is int and row["bytes"] > 0
                and path.stat().st_size == row["bytes"] and digest(path) == row["sha256"],
                "Installed world file is missing or changed: " + str(relative))
        parts = portable(relative).parts
        require(len(parts) == 4 and parts[0] in NAMESPACES
                and parts[1] == catalog[parts[0] + "_policy"]
                and parts[2] in {"entries", "blobs"}, "Installed world file has a foreign namespace")
        require(path.stem == row["sha256"] if parts[2] == "blobs" else path.suffix == ".json",
                "Installed world file is not content-addressed or metadata")
        total += row["bytes"]
    reached, checked_inputs = set(), {}
    for key in keys:
        require(isinstance(key, str) and "|" in key and key.split("|", 1)[0] in {"world", "asset"}
                and runtime_name(key.split("|", 1)[1]) == key.split("|", 1)[1],
                "Installed world target key is malformed")
        kind, source = key.split("|", 1)
        row = targets[key]
        require(isinstance(row, dict) and "geometry" in row and set(row).issubset(NAMESPACES),
                "Installed world target metadata is malformed")
        if plan is not None:
            target = next(t for t in plan["targets"] if target_key(t) == key)
            require(("collision" in row) == (kind == "world" and "__chunk_" in target["id"]),
                    "Installed collision coverage is incomplete")
        for cache_kind, relative in row.items():
            require(relative in files and relative.startswith(cache_kind + "/")
                    and "/entries/" in relative, "Installed metadata is undeclared")
            reached.add(relative)
            entry = geometry.read_json(regular(root, relative))
            require(entry.get("source") == source and entry.get("policy") == catalog[cache_kind + "_policy"]
                    and HASH.fullmatch(str(entry.get("source_digest", ""))), "Installed metadata identity changed")
            _verify_inputs(project, entry, checked_inputs, runtime_view)
            if cache_kind == "geometry":
                require(entry.get("kind") == kind and isinstance(entry.get("payloads"), dict)
                        and entry.get("primary") in entry["payloads"], "Installed geometry primary is undeclared")
                refs = entry["payloads"]
                require(isinstance(entry.get("shared_meshes", {}), dict)
                        and set(entry.get("shared_meshes", {})).issubset(refs), "Installed shared meshes are undeclared")
            elif cache_kind == "collision":
                refs = {entry.get("blob"): entry.get("sha256")}
            else:
                require(isinstance(entry.get("meshes"), dict), "Installed paving is malformed")
                refs = {r.get("blob"): r.get("sha256") for r in entry["meshes"].values()}
            for reference, sha in refs.items():
                require(reference in files and reference.startswith(cache_kind + "/")
                        and "/blobs/" in reference and files[reference]["sha256"] == sha,
                        "Installed world blob closure is incomplete")
                reached.add(reference)
    require(reached == set(files), "Installed world catalog contains unused or unverified files")
    return {"catalog": catalog, "files": len(files), "bytes": total + catalog_path.stat().st_size,
            "catalog_sha256": digest(catalog_path), "source_inputs": len(checked_inputs)}


def install(project, stage, catalog_path, *, plan, platform, links=False):
    from prepared_content_package import ExportView
    view = ExportView(Path(stage))
    checked = validate(project, catalog_path, plan=plan, platform=platform, runtime_view=view)
    catalog, source = checked["catalog"], Path(catalog_path).resolve().parent
    target = Path(stage) / "app/prepared-world" / catalog["compatibility"]
    require(not target.exists(), "Installed world destination must be fresh")
    for relative in sorted(catalog["files"]):
        _copy(regular(source, relative), target / relative, links=links)
    _copy(Path(catalog_path), target / "catalog.json", links=links)
    staged = validate(project, target / "catalog.json", plan=plan, platform=platform, runtime_view=view)
    require(staged["catalog_sha256"] == checked["catalog_sha256"], "Staged world catalog changed")
    write_json(Path(project) / DESCRIPTOR, {"schema": SCHEMA, "policy": POLICY,
        "variants": {catalog["compatibility"]: {"catalog": catalog["compatibility"] + "/catalog.json",
                                                "sha256": checked["catalog_sha256"]}}})
    owner = _claim_build(project)
    owner["descriptor_sha256"] = digest(Path(project) / DESCRIPTOR)
    write_json(Path(project) / BUILD_OWNER, owner)
    return {key: value for key, value in staged.items() if key != "catalog"} | {
        "compatibility": catalog["compatibility"], "targets": len(catalog["target_keys"]),
        "path": str(target / "catalog.json"), "renderer": catalog["renderer"],
        "producer_sha256": catalog["producer_sha256"]}


def _claim_build(project):
    project = Path(project).resolve()
    marker = project / BUILD_OWNER
    owner = {"schema": SCHEMA, "policy": POLICY, "project": str(project)}
    if marker.exists():
        actual = geometry.read_json(marker)
        require(all(actual.get(k) == v for k, v in owner.items()), "World build ownership differs")
        return actual
    write_json(marker, owner)
    return owner


def _regular_tree(root):
    require(not root.is_symlink() and not root.is_junction(), "World work tree is linked")
    for child in root.rglob("*"):
        require(not child.is_symlink() and not child.is_junction() and child.resolve().is_relative_to(root),
                "World work tree contains a link")


def reset_build(project):
    """Remove only a prior producer-owned tree/descriptor in this build path."""
    project = Path(project).resolve()
    root, descriptor, marker = project / "prepared-world", project / DESCRIPTOR, project / BUILD_OWNER
    if not root.exists() and not descriptor.exists() and not marker.exists():
        return
    require(marker.is_file(), "Unowned stale prepared-world output must be preserved")
    owner = geometry.read_json(marker)
    require(all(owner.get(k) == v for k, v in {"schema": SCHEMA, "policy": POLICY,
                                              "project": str(project)}.items()), "Stale world output belongs to another build")
    if descriptor.exists():
        require(owner.get("descriptor_sha256") == digest(descriptor), "Stale world descriptor changed")
        descriptor.unlink()
    if root.exists():
        _regular_tree(root)
        shutil.rmtree(root)
    marker.unlink()


def hydrate_native(project, users):
    project, users = Path(project).resolve(), Path(users).resolve()
    root, saved = project / "prepared-world", users / "native"
    require(not root.exists(), "World cook requires a fresh owned native work tree")
    _claim_build(project)
    root.mkdir()
    (root / ".gdignore").write_text("", encoding="utf-8")
    if saved.exists():
        _regular_tree(saved)
        for path in saved.rglob("*"):
            if path.is_file():
                relative = path.relative_to(saved).as_posix()
                parts = portable(relative).parts
                require(len(parts) == 5 and HASH.fullmatch(parts[0]) and parts[1] == "geometry"
                        and HASH.fullmatch(parts[2]) and parts[3] in {"entries", "blobs"},
                        "Persistent native cache contains a foreign path")
                _copy(path, root / relative, links=True)


def retain_native(project, users, catalog):
    project, users = Path(project).resolve(), Path(users).resolve()
    root, pending, saved, previous = project / "prepared-world", users / "native.pending", users / "native", users / "native.previous"
    require(not pending.exists() and not previous.exists(), "Unfinished native cache recovery must be preserved")
    pending.mkdir()
    for relative, row in catalog["files"].items():
        if not relative.startswith("geometry/"):
            continue
        local = catalog["compatibility"] + "/" + relative
        source = regular(root, local)
        if "/blobs/" in relative:
            require(digest(source) == row["sha256"], "Native source changed before cache retention")
        _copy(source, pending / local, links=True)
    if saved.exists():
        _regular_tree(saved)
        saved.rename(previous)
    pending.rename(saved)
    if previous.exists():
        shutil.rmtree(previous)


def runtime_import_overlay(project, stage, overlay):
    """Use real exported remaps/products and installed source-image presence.

    Original PNGs may be absent from an export even though their CTEX/remap is
    shipped. Hiding only those absent files prevents texture provenance from
    recording an editor-only raw-image dependency. Every mutation is reversible
    and happens only in the disposable project owned by the package builder.
    """
    from prepared_content_package import ExportView
    project, stage = Path(project).resolve(), Path(stage).resolve()
    view = ExportView(stage)
    updates, hidden = {}, set()
    for name in sorted(view.entries):
        if not name.endswith(".import"):
            continue
        raw = view.read(name)
        products = set(re.findall(rb'"(res://\.godot/imported/[^"\r\n\x00]+\.ctex)"', raw))
        if not products:
            continue
        original = regular(project, name)
        updates[name] = raw
        for product in products:
            local = product.decode("utf-8")[6:]
            require(local in view.entries, "Exported world texture remap lacks its product")
            # Exact product bytes are checked even when no rewrite is necessary.
            path = regular(project, local)
            if digest(path) != view.runtime_hash("godot-client/" + local):
                updates[local] = view.read(local, maximum=256 * 1024**2)
        image = name.removesuffix(".import")
        if image not in view.entries and not (stage / "app" / image).is_file():
            source = project / image
            if source.is_file():
                hidden.add(image)
    changed = []
    for name, raw in updates.items():
        path = project / name
        if path.read_bytes() == raw:
            continue
        overlay.remember(path)
        # Never modify a retained cache/stage hard link in place.
        path.unlink()
        path.write_bytes(raw)
        require(digest(path) == view.runtime_hash("godot-client/" + name), "Exported import snapshot changed")
        changed.append(name)
    for name in sorted(hidden):
        path = project / name
        overlay.remember(path)
        path.unlink()
    return {"changed": changed, "hidden_unshipped_sources": sorted(hidden)}


def prepare(project, stage, godot, *, platform, plan, cache_root, work_root,
            check_budget=None, software_gpu_index=None, catalog_path=None, links=False):
    """Run during packaging only; callers never invoke this for normal play."""
    project, stage = Path(project).resolve(), Path(stage).resolve()
    if catalog_path is not None:
        supplied = geometry.read_json(Path(catalog_path))
        require(supplied.get("engine_executable_sha256") == digest(godot),
                "Prebuilt world catalog was made by a different engine executable")
        return install(project, stage, catalog_path, plan=plan, platform=platform, links=links)
    require(platform in {"windows", "linux"}, "This platform needs a matching prebuilt world catalog")
    import release_graphics_preflight
    import release_software_graphics as graphics
    from release_prepared_content import _Overlay
    work_root, cache_root, godot = map(lambda p: Path(p).resolve(), (work_root, cache_root, godot))
    require(not work_root.exists() and not cache_root.is_relative_to(project.parent)
            and not cache_root.is_relative_to(stage) and cache_root != Path(cache_root.anchor),
            "World preparation needs fresh work and a separate persistent cache")
    work_root.mkdir(parents=True)
    budget = check_budget or (lambda phase, additional=0: None)
    config = graphics.prepare_world_graphics(platform, godot.parent, godot.parent, budget,
                                             gpu_index=software_gpu_index)
    release_graphics_preflight.run_preflight(config, godot, work_root / "graphics-preflight", budget)
    namespace = data_digest([POLICY, platform, "forward_plus", digest(godot), plan["producer_sha256"]])
    users = cache_root / platform / namespace
    require(not users.is_symlink() and not users.is_junction(), "World cache profile is linked")
    users.mkdir(parents=True, exist_ok=True)
    owner_path = users / "world-cache-owner.json"
    owner = {"schema": SCHEMA, "policy": POLICY, "platform": platform, "namespace": namespace}
    if owner_path.exists():
        require(geometry.read_json(owner_path) == owner, "World cache belongs to another producer")
    else:
        require(not any(users.iterdir()), "Unowned existing world profile cannot be adopted")
        write_json(owner_path, owner)
    lock = users / ".release-preparation.lock"
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise ValueError("Another world preparation owns this cache; preserve it and resume when finished") from exc
    try:
        plan_path = work_root / "plan.json"
        write_json(plan_path, plan)

        def run(argv, env, stdout, stderr, timeout):
            budget("world preparation running", 512 * 1024**2)
            # Runtime GLTF/texture extensions register only once, before work.
            env = {k: v for k, v in env.items() if k not in {"GH_TOKEN", "GITHUB_TOKEN", "CLIENT_UPDATE_SIGNING_KEY",
                                                            "ACTIONS_ID_TOKEN_REQUEST_TOKEN"}}
            return geometry._run_engine(graphics.cook_command(config, argv),
                                        graphics.child_environment(config, env), stdout, stderr, timeout,
                                        check_progress=lambda: budget("world preparation running"))

        overlay = _Overlay(project.parent, work_root / "import-backups", budget)
        marker = project / ".prepared-cook-project.json"
        require(not marker.exists(), "World cook requires an unclaimed disposable project")
        marker.write_text(json.dumps({"purpose": "disposable-native-cook", "policy": POLICY}), encoding="utf-8")
        try:
            hydrate_native(project, users)
            inputs = runtime_import_overlay(project, stage, overlay)
            write_json(work_root / "runtime-import-overlay.json", inputs)
            result = geometry.build(project, godot, user_root=users, plan_path=plan_path, resume=True,
                                    rendering_method="forward_plus", release_preparation=True, run_engine=run)
            report = geometry.read_json(Path(result["report"]))
            require(report.get("release_metadata", {}).get("platform") == PLATFORMS[platform],
                    "World producer ran on the wrong platform")
            generation = work_root / "generation"
            catalog = collect(project, plan, report, generation, links=links)
            retain_native(project, users, catalog)
        finally:
            overlay.restore()
            marker.unlink()
        receipt = install(project, stage, generation / "catalog.json", plan=plan, platform=platform, links=links)
        receipt.update({"prepared": result["prepared"], "reused": result["reused"],
                        "report": result["report"], "cache_namespace": namespace})
        receipt["retired_cache_namespaces"] = prune_cache_namespaces(users)
        write_json(work_root / "receipt.json", receipt)
        return receipt
    finally:
        lock.rmdir()


def prune_cache_namespaces(current):
    """Retain recovery until success, then remove only our marked older profiles."""
    current = Path(current).resolve()
    retired = []
    for candidate in current.parent.iterdir():
        if candidate == current or not candidate.is_dir() or not HASH.fullmatch(candidate.name):
            continue
        marker = candidate / "world-cache-owner.json"
        expected = {"schema": SCHEMA, "policy": POLICY, "platform": current.parent.name,
                    "namespace": candidate.name}
        if not marker.is_file() or geometry.read_json(marker) != expected:
            continue
        require(not candidate.is_symlink() and not candidate.is_junction()
                and candidate.resolve().parent == current.parent, "World cache retirement escaped its parent")
        require(not (candidate / ".release-preparation.lock").exists(), "Older world cache is still in use")
        for child in candidate.rglob("*"):
            require(not child.is_symlink() and not child.is_junction()
                    and child.resolve().is_relative_to(candidate), "World cache retirement contains a link")
        shutil.rmtree(candidate)
        retired.append(candidate.name)
    return sorted(retired)


def check_export(project, stage, receipt, *, plan, platform):
    from prepared_content_package import ExportView
    view = ExportView(Path(stage))
    require(not any(name.startswith("prepared-world/") or name == BUILD_OWNER for name in view.entries),
            "Main PCK contains loose native world output or private ownership metadata")
    path = Path(stage) / "app/prepared-world" / receipt["compatibility"] / "catalog.json"
    checked = validate(project, path, plan=plan, platform=platform, runtime_view=view)
    descriptor = {"schema": SCHEMA, "policy": POLICY,
        "variants": {receipt["compatibility"]: {"catalog": receipt["compatibility"] + "/catalog.json",
                                               "sha256": checked["catalog_sha256"]}}}
    exported = json.loads(view.read(DESCRIPTOR))
    require(exported == descriptor and checked["catalog_sha256"] == receipt["catalog_sha256"],
            "Final export does not bind the staged full world generation")
    return {key: value for key, value in checked.items() if key != "catalog"}
