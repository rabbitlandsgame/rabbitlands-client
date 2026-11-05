"""W2-UD-06: the exported PCK splits into a core pack and stable content packs.

tools/pck_split.py (reader/writer, rules, boot closure, split, partition proof),
the package_client glue (when a package splits, the resource comparison, the
smoke check) and, with a native Godot editor binary and an imported checkout,
the split layout end to end: src/boot/content_packs.gd mounts the packs from the
executable's packs/ folder before a later autoload preloads from them, a missing
pack never crashes the game, and check_split_pack_resources.gd finds the
monolith's resources in the split layout.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import os
from pathlib import Path
import random
import re
import shutil
import struct
import subprocess
import sys

import pytest

CLIENT = Path(__file__).resolve().parents[1]
REPO = CLIENT.parent
sys.path.insert(0, str(CLIENT / "tools"))
import pck_split as S  # noqa: E402

GODOT = Path(os.environ.get("ELORIA_GODOT") or CLIENT / "Godot_v4.7.2-stable_win64.exe")
VERSION = (4, 7, 2)


def make_pack(path: Path, files: dict[str, bytes], fmt: int = 4) -> S.Pack:
    S.write_pack(path, {name: S.Source(data=data) for name, data in files.items()}, fmt=fmt, version=VERSION)
    return S.read_pack(path)


def ctex(label: str) -> bytes:
    return b"GST2" + label.encode() * 8


def import_file(source: str, product: str, uid: str = "", key: str = "path") -> bytes:
    lines = ["[remap]", "", 'importer="texture"', 'type="CompressedTexture2D"']
    if uid:
        lines.append(f'uid="{uid}"')
    lines += [f'{key}="res://{product}"', "", "[deps]", "", f'source_file="res://{source}"',
              f'dest_files=["res://{product}"]', ""]
    return "\n".join(lines).encode()


def imported(files: dict, source: str, product: str, data: bytes, uid: str = "") -> None:
    files[source + ".import"] = import_file(source, product, uid)
    files[product] = data


def ecfg(settings: dict[str, bytes]) -> bytes:
    out = b"ECFG" + struct.pack("<I", len(settings))
    for key, value in settings.items():
        out += struct.pack("<I", len(key)) + key.encode() + struct.pack("<I", len(value)) + value
    return out


def variant_string(text: str) -> bytes:
    raw = text.encode()
    return struct.pack("<II", 4, len(raw)) + raw + b"\0" * ((-len(raw)) % 4)


def variant_strings(items: list[str]) -> bytes:
    out = struct.pack("<II", 34, len(items))
    for item in items:
        raw = item.encode() + b"\0"
        out += struct.pack("<I", len(raw)) + raw + b"\0" * ((-len(raw)) % 4)
    return out


def uid_cache(rows: dict[int, str]) -> bytes:
    out = struct.pack("<I", len(rows))
    for uid, path in rows.items():
        raw = path.encode()
        out += struct.pack("<qI", uid, len(raw)) + raw
    return out


def monolith_files() -> dict[str, bytes]:
    """A small export: every rule's kind of entry, a text project and its boot closure."""
    files = {
        "project.godot": ('config_version=5\n[application]\nconfig/name="Fixture"\n'
                          'config/icon="res://assets/icon.png"\nboot_splash/image="res://assets/splash.png"\n'
                          'run/main_scene="res://main.tscn"\n[autoload]\nA="*res://a.gd"\n'
                          '[gui]\ntheme/custom="res://ui/theme.tres"\n'
                          '[rendering]\nenvironment/defaults/default_environment="res://env.res"\n').encode(),
        ".godot/uid_cache.bin": uid_cache({}),
        ".godot/global_script_class_cache.cfg": b"list=[]\n",
        "a.gd.remap": b'[remap]\n\npath="res://a.gdc"\n',
        "a.gdc": b"GDSC" + b'preload("res://assets/hud.png")',
        "main.tscn": b'[gd_scene format=3]\n[ext_resource type="Texture2D" path="res://assets/world.png" id="1"]\n',
        "assets/icon.png": b"\x89PNG icon",
        "ui/theme.tres": b'[gd_resource type="Theme" format=3]\n[ext_resource type="Texture2D" path="res://ui/panel.png" id="1"]\n',
        "env.res": b"RSRC" + struct.pack("<I", len("res://sky.png") + 1) + b"res://sky.png\0" + b"tail",
        "data/table.json": b'{"rows": 1}',
        "prepared-content/half/x.res": b"RSRC prepared",
        "assets/ui/start_screen/01-a.ogv": b"OggS video one",
        "assets/ui/start_screen/02-b.ogv": b"OggS video two",
    }
    imported(files, "assets/icon.png", ".godot/imported/icon.png-1.ctex", ctex("icon"))
    imported(files, "assets/splash.png", ".godot/imported/splash.png-2.ctex", ctex("splash"))
    imported(files, "ui/panel.png", ".godot/imported/panel.png-3.ctex", ctex("panel"))
    imported(files, "sky.png", ".godot/imported/sky.png-4.ctex", ctex("sky"))
    imported(files, "assets/world.png", ".godot/imported/world.png-5.ctex", ctex("world"))
    imported(files, "assets/hud.png", ".godot/imported/hud.png-6.ctex", ctex("hud"))
    for index in range(12):
        imported(files, f"assets/actors/native/equipment/textures/canonical_{index:02d}.jpg",
                 f".godot/imported/canonical_{index:02d}.jpg-{index}.s3tc.ctex", ctex(f"gear{index}"))
    for index in range(6):
        imported(files, f"assets/ui/icon_{index}.png", f".godot/imported/icon_{index}.png-{index}.ctex", ctex(f"ui{index}"))
    files[".godot/imported/music.ogg-7.oggvorbisstr"] = b"OggS music"
    files["assets/audio/music.ogg.import"] = import_file("assets/audio/music.ogg", ".godot/imported/music.ogg-7.oggvorbisstr")
    files[".godot/imported/hit.wav-8.sample"] = b"RIFF hit"
    files["assets/audio/hit.wav.import"] = import_file("assets/audio/hit.wav", ".godot/imported/hit.wav-8.sample")
    files[".godot/imported/step.mp3-9.mp3str"] = b"ID3 step"
    return files


