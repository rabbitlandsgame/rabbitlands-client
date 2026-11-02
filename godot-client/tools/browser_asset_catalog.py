"""Verified lazy browser asset groups from the current runtime catalogs."""
from __future__ import annotations
import hashlib
import json
from collections import defaultdict
from pathlib import Path

IMAGE = {".png", ".jpg", ".jpeg", ".webp"}


def group_sources(web):
    repository, client = web.REPO, web.CLIENT
    tracked = set(web.subprocess.check_output(["git", "ls-files", "-z"], cwd=repository).decode().split("\0"))
    hashes = {}
    parsed = {}
    glb_dependencies = {}
    retirement = json.loads((client / "data/assets/retired_procedural_models.json").read_text())
    retired = {(client / "assets" / name).resolve() for name in retirement.get("runtimePaths", [])}

    def closure(seeds):
        result = set()

        def add(path):
            path = path.resolve()
            if path in retired: raise ValueError(f"Retired procedural asset cannot ship to browsers: {path}")
            if not path.is_relative_to(repository) or path.relative_to(repository).as_posix() not in tracked or not path.is_file():
                raise ValueError(f"Missing/unsafe browser runtime dependency: {path}")
            if path in result: return
            result.add(path)
            if path.suffix == ".glb":
                if path not in glb_dependencies: glb_dependencies[path] = tuple(web.glb_dependencies(path))
                for dependency in glb_dependencies[path]: add(dependency)
                if path.is_relative_to(repository / "eloria-assets/maps/_shared/meshes"):
                    add(path.parent / "index.json")
            elif path.suffix == ".json":
                # Shared indexes describe an entire pool, but a map only needs
                # the prototypes/images its own verified closure names.
                if path.name == "index.json": return
                if path not in parsed: parsed[path] = json.loads(path.read_text())
                document = parsed[path]
                if path.name == "world.json":
                    from road_ground_dependencies import dependencies
                    for dependency in dependencies(repository, path, document.get("roadGround")): add(dependency)
                # Streamed roots retain metadata but not the unused review GLB.
                streamed = bool(document.get("streamingChunks"))
                skip = str(document.get("asset", {}).get("glb", "")) if streamed else ""
                for value in web.strings(document):
                    if value == skip or ":" in value or value.startswith(("/", "\\")): continue
                    candidate = (path.parent / value).resolve()
                    if candidate.suffix.lower() in {".glb", ".gltf", ".json", ".bin", ".png", ".jpg", ".jpeg", ".webp", ".ktx", ".ktx2"} and candidate.is_file(): add(candidate)
                for section in ("externalResources", "externalMeshes"):
                    for relative, expected in document.get(section, {}).items():
                        dependency = (path.parent / relative).resolve()
                        # The source closure, including immutable shared pools,
                        # is verified once even when many maps reference it.
                        if dependency not in hashes:
                            with dependency.open("rb") as source: hashes[dependency] = hashlib.file_digest(source, "sha256").hexdigest()
                        if hashes[dependency] != expected: raise ValueError(f"Map dependency hash changed: {dependency}")
                        add(dependency)
        for seed in seeds: add(seed)
        return result

    def resources(document):
        return [client / value[6:] for value in web.strings(document)
                if value.startswith("res://assets/") and Path(value).suffix.lower() not in {".svg", ".tres", ".tscn"}]

    models = json.loads((client / "data/actors/models.json").read_text())["models"]
    equipment = json.loads((client / "data/actors/equipment.json").read_text())["models"]
    registry = json.loads((client / "data/maps/registry.json").read_text())["maps"]
    groups = {}; model_groups = {}; equipment_groups = {}; map_groups = {}
    startup = set()
    for root in ("rl_heads", "rl_head_textures", "face_masks"):
        startup.update(path for path in (client / "assets/actors/native" / root).rglob("*")
                       if path.is_file() and path.suffix not in {".uid", ".import", ".md"})
    startup.add(client / "assets/actors/native/equipment/generic_cape.glb")
    for root in (repository / "eloria-assets/fonts", repository / "eloria-assets/world/_shared/images", client / "assets/world"):
        startup.update(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in {".glb", ".json", ".png", ".jpg", ".jpeg", ".webp", ".ttf", ".otf"})
    startup.update((client / "assets/ui/cursors").glob("*.png"))
    for name, model in models.items():
        key = "model:" + name
        groups[key] = closure(resources(model))
        model_groups[name] = [key]
        if name.endswith(("_male", "_female")): startup.update(groups[key])
    for name, model in equipment.items():
        key = "equipment:" + name
        groups[key] = closure(resources(model))
        equipment_groups[name] = [key]
    # The existing four starter kits render before an account exists.
    import re
    for part, visual in re.findall(r'(\d+):\s*(\d+)', (client / "src/ui/creation_archetypes.gd").read_text()):
        startup.update(groups.get("equipment:" + part + ":" + visual, set()))
    groups["startup"] = closure(startup)
    for name, entry in registry.items():
        seen = set(); canonical = name
        while "alias" in registry[canonical]:
            if canonical in seen: raise ValueError("Cyclic map alias: " + name)
            seen.add(canonical); canonical = registry[canonical]["alias"]
        key = "map:" + canonical
        map_groups[name] = [key]
        if key not in groups:
            manifest = client / registry[canonical]["manifest"].removeprefix("res://")
            groups[key] = closure([manifest])
            # Small root metadata enables portal relationships, route planning
            # and streamed-map detection before a territory is downloaded.
            # Add only the JSON itself, never its geometry closure, to startup.
            groups["startup"].add(manifest.resolve())
    return groups, {"maps": map_groups, "model_groups": model_groups, "equipment_groups": equipment_groups}


def factor_groups(sources):
    """Each source path belongs to exactly one physical extraction bundle."""
    owners = defaultdict(list)
    for group, paths in sorted(sources.items()):
        for path in paths: owners[path].append(group)
    bundles = defaultdict(set); dependencies = defaultdict(set)
    for path, groups in owners.items():
        if "startup" in groups: bundle = "startup"
        elif len(groups) == 1: bundle = groups[0]
        else: bundle = "shared:" + hashlib.sha256("\0".join(groups).encode()).hexdigest()[:24]
        bundles[bundle].add(path)
        for group in groups:
            if group != bundle: dependencies[group].add(bundle)
    for name in sources: bundles[name]  # Keep logical groups with no unique files.
    return dict(bundles), {key: sorted(value) for key, value in dependencies.items()}


def build(web, assets):
    sources, catalog = group_sources(web)
    bundles, dependencies = factor_groups(sources)
    groups = {}
    for name, paths in sorted(bundles.items()):
        groups[name] = {"archives": web.raw_archives(sorted(paths), assets) if paths else [],
                        "dependencies": dependencies.get(name, []),
                        "unpacked_bytes": sum(path.stat().st_size for path in paths)}
    catalog["groups"] = groups
    return catalog, set().union(*sources.values())
