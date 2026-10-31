"""The map editor's region sources stay out of a package (owner call 2026-10-05: "exclude them now").

godot-client/world_authoring holds the map editor's region scenes, their
prototype models and textures and the territory catalogs. Only the editor and
its plugins open them, never the game, yet the export packed them all: 1.77 GB
of the 2.11 GB PCK of 91ce68374. All export presets now leave world_authoring/*
out, and check_editor_sources_unpacked stops a build whose PCK still holds any
of it. The map data a package stages may not name a res://world_authoring/ path
either (check_map_data_names_no_editor_sources): the game loads what it names by
res:// path from the PCK, so such a path would fail only in the package.

The real-tree guard at the end is the static half of the proof that the game
never loads them. From main.tscn, the autoloads and every res:// path the
game's data names, it follows every path literal, scene reference and global
class name; no file it reaches lies under world_authoring or names it. The
editor plugins ([editor_plugins] in project.godot) are not roots: an exported
game never loads them. Nor is a setting of the project's own until a file the
game reaches reads it: an isles editor session binds [map_authoring]
territory_catalog_path to world_authoring (continent-v2/sw-island commits it),
and only the editor plugins read that.
"""
import fnmatch
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import struct
import subprocess
import sys

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "tools" / "package_client.py"
sys.path.insert(0, str(SOURCE.parent))
SPEC = importlib.util.spec_from_file_location("package_client_editor_sources", SOURCE)
package = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = package
SPEC.loader.exec_module(package)

REGION_SOURCES = (
    "world_authoring/regions/example/example.tscn",
    "world_authoring/regions/vale/assets/prototypes/rock.glb",
    "world_authoring/regions/vale/assets/textures/rock.jpg",
    "world_authoring/regions/vale/surfaces/worn-earth-road.tres",
    "world_authoring/territories.json",
)
RUNTIME_FILES = (
    "src/app/main.tscn",
    "src/world/biome_blend_material.gd",
    "src/dev/map_authoring_pilot/style/textures/terrain-detail-normal.png",
    "src/dev/map_authoring_pilot/style/texture_packs/delta-silt/delta-silt-v001.png",
    "assets/world/continent/_textures/albedo.png",
    "addons/map_authoring_workspace/territory_catalog.gd",
    "data/maps/registry.json",
)


def _exclude_filters() -> list[list[str]]:
    return [line.split("=", 1)[1].strip('"').split(",")
            for line in package.EXPORT_PRESETS.splitlines() if line.startswith("exclude_filter=")]


def test_all_presets_leave_the_region_sources_out():
    filters = _exclude_filters()
    assert len(filters) == len(package.PLATFORMS)
    for preset in filters:
        assert "world_authoring/*" in preset
        # Godot matches a filter case-insensitively against the res:// path and the path without it, and its *
        # crosses folders, as fnmatch's does.
        for path in REGION_SOURCES:
            assert any(fnmatch.fnmatchcase(path.lower(), f.lower()) for f in preset), path
        for path in RUNTIME_FILES:
            assert not any(fnmatch.fnmatchcase(path.lower(), f.lower()) for f in preset), path


def _write_pck(path: Path, names: list[str]) -> None:
    """A Godot 4.7 (format 4) PCK directory listing empty files with these names."""
    header = b"GDPC" + struct.pack("<4I", 4, 4, 7, 2) + struct.pack("<I", 2)
    reserved = b"\0" * 64
    directory = struct.pack("<I", len(names))
    for name in names:
        raw = name.encode("utf-8")
        raw += b"\0" * (-len(raw) % 4)
        directory += struct.pack("<I", len(raw)) + raw
        directory += struct.pack("<QQ", 0, 0) + b"\0" * 16 + struct.pack("<I", 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + struct.pack("<QQ", 0, len(header) + 16 + len(reserved)) + reserved + directory)