def split_fixture(tmp_path: Path, files: dict[str, bytes] | None = None) -> tuple[Path, Path, Path, dict]:
    monolith = tmp_path / "monolith.pck"
    make_pack(monolith, files or monolith_files())
    app = tmp_path / "app"
    app.mkdir()
    core = app / "RabbitLands.core.pck"
    receipt = S.split(monolith, app, core)
    return monolith, core, app / "packs", receipt


# --- reader and writer --------------------------------------------------------

def test_written_pack_has_godots_layout(tmp_path):
    files = {"abcd": b"four", "a/b/name.txt": b"x" * 37, "empty.bin": b""}
    pack = make_pack(tmp_path / "p.pck", files)
    raw = (tmp_path / "p.pck").read_bytes()
    magic, fmt, major, minor, patch, flags, base, directory = S.HEADER.unpack_from(raw)
    assert (magic, fmt, (major, minor, patch), flags, base) == (b"GDPC", 4, VERSION, S.PACK_REL_FILEBASE, 112)
    assert raw[S.HEADER.size:112] == b"\0" * (112 - S.HEADER.size)
    assert directory % 16 == 0 and directory == pack.directory
    assert all(entry.offset % 16 == 0 for entry in pack.entries.values())
    assert {name: pack.read(name) for name in pack.entries} == files
    assert all(entry.md5 == hashlib.md5(files[name]).digest() for name, entry in pack.entries.items())
    # Names are padded to 4 bytes, with no NUL when already aligned; sorted.
    count, = struct.unpack_from("<I", raw, directory)
    first_length, = struct.unpack_from("<I", raw, directory + 4)
    assert count == 3 and raw[directory + 8:directory + 8 + first_length] == b"a/b/name.txt"
    assert first_length == 12
    assert raw.endswith(S.ENTRY_TAIL.pack(pack.entries["empty.bin"].offset - 112, 0, hashlib.md5(b"").digest(), 0))


def test_written_pack_is_deterministic(tmp_path):
    files = {f"f{index}.bin": bytes([index]) * (index * 7 + 1) for index in range(40)}
    shuffled = dict(random.Random(5).sample(sorted(files.items()), len(files)))
    make_pack(tmp_path / "a.pck", files)
    make_pack(tmp_path / "b.pck", shuffled)
    assert (tmp_path / "a.pck").read_bytes() == (tmp_path / "b.pck").read_bytes()


def test_copy_is_checked_against_the_input_md5(tmp_path):
    source = make_pack(tmp_path / "in.pck", {"x.bin": b"payload"})
    entry = source.entries["x.bin"]
    with pytest.raises(S.SplitError, match="md5"):
        S.write_pack(tmp_path / "out.pck", {"x.bin": S.Source(source.path, entry.offset, entry.size, b"\1" * 16)},
                     fmt=4, version=VERSION)


@pytest.mark.parametrize("damage, message", [
    (lambda raw: b"GDPX" + raw[4:], "not a Godot PCK"),
    (lambda raw: raw[:4] + struct.pack("<I", 2) + raw[8:], "format 2"),
    (lambda raw: raw[:20] + struct.pack("<I", 3) + raw[24:], "pack flags"),
    (lambda raw: raw[:20] + struct.pack("<I", 0) + raw[24:], "pack flags"),
    (lambda raw: raw + b"\0", "data after the directory"),
    (lambda raw: raw[:-3], "truncated"),
    (lambda raw: raw[:-4] + struct.pack("<I", 1), "file flags"),
    (lambda raw: raw[:-4] + struct.pack("<I", 2), "file flags"),
    (lambda raw: raw[:-36] + struct.pack("<Q", 1 << 40) + raw[-28:], "outside the data area"),
])
def test_reader_refuses_what_it_cannot_copy(tmp_path, damage, message):
    make_pack(tmp_path / "p.pck", {"only.bin": b"data"})
    raw = (tmp_path / "p.pck").read_bytes()
    (tmp_path / "bad.pck").write_bytes(damage(raw))
    with pytest.raises(S.SplitError, match=message):
        S.read_pack(tmp_path / "bad.pck")


def test_reader_reads_format_3(tmp_path):
    assert make_pack(tmp_path / "p.pck", {"a": b"1"}, fmt=3).format == 3


# --- rules and the boot closure ---------------------------------------------

