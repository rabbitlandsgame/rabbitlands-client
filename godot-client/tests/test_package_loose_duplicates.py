#!/usr/bin/env python3
"""Loose duplicates of PCK-imported resources (W2-UD-02, tools/package_client.py loose_duplicate_plan).

    python -m pytest -q godot-client/tests/test_package_loose_duplicates.py

The export packs an imported resource as its .import remap plus products; a loose copy beside the PCK
serves only a raw read. The packager leaves a loose audio or image file out when the PCK holds its
import and nothing can read it raw: the running client's path literals are each followed to the
resource system (else counted as a raw read), a glTF URI is a raw read unless the AW-03 actor parse
takes the image from the import, shipped data that names a file keeps it, and so do the stage's own
readers (installer helper, Inno). LiteralUses holds the use-site scan to snippets; Fixture stages a small
tree for real against a written PCK; CommittedClient runs the scan over this checkout's runtime code
for the readers the plan names (HUD medallion, leaderboard art, login posters, menu icons, cursors).
"""
from __future__ import annotations

import json
import re
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS.parent / "tools"))

import package_client as packager  # noqa: E402

REPO = TESTS.parents[1]


def write(root: Path, relative: str, data) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    elif isinstance(data, str):
        path.write_text(data, encoding="utf-8", newline="\n")
    else:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def glb(images: list[str], material_extensions: tuple[str, ...] = ()) -> bytes:
    """A GLB holding only a JSON chunk naming these images by URI (and one material using these
    extensions)."""
    document = {"asset": {"version": "2.0"}, "images": [{"uri": uri} for uri in images]}
    if material_extensions:
        document["materials"] = [{"extensions": {name: {} for name in material_extensions}}]
    document = json.dumps(document).encode()
    document += b" " * (-len(document) % 4)
    return b"glTF" + struct.pack("<II", 2, 20 + len(document)) + struct.pack("<II", len(document), 0x4E4F534A) \
        + document


def write_pck(path: Path, names: list[str]) -> None:
    """A Godot 4.7 (format 4) PCK directory listing empty files with these names."""
    path.parent.mkdir(parents=True, exist_ok=True)
    header = b"GDPC" + struct.pack("<4I", 4, 4, 7, 2) + struct.pack("<I", 2)
    reserved = b"\0" * 64
    directory = struct.pack("<I", len(names))
    for name in names:
        raw = name.encode("utf-8")
        raw += b"\0" * (-len(raw) % 4)
        directory += struct.pack("<I", len(raw)) + raw + struct.pack("<QQ", 0, 0) + b"\0" * 16 + struct.pack("<I", 0)
    path.write_bytes(header + struct.pack("<QQ", 0, len(header) + 16 + len(reserved)) + reserved + directory)


def uses(scripts: dict[str, str], autoloads: dict[str, str] | None = None) -> dict:
    """_LiteralUses over GDScript snippets (godot-client-relative names), every asset literal relevant."""
    files = {"godot-client/" + name: text for name, text in scripts.items()}
    return packager._LiteralUses(files, autoloads or {}).uses(lambda literal: "assets/" in literal)