def test_the_pack_check_refuses_a_region_source(tmp_path):
    runtime = ["project.binary", "src/app/main.tscn.remap", "src/dev/map_authoring_pilot/style/textures/a.png.import",
               ".godot/imported/a.png-1.s3tc.ctex", "assets/world/continent/_textures/albedo.png.import"]
    _write_pck(tmp_path / "RabbitLands.pck", runtime)
    package.check_editor_sources_unpacked(tmp_path)
    for stray in ("world_authoring/regions/vale/vale.tscn.remap", "world_authoring/territories.json",
                  "world_authoring/regions/vale/assets/textures/rock.jpg.import"):
        _write_pck(tmp_path / "RabbitLands.pck", runtime + [stray])
        with pytest.raises(package.PackageError, match="1 files of the map editor's sources are in the PCK"):
            package.check_editor_sources_unpacked(tmp_path)


def test_the_build_checks_the_pack_after_the_export():
    source = SOURCE.read_text(encoding="utf-8")
    body = source[source.index("def _main(argv=None, storage=None) -> int:"):]
    export = body.index("export_project(godot, project, app_dir")
    check = body.index("check_editor_sources_unpacked(app_dir)")
    assert export < check < body.index("make_zip(stage)")
    staged = body.index("stage_eloria_assets(build_dir, stage")
    assert staged < body.index("check_map_data_names_no_editor_sources(stage)") < body.index("make_zip(stage)")


def _glb(document: dict) -> bytes:
    raw = json.dumps({"asset": {"version": "2.0"}, **document}).encode("utf-8")
    raw += b" " * (-len(raw) % 4)
    return b"glTF" + struct.pack("<II", 2, 20 + len(raw)) + struct.pack("<II", len(raw), 0x4E4F534A) + raw


def test_the_map_data_check_refuses_a_path_into_the_region_sources(tmp_path):
    # The biome-blend records carry a terrain base material's texture path as the editor published it; one
    # under world_authoring would not load from a package that leaves world_authoring out.
    stage = tmp_path / "Eloria-Windows-x"
    maps = stage / "eloria-assets" / "maps"
    good = {
        "four-gates/chunks/02_07/world.json": json.dumps({"biomeBlend": {"palette": [{"albedoTexture":
            "res://src/dev/map_authoring_pilot/style/texture_packs/delta-silt/delta-silt-v001.png"}]}}),
        # The legacy maps' provenance names the region sources; nothing the game runs opens it.
        "four-gates/authoring/continent-authoring.json": json.dumps({"scene":
            "res://world_authoring/regions/four_gates/four_gates.tscn"}),
        "four-gates/world.glb": _glb({"images": [{"uri": "textures/a.png"}]}),
        # Binary data is not read.
        "four-gates/collision.escg": b"\0res://world_authoring/regions/x.png\0",
    }
    for relative, content in good.items():
        (maps / relative).parent.mkdir(parents=True, exist_ok=True)
        (maps / relative).write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    package.check_map_data_names_no_editor_sources(stage)
    bad = {
        "four-gates/chunks/02_08/world.json": json.dumps({"biomeBlend": {"palette": [{"albedoTexture":
            "res://world_authoring/regions/four_gates/assets/textures/ground.png"}]}}),
        "nymara-regions/vale/world.glb": _glb({"extras": {"material": "res://world_authoring/regions/vale/m.tres"}}),
        "nymara-regions/vale/model.gltf": json.dumps({"extras": {"x": "res://world_authoring/territories.json"}}),
    }
    for relative, content in bad.items():
        (maps / relative).parent.mkdir(parents=True, exist_ok=True)
        (maps / relative).write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
        with pytest.raises(package.PackageError, match="1 staged map files name the map editor's sources") as error:
            package.check_map_data_names_no_editor_sources(stage)
        assert relative in str(error.value) and "res://world_authoring/" in str(error.value)
        (maps / relative).unlink()
    package.check_map_data_names_no_editor_sources(stage)


# --- what the game can reach ---------------------------------------------------------