@pytest.mark.parametrize("name, pack", [
    (".godot/imported/canonical_015b.jpg-7b43.s3tc.ctex", "equipment-textures"),
    (".godot/imported/human_27_pc2.png-b7a8.s3tc.ctex", "textures"),
    (".godot/imported/canonical_x.jpg-1.import", None),  # only products move
    (".godot/imported/music.ogg-341f.oggvorbisstr", "audio"),
    (".godot/imported/hit.wav-5a82.sample", "audio"),
    (".godot/imported/step.mp3-1.mp3str", "audio"),
    ("assets/ui/start_screen/01-crownwater-first-light.ogv", "video"),
    (".godot/imported/strings.en.translation", None),
    (".godot/exported/133200997/export-1-main.scn", None),
    ("assets/branding/rabbitlands-icon.png.import", None),
    ("src/world/harvest_sparkle_3d.gd.remap", None),
    ("src/world/harvest_sparkle_3d.gdc", None),
    ("project.binary", None), (".godot/uid_cache.bin", None), (".godot/global_script_class_cache.cfg", None),
    ("data/maps/registry.json", None), ("prepared-content/half-retain/x.res", None),
    ("assets/textures/x.ctex", None),  # a .ctex outside .godot/imported is not an import product
    (S.MANIFEST, None),
])
def test_rules_choose_the_pack(name, pack):
    target = S.classify(name)
    if pack is None:
        assert target is None
    else:
        assert re.fullmatch(re.escape(pack) + r"(-\d+)?", target[0]) and target[1] == ""


def test_buckets_follow_the_path_hash():
    name = ".godot/imported/canonical_015b43728c0994c77895dce5750a567f64c9c344ced66bbf96877f50480daa0e.jpg-7b43f9e76f0255682731a9d444a02210.s3tc.ctex"
    assert S.bucket(name, 4) == int(hashlib.sha256(name.encode()).hexdigest()[:8], 16) % 4 == 2
    assert S.classify(name) == ("equipment-textures-2", "")
    other = ".godot/imported/human.png-1.ctex"
    assert S.classify(other) == (f"textures-{S.bucket(other, 2)}", "")
    assert [rule.pack for rule in S.RULES] == ["equipment-textures", "textures", "audio", "video"]
    assert [rule.buckets for rule in S.RULES] == [4, 2, 1, 1]


def test_uid_text_matches_godot():
    # Pairs read from release 4a57cea4's uid_cache.bin and .import files.
    assert S.uid_text(8845989355626036417) == "uid://dybcfga5qhqh2"
    assert S.uid_text(1807236601154987654) == "uid://00o6my70bkyw"
    assert S.uid_text(6159720298092235599) == "uid://ct02xtr7gdq0f"
    assert S.uid_text(0) == "uid://a" and S.uid_text(-1) == "uid://<invalid>"


def test_boot_closure_of_a_text_project(tmp_path):
    pack = make_pack(tmp_path / "m.pck", monolith_files())
    closure = S.boot_closure(pack)
    for name in ("assets/icon.png", "assets/icon.png.import", ".godot/imported/icon.png-1.ctex",
                 "assets/splash.png.import", ".godot/imported/splash.png-2.ctex",
                 "ui/theme.tres", "ui/panel.png.import", ".godot/imported/panel.png-3.ctex",
                 "env.res", "sky.png.import", ".godot/imported/sky.png-4.ctex"):
        assert name in closure, name
    assert closure[".godot/imported/panel.png-3.ctex"] == ["gui/theme/custom"]
    # Loaded after the first autoload's _init: not kept in the core.
    for name in (".godot/imported/world.png-5.ctex", ".godot/imported/hud.png-6.ctex", "main.tscn", "a.gdc"):
        assert name not in closure, name
    layout = S.plan(pack)
    assert ".godot/imported/icon.png-1.ctex" in layout["core"]
    assert any(".godot/imported/world.png-5.ctex" in group["entries"] for group in layout["packs"].values())


def test_boot_closure_of_a_binary_project_follows_uids(tmp_path):
    theme_uid, main_uid = 6159720298092235599, 1807236601154987654
    files = {
        "project.binary": ecfg({
            "application/config/icon": variant_string("res://icon.png"),
            "internationalization/locale/translations": variant_strings(["res://i18n/en.translation"]),
            "gui/theme/custom": variant_string(S.uid_text(theme_uid)),
            "application/run/main_scene": variant_string(S.uid_text(main_uid)),
            "autoload/Hud": variant_string("*res://hud.gd"),
            "display/window/size/viewport_width": struct.pack("<Ii", 2, 1280),
        }),
        ".godot/uid_cache.bin": uid_cache({theme_uid: "res://ui/theme.tres", main_uid: "res://main.tscn"}),
        "i18n/en.translation": b"RSRC translation",
        "ui/theme.tres": b'[gd_resource format=3]\n[ext_resource path="uid://dybcfga5qhqh2" id="1"]\n',
        "main.tscn": b'[gd_scene format=3]\n[ext_resource path="res://world.png" id="1"]\n',
        "hud.gd": b'preload("res://hudart.png")',
    }
    imported(files, "icon.png", ".godot/imported/icon.png-1.ctex", ctex("icon"))
    imported(files, "panel.png", ".godot/imported/panel.png-2.ctex", ctex("panel"), uid="uid://dybcfga5qhqh2")
    imported(files, "world.png", ".godot/imported/world.png-3.ctex", ctex("world"))
    imported(files, "hudart.png", ".godot/imported/hudart.png-4.ctex", ctex("hud"))
    pack = make_pack(tmp_path / "m.pck", files)
    closure = S.boot_closure(pack)
    assert {".godot/imported/icon.png-1.ctex", "i18n/en.translation", "ui/theme.tres", "panel.png.import",
            ".godot/imported/panel.png-2.ctex"} <= set(closure)
    assert not {"main.tscn", ".godot/imported/world.png-3.ctex", "hud.gd", ".godot/imported/hudart.png-4.ctex"} & set(closure)


