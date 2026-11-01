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
                archive.write(source, source.relative_to(REPO).as_posix())
        row = describe(temporary)
        target = assets / (row["sha256"] + ".zip")
        temporary.replace(target)
        result.append({**row, "file": target.name})
    return result


def finish_site(stage: Path, assets_base_url: str):
    site, assets = stage / "site", stage / "assets"
    pack = site / "index.pck"
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
    report = json.loads((stage / "build.json").read_text())
    manifest = {"schema": 1, "base_url": assets_base_url.rstrip("/") + "/",
                "pack": {"bytes": pack.stat().st_size, "parts": parts},
                "wasm": {**wasm, "file": target.name}, "archives": report["archives"]}
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
    shell = site / "index.html"
    text = shell.read_text(encoding="utf-8")
    if text.count("engine.startGame({") != 1:
        raise ValueError("Web template startup changed")
    text = text.replace('<script src="index.js"></script>', '<script src="index.js"></script>\n<script src="browser-assets.js"></script>')
    shell.write_text(text.replace("engine.startGame({", "RabbitLandsBrowser.start(engine, GODOT_CONFIG, {"), encoding="utf-8")
    # The launch folder cannot accidentally serve the large payloads.
    pack.unlink()
    (site / "index.wasm").unlink()
    (site / "assets.zip").unlink(missing_ok=True)
    report.update({"assets_base_url": assets_base_url,
                   "asset_download_bytes": sum(row["bytes"] for row in [*report["archives"], *parts, wasm]),
                   "launch_site_bytes": sum(p.stat().st_size for p in site.iterdir() if p.is_file())})
    (stage / "build.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


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


def stage_project(stage: Path, endpoint: str) -> dict:
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
    registry["maps"] = {key: row for key, row in registry["maps"].items() if key in MAPS}
    registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    (project / "data/maps/geometry-cache-scope.json").write_text(
        json.dumps({"schema": 1, "version": 1, "maps": [], "groups": {}, "asset_overlays": []}), encoding="utf-8")
    files = raw_files()
    archives = raw_archives(files, assets)
    cfg = {"schema": 2, "maps": list(MAPS), "endpoint": endpoint, "archives": archives}
    (project / "data/web_prototype.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    # A static login picture is enough for the prototype; save player choices separately.
    report = {**cfg, "raw_files": len(files), "raw_bytes": sum(p.stat().st_size for p in files),
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
    report = stage_project(stage, args.endpoint)
    print(f"Prepared {report['raw_files']} raw files in {len(report['archives'])} verified archives", flush=True)
    if args.prepare_only:
        return
    project = stage / "project"
    template_dir = args.templates.resolve()
    preset = f'''[preset.0]
name="Browser Prototype"
platform="Web"
runnable=true
export_filter="all_resources"
include_filter="*.json,*.csv,*.txt,*.bin"
exclude_filter="assets/ui/start_screen/*.ogv"
export_path="../site/index.html"
[preset.0.options]
custom_template/debug="{(template_dir / 'web_debug.zip').as_posix()}"
custom_template/release="{(template_dir / 'web_release.zip').as_posix()}"
variant/extensions_support=false
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
        with log.open("w", encoding="utf-8") as output:
            result = subprocess.run([str(args.godot.resolve()), "--headless", "--path", str(project), *options],
                                    env=env, stdout=output, stderr=subprocess.STDOUT, timeout=600)
        text = log.read_text(encoding="utf-8", errors="replace")
        if result.returncode or any(s in text for s in ("SCRIPT ERROR", "Parse Error", "ERROR:")):
            raise SystemExit(f"Browser {label} failed; inspect {log}")
    finish_site(stage, args.assets_base_url)
    print(f"Browser build ready: {stage / 'site/index.html'}", flush=True)


if __name__ == "__main__":
    main()