class LiteralUses(unittest.TestCase):
    def verdict(self, record: dict) -> str:
        if record["raw"]:
            return "raw"
        if record["exact"]:
            return "exact"
        return "data" if record["data"] else "safe"

    def test_a_constant_used_only_by_the_resource_system_is_safe(self):
        found = uses({"src/a.gd": (
            'const ROOT := "res://assets/audio/"\n'
            'const CATALOG := "res://assets/audio/catalog.json"\n'
            "func _ready() -> void:\n"
            "\tvar file := FileAccess.open(CATALOG, FileAccess.READ)\n"
            "\tvar catalog: Variant = JSON.parse_string(file.get_as_text())\n"
            "\tfor bed: Dictionary in catalog.beds:\n"
            '\t\tvar stream: Resource = load(ROOT + str(bed.get("file", "")))\n'
            "\tif ResourceLoader.exists(ROOT + \"x.ogg\"):\n"
            "\t\tpass\n")})
        self.assertEqual(self.verdict(found["res://assets/audio/"]), "safe")
        self.assertEqual(self.verdict(found["res://assets/audio/catalog.json"]), "data")
        self.assertEqual({path for path, _ in found["res://assets/audio/catalog.json"]["data"]},
                         {"godot-client/assets/audio/catalog.json"})

    def test_a_constant_path_built_from_constants_is_read_as_that_one_file(self):
        found = uses({"src/a.gd": (
            'const DIRECTORY := "res://assets/audio/"\n'
            'const PROGRAM := DIRECTORY + "music-program.json"\n'
            "func _ready() -> void:\n"
            "\tvar text := FileAccess.get_file_as_string(PROGRAM)\n"
            '\tvar icon := "res://assets/ui/a.png"\n'
            "\tif FileAccess.file_exists(icon):\n"
            "\t\tpass\n"
            "\tload(DIRECTORY + text)\n")})
        self.assertEqual(self.verdict(found["res://assets/audio/"]), "data")
        self.assertEqual(self.verdict(found["res://assets/ui/a.png"]), "exact")

    def test_a_raw_fallback_reads_the_folder_its_pattern_builds(self):
        found = uses({"src/medallion.gd": (
            "func configure(design: String) -> void:\n"
            '\tvar path := "res://assets/ui/hud-borders/%s.png" % design\n'
            "\tif ResourceLoader.exists(path):\n"
            "\t\tload(path)\n"
            "\telse:\n"
            "\t\tvar source := Image.load_from_file(ProjectSettings.globalize_path(path))\n")})
        record = found["res://assets/ui/hud-borders/%s.png"]
        self.assertEqual(self.verdict(record), "raw")
        self.assertTrue(any(joined for joined, _ in record["raw"]))
        self.assertEqual(packager._literal_reach(REPO, "res://assets/ui/hud-borders/%s.png", True),
                         (set(), {"godot-client/assets/ui/hud-borders/"}))

    def test_a_helper_of_the_same_script_returns_the_value_to_its_caller(self):
        found = uses({"src/a.gd": (
            'const ROOT := "res://assets/world/"\n'
            "static func is_world(path: String) -> bool:\n"
            "\treturn _canonical(path).begins_with(_canonical(ROOT))\n"
            "static func _canonical(path: String) -> String:\n"
            "\treturn ProjectSettings.globalize_path(path).simplify_path()\n")})
        self.assertEqual(self.verdict(found["res://assets/world/"]), "safe")

    def test_another_scripts_function_is_followed_through_its_alias_or_class_name(self):
        scripts = {
            "src/pool.gd": ("class_name Pool\n"
                            "static func load_image(path: String) -> Image:\n"
                            "\treturn Image.load_from_file(path)\n"
                            "static func load_texture(path: String) -> Texture2D:\n"
                            "\treturn load(path)\n"),
            "src/a.gd": ('const Helper := preload("res://src/pool.gd")\n'
                         "func _ready() -> void:\n"
                         '\tHelper.load_texture("res://assets/ui/a.png")\n'
                         '\tPool.load_image("res://assets/ui/b.png")\n')}
        found = uses(scripts)
        self.assertEqual(self.verdict(found["res://assets/ui/a.png"]), "safe")
        self.assertEqual(self.verdict(found["res://assets/ui/b.png"]), "raw")

    def test_what_the_scan_cannot_follow_counts_as_a_raw_read(self):
        found = uses({"src/a.gd": (
            "var cursors\n"
            "signal picked(path)\n"
            "func _ready() -> void:\n"
            '\tcursors.configure("res://assets/ui/cursors/cursors.json")\n'
            '\tpicked.emit("res://assets/ui/b.png")\n'
            '\tvar stream := VideoStreamTheora.new()\n'
            '\tstream.file = "res://assets/ui/c.ogv"\n'
            "func path() -> String:\n"
            '\treturn "res://assets/ui/d.png"\n'
            "func moved(old: String) -> void:\n"
            '\tvar path := old.replace("res://old/", "res://assets/ui/moved/")\n'
            "\tImage.load_from_file(path)\n")})
        for literal in ("res://assets/ui/cursors/cursors.json", "res://assets/ui/b.png",
                        "res://assets/ui/c.ogv", "res://assets/ui/d.png", "res://assets/ui/moved/"):
            with self.subTest(literal=literal):
                self.assertEqual(self.verdict(found[literal]), "raw")

    def test_comparisons_patterns_and_keys_read_nothing(self):
        found = uses({"src/a.gd": (
            "const ICONS := {\"a\": \"res://assets/ui/icons/a.png\"}\n"
            "func _ready(path: String) -> void:\n"
            '\tif path == "res://assets/ui/x.png": pass\n'
            '\tvar at := path.find("/godot-client/assets/")\n'
            '\tvar rest := path.trim_prefix("res://assets/ui/")\n'
            "\tvar seen := {}\n"
            '\tseen["res://assets/ui/y.png"] = true\n'
            "\tvar texture: Texture2D = load(ICONS[\"a\"])\n"
            '\tprint("res://assets/ui/z.png")\n')})
        for literal in ("res://assets/ui/x.png", "/godot-client/assets/", "res://assets/ui/",
                        "res://assets/ui/y.png", "res://assets/ui/icons/a.png", "res://assets/ui/z.png"):
            with self.subTest(literal=literal):
                self.assertEqual(self.verdict(found[literal]), "safe")

    def test_loops_and_members_carry_the_value(self):
        found = uses({
            "src/a.gd": ("class_name Art\n"
                         'const ROOT := "res://assets/ui/art/"\n'
                         'var poster := "res://assets/ui/p.jpg"\n'
                         "func _ready() -> void:\n"
                         '\tfor path in ["res://assets/ui/l1.png", "res://assets/ui/l2.png"]:\n'
                         "\t\tload(path)\n"
                         '\tfor raw_path in ["res://assets/ui/r1.png"]:\n'
                         "\t\tImage.load_from_file(raw_path)\n"
                         "func show() -> void:\n"
                         "\tImage.load_from_file(poster)\n"),
            "src/b.gd": ("func _ready() -> void:\n"
                         '\tvar image := Image.load_from_file(Art.ROOT + "x.png")\n')})
        self.assertEqual(self.verdict(found["res://assets/ui/l1.png"]), "safe")
        self.assertEqual(self.verdict(found["res://assets/ui/r1.png"]), "raw")
        self.assertEqual(self.verdict(found["res://assets/ui/p.jpg"]), "raw")
        # Another script's constant joined in a raw read: its folder counts as read.
        self.assertEqual(self.verdict(found["res://assets/ui/art/"]), "raw")

    def test_dispatch_super_branches_and_repeated_calls_reach_the_raw_read(self):
        # Review fixes: each of these reads the literal raw, and the scan once cleared it.
        cases = {
            "a subclass override of a helper the base calls": {
                "src/base.gd": ("class_name Base\n"
                                "func _ready() -> void:\n"
                                '\t_apply("res://assets/ui/a.png")\n'
                                "func _apply(path: String) -> void:\n"
                                "\tload(path)\n"),
                "src/child.gd": ("extends Base\n"
                                 "func _apply(path: String) -> void:\n"
                                 "\tImage.load_from_file(path)\n")},
            "a bare super() call": {
                "src/base.gd": "class_name Base\nfunc _init(path: String) -> void:\n\tImage.load_from_file(path)\n",
                "src/child.gd": 'extends Base\nfunc _init() -> void:\n\tsuper("res://assets/ui/a.png")\n'},
            "super.f() goes to the base's f": {
                "src/base.gd": "class_name Base\nfunc show(path: String) -> void:\n\tImage.load_from_file(path)\n",
                "src/child.gd": ("extends Base\n"
                                 "func show(path: String) -> void:\n"
                                 "\tsuper.show(path)\n"
                                 "func _ready() -> void:\n"
                                 '\tshow("res://assets/ui/a.png")\n')},
            "a match branch's one-line return": {
                "src/a.gd": ("static func path_for(kind: String) -> String:\n"
                             "\tmatch kind:\n"
                             '\t\t"a": return "res://assets/ui/a.png"\n'
                             '\treturn ""\n'
                             "func _ready() -> void:\n"
                             '\tImage.load_from_file(path_for("a"))\n')},
            "a match binding branch's one-line return": {
                "src/a.gd": ("static func path_for(kind: String) -> String:\n"
                             "\tmatch kind:\n"
                             '\t\tvar k when k == "a": return "res://assets/ui/a.png"\n'
                             '\treturn ""\n')},
            "the second call of a helper, whose return is read raw": {
                "src/a.gd": ("func f(path: String) -> String:\n"
                             "\treturn path\n"
                             "func _ready() -> void:\n"
                             '\tvar x := "res://assets/ui/a.png"\n'
                             "\tload(f(x))\n"
                             "\tImage.load_from_file(f(x))\n")},
        }
        for label, scripts in cases.items():
            with self.subTest(case=label):
                self.assertEqual(self.verdict(uses(scripts)["res://assets/ui/a.png"]), "raw")
        # A match pattern is still only compared with.
        found = uses({"src/a.gd": 'func f(x) -> void:\n\tmatch x:\n\t\t"res://assets/ui/a.png":\n\t\t\tpass\n'})
        self.assertEqual(self.verdict(found["res://assets/ui/a.png"]), "safe")

    def test_a_followed_parameter_returns_the_same_to_every_call(self):
        # What a helper returned is remembered by the call it was followed for, not by the
        # identity of a list that may be freed and reused: the second call gets it too.
        scanner = packager._LiteralUses({"godot-client/src/a.gd": "func f(path: String) -> String:\n\treturn path\n"},
                                        {})
        script = scanner.files["godot-client/src/a.gd"]
        record = {"raw": set(), "exact": set(), "data": set(), "safe": 0}
        visited, returned = {}, []
        scanner._follow_local(script, script.by_name["f"][0], "path", False, 1, record, visited, returned)
        self.assertEqual(returned, [False])
        returned.clear()
        scanner._follow_local(script, script.by_name["f"][0], "path", False, 1, record, visited, returned)
        self.assertEqual(returned, [False])
        self.assertFalse(record["raw"])

    def test_a_holder_extended_in_place_is_joined(self):
        found = uses({"src/a.gd": ("var stem := \"res://assets/ui/icon_\"\n"
                                   "func _ready(name: String) -> void:\n"
                                   "\tvar path := \"res://assets/ui/sheet\"\n"
                                   "\tpath += name\n"
                                   "\tImage.load_from_file(path)\n"
                                   "\tstem += name\n"
                                   "\tFileAccess.file_exists(stem)\n")})
        for literal in ("res://assets/ui/sheet", "res://assets/ui/icon_"):
            with self.subTest(literal=literal):
                record = found[literal]
                self.assertEqual(self.verdict(record), "raw")
                self.assertTrue(all(joined for joined, _ in record["raw"]), record["raw"])
        self.assertEqual(packager._literal_reach(REPO, "res://assets/ui/icon_", True),
                         (set(), {"godot-client/assets/ui/icon_"}))

    def test_bare_roots_and_words_name_nothing(self):
        self.assertIsNone(packager._literal_repo_path("assets"))
        self.assertEqual(packager._literal_repo_path("res://"), "godot-client/")
        self.assertEqual(packager._literal_repo_path("assets/ui/x.png"), "godot-client/assets/ui/x.png")
        self.assertIsNone(packager._literal_repo_path("res://../eloria-assets/maps/x/world.json"))