def test_length_prefixed_strings_stop_at_their_length():
    # The release's project.binary: an autoload path followed by the next
    # setting's length byte '&' - a plain regex read "network_client.gd&".
    data = (struct.pack("<II", 4, len("*res://src/network/network_client.gd"))
            + b"*res://src/network/network_client.gd" + struct.pack("<I", 38) + b"\0" * 8)
    assert S._length_prefixed(data, b"res://") == []  # the length counts the '*'
    data = struct.pack("<I", 14) + b"res://a/b.png\0" + struct.pack("<I", 38)
    assert S._length_prefixed(data, b"res://") == ["res://a/b.png"]


# --- split and partition proof ------------------------------------------------

def test_split_partitions_the_monolith(tmp_path):
    monolith, core, packs, receipt = split_fixture(tmp_path)
    source = S.read_pack(monolith)
    proof = S.prove(monolith, core, packs)
    assert proof["entries"] == len(source.entries)
    written = sorted(path.name for path in packs.iterdir())
    assert {"audio.pck", "video.pck"} <= set(written) <= {
        "audio.pck", "video.pck", *(f"equipment-textures-{i}.pck" for i in range(4)),
        *(f"textures-{i}.pck" for i in range(2))}
    assert any(name.startswith("equipment-textures-") for name in written)
    assert any(name.startswith("textures-") for name in written)
    manifest = json.loads(S.read_pack(core).read(S.MANIFEST))
    assert manifest["schema"] == 1
    assert [row["file"] for row in manifest["packs"]] == sorted(f"packs/{name}" for name in written)
    for row in manifest["packs"]:
        path = packs / row["file"].removeprefix("packs/")
        assert row == {"file": row["file"], "bytes": path.stat().st_size, "entries": len(S.read_pack(path).entries),
                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "feature": ""}
    core_pack = S.read_pack(core)
    assert set(core_pack.entries) == set(S.plan(source)["core"]) | {S.MANIFEST}
    assert {"project.godot", "a.gdc", "data/table.json", "prepared-content/half/x.res",
            ".godot/imported/icon.png-1.ctex", "assets/audio/music.ogg.import"} <= set(core_pack.entries)
    moved = {name for row in manifest["packs"]
             for name in S.read_pack(packs / row["file"].removeprefix("packs/")).entries}
    assert ".godot/imported/world.png-5.ctex" in moved and "assets/ui/start_screen/01-a.ogv" in moved
    assert not any(name.endswith((".import", ".remap", ".gdc")) for name in moved)
    assert receipt["core"]["entries"] == len(core_pack.entries) and receipt["monolith"]["version"] == "4.7.2"
    assert S.read_pack(monolith).entries == source.entries  # untouched


def test_split_is_deterministic_and_skips_empty_packs(tmp_path):
    files = monolith_files()
    for name in [n for n in files if n.endswith(".ogv")]:
        del files[name]
    hashes = []
    for run in ("one", "two"):
        (tmp_path / run).mkdir()
        _, core, packs, receipt = split_fixture(tmp_path / run, files)
        hashes.append({path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                       for path in [core, *sorted(packs.iterdir())]})
        assert "packs/video.pck" not in {row["file"] for row in receipt["packs"]}
    assert hashes[0] == hashes[1]


def test_split_refuses_a_core_or_a_used_stage(tmp_path):
    monolith, core, packs, _ = split_fixture(tmp_path)
    again = tmp_path / "again"
    again.mkdir()
    with pytest.raises(S.SplitError, match="core pack, not a monolith"):
        S.split(core, again, again / "core.pck")
    with pytest.raises(S.SplitError, match="not empty"):
        S.split(monolith, tmp_path / "app", tmp_path / "other-core.pck")
    with pytest.raises(S.SplitError, match="already exists"):
        S.split(monolith, again, monolith)
    files = monolith_files()
    files["packs/stray.pck"] = b"x"
    make_pack(tmp_path / "stray.pck", files)
    with pytest.raises(S.SplitError, match="entries under packs/"):
        S.split(tmp_path / "stray.pck", again, again / "c.pck")


def _flip_data_byte(path: Path) -> None:
    pack = S.read_pack(path)
    entry = max(pack.entries.values(), key=lambda e: e.size)
    raw = bytearray(path.read_bytes())
    raw[entry.offset] ^= 0x55
    path.write_bytes(bytes(raw))


def _rewrite_core(core: Path, change) -> None:
    pack = S.read_pack(core)
    files = {name: pack.read(name) for name in pack.entries}
    change(files)
    core.unlink()
    make_pack(core, files)