TEXT_SUFFIXES = (".gd", ".tscn", ".tres", ".gdshader", ".gdshaderinc", ".godot", ".cfg", ".json", ".csv",
                 ".txt", ".gdextension")
UNSHIPPED = ("docs/", "tests/", "tools/", "test-artifacts/")
RES_PATH = re.compile(r"""res://[^"'\s)\],]*""")
CLASS_NAME = re.compile(r"^\s*(?:@\w+\s+)*class_name\s+(\w+)", re.M)
EXT_RESOURCE = re.compile(r'\[ext_resource[^\]]*\bpath="([^"]+)"')
INCLUDE = re.compile(r'#include\s+"([^"]+)"')
IDENTIFIER = re.compile(r"\b[A-Z]\w*\b")
NAMED_FILE = TEXT_SUFFIXES + (".png", ".jpg", ".jpeg", ".webp", ".glb", ".gltf", ".ogg", ".wav", ".bin")
# project.godot sections: the engine's own, which the exported game reads, and the editor's, which it never does.
ENGINE_SECTIONS = {"application", "audio", "autoload", "debug", "display", "gui", "input", "input_devices",
                   "internationalization", "layer_names", "navigation", "network", "physics", "rendering",
                   "shader_globals", "global_group", "threading", "xr", "accessibility", "animation", "memory"}
EDITOR_SECTIONS = {"editor", "editor_plugins", "importer_defaults", "filesystem", "dotnet"}


def _gdscript(source: str) -> tuple[str, list[str]]:
    """GDScript code with its comments and strings blanked out, and its string literals."""
    code: list[str] = []
    literals: list[str] = []
    i = 0
    while i < len(source):
        c = source[i]
        if c == "#":
            end = source.find("\n", i)
            i = len(source) if end < 0 else end
            continue
        if c in "\"'":
            quote = source[i:i + 3] if source[i:i + 3] in ('"""', "'''") else c
            j = i + len(quote)
            while j < len(source) and not source.startswith(quote, j) and not (len(quote) == 1 and source[j] == "\n"):
                j += 2 if source[j] == "\\" else 1
            literals.append(source[i + len(quote):j])
            code.append(" ")
            i = j + len(quote)
            continue
        code.append(c)
        i += 1
    return "".join(code), literals