AW03_IMAGES = "func resolve_uri(base, uri):\n\tpass\nfunc x(path):\n\tResourceLoader.load(path, \"Texture2D\")\n"
AW03_CACHE = "static func parse(state, path):\n\tActorImages.enable(state, path)\n"


class Fixture(unittest.TestCase):
    """A small client tree, its imports and a PCK, staged for real."""

    IMPORTED = ["assets/audio/music_a.ogg", "assets/audio/hit.wav", "assets/ui/hud-borders/gold.png",
                "assets/ui/cursors/arrow.png", "assets/ui/icons/sheet.png", "assets/ui/old.png",
                "assets/world/tex/grass.png", "assets/world/props/crate_albedo.png", "assets/ui/emblem.png",
                "assets/ui/panel_bg.png", "assets/branding/rabbitlands-mark-64.png",
                "assets/branding/rabbitlands-icon.png", "assets/ui/unpacked.png"]

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="loose-duplicates-tree-"))
        self.app = Path(tempfile.mkdtemp(prefix="loose-duplicates-app-")) / "app"
        root, client = self.root, "godot-client/"
        write(root, client + "project.godot",
              '[application]\nconfig/icon="res://assets/branding/rabbitlands-icon.png"\n')
        write(root, client + "assets/audio/catalog.json", {"beds": [{"file": "music_a.ogg"}]})
        write(root, client + "assets/audio/CREDITS.txt", "credits\n")
        write(root, client + "src/audio/director.gd",
              'const CATALOG_PATH := "res://assets/audio/catalog.json"\n'
              'const AUDIO_DIRECTORY := "res://assets/audio/"\n'
              "func _load_catalog() -> void:\n"
              "\tvar file := FileAccess.open(CATALOG_PATH, FileAccess.READ)\n"
              "\tvar catalog: Variant = JSON.parse_string(file.get_as_text())\n"
              "\tfor bed: Dictionary in catalog.beds:\n"
              '\t\tvar music: Resource = load(AUDIO_DIRECTORY + str(bed.get("file", "")))\n'
              "func hit() -> void:\n"
              '\tvar stream := preload("res://assets/audio/hit.wav")\n')
        write(root, client + "src/ui/medallion.gd",
              "func configure(design: String) -> void:\n"
              '\tvar path := "res://assets/ui/hud-borders/%s.png" % design\n'
              "\tif ResourceLoader.exists(path):\n"
              "\t\tload(path)\n"
              "\telse:\n"
              "\t\tImage.load_from_file(ProjectSettings.globalize_path(path))\n")
        write(root, client + "assets/ui/cursors/cursors.json", {"cursors": [{"file": "arrow.png"}]})
        write(root, client + "src/ui/cursors.gd",
              "class_name Cursors\n"
              "func configure(manifest_path: String) -> bool:\n"
              "\tvar text := FileAccess.get_file_as_string(ProjectSettings.globalize_path(manifest_path))\n"
              "\tvar data: Variant = JSON.parse_string(text)\n"
              "\tfor entry: Dictionary in data.cursors:\n"
              "\t\tvar image := Image.new()\n"
              "\t\timage.load(ProjectSettings.globalize_path(manifest_path.get_base_dir().path_join(entry.file)))\n"
              "\treturn true\n")
        write(root, client + "src/app/main.gd",
              "var cursors := Cursors.new()\n"
              'const SHEET := "res://assets/ui/icons/sheet.png"\n'
              "func _ready() -> void:\n"
              '\tcursors.configure("res://assets/ui/cursors/cursors.json")\n'
              "\tvar sheet: Texture2D = load(SHEET)\n"
              '\tvar key := "res://" + name\n'
              "\tsomething_unknown(key)\n")
        write(root, client + "data/ui/panels.json", {"background": "res://assets/ui/panel_bg.png", "assets": 1})
        write(root, "eloria-assets/maps/meadow/world.json",
              {"asset": {"glb": "world.glb"}, "ground": "res://assets/world/tex/grass.png"})
        write(root, "eloria-assets/maps/meadow/world.glb", glb([]))
        write(root, client + "assets/world/props/crate.glb", glb(["crate_albedo.png"]))
        write(root, client + "assets/actors/native/equipment/sword.glb", glb(["../../../ui/emblem.png"]))
        write(root, client + "src/actors/actor_images.gd", AW03_IMAGES)
        write(root, client + "src/actors/glb_scene_cache.gd", AW03_CACHE)
        write(root, client + "assets/branding/rabbitlands-icon.ico", b"\0\0\1\0")
        self.products = {}
        for local in self.IMPORTED:
            write(root, client + local, b"\x89PNG" + local.encode())
            product = ".godot/imported/" + Path(local).name + "-0123.ctex"
            write(root, client + product, b"GST2")
            write(root, client + local + ".import",
                  f'[remap]\n\nimporter="texture"\npath="res://{product}"\n\n[deps]\n\n'
                  f'dest_files=["res://{product}"]\n')
            self.products[local] = product
        self._tracked, self._log = packager.tracked, packager.log
        packager._LOOSE_READ_CACHE.clear()

        def tracked(tree, *pathspecs):
            files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*")
                           if p.is_file() and ".godot" not in p.parts)
            return [p for p in files if any(p == s or p.startswith(s.rstrip("/") + "/") for s in pathspecs)]
        packager.tracked = tracked
        packager.log = lambda message: None

    def tearDown(self):
        packager.tracked, packager.log = self._tracked, self._log
        packager._LOOSE_READ_CACHE.clear()
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.app.parent, ignore_errors=True)

    def packed(self, missing_products=("assets/ui/unpacked.png",)) -> set[str]:
        names = {"project.binary"}
        for local, product in self.products.items():
            names.add(local + ".import")
            if local not in missing_products:
                names.add(product)
        return names

    def test_the_plan_drops_only_what_nothing_reads_raw(self):
        plan = packager.loose_duplicate_plan(self.root, self.packed())
        self.assertEqual(set(plan["drop"]), {"assets/audio/music_a.ogg", "assets/audio/hit.wav",
                                             "assets/ui/icons/sheet.png", "assets/ui/old.png",
                                             "assets/ui/emblem.png"})
        keep = plan["keep"]
        self.assertIn("medallion.gd", " ".join(keep["assets/ui/hud-borders/gold.png"]))
        self.assertIn("main.gd", " ".join(keep["assets/ui/cursors/arrow.png"]))  # cursors.configure(...)
        self.assertIn("eloria-assets/maps/meadow/world.json", " ".join(keep["assets/world/tex/grass.png"]))
        self.assertIn("crate.glb -> crate_albedo.png", " ".join(keep["assets/world/props/crate_albedo.png"]))
        self.assertIn("data/ui/panels.json", " ".join(keep["assets/ui/panel_bg.png"]))
        self.assertIn("export_installer_helper", " ".join(keep["assets/branding/rabbitlands-mark-64.png"]))
        self.assertIn("project.godot", " ".join(keep["assets/branding/rabbitlands-icon.png"]))
        # Its product is not in the PCK: no candidate, it stays loose as before.
        self.assertNotIn("assets/ui/unpacked.png", set(plan["drop"]) | set(keep))

    def test_an_actor_uri_is_a_raw_read_without_the_aw03_path(self):
        (self.root / "godot-client/src/actors/actor_images.gd").unlink()
        plan = packager.loose_duplicate_plan(self.root, self.packed())
        self.assertIn("sword.glb -> ../../../ui/emblem.png", " ".join(plan["keep"]["assets/ui/emblem.png"]))
        packager._LOOSE_READ_CACHE.clear()
        write(self.root, "godot-client/src/actors/actor_images.gd", AW03_IMAGES)
        imported = {"godot-client/assets/ui/emblem.png"}
        self.assertEqual(packager.gltf_uri_raw_reads(self.root, imported).get("godot-client/assets/ui/emblem.png"),
                         None)
        self.assertIn("godot-client/assets/ui/emblem.png", packager.gltf_uri_raw_reads(self.root, set()))
        # A spec-gloss material makes actor_images.gd leave the URIs to GLTFDocument's raw read.
        write(self.root, "godot-client/assets/actors/native/equipment/sword.glb",
              glb(["../../../ui/emblem.png"], ("KHR_materials_pbrSpecularGlossiness",)))
        self.assertIn("sword.glb -> ../../../ui/emblem.png",
                      " ".join(packager.gltf_uri_raw_reads(self.root, imported)["godot-client/assets/ui/emblem.png"]))

    def test_relative_data_names_count_unless_their_folder_only_loads(self):
        # The cursor manifest's names keep its images; the audio catalog's do not, because every
        # literal naming assets/audio/ ends in load().
        candidates = {"godot-client/assets/ui/cursors/arrow.png", "godot-client/assets/audio/music_a.ogg"}
        named = packager.loose_data_names(self.root, candidates, {"godot-client/assets/audio/"})
        self.assertEqual(set(named), {"godot-client/assets/ui/cursors/arrow.png"})
        named = packager.loose_data_names(self.root, candidates)
        self.assertEqual(set(named), candidates)

    def test_staging_leaves_the_duplicates_out_and_the_check_holds_it(self):
        write_pck(self.app / "RabbitLands.pck", sorted(self.packed()))
        (self.root / "godot-client/assets/actors/native/equipment/sword.glb").unlink()  # actor shipping is not under test
        actor = {"pck": set(), "loose": set(), "dropped": set()}
        world = {"dropped_images": set()}
        actor_shipping, world_import_shipping = packager.actor_shipping, packager.world_import_shipping
        packager.actor_shipping = lambda build_dir: actor
        packager.world_import_shipping = lambda build_dir: world
        try:
            plan = packager.stage_loose_client_files(self.root, self.app)
            staged = {p.relative_to(self.app).as_posix() for p in self.app.rglob("*") if p.is_file()}
            for local in plan["drop"]:
                self.assertNotIn(local, staged)
            for local in ("assets/ui/hud-borders/gold.png", "assets/ui/cursors/arrow.png",
                          "assets/ui/cursors/cursors.json", "assets/audio/catalog.json", "assets/audio/CREDITS.txt",
                          "assets/branding/rabbitlands-icon.ico", "assets/branding/rabbitlands-mark-64.png",
                          "assets/ui/unpacked.png", "data/ui/panels.json"):
                self.assertIn(local, staged)
            packager.check_loose_duplicates(self.root, self.app)
            (self.app / "assets/ui/hud-borders/gold.png").unlink()
            with self.assertRaisesRegex(packager.PackageError, "gold.png: read raw .*medallion.gd"):
                packager.check_loose_duplicates(self.root, self.app)
            write(self.app, "assets/ui/hud-borders/gold.png", b"x")
            (self.app / "assets/branding/rabbitlands-mark-64.png").unlink()
            with self.assertRaisesRegex(packager.PackageError, "rabbitlands-mark-64.png: .*export_installer_helper"):
                packager.check_loose_duplicates(self.root, self.app)
            write(self.app, "assets/branding/rabbitlands-mark-64.png", b"x")
            # A re-export whose PCK lost a dropped file's product: the file is now nowhere.
            write_pck(self.app / "RabbitLands.pck",
                      sorted(self.packed(missing_products=("assets/ui/unpacked.png", "assets/audio/hit.wav"))))
            packager._LOOSE_READ_CACHE.clear()
            with self.assertRaisesRegex(packager.PackageError, "hit.wav: neither loose nor in the PCK"):
                packager.check_loose_duplicates(self.root, self.app)
        finally:
            packager.actor_shipping, packager.world_import_shipping = actor_shipping, world_import_shipping