@pytest.mark.parametrize("mutation, message", [
    ("flip a content byte", "do not hash"),
    ("drop a pack", "listed but not written"),
    ("stray pack", "written but not listed"),
    ("manifest size", "the manifest says"),
    ("drop a core entry", "in no output"),
    ("duplicate an entry", "in core and in packs/|in packs/.* and in core"),
    ("add an entry", "not in the monolith"),
    ("change a core entry", "differ from the monolith"),
    ("bad manifest file", "bad or repeated pack file"),
])
def test_prove_catches(tmp_path, mutation, message):
    monolith, core, packs, receipt = split_fixture(tmp_path)
    first = packs / receipt["packs"][0]["file"].removeprefix("packs/")
    if mutation == "flip a content byte":
        _flip_data_byte(first)
    elif mutation == "drop a pack":
        first.unlink()
    elif mutation == "stray pack":
        (packs / "extra.pck").write_bytes(first.read_bytes())
    elif mutation == "manifest size":
        def bigger(files):
            manifest = json.loads(files[S.MANIFEST])
            manifest["packs"][0]["bytes"] += 1
            files[S.MANIFEST] = json.dumps(manifest).encode()
        _rewrite_core(core, bigger)
    elif mutation == "drop a core entry":
        _rewrite_core(core, lambda files: files.pop("data/table.json"))
    elif mutation == "duplicate an entry":
        moved = next(iter(S.read_pack(first).entries))
        _rewrite_core(core, lambda files: files.__setitem__(moved, S.read_pack(first).read(moved)))
    elif mutation == "add an entry":
        _rewrite_core(core, lambda files: files.__setitem__("data/new.json", b"{}"))
    elif mutation == "change a core entry":
        _rewrite_core(core, lambda files: files.__setitem__("data/table.json", b'{"rows": 2}'))
    elif mutation == "bad manifest file":
        def traversal(files):
            manifest = json.loads(files[S.MANIFEST])
            manifest["packs"][0]["file"] = "packs/../escape.pck"
            files[S.MANIFEST] = json.dumps(manifest).encode()
        _rewrite_core(core, traversal)
    with pytest.raises(S.SplitError, match=message):
        S.prove(monolith, core, packs)


def test_prove_catches_a_version_mismatch(tmp_path):
    monolith, core, packs, receipt = split_fixture(tmp_path)
    first = packs / receipt["packs"][0]["file"].removeprefix("packs/")
    raw = bytearray(first.read_bytes())
    struct.pack_into("<I", raw, 16, 3)  # engine patch 2 -> 3
    first.write_bytes(bytes(raw))
    with pytest.raises(S.SplitError):
        S.prove(monolith, core, packs)


def test_cli(tmp_path, capsys):
    make_pack(tmp_path / "m.pck", monolith_files())
    assert S.main(["plan", str(tmp_path / "m.pck")]) == 0
    out = capsys.readouterr().out
    assert "core:" in out and "packs/audio.pck: 3 entries" in out and "boot closure:" in out
    (tmp_path / "app").mkdir()
    assert S.main(["split", str(tmp_path / "m.pck"), str(tmp_path / "app"), "--core-out",
                   str(tmp_path / "app/core.pck"), "--receipt", str(tmp_path / "r.json")]) == 0
    receipt = json.loads((tmp_path / "r.json").read_text())
    assert receipt["proof"]["entries"] == len(monolith_files()) and receipt["packs"]
    assert S.main(["prove", str(tmp_path / "m.pck"), str(tmp_path / "app/core.pck"), str(tmp_path / "app/packs")]) == 0
    assert S.main(["prove", str(tmp_path / "app/core.pck"), str(tmp_path / "app/core.pck"),
                   str(tmp_path / "app/packs")]) == 1


# --- package_client glue -------------------------------------------------------

def _packager():
    import package_client
    return package_client


def _build_tree(tmp_path: Path, autoloads: str, script: str = "const MANIFEST_SCHEMA := 1\n", tool=True) -> Path:
    build = tmp_path / "build"
    client = build / "godot-client"
    (client / "src/boot").mkdir(parents=True)
    (client / "tools").mkdir()
    (client / "project.godot").write_text(f'config_version=5\n\n[autoload]\n\n{autoloads}\n[debug]\n\nx=1\n')
    if script is not None:
        (client / "src/boot/content_packs.gd").write_text(script)
    if tool:
        (client / "tools/check_split_pack_resources.gd").write_text("extends SceneTree\n")
    return build


FIRST = 'ContentPacks="*res://src/boot/content_packs.gd"\n'
OTHERS = 'ClientDiagnostics="*res://src/diagnostics/client_diagnostics.gd"\nAppState="*res://src/state/app_state.gd"\n'


def test_split_decision(tmp_path):
    P = _packager()
    ready = _build_tree(tmp_path / "ready", FIRST + OTHERS)
    assert P.split_pack_support(ready) == ""
    assert P.split_pack_reason(ready, "windows", disabled=False, benchmark=False) == ""
    assert P.split_pack_reason(ready, "linux", disabled=False, benchmark=False) == ""
    assert "no-split-pck" in P.split_pack_reason(ready, "windows", disabled=True, benchmark=False)
    assert "macos" in P.split_pack_reason(ready, "macos", disabled=False, benchmark=False)
    assert "benchmark" in P.split_pack_reason(ready, "windows", disabled=False, benchmark=True)
    assert "predates" in P.split_pack_support(_build_tree(tmp_path / "old", OTHERS, script=None))
    assert "predates" in P.split_pack_support(_build_tree(tmp_path / "notool", FIRST + OTHERS, tool=False))
    assert "schema" in P.split_pack_support(_build_tree(tmp_path / "schema", FIRST + OTHERS, script="const MANIFEST_SCHEMA := 2\n"))
    assert "first autoload" in P.split_pack_support(_build_tree(tmp_path / "second", OTHERS + FIRST))
    assert P.split_pack_support(_build_tree(tmp_path / "comment", "; note\n" + FIRST + OTHERS)) == ""


def test_this_checkout_splits():
    """The commit this test runs in loads ContentPacks first: its packages split."""
    assert _packager().split_pack_support(REPO) == ""


