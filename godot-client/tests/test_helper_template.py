"""The helper's own small export template (tools/helper_template.py, tools/helper_template.json).

No network, compiler or Godot: downloads are fakes and the recipe's pins are
replaced by pins of fake bytes where a test needs a template file.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import urllib.request

import pytest

GODOT = Path(__file__).resolve().parents[1]
TOOLS = GODOT / "tools"
sys.path.insert(0, str(TOOLS))
import helper_template as ht  # noqa: E402

ENGINE_COMMIT = "ed1daf0bf001b61586d9930840f2f1394092c079"
KEPT_MODULES = {"gdscript", "mbedtls", "freetype", "text_server_adv", "svg"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fake_recipe(data: bytes = b"template", official: bytes = b"official", select: str = "custom") -> dict:
    """The committed recipe with both platforms pinned to fake template bytes."""
    recipe = json.loads(ht.RECIPE.read_text(encoding="utf-8"))
    for spec in recipe["platforms"].values():
        spec["select"] = select
        spec["custom"] = {"file": spec["custom"]["file"], "size": len(data), "sha256": sha(data)}
        spec["official"] = {"file": spec["official"]["file"], "size": len(official), "sha256": sha(official)}
    return ht.validate(recipe)


def pin_templates(monkeypatch, tmp_path, data: bytes = b"template", *, official: bytes = b"official",
                  select: str = "custom", place: bool = True) -> dict:
    """Pin fake template bytes for every caller of helper_template (desktop_helpers,
    desktop_release_ci) and, with `place`, put them in the local template folder."""
    recipe = fake_recipe(data, official, select)
    monkeypatch.setattr(ht, "load", lambda path=None: recipe)
    monkeypatch.setattr(ht, "LOCAL_DIR", tmp_path / "local-template")
    if place:
        for spec in recipe["platforms"].values():
            path = tmp_path / "local-template" / spec["custom"]["file"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    return recipe


def arguments(platform: str) -> dict:
    recipe = ht.load()
    return dict(item.split("=", 1) for item in recipe["arguments"] + recipe["platforms"][platform]["arguments"])


# --- The committed recipe --------------------------------------------------------------------

def test_the_committed_recipe_pins_the_official_engine_tag_and_a_reproducible_build():
    recipe = ht.load()
    assert recipe["engine"] == {"repository": "https://github.com/godotengine/godot.git", "tag": "4.7.2-stable",
                                "commit": ENGINE_COMMIT, "commit_time": 1786929518, "version": "4.7.2.stable"}
    assert recipe["build_name"] == "rl_helper"  # an honest name: this is not the official build
    assert re.fullmatch("[0-9a-f]{64}", recipe["scons"]["wheel_sha256"]) and recipe["scons"]["version"] == "4.10.1"
    windows = recipe["platforms"]["windows"]
    assert windows["toolchain"]["packages"]["mingw-w64-x86_64-gcc"] == "16.2.0-3"
    assert {"mingw64/bin/ld.exe", "mingw64/lib/gcc/x86_64-w64-mingw32/16.2.0/cc1plus.exe"} <= set(
        windows["toolchain"]["files"])
    assert "linkflags=-Wl,--no-insert-timestamp" in windows["arguments"]  # PE timestamp 0: reproducible bytes


@pytest.mark.parametrize("platform", ht.PLATFORMS)
def test_the_build_keeps_only_what_the_helper_needs(platform):
    args = arguments(platform)
    enabled = {name[len("module_"):-len("_enabled")] for name, value in args.items()
               if name.startswith("module_") and value == "yes"}
    # ANGLE's static library calls the astcenc module's decoder (the official template links both)
    assert enabled == KEPT_MODULES | ({"astcenc"} if platform == "windows" else set())
    assert args["modules_enabled_by_default"] == "no"
    for name in ("disable_3d", "disable_physics_2d", "disable_navigation_2d"):
        assert args[name] == "yes"
    assert args["vulkan"] == "no" and args["opengl3"] == "yes" and args["sdl"] == "no"
    assert args["target"] == "template_release" and args["production"] == "yes" and args["arch"] == "x86_64"
    # the uninstaller's ConfirmationDialog is advanced GUI; the helper prints only through GDScript
    assert "disable_advanced_gui" not in args and "deprecated" not in args
    if platform == "windows":
        assert args["platform"] == "windows" and args["use_mingw"] == "yes" and args["d3d12"] == "no"
        # as the official template: ANGLE for GL < 3.3, remote displays and ARM; AccessKit for screen readers
        assert args["angle"] == "yes" and args["accesskit"] == "yes" and args["winrt"] == "no"
    else:
        assert args["platform"] == "linuxbsd"
    # their folders come from the pinned archives at build time, never from the recipe
    assert not set(ht.DEPENDENCY_OPTIONS) & set(args)


def test_windows_links_godots_own_angle_and_accesskit_archives_pinned_by_hash():
    recipe = ht.load()
    dependencies = recipe["platforms"]["windows"]["dependencies"]
    assert recipe["platforms"]["linux"]["dependencies"] == {}
    angle, accesskit = dependencies["angle"], dependencies["accesskit"]
    # the URLs misc/scripts/install_angle.py and install_accesskit.py use at 4.7.2-stable (MinGW GCC, x86_64)
    assert angle["url"] == ("https://github.com/godotengine/godot-angle-static/releases/download/chromium/7219/"
                            "godot-angle-static-x86_64-gcc-release.zip") and angle["version"] == "chromium/7219"
    assert accesskit["url"] == ("https://github.com/godotengine/godot-accesskit-c-static/releases/download/0.22.3/"
                                "accesskit-c-0.22.3.zip") and accesskit["version"] == "0.22.3"
    assert (angle["size"], angle["sha256"]) == (
        4739323, "ebf94e32334b04fa76b3907727c7a69c35adb713cf0a5d194c83c7ad955217bd")
    assert (accesskit["size"], accesskit["sha256"]) == (
        101767087, "41b30b1382d03b225b6f7e8721269a32557a68065804f3797bdffc34a3273498")
    assert (angle["option"], angle["root"]) == ("angle_libs", "")
    assert (accesskit["option"], accesskit["root"]) == ("accesskit_sdk_path", "accesskit-c-0.22.3")
    assert angle["imports"] == ["dxgi.dll"] and accesskit["imports"] == ["uiautomationcore.dll"]
    assert angle["modules"] == ["astcenc"] and "modules" not in accesskit
    assert "mingw64/bin/dlltool.exe" in recipe["platforms"]["windows"]["toolchain"]["files"]  # AccessKit's import lib


def test_windows_uses_the_custom_template_and_linux_keeps_the_official_until_its_glibc_floor_is_met():
    windows, linux = ht.selection("windows"), ht.selection("linux")
    # less than half the official template, ANGLE and AccessKit included
    assert windows["template"] == "custom" and windows["size"] < ht.selection("windows", choice="official")["size"] / 2
    assert windows["url"] == ("https://github.com/rabbitlandsgame/rabbitlands-client/releases/download/"
                              "helper-template-4.7.2-rl1/rabbitlands-helper-template-4.7.2-windows-x86_64.exe")
    assert linux["template"] == "official" and linux["sha256"] == ht.load()["platforms"]["linux"]["official"]["sha256"]
    assert ht.load()["platforms"]["linux"]["glibc_max"] == "2.28"
    with pytest.raises(ht.TemplateError) as error:
        ht.selection("linux", choice="custom")
    assert error.value.code == "blocked"
    official = ht.selection("windows", choice="official")  # the fallback switch
    assert official == {"template": "official", "file": "windows_release_x86_64.exe", "size": 109268480,
                        "sha256": "d34d36f3be1a6c49c56525ae86469b92e4f417ddf0b43cf00dd80c385c4b0562"}


def test_the_hosting_tag_is_never_a_release_or_pool_tag():
    import desktop_r2
    import shared_release_assets
    tag = ht.load()["hosting"]["tag"]
    assert ht.REPOSITORY == desktop_r2.REPOSITORY
    # promote's pruning and collect_unused handle only these tags; the template release is never touched
    assert not shared_release_assets.CLIENT_TAG.fullmatch(tag) and not shared_release_assets.STORAGE_TAG.fullmatch(tag)
    assert not tag.startswith("client-")


@pytest.mark.parametrize("change", [
    lambda r: r["arguments"].append("module_regex_enabled=yes"),
    lambda r: r["arguments"].remove("module_svg_enabled=yes"),
    lambda r: r["arguments"].remove("modules_enabled_by_default=no"),
    lambda r: r.update(build_name="official"),
    lambda r: r["platforms"]["linux"].update(select="custom"),
    lambda r: r["platforms"]["windows"].update(select="newest"),
    lambda r: r["platforms"]["windows"]["custom"].update(sha256="A" * 64),
    lambda r: r["platforms"]["windows"]["custom"].update(file="../template.exe"),
    lambda r: r["platforms"]["windows"]["arguments"].append("optimize=speed"),
    lambda r: r["platforms"]["windows"]["arguments"].append("module_webp_enabled=yes"),
    lambda r: r["arguments"].__setitem__(r["arguments"].index("module_svg_enabled=yes"), "module_svg_enabled=true"),
    lambda r: r["arguments"].append("module_regex_enabled=no"),
    lambda r: r["engine"].update(repository="https://example.com/godot.git"),
    lambda r: r["hosting"].update(tag="client-assets"),
    # the dependency archives
    lambda r: r["platforms"]["windows"]["arguments"].append("angle_libs=deps/angle"),
    lambda r: r["arguments"].append("accesskit_sdk_path=deps/accesskit"),
    lambda r: r["platforms"]["windows"]["arguments"].__setitem__(
        r["platforms"]["windows"]["arguments"].index("angle=yes"), "angle=no"),
    lambda r: r["platforms"]["windows"]["arguments"].remove("accesskit=yes"),
    lambda r: r["platforms"]["windows"]["dependencies"].pop("accesskit"),
    lambda r: r["platforms"]["windows"].pop("dependencies"),
    lambda r: r["platforms"]["linux"]["dependencies"].update(
        angle=r["platforms"]["windows"]["dependencies"]["angle"]),
    lambda r: r["platforms"]["windows"]["dependencies"]["angle"].update(sha256="0" * 63),
    lambda r: r["platforms"]["windows"]["dependencies"]["angle"].update(size=0),
    lambda r: r["platforms"]["windows"]["dependencies"]["angle"].update(
        url="https://example.com/godot-angle-static-x86_64-gcc-release.zip"),
    lambda r: r["platforms"]["windows"]["dependencies"]["angle"].update(
        url="https://github.com/godotengine/godot-angle-static/releases/download/chromium/7219/other.zip"),
    lambda r: r["platforms"]["windows"]["dependencies"]["accesskit"].update(root="../accesskit-c-0.22.3"),
    lambda r: r["platforms"]["windows"]["dependencies"]["accesskit"].update(option="winrt_path"),
    lambda r: r["platforms"]["windows"]["dependencies"]["accesskit"].update(option="angle_libs"),
    lambda r: r["platforms"]["windows"]["dependencies"]["accesskit"].update(imports=[]),
    lambda r: r["platforms"]["windows"]["dependencies"]["accesskit"].update(imports=["UIAutomationCore.dll"]),
    # a platform's own module switch exists only for a pinned library that links against it
    lambda r: r["platforms"]["windows"]["arguments"].remove("module_astcenc_enabled=yes"),
    lambda r: r["platforms"]["windows"]["dependencies"]["angle"].pop("modules"),
    lambda r: r["platforms"]["windows"]["dependencies"]["accesskit"].update(modules=["webp"]),
    lambda r: r["platforms"]["windows"]["dependencies"]["angle"].update(modules=["astcenc", "svg"]),
    lambda r: r["platforms"]["linux"]["arguments"].append("module_astcenc_enabled=yes"),
])
def test_validation_refuses_a_changed_recipe(change):
    recipe = json.loads(ht.RECIPE.read_text(encoding="utf-8"))
    change(recipe)
    with pytest.raises(ht.TemplateError) as error:
        ht.validate(recipe)
    assert error.value.code == "recipe"


# --- Obtaining the pinned template -----------------------------------------------------------

def test_obtain_reuses_a_verified_file_and_downloads_only_when_missing(tmp_path):
    recipe = fake_recipe(b"template")
    calls = []

    def download(url, size, sha256, target):
        calls.append((url, size, sha256, target.name))
        Path(target).write_bytes(b"template")
    path = ht.obtain("windows", directory=tmp_path / "t", recipe=recipe, download=download)
    assert path.read_bytes() == b"template" and len(calls) == 1
    chosen = ht.selection("windows", recipe=recipe)
    assert calls[0] == (chosen["url"], 8, sha(b"template"), chosen["file"])
    assert ht.obtain("windows", directory=tmp_path / "t", recipe=recipe, download=download) == path
    assert len(calls) == 1  # the verified file is used again


def test_obtain_refuses_bytes_that_are_not_the_pin_and_never_replaces_a_file(tmp_path):
    recipe = fake_recipe(b"template")
    with pytest.raises(ht.TemplateError) as error:
        ht.obtain("windows", directory=tmp_path, recipe=recipe,
                  download=lambda url, size, digest, target: Path(target).write_bytes(b"templatX"))
    assert error.value.code == "template-hash"
    existing = tmp_path / "other"
    existing.mkdir()
    (existing / ht.selection("windows", recipe=recipe)["file"]).write_bytes(b"something else")
    with pytest.raises(ht.TemplateError):
        ht.obtain("windows", directory=existing, recipe=recipe,
                  download=lambda *args: pytest.fail("an existing file is never replaced"))
    assert (existing / ht.selection("windows", recipe=recipe)["file"]).read_bytes() == b"something else"


@pytest.mark.parametrize("served", [b"template!", b"templatX", b"templ"])
def test_the_pinned_download_refuses_a_wrong_size_or_hash_and_leaves_nothing(tmp_path, monkeypatch, served):
    recipe = fake_recipe(b"template")

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False
    requests = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout: requests.append(request.full_url)
                        or Response(served))
    with pytest.raises(ht.TemplateError) as error:
        ht.obtain("windows", directory=tmp_path, recipe=recipe)
    assert error.value.code == "template-download"
    assert requests == [ht.selection("windows", recipe=recipe)["url"]] and list(tmp_path.iterdir()) == []
    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout: Response(b"template"))
    assert ht.obtain("windows", directory=tmp_path, recipe=recipe).read_bytes() == b"template"


def test_a_broken_download_connection_is_a_template_download_refusal(tmp_path, monkeypatch):
    import http.client
    recipe = fake_recipe(b"template")

    class Broken(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, *args):
            raise http.client.IncompleteRead(b"temp", 4)
    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout: Broken())
    with pytest.raises(ht.TemplateError) as error:
        ht.obtain("windows", directory=tmp_path, recipe=recipe)
    assert error.value.code == "template-download" and list(tmp_path.iterdir()) == []


def test_the_official_fallback_uses_the_pinned_official_template(tmp_path):
    recipe = fake_recipe(b"template", b"official", select="official")
    official = tmp_path / "windows_release_x86_64.exe"
    official.write_bytes(b"official")
    no_download = lambda *args: pytest.fail("the official template is never downloaded here")  # noqa: E731
    assert ht.obtain("windows", directory=tmp_path / "t", official=official, recipe=recipe,
                     download=no_download) == official
    official.write_bytes(b"officiaX")
    with pytest.raises(ht.TemplateError):
        ht.obtain("windows", directory=tmp_path / "t", official=official, recipe=recipe, download=no_download)
    with pytest.raises(ht.TemplateError) as error:
        ht.obtain("windows", directory=tmp_path / "t", official=None, recipe=recipe, download=no_download)
    assert error.value.code == "template-missing"


def test_cli_verify_checks_a_file_against_the_pin(tmp_path, monkeypatch, capsys):
    pin_templates(monkeypatch, tmp_path, b"template", place=False)
    good, bad = tmp_path / "good.exe", tmp_path / "bad.exe"
    good.write_bytes(b"template")
    bad.write_bytes(b"other")
    assert ht._main(["verify", "--platform", "windows", "--file", str(good)]) == 0
    assert ht._main(["verify", "--platform", "windows", "--file", str(bad)]) == 2
    assert "Refused: template-hash" in capsys.readouterr().err


# --- Build checks ----------------------------------------------------------------------------

def test_the_build_runs_scons_with_the_recipe_and_a_scrubbed_environment():
    recipe = ht.load()
    args = ht.scons_arguments(recipe, "windows", 6)
    assert args[0] == "-j6" and args[1:] == recipe["arguments"] + recipe["platforms"]["windows"]["arguments"]
    env = ht.build_environment(recipe, "windows", msys2=Path("msys"),
                               environ={"PATH": "x", "SCONSFLAGS": "-j99", "SCONS_CACHE": "c", "CXXFLAGS": "-O0",
                                        "GODOT_VERSION_STATUS": "dev", "HOME": "h"})
    assert env["BUILD_NAME"] == "rl_helper" and env["SOURCE_DATE_EPOCH"] == "1786929518"
    assert env["PYTHONHASHSEED"] == "0" and env["HOME"] == "h"
    assert not {"SCONSFLAGS", "SCONS_CACHE", "CXXFLAGS", "GODOT_VERSION_STATUS"} & set(env)
    assert env["PATH"].startswith(str(Path("msys") / "mingw64" / "bin") + os.pathsep)
    with pytest.raises(ht.TemplateError):
        ht.build_environment(recipe, "windows", environ={})


def test_dependency_folders_follow_the_recipe_arguments_and_never_come_from_it(tmp_path):
    recipe = ht.load()
    plain = ht.scons_arguments(recipe, "windows", 4)
    folders = {"angle_libs": str(tmp_path / "a" / "deps" / "angle"),
               "accesskit_sdk_path": str(tmp_path / "a" / "deps" / "accesskit" / "accesskit-c-0.22.3")}
    args = ht.scons_arguments(recipe, "windows", 4, folders)
    assert args[:len(plain)] == plain
    assert args[len(plain):] == [f"accesskit_sdk_path={folders['accesskit_sdk_path']}",
                                 f"angle_libs={folders['angle_libs']}"]


def dependency_archive(path: Path, members: dict) -> dict:
    """A zip of `members` at `path` and its pin (fake dependency)."""
    import zipfile
    with zipfile.ZipFile(path, "w") as bundle:
        for name, data in members.items():
            bundle.writestr(name, data)
    data = path.read_bytes()
    return {"file": path.name, "size": len(data), "sha256": sha(data), "root": "sdk", "option": "accesskit_sdk_path",
            "imports": ["uiautomationcore.dll"],
            "url": f"https://github.com/godotengine/godot-accesskit-c-static/releases/download/0.1/{path.name}"}


def test_dependency_archives_are_checked_against_their_pins_before_a_build(tmp_path):
    archive = tmp_path / "sdk.zip"
    pin = dependency_archive(archive, {"sdk/include/accesskit.h": b"h", "sdk/lib/libaccesskit.a": b"a"})
    spec = {"dependencies": {"accesskit": pin}}
    assert ht.check_dependencies(spec, {"accesskit": archive}) == {"accesskit": archive}
    for archives in ({}, {"accesskit": archive, "angle": archive}, {"angle": archive},
                     {"accesskit": tmp_path / "missing.zip"}):
        with pytest.raises(ht.TemplateError) as error:
            ht.check_dependencies(spec, archives)
        assert error.value.code == "dependency"
    other = tmp_path / "other.zip"
    dependency_archive(other, {"sdk/include/accesskit.h": b"H"})
    with pytest.raises(ht.TemplateError) as error:
        ht.check_dependencies(spec, {"accesskit": other})
    assert error.value.code == "dependency" and pin["sha256"] in str(error.value)
    assert ht.check_dependencies({"dependencies": {}}, {}) == {}


def test_a_dependency_is_unpacked_from_the_checked_bytes_into_a_new_folder(tmp_path):
    archive = tmp_path / "sdk.zip"
    pin = dependency_archive(archive, {"sdk/include/accesskit.h": b"h", "sdk/lib/libaccesskit.a": b"a"})
    folder = ht.unpack_dependency(archive, pin, tmp_path / "a" / "deps" / "accesskit")
    assert folder == tmp_path / "a" / "deps" / "accesskit" / "sdk"
    assert (folder / "lib" / "libaccesskit.a").read_bytes() == b"a"
    with pytest.raises(ht.TemplateError):  # never into an existing folder
        ht.unpack_dependency(archive, pin, tmp_path / "a" / "deps" / "accesskit")
    with pytest.raises(ht.TemplateError):  # the root the recipe names must exist
        ht.unpack_dependency(archive, {**pin, "root": "other"}, tmp_path / "b")
    assert ht.unpack_dependency(archive, {**pin, "root": ""}, tmp_path / "c") == tmp_path / "c"
    dependency_archive(archive, {"sdk/include/accesskit.h": b"changed"})  # replaced after the check
    with pytest.raises(ht.TemplateError) as error:
        ht.unpack_dependency(archive, pin, tmp_path / "d")
    assert error.value.code == "dependency" and not (tmp_path / "d").exists()
    for member in ("../escape.h", "sdk/../../escape.h", "/abs.h", "C:/drive.h"):
        evil = tmp_path / "evil.zip"
        evil_pin = dependency_archive(evil, {"sdk/ok.h": b"h", member: b"x"})
        with pytest.raises(ht.TemplateError):
            ht.unpack_dependency(evil, evil_pin, tmp_path / "e")
        assert not (tmp_path / "e").exists() and not (tmp_path / "escape.h").exists()


def test_a_build_refuses_missing_or_other_dependency_archives_before_it_starts(tmp_path):
    native = "windows" if os.name == "nt" else "linux"
    if not ht.load()["platforms"][native]["dependencies"]:
        pytest.skip("this platform's recipe pins no dependency archive")
    wrong = tmp_path / "wrong.zip"
    wrong.write_bytes(b"not the archive")
    for dependencies in ({}, {name: wrong for name in ht.load()["platforms"][native]["dependencies"]}):
        with pytest.raises(ht.TemplateError) as error:
            ht.build(native, source="unused", work=tmp_path / "work", scons_wheel=tmp_path / "unused.whl", jobs=1,
                     twice=True, msys2=tmp_path, dependencies=dependencies)
        assert error.value.code == "dependency" and not (tmp_path / "work").exists()


def test_cli_build_takes_each_dependency_once(tmp_path, capsys):
    assert ht._main(["build", "--platform", "windows", "--source", "x", "--work", str(tmp_path / "w"),
                     "--scons-wheel", "x.whl", "--dependency", "angle=a.zip", "--dependency", "angle=b.zip"]) == 2
    assert "Refused: dependency" in capsys.readouterr().err and not (tmp_path / "w").exists()


def test_scons_that_drops_a_switched_on_library_fails_the_build(tmp_path, monkeypatch):
    def run(args, cwd, env, stdout, stderr, **kwargs):
        stdout.write("WARNING: The ANGLE rendering driver requires dependencies to be installed.\n")
        return type("Done", (), {"returncode": 0})()
    monkeypatch.setattr(ht.subprocess, "run", run)
    with pytest.raises(ht.TemplateError) as error:
        ht._scons(tmp_path, tmp_path, [], {}, tmp_path / "scons.log", "windows")
    assert error.value.code == "dependency"
    # a recipe that pins no library (Linux) keeps Godot's AccessKit default, which a fresh clone drops
    ht._scons(tmp_path, tmp_path, [], {}, tmp_path / "linux.log", "linux", pinned_libraries=False)


def test_only_a_platform_that_pins_libraries_fails_on_a_dropped_one(tmp_path, monkeypatch):
    calls = []

    def scons(tree, scons, arguments, env, log, platform, *, pinned_libraries=True):
        calls.append(pinned_libraries)
        raise ht.TemplateError("scons", "stop after the first SCons call")
    monkeypatch.setattr(ht, "_scons", scons)
    monkeypatch.setattr(ht, "check_toolchain", lambda *args, **kwargs: {"problems": []})
    monkeypatch.setattr(ht, "install_scons", lambda *args: tmp_path / "scons")
    monkeypatch.setattr(ht, "clone", lambda source, tree, engine: tree.mkdir(parents=True) or engine["commit"])
    monkeypatch.setattr(ht, "unpack_dependency", lambda archive, pin, target: target)
    native = "windows" if os.name == "nt" else "linux"
    recipe = json.loads(ht.RECIPE.read_text(encoding="utf-8"))
    without = tmp_path / "without.json"  # the native platform's recipe with no pinned library
    spec = recipe["platforms"][native]
    spec["arguments"] = [item for item in spec["arguments"] if not item.startswith("module_astcenc_enabled=")]
    spec["arguments"] = [f"{item.split('=')[0]}=no" if item.split("=")[0] in ht.WINDOWS_SWITCHES else item
                         for item in spec["arguments"]]
    spec["dependencies"] = {}
    without.write_text(json.dumps(recipe), encoding="utf-8")
    for path in (None, without):
        archives = {name: tmp_path / name for name in ht.load(path)["platforms"][native]["dependencies"]}
        monkeypatch.setattr(ht, "check_dependencies", lambda spec, given: dict(given))
        calls.clear()
        with pytest.raises(ht.TemplateError):
            ht.build(native, source="unused", work=tmp_path / str(len(archives)), scons_wheel=tmp_path / "unused.whl",
                     jobs=1, twice=False, msys2=tmp_path, recipe_path=path, dependencies=archives)
        assert calls == [bool(archives)]


def fake_pe(*dlls: str) -> bytes:
    """A minimal PE32+ image whose import directory names `dlls` (timestamp 0)."""
    import struct
    section_rva, section_raw, header = 0x1000, 0x200, 0x40
    names = b"".join(name.encode() + b"\0" for name in dlls)
    descriptors = bytearray(20 * (len(dlls) + 1))
    position = len(descriptors)
    for index, name in enumerate(dlls):
        struct.pack_into("<I", descriptors, 20 * index + 12, section_rva + position)
        position += len(name) + 1
    body = bytes(descriptors) + names
    optional = bytearray(240)
    struct.pack_into("<H", optional, 0, 0x20B)
    struct.pack_into("<II", optional, 112 + 8, section_rva, len(descriptors))  # data directory 1: imports
    coff = struct.pack("<HHIIIHH", 0x8664, 1, 0, 0, 0, len(optional), 0x22)
    section = b".idata\0\0" + struct.pack("<IIII", len(body), section_rva, len(body), section_raw) + b"\0" * 16
    image = bytearray(b"MZ" + b"\0" * 0x3A + struct.pack("<I", header))
    image += b"PE\0\0" + coff + optional + section
    image += b"\0" * (section_raw - len(image)) + body
    return bytes(image)


def test_the_windows_output_check_finds_each_linked_dependency_by_its_imports(tmp_path):
    assert ht.pe_imports(fake_pe("KERNEL32.dll", "dxgi.dll", "UIAutomationCore.dll")) == {
        "kernel32.dll", "dxgi.dll", "uiautomationcore.dll"}
    assert ht.pe_imports(fake_pe()) == set()
    spec = ht.load()["platforms"]["windows"]
    linked, without = tmp_path / "linked.exe", tmp_path / "without.exe"
    linked.write_bytes(fake_pe("KERNEL32.dll", "dxgi.dll", "uiautomationcore.dll"))
    without.write_bytes(fake_pe("KERNEL32.dll", "dxgi.dll"))  # AccessKit dropped
    assert ht.inspect(linked, "windows", spec, private=[str(tmp_path / "build")])["checks"] == {
        "pe_timestamp_zero": True, "dependencies_linked": True, "no_build_paths": True}
    assert ht.inspect(without, "windows", spec, private=[])["checks"]["dependencies_linked"] is False
    with pytest.raises(ht.TemplateError):
        ht.pe_imports(b"\x7fELF" + b"\0" * 64)


def test_output_checks_find_timestamps_glibc_floors_and_build_paths(tmp_path):
    pe = bytearray(b"MZ" + b"\0" * 0x3A + (0x40).to_bytes(4, "little") + b"PE\0\0" + b"\0" * 64)
    assert ht.pe_timestamp(bytes(pe)) == 0
    pe[0x48:0x4C] = (1786929518).to_bytes(4, "little")
    assert ht.pe_timestamp(bytes(pe)) == 1786929518
    assert ht.glibc_floor(b"\0GLIBC_2.2.5\0GLIBC_2.17\0GLIBC_2.28\0") == "2.28"
    assert ht.glibc_floor(b"\0GLIBC_2.34\0GLIBC_2.38\0") == "2.38" and ht.glibc_floor(b"none") is None
    spec = ht.load()["platforms"]["linux"]
    elf = tmp_path / "t"
    elf.write_bytes(b"\x7fELF GLIBC_2.28 " + str(tmp_path / "build").encode())
    record = ht.inspect(elf, "linux", spec, private=[str(tmp_path / "build")])
    assert record["checks"] == {"glibc_floor": True, "no_build_paths": False}
    elf.write_bytes(b"\x7fELF GLIBC_2.38")
    assert ht.inspect(elf, "linux", spec, private=[str(tmp_path / "build")])["checks"] == {
        "glibc_floor": False, "no_build_paths": True}


def test_recipe_and_tool_hold_no_machine_paths():
    for path in (ht.RECIPE, TOOLS / "helper_template.py"):
        data = path.read_bytes()
        assert data.isascii() and b"\r" not in data, path.name
        for needle in (b"C:/", b"C:" + bytes([92]), b"AppData", b"scratchpad", b"/Users/", b"/home/", b"worktrees/",
                       b"dist/ud09"):
            assert needle not in data, (path.name, needle)


# --- Audit: the helper uses only classes the custom template has ------------------------------

def test_the_class_list_was_measured_for_the_pinned_template():
    classes = ht.unavailable_classes()
    assert classes["template_sha256"] == ht.load()["platforms"]["windows"]["custom"]["sha256"]
    unavailable = set(classes["unavailable"])
    assert len(unavailable) == classes["official_classes"] - classes["custom_classes"]
    # what the build removes, and what the helper relies on
    assert {"RegEx", "ZIPReader", "Node3D", "WebSocketPeer", "PhysicsServer2D", "NavigationServer2D"} <= unavailable
    assert not {"HTTPRequest", "Crypto", "CryptoKey", "HashingContext", "ConfirmationDialog", "Label", "Thread",
                "Mutex", "JSON", "ConfigFile", "Marshalls", "DisplayServer", "FileAccess", "DirAccess"} & unavailable


def test_the_committed_helper_uses_no_class_the_custom_template_lacks():
    import desktop_helpers
    files = {f"src/updates/{name}": (GODOT / "src/updates" / name).read_bytes()
             for name in desktop_helpers.HELPER_SCRIPTS}
    files["main.tscn"] = desktop_helpers.MAIN_TSCN.encode()
    assert ht.audit(files) == []
    used = set().union(*(ht.code_identifiers(data.decode()) for name, data in files.items() if name.endswith(".gd")))
    assert {"HTTPRequest", "Crypto", "HashingContext", "ConfirmationDialog"} <= used


def test_the_audit_reads_code_not_comments_or_strings():
    source = ('var expression := RegEx.new()  # ZIPReader in a comment\n'
              'var text := "Node3D is only text" + \'Area2D\' + """WebSocketPeer\n"Skin" """\n'
              'var escaped := "a \\" Camera3D"\nvar kept := Label.new()\n')
    assert ht.code_identifiers(source) >= {"RegEx", "Label"}
    assert not {"ZIPReader", "Node3D", "Area2D", "WebSocketPeer", "Skin", "Camera3D"} & ht.code_identifiers(source)
    found = ht.audit({"src/updates/release.gd": source.encode(),
                      "main.tscn": b'[node name="World" type="Node3D"]\n[node name="Status" type="Label"]\n'})
    assert found == ["main.tscn: Node3D", "src/updates/release.gd: RegEx"]