def runtime_closure(files: list[str], read) -> dict[str, tuple[str | None, str]]:
    """{project path: (the file that reached it, how)} for every file the game can reach.

    files are the project's tracked paths (relative to godot-client); read(path) returns a text file's
    contents, or None when it cannot be read. A literal naming a folder, or the start of a built path, reaches
    every file under it, which over-approximates what a script builds.
    """
    tracked = set(files)
    folders: dict[str, list[str]] = {}
    for path in files:
        parts = path.split("/")
        for i in range(1, len(parts)):
            folders.setdefault("/".join(parts[:i]), []).append(path)
    texts: dict[str, str] = {}

    def text(path: str) -> str:
        if path not in texts:
            texts[path] = (read(path) or "") if path.lower().endswith(TEXT_SUFFIXES) else ""
        return texts[path]

    classes = {name: path for path in files if path.endswith(".gd") and not path.startswith(UNSHIPPED)
               for name in CLASS_NAME.findall(text(path))}

    def resolve(literal: str, base: str) -> list[str]:
        literal = literal.strip()
        if literal.startswith("res://"):
            path = literal[len("res://"):]
        elif "://" in literal or not literal or " " in literal or not ("/" in literal or literal.endswith(NAMED_FILE)):
            return []
        else:
            path = str(PurePosixPath(PurePosixPath(base).parent, literal))
        path = path.split("::")[0].rstrip("/")
        if not path or path.startswith("../"):
            return []
        if path in tracked:
            return [path]
        if path in folders:
            return folders[path]
        return [p for p in files if p.startswith(path)] if literal.startswith("res://") else []

    def edges(path: str) -> list[tuple[str, str]]:
        source = text(path)
        found: list[tuple[str, str]] = []
        if path.endswith(".gd"):
            code, literals = _gdscript(source)
            found += [(t, f"literal {s!r}") for s in literals for t in resolve(s, path)]
            found += [(classes[n], f"class {n}") for n in set(IDENTIFIER.findall(code))
                      if n in classes and classes[n] != path]
        elif source:
            for reference in EXT_RESOURCE.findall(source) + INCLUDE.findall(source) + RES_PATH.findall(source):
                found += [(t, f"names {reference}") for t in resolve(reference, path)]
            found += [(classes[n], f"script_class {n}") for n in set(re.findall(r'script_class="(\w+)"', source))
                      if n in classes]
        return found

    roots: list[tuple[str, str]] = []
    # A project's own setting ([map_authoring] territory_catalog_path, which an isles editor session binds to
    # world_authoring) is a root only once a file the game reaches names it.
    settings: dict[str, list[str]] = {}
    section = ""
    for line in text("project.godot").splitlines():
        header = re.match(r"^\[(\w+)\]", line)
        if header:
            section = header.group(1)
            continue
        targets = [t for r in RES_PATH.findall(line) for t in resolve(r, "")]
        if section in ENGINE_SECTIONS:
            roots += [(t, f"project.godot [{section}]") for t in targets]
        elif section not in EDITOR_SECTIONS and targets and "=" in line:
            settings[f"{section}/{line.split('=', 1)[0].strip()}"] = targets
    for path in files:
        if path.startswith(("data/", "schemas/", "assets/")) and not path.endswith((".gd", ".tscn", ".tres")):
            roots += [(t, f"data {path}") for r in RES_PATH.findall(text(path)) for t in resolve(r, path)]
    reached: dict[str, tuple[str | None, str]] = {}
    queue = []

    def visit(targets: list[tuple[str, str]], via: str | None) -> None:
        for target, why in targets:
            if target not in reached:
                reached[target] = (via, why)
                queue.append(target)

    visit(roots, None)
    while queue:
        while queue:
            current = queue.pop()
            visit(edges(current), current)
        for key, targets in list(settings.items()):
            # Read by its name, or by one built from its section ("map_authoring/" + key, as the editor's
            # usability settings do).
            section = key.split("/", 1)[0] + "/"
            reader = next((p for p in reached if key in text(p) or section in text(p)), None)
            if reader is not None:
                del settings[key]
                visit([(t, f"project.godot setting {key}, read by {reader}") for t in targets], None)
    return reached


def names_world_authoring(path: str, source: str) -> bool:
    """Whether a file names world_authoring: in a script's string literals (not its comments), or anywhere in
    any other text file."""
    if path.endswith(".gd"):
        return any("world_authoring" in literal for literal in _gdscript(source)[1])
    return "world_authoring" in source


def _chain(reached: dict, path: str) -> str:
    steps = []
    while path is not None:
        steps.append(f"{path} ({reached[path][1]})")
        path = reached[path][0]
    return " <- ".join(steps)