def test_the_repair_message_covers_every_distribution():
    """Every --distribution splits its PCK, and only GitHub builds ship an updater:
    ContentPacks has a repair message of its own for each one the packager builds."""
    source = (CLIENT / "tools/package_client.py").read_text(encoding="utf-8")
    choices = re.search(r'"--distribution", choices=\(([^)]*)\)', source)
    distributions = re.findall(r'"([a-z]+)"', choices.group(1))
    assert distributions and "steam" in distributions
    script = (CLIENT / "src/boot/content_packs.gd").read_text(encoding="utf-8")
    table = re.search(r"(?s)const REPAIR_MESSAGES := \{(.*?)\n\}", script).group(1)
    assert sorted(re.findall(r'(?m)^\t"([a-z]+)":', table)) == sorted(distributions)


def test_package_steps_run_in_the_wave_2_order():
    source = inspect.getsource(_packager()._main)
    order = ["check_shared_meshes(build_dir, stage)\n        if not split_reason",
             "split_client_pack(godot, project, app_dir, logs, storage)",
             "client_release.export_launcher(", "smoke_launch(app_dir", "optimization.check_final_package()",
             "client_release.publish_artifacts("]
    positions = [source.index(step) for step in order]
    assert positions == sorted(positions)
    assert source.count("content_packs=content_packs") == 2


def _report(classes: dict[str, tuple[str, str, int, str]], files=None, mount=None) -> dict:
    return {"resources": {path: {"class": c, "detail": d, "products": {f".godot/imported/{path}.ctex": {"bytes": b, "md5": m}}}
                          for path, (c, d, b, m) in classes.items()},
            "files": files or {}, "mount": mount if mount is not None else {"state": "mounted"}, "usec": 1}


def test_compare_split_reports(tmp_path):
    P = _packager()
    pack = make_pack(tmp_path / "m.pck", {".godot/imported/a.png.ctex": b"alpha", "v.ogv": b"video"})
    md5 = lambda data: hashlib.md5(data).hexdigest()
    record = _report({"a.png": ("CompressedTexture2D", "64x64", 5, "")},
                     files={"v.ogv": {"class": "VideoStreamTheora", "bytes": 5}}, mount={})
    verify = _report({"a.png": ("CompressedTexture2D", "64x64", 5, md5(b"alpha"))},
                     files={"v.ogv": {"class": "VideoStreamTheora", "bytes": 5, "md5": md5(b"video")}})
    assert P.compare_split_reports(pack, record, verify)["resources"] == 1
    cases = [
        (_report({"a.png": ("Texture2D", "64x64", 5, md5(b"alpha"))}, files=verify["files"]), "class"),
        (_report({"a.png": ("CompressedTexture2D", "32x32", 5, md5(b"alpha"))}, files=verify["files"]), "detail"),
        (_report({"a.png": ("CompressedTexture2D", "64x64", 6, md5(b"alpha"))}, files=verify["files"]), "import products"),
        (_report({"a.png": ("CompressedTexture2D", "64x64", 5, md5(b"other"))}, files=verify["files"]), "not the monolith's"),
        (_report({"a.png": ("CompressedTexture2D", "64x64", 5, md5(b"alpha"))}, files=verify["files"],
                 mount={"state": "failed"}), "not mounted"),
        (_report({}, files=verify["files"]), "different paths"),
        (_report({"a.png": ("CompressedTexture2D", "64x64", 5, md5(b"alpha"))},
                 files={"v.ogv": {"class": "", "bytes": 5, "md5": md5(b"video")}}), "class"),
    ]
    for bad, message in cases:
        with pytest.raises(P.PackageError, match=message):
            P.compare_split_reports(pack, record, bad)
    with pytest.raises(P.PackageError, match="logged only on the split layout"):
        P.compare_split_reports(pack, record, verify, "fine\n", "ERROR: Failed loading resource: res://x\n")
    both = "ERROR: Failed loading resource: res://old\n"
    assert P.compare_split_reports(pack, record, verify, both, both)
    broken = json.loads(json.dumps(record))
    broken["resources"]["a.png"]["error"] = "did not load"
    still = json.loads(json.dumps(verify))
    still["resources"]["a.png"]["error"] = "did not load"
    assert P.compare_split_reports(pack, broken, still)["broken_in_both"] == ["a.png"]


def test_smoke_requires_the_mount():
    P = _packager()
    manifest = {"schema": 1, "packs": [{"file": "packs/audio.pck", "feature": ""},
                                      {"file": "packs/pilot.pck", "feature": "prepared-content"}]}
    line = lambda state, packs: "client_diagnostic " + json.dumps(
        {"directory": "C:/x/app/packs", "event": "content_packs", "packs": packs, "state": state}, separators=(",", ":"))
    ok = line("mounted", [{"file": "packs/audio.pck", "state": "mounted", "usec": 3}])
    assert P.check_content_packs_mounted("Godot Engine\n" + ok + "\n", manifest, "smoke.log")["state"] == "mounted"
    for text in ("no diagnostic here\n",
                 line("failed", [{"file": "packs/audio.pck", "state": "missing", "usec": 0}]),
                 line("mounted", [])):
        with pytest.raises(P.PackageError):
            P.check_content_packs_mounted(text, manifest, "smoke.log")


