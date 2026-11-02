"""Build a local desktop-browser prototype from the existing client.

Writes only an ignored .local directory. No upload, release, desktop packaging,
asset regeneration, or change to the server's saved world is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import zipfile

REPO = Path(__file__).resolve().parents[2]
CLIENT = REPO / "godot-client"
MAPS = ("landfall",)
CREATURES = {"rabbit", "beaver", "shrew", "squirrel", "hedgehog", "dormouse", "gecko", "pheasant", "stoat"}
MOUNTS = {"moor_pony", "golden_plains_horse", "crystalback_tortoise", "jadefeather_raptor", "giant_rat"}
SKIP = {".godot", "bin", "native", "tools", "tests", "docs", "prototypes", "world_authoring", "test-artifacts"}
PART_BYTES = 24 * 1024 * 1024


def describe(path: Path) -> dict:
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    return {"file": path.name, "bytes": path.stat().st_size, "sha256": digest}


def raw_archives(files: list[Path], assets: Path) -> list[dict]:
    """Independent archives keep temporary browser download memory bounded."""
    groups, group, size = [], [], 0
    for path in files:
        length = path.stat().st_size
        if group and size + length > PART_BYTES:
            groups.append(group)
            group, size = [], 0
        group.append(path)
        size += length
    if group:
        groups.append(group)
    result = []
    for group in groups:
        temporary = assets / "packing.zip"
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for source in group:
                # Stable archives survive new worktrees and source checkouts;
                # timestamps and local permissions never invalidate disk cache.
                # Independently compressed 2 MiB entries let the browser yield
                # between pieces of a large model instead of blocking a frame
                # to decompress/write the complete creature or hairstyle.
                with source.open("rb") as incoming:
                    offset = 0
                    multipart = source.stat().st_size > 2 * 1024 * 1024
                    while data := incoming.read(2 * 1024 * 1024):
                        name = source.relative_to(REPO).as_posix()
                        if multipart: name += ".__rlpart_%012d" % offset
                        entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                        entry.compress_type = zipfile.ZIP_DEFLATED
                        entry.external_attr = 0o100644 << 16
                        archive.writestr(entry, data, compresslevel=6)
                        offset += len(data)
        row = describe(temporary)
        if row["bytes"] > 64 * 1024 * 1024:
            raise ValueError("An asset archive exceeds the 64 MiB browser payload limit: " + str(group[0]))
        target = assets / (row["sha256"] + ".zip")
        temporary.replace(target)
        result.append({**row, "file": target.name})
    return result


def finish_site(stage: Path, assets_base_url: str):
    site, assets = stage / "site", stage / "assets"
    pack = site / "index.pck"
    if pack.stat().st_size > 512 * 1024 * 1024:
        raise ValueError("Browser package exceeds 512 MiB; use a fresh --stage folder to exclude stale editor-extracted images")
    parts = []
    with pack.open("rb") as source:
        while data := source.read(PART_BYTES):
            digest = hashlib.sha256(data).hexdigest()
            target = assets / (digest + ".bin")
            target.write_bytes(data)
            parts.append({"file": target.name, "bytes": len(data), "sha256": digest})
    wasm = describe(site / "index.wasm")
    target = assets / (wasm["sha256"] + ".wasm")
    shutil.copy2(site / "index.wasm", target)
    libraries = []
    for name in ("index.side.wasm", "browser_cape.wasm"):
        source = site / name
        if not source.is_file(): continue
        row = describe(source)
        target = assets / (row["sha256"] + ".wasm")
        shutil.copy2(source, target)
        libraries.append({**row, "file": target.name, "name": name,
                          "extension": name != "index.side.wasm"})
    report = json.loads((stage / "build.json").read_text())
    manifest = {"schema": 1, "base_url": assets_base_url.rstrip("/") + "/",
                "pack": {"bytes": pack.stat().st_size, "parts": parts},
                "wasm": {**wasm, "file": wasm["sha256"] + ".wasm"}, "archives": report["archives"]}
    for name in ("groups", "maps", "model_groups", "equipment_groups"):
        if name in report: manifest[name] = report[name]
    if libraries: manifest["libraries"] = libraries
    (site / "browser-assets.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    shutil.copy2(CLIENT / "src/platform/browser_assets.js", site / "browser-assets.js")
    # Keep the worker script on the launch origin while loading verified WASM
    # from the asset origin. Assert the supported engine hook rather than
    # silently producing a broken build after an export-template upgrade.
    script = site / "index.js"
    text = script.read_text(encoding="utf-8")
    hook = 'preloader.loadPromise(`${loadPath}.wasm`, size, true)'
    if text.count(hook) != 1:
        raise ValueError("Web template WASM hook changed; qualify the new engine before exporting")
    script.write_text(text.replace(hook, 'preloader.loadPromise(globalThis.RL_BROWSER_WASM_URL || `${loadPath}.wasm`, size, true)'), encoding="utf-8")
    text = script.read_text(encoding="utf-8")
    hook = 'FS.writeFile(path,new Uint8Array(buffer))'
    if text.count(hook) != 1:
        raise ValueError("Web template filesystem hook changed; qualify buffer ownership before exporting")
    script.write_text(text.replace(hook, 'FS.writeFile(path,new Uint8Array(buffer),{canOwn:globalThis.RL_BROWSER_TAKE_BUFFER===true})'), encoding="utf-8")
    # Emscripten's offscreen frame blit asks whether scissoring is enabled.
    # Chromium's generic getParameter path waits for the GPU command queue;
    # isEnabled reads the same capability through its cached state. Keep the
    # renderer's framebuffer validation and the blit's save/restore intact.
    text = script.read_text(encoding="utf-8")
    hook = 'var prevScissorTest=gl.getParameter(3089);'
    if text.count(hook) != 1:
        raise ValueError("Web template frame-presentation hook changed; qualify the new engine before exporting")
    text = text.replace(hook, 'var prevScissorTest=gl.isEnabled(3089);')
    # This is a browser hint, not a guarantee: OS/browser GPU selection may
    # override it. The local launcher can request Chrome's faster adapter too.
    hook = 'powerPreference:webglPowerPreferences[powerPreference]'
    if text.count(hook) != 1:
        raise ValueError("Web template GPU-preference hook changed; qualify the new engine before exporting")
    script.write_text(text.replace(hook, 'powerPreference:"high-performance"'), encoding="utf-8")
    shell = site / "index.html"
    text = shell.read_text(encoding="utf-8")
    if text.count("engine.startGame({") != 1:
        raise ValueError("Web template startup changed")
    text = text.replace('<script src="index.js"></script>', '<script src="index.js"></script>\n<script src="browser-assets.js"></script>')
    shell.write_text(text.replace("engine.startGame({", "RabbitLandsBrowser.start(engine, GODOT_CONFIG, {"), encoding="utf-8")
    # The launch folder cannot accidentally serve the large payloads.
    pack.unlink()
    (site / "index.wasm").unlink()
    for row in libraries: (site / row["name"]).unlink()
    (site / "assets.zip").unlink(missing_ok=True)
    all_archives = {row["sha256"]: row for row in report["archives"]}
    for group in report.get("groups", {}).values():
        all_archives.update({row["sha256"]: row for row in group["archives"]})
    report.update({"assets_base_url": assets_base_url,
                   "asset_download_bytes": sum(row["bytes"] for row in [*all_archives.values(), *parts, wasm, *libraries]),
                   "startup_download_bytes": sum(row["bytes"] for row in [*report["archives"], *parts, wasm, *libraries]),
                   "launch_site_bytes": sum(p.stat().st_size for p in site.iterdir() if p.is_file())})
    (stage / "build.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


def stage_browser_cape(stage: Path, module: Path, editor_runtime: Path):
    """Register arithmetic at engine startup using a valid editor counterpart."""
    if module.read_bytes()[:4] != b"\0asm":
        raise ValueError("The browser cape module must be WebAssembly")
    platform = {".dll": "windows.x86_64", ".so": "linux.x86_64", ".dylib": "macos"}.get(editor_runtime.suffix)
    if platform is None: raise ValueError("Supply the matching editor's client_runtime library")
    notice = module.parent / "godot-cpp-LICENSE.md"
    if not notice.is_file(): raise ValueError("Build the cape payload with its godot-cpp-LICENSE.md notice")
    shutil.copy2(notice, stage / "site/godot-cpp-LICENSE.md")
    directory = stage / "project/assets/platform/browser_cape"
    directory.mkdir(parents=True, exist_ok=True)
    shutil.copy2(module, directory / "browser_cape.wasm")
    shutil.copy2(editor_runtime, directory / editor_runtime.name)
    descriptor = f'''[configuration]
entry_symbol="rl_client_runtime_library_init"
compatibility_minimum="4.7"
compatibility_maximum="4.7"
reloadable=false
[libraries]
web.wasm32="./browser_cape.wasm"
{platform}="./{editor_runtime.name}"
'''
    (directory / "browser_cape.gdextension").write_text(descriptor, encoding="utf-8")
    path = stage / "build.json"
    document = json.loads(path.read_text())
    document["browser_cape_sha256"] = describe(module)["sha256"]
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in {"provenance", "sources", "knownLimitations", "conceptArt", "draft"}:
                continue
            yield key
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def glb_dependencies(path: Path):
    with path.open("rb") as source:
        magic, version, _ = struct.unpack("<4sII", source.read(12))
        if magic != b"glTF" or version != 2:
            raise ValueError(f"Expected an ordinary GLB: {path}")
        length, kind = struct.unpack("<II", source.read(8))
        if kind != 0x4E4F534A:
            raise ValueError(f"Missing GLB JSON: {path}")
        doc = json.loads(source.read(length))
    for section in ("images", "buffers"):
        for item in doc.get(section, []):
            uri = item.get("uri", "")
            if uri and not uri.startswith("data:"):
                from urllib.parse import unquote
                yield (path.parent / unquote(uri)).resolve()


def raw_world_models(project: Path) -> set[Path]:
    """Use the production raw-scenery policy without requiring other maps.

    Explicit ResourceLoader users win. Keep images imported and make no
    changes to geometry, materials, raw files or runtime source selection.
    """
    from package_client import SOURCE_LITERAL, WORLD_RESOURCE_LITERAL, WORLD_LOAD_LITERAL
    import re
    reader = project / "src/actors/glb_scene_cache.gd"
    if not reader.is_file() or 'if not resource_path.begins_with("res://assets/actors/")' not in reader.read_text():
        return set()  # Unknown reader: conservatively retain scene imports.
    models = {p.relative_to(project).as_posix(): p for p in (project / "assets/world").rglob("*")
              if p.suffix.lower() in {".glb", ".gltf"}}
    imported = set()
    for path in project.rglob("*"):
        if path.suffix not in {".gd", ".tscn", ".tres"} or ".godot" in path.relative_to(project).parts:
            continue
        source = path.read_text(encoding="utf-8-sig", errors="replace")
        if path != reader:
            for _, literal in SOURCE_LITERAL.findall(source):
                if literal.startswith("res://assets/world/") and (literal.endswith("/") or "%" in literal or "{" in literal):
                    prefix = re.split(r"[%{]", literal[6:], maxsplit=1)[0]
                    imported.update(name for name in models if name.startswith(prefix))
        references = {name for name in WORLD_RESOURCE_LITERAL.findall(source) if name in models}
        if path.suffix in {".tscn", ".tres"}:
            imported.update(references)
        else:
            imported.update(WORLD_LOAD_LITERAL.findall(source))
            if re.search(r"\b(?:load|preload)\s*\(\s*[A-Za-z_]", source):
                imported.update(references)
    return {path for name, path in models.items() if name not in imported}


def raw_files() -> list[Path]:
    tracked = set(subprocess.check_output(["git", "ls-files", "-z"], cwd=REPO).decode().split("\0"))
    models = json.loads((CLIENT / "data/actors/models.json").read_text())
    selected = {name: row for name, row in models["models"].items()
                if name.endswith(("_male", "_female")) or name in CREATURES | MOUNTS}
    found: set[Path] = set()

    def add(path):
        path = path.resolve()
        if not path.is_relative_to(REPO) or not path.is_file():
            raise ValueError(f"Missing or unsafe prototype dependency: {path}")
        if path.relative_to(REPO).as_posix() not in tracked:
            raise ValueError(f"Prototype assets must be tracked source files: {path}")
        if path in found:
            return
        found.add(path)
        if path.suffix == ".glb":
            for dependency in glb_dependencies(path):
                add(dependency)
            if path.is_relative_to(REPO / "eloria-assets/maps/_shared/meshes"):
                add(path.parent / "index.json")
        elif path.name == "world.json" and path.is_relative_to(REPO / "eloria-assets/maps"):
            doc = json.loads(path.read_text())
            from road_ground_dependencies import dependencies as road_dependencies
            for dependency in road_dependencies(REPO, path, doc.get("roadGround")):
                add(dependency)
            for value in strings(doc):
                if Path(value).suffix.lower() in {".glb", ".json", ".png", ".jpg", ".webp"}:
                    candidate = (path.parent / value).resolve()
                    if candidate.is_file():
                        add(candidate)
            for section in ("externalResources", "externalMeshes"):
                for relative, digest in doc.get(section, {}).items():
                    dependency = (path.parent / relative).resolve()
                    add(dependency)
                    if hashlib.sha256(dependency.read_bytes()).hexdigest() != digest:
                        raise ValueError(f"Map dependency hash mismatch: {dependency}")

    for value in strings(selected):
        if value.startswith("res://assets/"):
            add(CLIENT / value.removeprefix("res://"))
    native = CLIENT / "assets/actors/native"
    # Preserve the current Human identities, hair, animation and starter gear.
    for root in ("rl_heads", "rl_head_textures", "face_masks", "mounts"):
        for path in (native / root).rglob("*"):
            if path.is_file() and path.suffix not in {".uid", ".import", ".md"}:
                add(path)
    equipment = native / "equipment"
    for path in equipment.glob("*.glb"):
        add(path)
    for path in (native / "races").glob("*.glb"):
        add(path)
    # Both the home-town NPCs moved onto Landfall and its local NPCs wear their
    # authored clothes. Keep their Human variants and all four starter kits.
    npcs = json.loads((CLIENT / "data/actors/npc_characters.json").read_text())["npcs"]
    equipment_models = json.loads((CLIENT / "data/actors/equipment.json").read_text())["models"]
    visual_keys = set()
    for npc in npcs.values():
        if npc.get("homeRegion") in {"landfall", "four_gates"}:
            visual_keys.update(f"{part}:{visual}" for part, visual in npc.get("equipmentVisuals", {}).items())
    import re
    kits = re.findall(r'"equipment_visuals":\s*\{([^}]+)\}', (CLIENT / "src/ui/creation_archetypes.gd").read_text())
    if len(kits) != 4:
        raise ValueError("Expected the four current starter kits")
    for kit in kits:
        visual_keys.update(f"{part}:{visual}" for part, visual in re.findall(r'(\d+):\s*(\d+)', kit))
    for key in sorted(visual_keys):
        for value in strings(equipment_models.get(key, {})):
            if value.startswith("res://assets/") and Path(value).suffix != ".svg":
                add(CLIENT / value.removeprefix("res://"))
    for path in (CLIENT / "assets/ui/cursors").glob("*.png"):
        add(path)
    registry = json.loads((CLIENT / "data/maps/registry.json").read_text())["maps"]
    for map_id in MAPS:
        manifest = (CLIENT / registry[map_id]["manifest"].removeprefix("res://")).resolve()
        add(manifest)
        doc = json.loads(manifest.read_text())
    for path in (REPO / "eloria-assets/fonts").rglob("*"):
        if path.is_file() and path.suffix not in {".md", ".import"}:
            add(path)
    # Runtime scenery GLBs refer to this shared pool by relative URI.
    for path in (REPO / "eloria-assets/world/_shared/images").rglob("*"):
        if path.is_file() and path.suffix not in {".md", ".import"}:
            add(path)
    for path in (CLIENT / "assets/world").rglob("*"):
        if path.is_file() and path.suffix.lower() in {".glb", ".json", ".png", ".jpg", ".webp"}:
            add(path)
    return sorted(found)


def stage_project(stage: Path, endpoint: str, asset_catalog: Path | None = None) -> dict:
    project = stage / "project"
    site = stage / "site"
    project.mkdir(parents=True, exist_ok=True)
    site.mkdir(exist_ok=True)
    assets = stage / "assets"
    assets.mkdir(exist_ok=True)
    # Importers also need external scenery images in their existing relative
    # location. This generated sibling stays inside the isolated build stage.
    images = REPO / "eloria-assets/world/_shared/images"
    if images.is_dir():
        shutil.copytree(images, stage / "eloria-assets/world/_shared/images", dirs_exist_ok=True)
    tracked = subprocess.check_output(["git", "ls-files", "-z", "godot-client"], cwd=REPO).decode().split("\0")
    tracked.extend(["godot-client/src/platform/web_bootstrap.gd", "godot-client/src/platform/web_bootstrap.tscn",
                    "godot-client/src/platform/web_prototype.gd"])
    for name in set(tracked):
        if not name:
            continue
        relative = Path(name).relative_to("godot-client")
        if relative.parts[0] in SKIP or relative.name.startswith("Godot") or relative.suffix in {".log", ".py", ".exe", ".dll"}:
            continue
        actor_pck = relative.parts[3:4] in [("face_masks",), ("rl_head_textures",)] or relative.parts[3:5] == ("equipment", "perk_capes")
        if relative.parts[:3] == ("assets", "actors", "native") and not actor_pck:
            continue
        source = REPO / name
        if not source.is_file():
            continue
        target = project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if relative.parts[:4] == ("assets", "actors", "native", "rl_head_textures") and relative.name.endswith(".png.import"):
            # Browser-only import limit for ordinary hair albedo images. Raw
            # actors and the authored PNGs remain unchanged, as does desktop art.
            import re
            target.write_text(re.sub(r'process/size_limit=\d+', 'process/size_limit=1024', target.read_text()), encoding="utf-8")
    # Nothing raw is editor-imported: the unchanged game reads these loose files.
    config_path = project / "project.godot"
    config = config_path.read_text()
    config = config.replace('run/main_scene="res://src/app/main.tscn"', 'run/main_scene="res://src/platform/web_bootstrap.tscn"')
    config = config.replace('renderer/rendering_method="forward_plus"', 'renderer/rendering_method="gl_compatibility"')
    config = config.replace('config/custom_user_dir_name="Godot/app_userdata/Eloria"', 'config/custom_user_dir_name="RabbitLandsBrowserPrototype"')
    import re
    config = re.sub(r'enabled=PackedStringArray\([^\n]*\)', 'enabled=PackedStringArray()', config)
    config_path.write_text(config, encoding="utf-8")
    registry_path = project / "data/maps/registry.json"
    registry = json.loads(registry_path.read_text())
    registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    (project / "data/maps/geometry-cache-scope.json").write_text(
        json.dumps({"schema": 1, "version": 1, "maps": [], "groups": {}, "asset_overlays": []}), encoding="utf-8")
    raw_scenes = raw_world_models(project)
    for model in raw_scenes:
        model.with_name(model.name + ".import").write_text('[remap]\n\nimporter="skip"\n', encoding="utf-8")
    import browser_asset_catalog
    catalog, files = browser_asset_catalog.load(__import__(__name__), asset_catalog, assets) if asset_catalog else browser_asset_catalog.build(__import__(__name__), assets)
    asset_source = files.source_root
    # Source scenery can point into several shared map image pools, not only
    # world/_shared/images. Mirror the already verified raw dependency closure
    # for the editor too, preserving relative URIs without importing raw maps.
    for source in files:
        if not source.is_relative_to(asset_source / "godot-client") and source.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            target = stage / source.relative_to(asset_source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    archives = catalog["groups"]["startup"]["archives"]
    cfg = {"schema": 3, **catalog, "endpoint": endpoint, "archives": archives,
           "live_asset_budget_bytes": 768 * 1024 * 1024}
    (project / "data/web_prototype.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    # A static login picture is enough for the prototype; save player choices separately.
    report = {**cfg, "raw_files": len(files), "raw_world_scenes": len(raw_scenes), "raw_bytes": sum(p.stat().st_size for p in files),
              "download_bytes": sum(row["bytes"] for row in archives),
              "client_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()}
    (stage / "build.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", required=True, type=Path)
    parser.add_argument("--templates", required=True, type=Path)
    parser.add_argument("--stage", type=Path, default=REPO / ".local/browser-prototype/build")
    parser.add_argument("--endpoint", default="ws://127.0.0.1:2002")
    parser.add_argument("--assets-base-url", default="http://127.0.0.1:8061/", help="CORS-enabled asset folder; HTTPS outside loopback")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--asset-catalog", type=Path, help="Reuse verified task-local grouped assets with identical committed source inputs")
    parser.add_argument("--cape-runtime", type=Path, help="Optional compiled browser_cape.wasm; enables extension-capable templates")
    parser.add_argument("--editor-runtime", type=Path, help="Matching browser_cape editor library; required with --cape-runtime")
    args = parser.parse_args()
    stage = args.stage.resolve()
    if not stage.is_relative_to(REPO / ".local"):
        parser.error("Prototype output must stay inside this worktree's ignored .local directory")
    stage.mkdir(parents=True, exist_ok=True)
    from urllib.parse import urlsplit
    url = urlsplit(args.assets_base_url)
    if not url.hostname or url.username or url.password or url.query or url.fragment or (url.scheme != "https" and not
            (url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"})):
        parser.error("Assets require HTTPS without credentials, query or fragments; HTTP is allowed only on loopback")
    report = stage_project(stage, args.endpoint, args.asset_catalog.resolve() if args.asset_catalog else None)
    if args.cape_runtime:
        if not args.editor_runtime: parser.error("--cape-runtime requires --editor-runtime for extension registration during export")
        stage_browser_cape(stage, args.cape_runtime.resolve(), args.editor_runtime.resolve())
    print(f"Prepared {report['raw_files']} raw files in {len(report['archives'])} verified archives", flush=True)
    if args.prepare_only:
        return
    project = stage / "project"
    template_dir = args.templates.resolve()
    variant = "web_dlink" if args.cape_runtime else "web"
    preset = f'''[preset.0]
name="Browser Prototype"
platform="Web"
runnable=true
export_filter="all_resources"
include_filter="*.json,*.csv,*.txt,*.bin"
exclude_filter="assets/ui/start_screen/*.ogv"
export_path="../site/index.html"
[preset.0.options]
custom_template/debug="{(template_dir / (variant + '_debug.zip')).as_posix()}"
custom_template/release="{(template_dir / (variant + '_release.zip')).as_posix()}"
variant/extensions_support={str(bool(args.cape_runtime)).lower()}
variant/thread_support=true
threads/emscripten_pool_size=16
threads/godot_pool_size=4
vram_texture_compression/for_desktop=true
vram_texture_compression/for_mobile=false
html/canvas_resize_policy=2
html/focus_canvas_on_start=true
progressive_web_app/enabled=false
'''
    (project / "export_presets.cfg").write_text(preset, encoding="utf-8")
    env = dict(os.environ, APPDATA=str(stage / "profile/roaming"), LOCALAPPDATA=str(stage / "profile/local"),
               TEMP=str(stage / "temp"), TMP=str(stage / "temp"))
    for folder in (env["APPDATA"], env["LOCALAPPDATA"], env["TEMP"]):
        Path(folder).mkdir(parents=True, exist_ok=True)
    for label, options in (("import", ["--editor", "--import"]),
                           ("export", ["--export-debug", "Browser Prototype", str(stage / "site/index.html")])):
        log = stage / f"{label}.log"
        configuration = project / "project.godot"
        original = configuration.read_bytes()
        # On the first import CSV translations do not exist yet. Avoid loading
        # those generated files at startup; restore the exact authored setting
        # before exporting, once the CSV importer has produced them.
        if label == "import":
            import re
            configuration.write_bytes(re.sub(rb'^locale/translations=.+\r?\n', b'', original, flags=re.MULTILINE))
        try:
            with log.open("w", encoding="utf-8") as output:
                result = subprocess.run([str(args.godot.resolve()), "--headless", "--path", str(project), *options],
                                        env=env, stdout=output, stderr=subprocess.STDOUT, timeout=600)
        finally:
            configuration.write_bytes(original)
        text = log.read_text(encoding="utf-8", errors="replace")
        if result.returncode or any(s in text for s in ("SCRIPT ERROR", "Parse Error", "ERROR:")):
            raise SystemExit(f"Browser {label} failed; inspect {log}")
    finish_site(stage, args.assets_base_url)
    print(f"Browser build ready: {stage / 'site/index.html'}", flush=True)


if __name__ == "__main__":
    main()