class StageReaders(unittest.TestCase):
    def test_every_branding_file_the_installer_takes_from_the_stage_stays_loose(self):
        release = (REPO / "godot-client/tools/client_release.py").read_text(encoding="utf-8")
        names = set()
        for match in re.finditer(r"for name in \(([^)]*)\):\s*\n\s*shutil\.copyfile\(stage / \"app/assets/branding\"",
                                 release):
            names |= set(re.findall(r'"([^"]+)"', match.group(1)))
        self.assertTrue(names)
        for name in names:
            self.assertIn("assets/branding/" + name, packager.LOOSE_STAGE_READERS)
        source = (REPO / "godot-client/tools/package_client.py").read_text(encoding="utf-8")
        for icon in set(re.findall(r"SetupIconFile=\{\w+\}\\\\app\\\\(\S+)", source)):
            self.assertIn(icon.replace("\\\\", "/"), packager.LOOSE_STAGE_READERS)


class CommittedClient(unittest.TestCase):
    """The scan over this checkout's runtime code: the readers W2-UD-02 names keep their files."""

    def test_the_pixel_reading_materials_match_the_actor_parse(self):
        source = (REPO / "godot-client/src/actors/actor_images.gd").read_text(encoding="utf-8")
        match = re.search(r"const PIXEL_READING_MATERIALS: Array\[String\] = \[([^\]]*)\]", source)
        self.assertIsNotNone(match)
        self.assertEqual({name.encode() for name in re.findall(r'"([^"]+)"', match.group(1))},
                         set(packager.ACTOR_PIXEL_READING_MATERIALS))
        self.assertTrue(packager._actor_glb_reads_imports(REPO))

    def test_the_named_raw_readers_keep_their_files_and_audio_is_resource_only(self):
        client = REPO / "godot-client"
        wanted = {
            "hud borders": "assets/ui/hud-borders/",
            "leaderboard art": "assets/ui/leaderboards/",
            "login posters": "assets/ui/start_screen/",
            "service menu icons": "assets/ui/menu-icons/exchange.png",
            "cursors": "assets/ui/cursors/",
        }
        candidates = set()
        for prefix in wanted.values():
            found = [p for p in (client / prefix).rglob("*") if p.is_file()
                     and p.suffix.lower() in packager.LOOSE_DUPLICATE_SUFFIXES] \
                if prefix.endswith("/") else [client / prefix]
            candidates |= {"godot-client/" + p.relative_to(client).as_posix() for p in found}
        audio = {"godot-client/" + p.relative_to(client).as_posix()
                 for p in (client / "assets/audio").glob("*") if p.suffix.lower() in (".ogg", ".wav")}
        self.assertTrue(audio)
        allowlist = packager.loose_read_allowlist(REPO, candidates | audio)
        prefixes = tuple(allowlist["prefixes"])

        def kept(path: str) -> bool:
            return path in allowlist["files"] or path.startswith(prefixes)

        for label, prefix in wanted.items():
            named = [c for c in candidates if c.startswith("godot-client/" + prefix)]
            with self.subTest(reader=label):
                self.assertTrue(named, prefix)
                self.assertTrue(all(kept(c) for c in named), [c for c in named if not kept(c)][:5])
        self.assertFalse([path for path in audio if kept(path)][:5])
        self.assertIn("godot-client/assets/audio/", allowlist["resource_prefixes"])
        self.assertFalse(packager.loose_data_names(REPO, audio, allowlist["resource_prefixes"]))


if __name__ == "__main__":
    unittest.main()