def test_smoke_launch_checks_the_mount(tmp_path, monkeypatch):
    P = _packager()
    app = tmp_path / "stage/app"
    app.mkdir(parents=True)
    manifest = {"schema": 1, "packs": [{"file": "packs/audio.pck", "feature": ""}]}
    monkeypatch.setattr(P, "_launch", lambda *args, **kwargs: "Godot Engine\n")
    with pytest.raises(P.PackageError, match="no content_packs diagnostic"):
        P.smoke_launch(app, tmp_path, P.PLATFORMS["windows"], content_packs=manifest)
    P.smoke_launch(app, tmp_path, P.PLATFORMS["windows"])  # a single PCK: nothing to mount
    mounted = ('client_diagnostic {"event":"content_packs","packs":[{"file":"packs/audio.pck","state":"mounted"}],'
               '"state":"mounted"}\n')
    monkeypatch.setattr(P, "_launch", lambda *args, **kwargs: mounted)
    P.smoke_launch(app, tmp_path, P.PLATFORMS["windows"], content_packs=manifest)
    monkeypatch.setattr(P, "_launch", lambda *args, **kwargs: None)  # WSL absent: no log to read
    P.smoke_launch(app, tmp_path, P.PLATFORMS["linux"], content_packs=manifest)


# --- with Godot: the split layout end to end ----------------------------------

FIXTURE_RESOURCES = (
    "assets/branding/rabbitlands-mark-64.png",
    "assets/actors/native/equipment/textures/canonical_015b43728c0994c77895dce5750a567f64c9c344ced66bbf96877f50480daa0e.jpg",
    "assets/audio/civic_crowd.wav",
    "assets/audio/music_enemy_ship_approaching.ogg",
)
FIXTURE_VIDEO = "assets/ui/start_screen/03-whitehorn-silent-ascent.ogv"
PROBE = '''extends Node
const MARK := preload("res://assets/branding/rabbitlands-mark-64.png")
func _ready() -> void:
	var gear: Texture2D = load("%s")
	var crowd: AudioStream = load("res://assets/audio/civic_crowd.wav")
	var music: AudioStream = load("res://assets/audio/music_enemy_ship_approaching.ogg")
	var video: Resource = load("res://%s") if ResourceLoader.exists("res://%s") else null
	print("PROBE " + JSON.stringify({"mark": str(MARK.get_size()), "gear": str(gear.get_size()) if gear else "",
		"crowd": crowd.get_length() if crowd else -1.0, "music": music.get_length() if music else -1.0,
		"video": video.get_class() if video else "", "video_bytes": FileAccess.open("res://%s", FileAccess.READ).get_length()
			if FileAccess.file_exists("res://%s") else -1}))
	get_tree().quit()
''' % ("res://" + FIXTURE_RESOURCES[1], FIXTURE_VIDEO, FIXTURE_VIDEO, FIXTURE_VIDEO, FIXTURE_VIDEO)


def _godot_fixture() -> dict[str, bytes]:
    if not GODOT.is_file():
        pytest.skip("a native Godot 4.7.2 editor binary is required (set ELORIA_GODOT)")
    files = {
        "project.godot": ('config_version=5\n\n[application]\n\nconfig/name="Content packs probe"\n'
                          'run/main_scene="res://main.tscn"\nconfig/use_custom_user_dir=true\n'
                          'config/custom_user_dir_name="RLContentPacksProbe"\n\n[autoload]\n\n'
                          'ContentPacks="*res://src/boot/content_packs.gd"\nProbe="*res://probe.gd"\n').encode(),
        "src/boot/content_packs.gd": (CLIENT / "src/boot/content_packs.gd").read_bytes(),
        "probe.gd": PROBE.encode(),
        "main.tscn": b'[gd_scene format=3]\n\n[node name="Main" type="Node"]\n',
        ".godot/global_script_class_cache.cfg": b"list=[]\n",  # every mount reloads it
        FIXTURE_VIDEO: (CLIENT / FIXTURE_VIDEO).read_bytes(),
    }
    for source in FIXTURE_RESOURCES:
        sidecar = CLIENT / (source + ".import")
        text = sidecar.read_text(encoding="utf-8")
        files[source + ".import"] = text.encode()
        for product in set(re.findall(r'(?m)^path(?:\.\w+)?="res://([^"]+)"', text)):
            if not (CLIENT / product).is_file():
                pytest.skip(f"the checkout is not imported ({product})")
            files[product] = (CLIENT / product).read_bytes()
    return files


def _run_game(app: Path, user: Path, *args) -> tuple[int, str]:
    env = dict(os.environ, APPDATA=str(user), LOCALAPPDATA=str(user))
    env.pop("RABBITLANDS_CONTENT_PACKS", None)
    result = subprocess.run([str(app / "RabbitLands.exe"), "--headless", "--quit-after", "600", *args],
                            capture_output=True, text=True, timeout=300, env=env, cwd=user)
    return result.returncode, result.stdout + result.stderr


def _probe(text: str) -> dict | None:
    lines = [line for line in text.splitlines() if line.startswith("PROBE ")]
    return json.loads(lines[-1][6:]) if lines else None


def _mount(text: str) -> dict | None:
    lines = [line for line in text.splitlines() if '"event":"content_packs"' in line]
    return json.loads(lines[-1].split(" ", 1)[1]) if lines else None