def test_the_closure_follows_what_a_script_can_load():
    # Teeth: a preload, a built path, a global class and a project setting the game reads each reach a region
    # source from main.tscn; the editor plugins and a setting only they read do not.
    sources = {
        "project.godot": '[application]\nrun/main_scene="res://src/app/main.tscn"\n'
                         '[autoload]\nState="*res://src/state.gd"\n'
                         '[editor_plugins]\nenabled=PackedStringArray("res://addons/tool/plugin.cfg")\n'
                         '[map_authoring]\ncatalog_path="res://world_authoring/territories.json"\n',
        "src/app/main.tscn": '[ext_resource type="Script" path="res://src/app/main.gd" id="1"]\n',
        "src/app/main.gd": 'const Surface := preload("surface.gd")\nfunc _ready():\n\tRegionReader.new()\n',
        "src/app/surface.gd": 'class_name Surface\n',
        "src/dev/region_reader.gd": 'class_name RegionReader\n'
                                    'func path(id): return "res://world_authoring/regions/%s/spec.json" % id\n',
        "src/state.gd": '# res://world_authoring/in-a-comment.json\nvar x := 1\n',
        "addons/tool/plugin.cfg": '[plugin]\nscript="plugin.gd"\n',
        "addons/tool/plugin.gd": 'const C := "res://world_authoring/territories.json"\n'
                                 'var catalog = ProjectSettings.get_setting("map_authoring/catalog_path")\n',
        "world_authoring/territories.json": "{}",
        "world_authoring/regions/vale/spec.json": "{}",
    }
    reached = runtime_closure(sorted(sources), sources.get)
    assert "src/dev/region_reader.gd" in reached and "src/app/surface.gd" in reached
    assert "addons/tool/plugin.gd" not in reached
    assert [p for p in reached if p.startswith("world_authoring/")] == []
    assert [p for p in sorted(reached) if names_world_authoring(p, sources.get(p, ""))] == [
        "src/dev/region_reader.gd"]
    # A project setting of the project's own is followed once something the game runs reads it.
    sources["src/state.gd"] = 'var catalog = ProjectSettings.get_setting("map_authoring/catalog_path")\n'
    reached = runtime_closure(sorted(sources), sources.get)
    assert "world_authoring/territories.json" in reached
    # So is one read by a name built from its section.
    sources["src/state.gd"] = ('const PREFIX := "map_authoring/"\n'
                               'var catalog = ProjectSettings.get_setting(PREFIX + "catalog_path")\n')
    reached = runtime_closure(sorted(sources), sources.get)
    assert "world_authoring/territories.json" in reached
    sources["src/state.gd"] = 'const SPEC := preload("res://world_authoring/regions/vale/spec.json")\n'
    reached = runtime_closure(sorted(sources), sources.get)
    assert "world_authoring/regions/vale/spec.json" in reached


def test_nothing_the_game_runs_reaches_world_authoring():
    try:
        tracked = package.tracked(package.REPO, "godot-client")
    except (OSError, subprocess.CalledProcessError) as error:
        pytest.skip(f"git cannot list this checkout: {error}")
    files = [p[len("godot-client/"):] for p in tracked if p.startswith("godot-client/")]
    missing: list[str] = []

    def read(path: str) -> str | None:
        try:
            raw = (package.CLIENT / path).read_bytes()
        except OSError:
            missing.append(path)
            return None
        return None if b"\0" in raw[:8000] else raw.decode("utf-8", "replace")

    reached = runtime_closure(files, read)
    if missing:
        pytest.skip(f"{len(missing)} files the game reads are not checked out, e.g. {missing[0]}")
    # Not vacuous: the walk gets from main.tscn to the map-authoring material the game's terrain uses.
    for path in ("src/app/main.gd", "src/network/network_client.gd", "src/world/biome_blend_material.gd",
                 "src/dev/map_authoring_pilot/style/map_authoring_surface.gd"):
        assert path in reached, path
    inside = [_chain(reached, p) for p in sorted(reached) if p.startswith("world_authoring/")]
    assert inside == []
    naming = []
    for path in sorted(reached):
        source = read(path) if path.lower().endswith(TEXT_SUFFIXES) else None
        if source and names_world_authoring(path, source):
            naming.append(_chain(reached, path))
    assert naming == []
    # The isles' editor binding (continent-v2/sw-island's project.godot, or an editor session's own edit) is read
    # by the editor plugins only, so it changes nothing.
    binding = '\n[map_authoring]\nterritory_catalog_path="res://world_authoring/continent-v2/territories.json"\n'

    def read_bound(path: str) -> str | None:
        return (read(path) or "") + binding if path == "project.godot" else read(path)

    assert sorted(runtime_closure(files, read_bound)) == sorted(reached)