@pytest.mark.skipif(os.name != "nt", reason="the fixture links the Windows editor binary as RabbitLands.exe")
def test_split_layout_runs(tmp_path):
    files = _godot_fixture()
    layouts = {}
    for label in ("monolith", "split"):
        app = tmp_path / label / "app"
        app.mkdir(parents=True)
        (tmp_path / label / "user").mkdir()
        try:
            os.link(GODOT, app / "RabbitLands.exe")
        except OSError:
            shutil.copy2(GODOT, app / "RabbitLands.exe")
        layouts[label] = app
    make_pack(layouts["monolith"] / "RabbitLands.pck", files)
    receipt = S.split(layouts["monolith"] / "RabbitLands.pck", layouts["split"], layouts["split"] / "RabbitLands.pck")
    S.prove(layouts["monolith"] / "RabbitLands.pck", layouts["split"] / "RabbitLands.pck", layouts["split"] / "packs")
    assert {row["file"] for row in receipt["packs"]} >= {"packs/audio.pck", "packs/video.pck"}

    code, text = _run_game(layouts["monolith"], tmp_path / "monolith/user")
    expected = _probe(text)
    assert code == 0 and expected and expected["video"] == "VideoStreamTheora", text[-3000:]
    assert "ERROR" not in text, text[-3000:]
    assert expected["gear"] not in ("", "(0, 0)") and expected["crowd"] > 0 and expected["music"] > 0
    assert _mount(text) is None, "a monolith has no manifest: ContentPacks stays silent"

    code, text = _run_game(layouts["split"], tmp_path / "split/user")
    assert code == 0 and _probe(text) == expected, text[-3000:]
    mount = _mount(text)
    assert mount["state"] == "mounted" and mount["directory"].replace("\\", "/").endswith("/split/app/packs")
    assert {row["file"] for row in mount["packs"] if row["state"] == "mounted"} == {row["file"] for row in receipt["packs"]}
    assert "ERROR" not in text and "Failed loading resource" not in text, text[-3000:]

    # A missing pack: the report fails, the game carries on without its files.
    (layouts["split"] / "packs/video.pck").unlink()
    code, text = _run_game(layouts["split"], tmp_path / "split/user")
    probe = _probe(text)
    assert code == 0 and probe and probe["video"] == "" and probe["video_bytes"] == -1 and probe["mark"] == expected["mark"]
    mount = _mount(text)
    assert mount["state"] == "failed"
    assert [row["state"] for row in mount["packs"] if row["file"] == "packs/video.pck"] == ["missing"]

    # A pack a preload needs: the probe autoload cannot compile, nothing crashes.
    mark_pack = next(row["file"] for row in receipt["packs"] if row["file"].startswith("packs/textures-"))
    (layouts["split"] / mark_pack).unlink()
    code, text = _run_game(layouts["split"], tmp_path / "split/user")
    assert code == 0 and _probe(text) is None and _mount(text)["state"] == "failed"


def test_check_split_pack_resources_on_a_fixture(tmp_path):
    P = _packager()
    files = _godot_fixture()
    monolith = tmp_path / "RabbitLands.pck"
    make_pack(monolith, files)
    app = tmp_path / "app"
    app.mkdir()
    S.split(monolith, app, app / "RabbitLands.core.pck")
    logs = tmp_path / "logs"
    logs.mkdir()
    result = P.check_split_pack_resources(GODOT, CLIENT, monolith, app / "RabbitLands.core.pck", app / "packs", logs)
    assert result["resources"] == len(FIXTURE_RESOURCES) and result["files"] == 1
    assert result["mount"]["state"] == "mounted" and not result["broken_in_both"]
    # A changed byte in a content pack: the split layout reads other bytes.
    _flip_data_byte(next((app / "packs").glob("audio.pck")))
    with pytest.raises(P.PackageError, match="not the monolith's|differ"):
        P.check_split_pack_resources(GODOT, CLIENT, monolith, app / "RabbitLands.core.pck", app / "packs", logs)


def test_split_client_pack_replaces_the_monolith_only_after_every_check(tmp_path, monkeypatch):
    P = _packager()
    files = _godot_fixture()
    app = tmp_path / "stage/app"
    app.mkdir(parents=True)
    make_pack(app / "RabbitLands.pck", files)
    size = (app / "RabbitLands.pck").stat().st_size
    logs = tmp_path / "logs"
    logs.mkdir()
    checks = []

    class Storage:
        def check(self, phase, additional=0):
            checks.append((phase, additional))

    receipt = P.split_client_pack(GODOT, CLIENT, app, logs, Storage())
    assert checks == [("before PCK split", size)]
    assert not (app / P.SPLIT_CORE_TEMPORARY).exists()
    core = S.read_pack(app / "RabbitLands.pck")
    assert json.loads(core.read(S.MANIFEST)) == receipt["manifest"]
    assert sorted(path.name for path in (app / "packs").iterdir()) == sorted(
        row["file"].removeprefix("packs/") for row in receipt["packs"])
    written = json.loads((logs / "pck-split.json").read_text())
    assert written["core"]["file"] == "RabbitLands.pck" and written["proof"]["entries"] == len(files)
    assert written["resources"]["resources"] == len(FIXTURE_RESOURCES) and written["resources"]["files"] == 1

    # A failed resource check keeps the exported monolith where it was.
    other = tmp_path / "other/app"
    other.mkdir(parents=True)
    make_pack(other / "RabbitLands.pck", files)
    before = (other / "RabbitLands.pck").read_bytes()

    def fail(*_args, **_kwargs):
        raise P.PackageError("resources differ")

    monkeypatch.setattr(P, "check_split_pack_resources", fail)
    with pytest.raises(P.PackageError, match="resources differ"):
        P.split_client_pack(GODOT, CLIENT, other, logs)
    assert (other / "RabbitLands.pck").read_bytes() == before
