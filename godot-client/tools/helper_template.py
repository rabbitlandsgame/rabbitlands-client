"""The updater/uninstaller helper's own small export template (UD-09): recipe, pins, build, fetch.

The helper (desktop_helpers.py) needs a window with a label and a dialog, HTTPS,
SHA-256/RSA, zstd and GDScript. The official 4.7.2 template carries the whole
engine (109 MB on Windows); this recipe builds Godot 4.7.2 without 3D, 2D
physics/navigation, Vulkan/D3D12 and every module the helper does not use. On
Windows it keeps what the official template links for players: ANGLE (OpenGL ES
over Direct3D 11, for GPUs and remote displays without OpenGL 3.3, and Windows on
ARM) and AccessKit (screen readers).

  helper_template.json  the committed recipe: the Godot tag and commit, the SCons
                        arguments, the toolchain pins, the pinned dependency
                        archives (Godot's own ANGLE and AccessKit downloads: URL,
                        size, SHA-256) and, per platform, the pinned custom
                        template (size, SHA-256; download URL derived from the
                        hosting tag), the official template's pin, and `select`:
                        which of the two the helper is exported with.
                        "official" is the fallback switch.
  selection()           the pinned template a platform's helper uses. Its SHA-256
                        is the helpers_fingerprint input, so a release whose
                        helper inputs are unchanged reuses the previous helper
                        without fetching any template.
  obtain()              that template as a verified local file, downloaded from
                        the pinned URL only when a helper must be exported.

  python helper_template.py build --platform windows --source <godot clone or URL> --work <new dir>
         --scons-wheel <scons-4.10.1-py3-none-any.whl> --msys2 <MSYS2 root>
         --dependency angle=<archive> --dependency accesskit=<archive> [--twice] [--jobs N]
  python helper_template.py verify --platform windows --file <template>
  python helper_template.py fetch --platform windows --dir <folder>

`build` checks the toolchain and every dependency archive (exact size and
SHA-256) against their pins before anything else, clones the tag
(core.autocrlf=false) into a new tree, unpacks each verified archive inside that
tree's own folder and hands SCons its path (the recipe never names a path), runs
SCons with the recipe's arguments, and checks the result (PE timestamp 0 and the
dependencies' imports on Windows, the glibc floor on Linux, no build, archive or
home paths in the binary). --twice builds a second fresh tree, with its own
unpacked dependencies, at another path and requires equal bytes. A pin is
accepted only from such a reproducible build.

Only the standard library is imported at module level, so `build` also runs
under a plain Linux Python (WSL).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import time
import zipfile

RECIPE = Path(__file__).with_name("helper_template.json")
# Local builds keep a fetched template here (ignored by Git); CI fetches into its work folder.
LOCAL_DIR = Path(__file__).resolve().parents[2] / ".local" / "helper-template"
KIND = "rabbitlands-helper-template"
PLATFORMS = ("windows", "linux")
CHOICES = ("custom", "official")
REPOSITORY = "rabbitlandsgame/rabbitlands-client"
TAG = re.compile(r"helper-template-[0-9]+\.[0-9]+\.[0-9]+-rl[0-9]+")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_FILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}")
_GLIBC = re.compile(rb"GLIBC_2\.([0-9]+)(?:\.[0-9]+)?")
# Variables that would change what SCons builds or where it caches objects.
_SCRUBBED_ENV = ("SCONSFLAGS", "SCONS_CACHE", "SCONS_CACHE_LIMIT", "SCONS_LIB_DIR", "GODOT_VERSION_STATUS",
                 "CC", "CXX", "CFLAGS", "CXXFLAGS", "CCFLAGS", "CPPFLAGS", "LDFLAGS", "LINKFLAGS", "MINGW_PREFIX")
BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
_SCONS_BOOT = "import sys; sys.path.insert(0, sys.argv.pop(1)); import SCons.Script; SCons.Script.main()"
# The SCons option that takes a dependency's unpacked folder, and the switch that
# must say "yes" for it. Godot drops a switched-on library whose folder is missing,
# with only a warning, so the recipe pins the archive and the build supplies the folder.
DEPENDENCY_OPTIONS = {"angle_libs": "angle", "accesskit_sdk_path": "accesskit"}
# Switches a Windows recipe names explicitly (Godot's defaults would look in a per-user folder).
WINDOWS_SWITCHES = ("angle", "accesskit")
_DEPENDENCY_URL = re.compile(r"https://github\.com/godotengine/[A-Za-z0-9_.-]+/releases/download/[A-Za-z0-9_./-]+")
_DLL = re.compile(r"[a-z0-9_.-]+\.dll")
# What Godot's SCons prints when it drops a switched-on library for want of its files.
_MISSING_DEPENDENCY = "requires dependencies to be installed"


class TemplateError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def _digest(path: Path) -> str:
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _module_switches(arguments: list) -> dict:
    """{module: value} of every module_<name>_enabled argument."""
    return {name[len("module_"):-len("_enabled")]: value for name, value in
            (item.split("=", 1) for item in arguments) if name.startswith("module_") and name.endswith("_enabled")}


def _pin(value, where: str) -> dict:
    if not isinstance(value, dict):
        raise TemplateError("recipe", f"{where} is not an object")
    if type(value.get("file")) is not str or not _FILE.fullmatch(value["file"]):
        raise TemplateError("recipe", f"{where}.file")
    if type(value.get("size")) is not int or not 0 < value["size"] <= 512 * 1024 ** 2:
        raise TemplateError("recipe", f"{where}.size")
    if type(value.get("sha256")) is not str or not _SHA256.fullmatch(value["sha256"]):
        raise TemplateError("recipe", f"{where}.sha256")
    return value


def _dependency(value, where: str) -> dict:
    """A pinned dependency archive: Godot's own download URL, its size and SHA-256,
    the folder inside it SCons is given, that SCons option, and the DLLs it adds."""
    _pin(value, where)
    if type(value.get("url")) is not str or not _DEPENDENCY_URL.fullmatch(value["url"]) \
            or not value["url"].endswith("/" + value["file"]):
        raise TemplateError("recipe", f"{where}.url must be a godotengine release asset named by file")
    root = value.get("root")
    if type(root) is not str or (root and not _FILE.fullmatch(root)):
        raise TemplateError("recipe", f"{where}.root must be empty or one folder name")
    if value.get("option") not in DEPENDENCY_OPTIONS:
        raise TemplateError("recipe", f"{where}.option must be one of {sorted(DEPENDENCY_OPTIONS)}")
    imports = value.get("imports")
    if not isinstance(imports, list) or not imports or not all(type(item) is str and _DLL.fullmatch(item)
                                                               for item in imports):
        raise TemplateError("recipe", f"{where}.imports must name the lower-case DLLs the library adds")
    modules = value.get("modules", [])
    if not isinstance(modules, list) or not all(type(item) is str and re.fullmatch(r"[a-z0-9_]+", item)
                                                for item in modules):
        raise TemplateError("recipe", f"{where}.modules must name the Godot modules the library links against")
    return value


def validate(recipe) -> dict:
    """The recipe, or TemplateError naming the first problem."""
    if not isinstance(recipe, dict) or recipe.get("kind") != KIND or recipe.get("schema") != 1:
        raise TemplateError("recipe", "not a schema 1 helper template recipe")
    engine = recipe.get("engine") or {}
    if not re.fullmatch(r"[0-9a-f]{40}", str(engine.get("commit"))) or not str(engine.get("tag")).endswith("-stable") \
            or type(engine.get("commit_time")) is not int or engine.get("repository") != \
            "https://github.com/godotengine/godot.git":
        raise TemplateError("recipe", "engine: the official repository, a -stable tag, its commit and commit time")
    if not re.fullmatch(r"[a-z0-9_]+", str(recipe.get("build_name"))) or recipe["build_name"] == "official":
        raise TemplateError("recipe", "build_name must name this custom build")
    scons = recipe.get("scons") or {}
    if not _SHA256.fullmatch(str(scons.get("wheel_sha256"))) or not _FILE.fullmatch(str(scons.get("wheel"))):
        raise TemplateError("recipe", "scons wheel pin")
    if not TAG.fullmatch(str((recipe.get("hosting") or {}).get("tag"))):
        raise TemplateError("recipe", "hosting.tag must be helper-template-<version>-rl<n>")
    modules = recipe.get("modules")
    arguments = recipe.get("arguments")
    if not isinstance(modules, list) or not isinstance(arguments, list) \
            or not all(type(item) is str and "=" in item for item in arguments):
        raise TemplateError("recipe", "modules and arguments")
    switches = _module_switches(arguments)
    if set(switches) != set(modules) or set(switches.values()) != {"yes"} \
            or "modules_enabled_by_default=no" not in arguments:
        raise TemplateError("recipe", "the arguments must enable exactly the listed modules and no others")
    platforms = recipe.get("platforms")
    if not isinstance(platforms, dict) or set(platforms) != set(PLATFORMS):
        raise TemplateError("recipe", "platforms must be windows and linux")
    for platform, spec in platforms.items():
        if not isinstance(spec, dict) or spec.get("select") not in CHOICES:
            raise TemplateError("recipe", f"{platform}.select must be custom or official")
        _pin(spec.get("official"), f"{platform}.official")
        custom = _pin(spec.get("custom"), f"{platform}.custom")
        if spec["select"] == "custom" and custom.get("blocked"):
            raise TemplateError("recipe", f"{platform} selects a custom template that is blocked: {custom['blocked']}")
        if not isinstance(spec.get("arguments"), list) or not all(type(item) is str and "=" in item
                                                                  for item in spec["arguments"]):
            raise TemplateError("recipe", f"{platform}.arguments")
        names = [item.split("=", 1)[0] for item in arguments + spec["arguments"]]
        if len(names) != len(set(names)) or "platform" not in names:
            raise TemplateError("recipe", f"{platform}: every SCons argument once, the platform included")
        dependencies = spec.get("dependencies")
        if not isinstance(dependencies, dict) or not all(re.fullmatch(r"[a-z0-9_]+", name) for name in dependencies):
            raise TemplateError("recipe", f"{platform}.dependencies")
        options = [_dependency(pin, f"{platform}.dependencies.{name}")["option"] for name, pin in dependencies.items()]
        # A platform switches on a module only because a pinned library links against it
        # (ANGLE's static library calls the astcenc module's decoder, as in the official build).
        needed = {module for pin in dependencies.values() for module in pin.get("modules", [])}
        own = _module_switches(spec["arguments"])
        if set(own) != needed or set(own.values()) - {"yes"} or needed & set(modules):
            raise TemplateError("recipe", f"{platform}: modules are switched by the common arguments, or here "
                                          f"only for a pinned library that needs them")
        values = dict(item.split("=", 1) for item in arguments + spec["arguments"])
        if len(options) != len(set(options)) or set(DEPENDENCY_OPTIONS) & set(values):
            raise TemplateError("recipe", f"{platform}: a dependency folder comes only from its pinned archive")
        if platform == "windows" and not all(values.get(switch) in ("yes", "no") for switch in WINDOWS_SWITCHES):
            raise TemplateError("recipe", f"windows names {', '.join(WINDOWS_SWITCHES)} explicitly")
        for option, switch in DEPENDENCY_OPTIONS.items():
            if (values.get(switch) == "yes") != (option in options):
                raise TemplateError("recipe", f"{platform}: {switch}=yes and a pinned {option} archive go together")
        toolchain = spec.get("toolchain") or {}
        if not isinstance(toolchain.get("packages"), dict) or not isinstance(toolchain.get("files"), dict) \
                or not all(_SHA256.fullmatch(str(value)) for value in toolchain["files"].values()):
            raise TemplateError("recipe", f"{platform}.toolchain")
    return recipe


def load(path: Path | None = None) -> dict:
    try:
        return validate(json.loads(Path(path or RECIPE).read_text(encoding="utf-8")))
    except (OSError, ValueError) as error:
        if isinstance(error, TemplateError):
            raise
        raise TemplateError("recipe", f"{Path(path or RECIPE).name} is unreadable: {error}") from None


def recipe_sha256(path: Path | None = None) -> str:
    """The SHA-256 of the committed recipe bytes (records only; pins are what count)."""
    return _digest(Path(path or RECIPE))


def download_url(recipe: dict, platform: str) -> str:
    """Where the custom template is hosted: an asset of the dedicated prerelease."""
    return (f"https://github.com/{REPOSITORY}/releases/download/{recipe['hosting']['tag']}/"
            f"{recipe['platforms'][platform]['custom']['file']}")


def selection(platform: str, *, choice: str | None = None, recipe: dict | None = None) -> dict:
    """The pinned template `platform`'s helper is exported with: {template, file, size,
    sha256[, url]}. `choice` overrides the recipe's select (tests and fallbacks)."""
    if platform not in PLATFORMS:
        raise TemplateError("platform", ascii(platform))
    recipe = recipe or load()
    spec = recipe["platforms"][platform]
    choice = choice or spec["select"]
    if choice not in CHOICES:
        raise TemplateError("choice", ascii(choice))
    pin = spec[choice]
    if choice == "custom" and pin.get("blocked"):
        raise TemplateError("blocked", f"the {platform} custom template is blocked: {pin['blocked']}")
    chosen = {"template": choice, "file": pin["file"], "size": pin["size"], "sha256": pin["sha256"]}
    if choice == "custom":
        chosen["url"] = download_url(recipe, platform)
    return chosen


def check_file(path: Path, chosen: dict) -> Path:
    """`path` when its size and SHA-256 equal the pin, else TemplateError."""
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise TemplateError("template-missing", f"no {chosen['template']} template file at {path.name}")
    if path.stat().st_size != chosen["size"] or _digest(path) != chosen["sha256"]:
        raise TemplateError("template-hash", f"{path.name} is not the pinned {chosen['template']} template "
                                             f"({chosen['size']} bytes, {chosen['sha256']})")
    return path


def _download(url: str, size: int, sha256: str, target: Path) -> None:
    """setup_runner_tools' pinned download: exact size and SHA-256, a new file only,
    nothing left behind on failure."""
    import http.client
    import setup_runner_tools
    try:
        setup_runner_tools.download((url, size, sha256), target)
    except (OSError, ValueError, http.client.HTTPException) as error:  # IncompleteRead is neither of the first two
        raise TemplateError("template-download", f"{url} could not be fetched as pinned: {error}") from None


def obtain(platform: str, *, directory: Path, official: Path | None = None, choice: str | None = None,
           recipe: dict | None = None, download=None) -> Path:
    """The selected template as a verified local file.

    official: the official template file (the pinned editor's export template);
    used, after its pin check, when the selection is official. custom: the file
    `directory/<pinned name>` when it already holds the pinned bytes, else a
    download from the pinned URL (exact size and SHA-256, a new file only)."""
    chosen = selection(platform, choice=choice, recipe=recipe)
    if chosen["template"] == "official":
        if official is None:
            raise TemplateError("template-missing", f"the official {platform} export template was not found")
        return check_file(official, chosen)
    target = Path(directory) / chosen["file"]
    if target.exists() or target.is_symlink():
        return check_file(target, chosen)
    target.parent.mkdir(parents=True, exist_ok=True)
    (download or _download)(chosen["url"], chosen["size"], chosen["sha256"], target)
    return check_file(target, chosen)


# --- audit: the helper may use only classes the custom template has -------------------------

CLASSES = Path(__file__).with_name("helper_template_classes.json")
_GD_TOKEN = re.compile(r'"""|\'\'\'|"|\'|#|\\|\n')
_IDENTIFIER = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
_SCENE_TYPE = re.compile(r'\btype="([A-Za-z0-9_]+)"')


def code_identifiers(text: str) -> set[str]:
    """The identifiers of GDScript source outside comments and string literals."""
    code, index, quote = [], 0, None
    while index < len(text):
        match = _GD_TOKEN.search(text, index)
        if match is None:
            if quote is None:
                code.append(text[index:])
            break
        token = match.group()
        if quote is None:
            code.append(text[index:match.start()])
            if token == "#":
                end = text.find("\n", match.end())
                index = len(text) if end < 0 else end
                continue
            if token in ('"""', "'''", '"', "'"):
                quote = token
            elif token == "\n":
                code.append("\n")
        elif token == "\\":
            index = match.end() + 1  # an escaped character never closes the literal
            continue
        elif token == quote or (token == "\n" and len(quote) == 1):
            quote = None
        index = match.end()
    return set(_IDENTIFIER.findall("".join(code)))


def unavailable_classes(path: Path | None = None) -> dict:
    data = json.loads(Path(path or CLASSES).read_text(encoding="utf-8"))
    if data.get("kind") != KIND + "-classes" or not isinstance(data.get("unavailable"), list):
        raise TemplateError("classes", "not a helper template class list")
    return data


def audit(files: dict, path: Path | None = None) -> list[str]:
    """`name: Class` for every class a helper script or scene uses that the custom
    template lacks (helper_template_classes.json, measured from both templates)."""
    missing = set(unavailable_classes(path)["unavailable"])
    found = []
    for name, data in sorted(files.items()):
        text = data.decode("utf-8", "replace") if isinstance(data, bytes) else data
        if name.endswith(".gd"):
            used = code_identifiers(text)
        elif name.endswith(".tscn"):
            used = set(_SCENE_TYPE.findall(text))
        else:
            continue
        found.extend(f"{name}: {item}" for item in sorted(used & missing))
    return found


# --- build ----------------------------------------------------------------------------------

def _run(args: list, **kwargs) -> str:
    result = subprocess.run(args, capture_output=True, text=True, **kwargs)
    if result.returncode:
        raise TemplateError("command", f"{Path(args[0]).name} {' '.join(map(str, args[1:3]))} exited "
                                       f"{result.returncode}: {result.stderr.strip()[-400:]}")
    return result.stdout


def check_toolchain(platform: str, spec: dict, *, msys2: Path | None = None) -> dict:
    """The installed compiler packages and binaries against the recipe's pins."""
    toolchain = spec["toolchain"]
    found = {"python": f"{sys.version_info.major}.{sys.version_info.minor}", "packages": {}, "files": {}}
    problems = []
    if toolchain.get("python") and found["python"] != toolchain["python"]:
        problems.append(f"Python {found['python']} (pinned {toolchain['python']})")
    # SCons writes source paths with the Python's separator, and GCC embeds them
    # (__FILE__): MSYS2's own Python uses "/" and gives other bytes than CPython.
    found["path_separator"] = os.sep
    if toolchain.get("path_separator") and os.sep != toolchain["path_separator"]:
        problems.append(f"a Python whose path separator is {os.sep!r} (pinned {toolchain['path_separator']!r})")
    if platform == "windows":
        if msys2 is None:
            raise TemplateError("toolchain", "name the MSYS2 installation (--msys2)")
        root = Path(msys2)
        if toolchain["packages"]:
            listing = _run([str(root / "usr/bin/pacman.exe"), "-Q", *toolchain["packages"]])
            found["packages"] = dict(line.split(" ", 1) for line in listing.splitlines() if " " in line)
        files = {name: root / name for name in toolchain["files"]}
    else:
        if toolchain["packages"]:
            listing = _run(["dpkg-query", "-W", "-f", "${Package} ${Version}\n", *toolchain["packages"]])
            found["packages"] = dict(line.split(" ", 1) for line in listing.splitlines() if " " in line)
        files = {name: Path(name) for name in toolchain["files"]}
    for name, version in toolchain["packages"].items():
        if found["packages"].get(name) != version:
            problems.append(f"{name} {found['packages'].get(name)} (pinned {version})")
    for name, path in files.items():
        found["files"][name] = _digest(path) if path.is_file() else None
        if found["files"][name] != toolchain["files"][name]:
            problems.append(f"{name} differs from its pin")
    found["problems"] = problems
    return found


def install_scons(wheel: Path, target: Path, sha256: str) -> Path:
    """The pinned SCons wheel, hash-checked and unpacked into a new folder."""
    if _digest(wheel) != sha256:
        raise TemplateError("scons", f"{Path(wheel).name} is not the pinned SCons wheel")
    if target.exists():
        raise TemplateError("scons", "the SCons folder must be new")
    with zipfile.ZipFile(wheel) as archive:
        for member in archive.namelist():
            if member.startswith("/") or ".." in Path(member).parts:
                raise TemplateError("scons", "unexpected path in the SCons wheel")
        archive.extractall(target)
    return target


def clone(source: str, tree: Path, engine: dict) -> str:
    """A fresh clone of the pinned tag at `tree` (LF line endings); returns its commit."""
    if tree.exists():
        raise TemplateError("tree", "the source tree must be new")
    tree.parent.mkdir(parents=True, exist_ok=True)
    local = Path(source).is_dir()
    args = ["git", "-c", "core.autocrlf=false", "-c", "advice.detachedHead=false", "clone", "--quiet",
            "--config", "core.autocrlf=false", "--branch", engine["tag"]]
    args += ["--no-hardlinks"] if local else ["--depth", "1"]
    _run(args + [str(source), str(tree)])
    commit = _run(["git", "-C", str(tree), "rev-parse", "HEAD^{commit}"]).strip()
    if commit != engine["commit"]:
        raise TemplateError("engine-commit", f"{engine['tag']} is {commit}, not the pinned {engine['commit']}")
    if _run(["git", "-C", str(tree), "status", "--porcelain", "--untracked-files=all"]).strip():
        raise TemplateError("tree", "the fresh clone is not clean")
    return commit


def check_dependencies(spec: dict, archives: dict) -> dict:
    """{name: archive} once every pinned dependency archive is named exactly once and
    its size and SHA-256 equal the pin; checked before any clone or build."""
    pins = spec["dependencies"]
    if set(archives) != set(pins):
        raise TemplateError("dependency", f"name each pinned archive once: {', '.join(sorted(pins)) or 'none'}"
                                          f" (given {', '.join(sorted(archives)) or 'none'})")
    checked = {}
    for name, pin in pins.items():
        path = Path(archives[name])
        if path.is_symlink() or not path.is_file():
            raise TemplateError("dependency", f"no {name} archive at {path.name}; download {pin['url']}")
        if path.stat().st_size != pin["size"] or _digest(path) != pin["sha256"]:
            raise TemplateError("dependency", f"{path.name} is not the pinned {name} archive "
                                              f"({pin['size']} bytes, {pin['sha256']})")
        checked[name] = path
    return checked


def unpack_dependency(archive: Path, pin: dict, target: Path) -> Path:
    """The verified archive unpacked into the new folder `target`; returns the folder
    SCons is given. The bytes are hashed from the same open file they are read from."""
    if target.exists():
        raise TemplateError("dependency", "the dependency folder must be new")
    with Path(archive).open("rb") as handle:
        if os.fstat(handle.fileno()).st_size != pin["size"] \
                or hashlib.file_digest(handle, "sha256").hexdigest() != pin["sha256"]:
            raise TemplateError("dependency", f"{Path(archive).name} changed after it was checked")
        handle.seek(0)
        with zipfile.ZipFile(handle) as bundle:
            for member in bundle.infolist():
                parts = member.filename.split("/")
                if not member.filename or member.filename.startswith("/") or "\\" in member.filename \
                        or ":" in member.filename or ".." in parts \
                        or (member.external_attr >> 16) & 0o170000 == 0o120000:  # a symbolic link
                    raise TemplateError("dependency", f"unexpected member in {Path(archive).name}")
            target.mkdir(parents=True)
            bundle.extractall(target)
    folder = target / pin["root"] if pin["root"] else target
    if not folder.is_dir():
        raise TemplateError("dependency", f"{Path(archive).name} has no {pin['root']} folder")
    return folder


def scons_arguments(recipe: dict, platform: str, jobs: int, folders: dict | None = None) -> list[str]:
    """SCons' arguments: the recipe's, then each dependency option with its unpacked folder."""
    return [f"-j{int(jobs)}", *recipe["arguments"], *recipe["platforms"][platform]["arguments"],
            *(f"{option}={folder}" for option, folder in sorted((folders or {}).items()))]


def build_environment(recipe: dict, platform: str, *, msys2: Path | None = None, environ=None) -> dict:
    env = {key: value for key, value in (os.environ if environ is None else environ).items()
           if key.upper() not in _SCRUBBED_ENV}
    env.update(BUILD_NAME=recipe["build_name"], SOURCE_DATE_EPOCH=str(recipe["engine"]["commit_time"]),
               PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1")
    if platform == "windows":
        if msys2 is None:
            raise TemplateError("toolchain", "name the MSYS2 installation (--msys2)")
        env["PATH"] = str(Path(msys2) / "mingw64" / "bin") + os.pathsep + env.get("PATH", "")
    return env


def pe_timestamp(data: bytes) -> int:
    offset = struct.unpack_from("<I", data, 0x3C)[0]
    if data[:2] != b"MZ" or data[offset:offset + 4] != b"PE\0\0":
        raise TemplateError("output", "not a PE executable")
    return struct.unpack_from("<I", data, offset + 8)[0]


def pe_imports(data: bytes) -> set[str]:
    """The lower-case names of the DLLs a PE executable imports (its import directory)."""
    pe_timestamp(data)  # refuses what is not a PE executable
    header = struct.unpack_from("<I", data, 0x3C)[0] + 4
    count, optional_size = struct.unpack_from("<H", data, header + 2)[0], struct.unpack_from("<H", data, header + 16)[0]
    optional = header + 20
    directories = optional + (112 if struct.unpack_from("<H", data, optional)[0] == 0x20B else 96)
    sections = [struct.unpack_from("<IIII", data, optional + optional_size + 40 * index + 8) for index in range(count)]

    def offset(rva: int) -> int:
        for virtual_size, address, raw_size, raw in sections:
            if address <= rva < address + max(virtual_size, raw_size):
                return raw + rva - address
        raise TemplateError("output", "an import outside every section")
    names, rva = set(), struct.unpack_from("<I", data, directories + 8)[0]
    position = offset(rva) if rva else None
    while position is not None and any(data[position:position + 20]):
        start = offset(struct.unpack_from("<I", data, position + 12)[0])
        names.add(data[start:data.index(b"\0", start)].decode("ascii").lower())
        position += 20
    return names


def glibc_floor(data: bytes) -> str | None:
    """The newest GLIBC_2.x symbol version an ELF names (None when it names none)."""
    minors = [int(match.group(1)) for match in _GLIBC.finditer(data)]
    return f"2.{max(minors)}" if minors else None


def inspect(path: Path, platform: str, spec: dict, *, private: list[str]) -> dict:
    """Size, SHA-256 and the reproducibility/compatibility checks of a built template."""
    data = Path(path).read_bytes()
    record = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest(), "checks": {}}
    if platform == "windows":
        record["checks"]["pe_timestamp_zero"] = pe_timestamp(data) == 0
        imports = pe_imports(data)
        # each linked library leaves its DLL imports (ANGLE: dxgi.dll; AccessKit: uiautomationcore.dll)
        record["checks"]["dependencies_linked"] = all(
            set(pin["imports"]) <= imports for pin in spec.get("dependencies", {}).values())
    else:
        floor = glibc_floor(data)
        record["glibc"] = floor
        limit = spec.get("glibc_max")
        record["checks"]["glibc_floor"] = bool(floor and limit and
                                              tuple(map(int, floor.split("."))) <= tuple(map(int, limit.split("."))))
    needles = set()
    for text in private:
        for variant in {text, text.replace("\\", "/"), text.replace("/", "\\")}:
            if len(variant) >= 6:
                needles.add(variant.encode("utf-8"))
                needles.add(variant.encode("utf-16-le"))
    record["checks"]["no_build_paths"] = not any(needle in data for needle in needles)
    return record


def _scons(tree: Path, scons: Path, arguments: list, env: dict, log: Path, platform: str, *,
           pinned_libraries: bool = True) -> float:
    """Run SCons; with pinned_libraries, a library it drops for want of its files fails the
    build. The Linux recipe pins none and leaves AccessKit to Godot's default, which a
    fresh clone drops with that warning (as its pinned template was built)."""
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = BELOW_NORMAL_PRIORITY_CLASS
    else:
        kwargs["preexec_fn"] = lambda: os.nice(10)
    start = time.monotonic()
    with log.open("w", encoding="utf-8") as output:
        result = subprocess.run([sys.executable, "-c", _SCONS_BOOT, str(scons), *arguments], cwd=tree, env=env,
                                stdout=output, stderr=subprocess.STDOUT, **kwargs)
    if result.returncode:
        raise TemplateError("scons", f"SCons exited {result.returncode}; see {log.name}")
    if pinned_libraries and _MISSING_DEPENDENCY in log.read_text(encoding="utf-8", errors="replace"):
        raise TemplateError("dependency", f"SCons dropped a switched-on library; see {log.name}")
    return round(time.monotonic() - start, 1)


def build(platform: str, *, source: str, work: Path, scons_wheel: Path, jobs: int, twice: bool,
          msys2: Path | None = None, recipe_path: Path | None = None, allow_other_toolchain: bool = False,
          dependencies: dict | None = None) -> dict:
    """Build the custom template of `platform` (twice in two fresh trees with --twice).
    dependencies: {name: archive} for every dependency the recipe pins."""
    recipe = load(recipe_path)
    spec = recipe["platforms"][platform]
    native = "windows" if os.name == "nt" else "linux"
    if platform != native:
        raise TemplateError("platform", f"build the {platform} template on {platform}")
    archives = check_dependencies(spec, dict(dependencies or {}))
    work = Path(work).resolve()
    if work.exists() and any(work.iterdir()):
        raise TemplateError("work", "the work folder must be new or empty")
    work.mkdir(parents=True, exist_ok=True)
    toolchain = check_toolchain(platform, spec, msys2=msys2)
    if toolchain["problems"] and not allow_other_toolchain:
        raise TemplateError("toolchain", "; ".join(toolchain["problems"]))
    scons = install_scons(Path(scons_wheel), work / "scons", recipe["scons"]["wheel_sha256"])
    env = build_environment(recipe, platform, msys2=msys2)
    # Neither the archives' folders nor a tree's unpacked copies may reach the binary.
    private = [str(work), str(Path.home()), *(str(path.resolve().parent) for path in archives.values())]
    runs = []
    for label in ("a", "b") if twice else ("a",):
        tree = work / label / "godot"
        commit = clone(source, tree, recipe["engine"])
        folders = {dep["option"]: unpack_dependency(archives[name], dep, work / label / "deps" / name)
                   for name, dep in spec["dependencies"].items()}
        seconds = _scons(tree, scons, scons_arguments(recipe, platform, jobs, folders), env,
                         work / label / "scons.log", platform, pinned_libraries=bool(spec["dependencies"]))
        output = tree / spec["output"]
        if not output.is_file():
            raise TemplateError("output", f"SCons left no {spec['output']}")
        record = inspect(output, platform, spec, private=private)
        kept = work / label / spec["custom"]["file"]
        shutil.copyfile(output, kept)
        runs.append({"tree": label, "commit": commit, "seconds": seconds, **record})
    pin = spec["custom"]
    identical = len({run["sha256"] for run in runs}) == 1
    placeholders = {dep["option"]: f"<{name}>" for name, dep in spec["dependencies"].items()}
    result = {"kind": KIND + "-build", "platform": platform, "recipe_sha256": recipe_sha256(recipe_path),
              "engine": recipe["engine"], "arguments": scons_arguments(recipe, platform, jobs, placeholders)[1:],
              "dependencies": {name: {key: dep[key] for key in ("version", "file", "size", "sha256")}
                               for name, dep in spec["dependencies"].items()},
              "jobs": jobs, "toolchain": toolchain, "runs": runs, "identical": identical,
              "checks_pass": all(all(run["checks"].values()) for run in runs),
              "matches_pin": all(run["sha256"] == pin["sha256"] and run["size"] == pin["size"] for run in runs)}
    result["pinnable"] = bool(twice and identical and result["checks_pass"] and not toolchain["problems"])
    (work / "build-result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def _main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    build_parser = commands.add_parser("build")
    build_parser.add_argument("--platform", choices=PLATFORMS, required=True)
    build_parser.add_argument("--source", required=True, help="a Godot clone holding the tag, or the repository URL")
    build_parser.add_argument("--work", type=Path, required=True, help="a new folder outside every repository")
    build_parser.add_argument("--scons-wheel", type=Path, required=True)
    build_parser.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    build_parser.add_argument("--twice", action="store_true")
    build_parser.add_argument("--msys2", type=Path, help="the MSYS2 installation (Windows)")
    build_parser.add_argument("--recipe", type=Path)
    build_parser.add_argument("--allow-other-toolchain", action="store_true",
                              help="experiments only: the result is never pinnable")
    build_parser.add_argument("--dependency", action="append", default=[], metavar="NAME=ARCHIVE",
                              help="a pinned dependency archive (the recipe's url), once per dependency")
    for name in ("verify", "fetch"):
        sub = commands.add_parser(name)
        sub.add_argument("--platform", choices=PLATFORMS, required=True)
        sub.add_argument("--choice", choices=CHOICES, default="custom")
        if name == "verify":
            sub.add_argument("--file", type=Path, required=True)
        else:
            sub.add_argument("--dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            dependencies = {}
            for item in args.dependency:
                name, _, archive = item.partition("=")
                if not archive or name in dependencies:
                    raise TemplateError("dependency", f"--dependency {ascii(item)}: NAME=ARCHIVE, once per name")
                dependencies[name] = Path(archive)
            result = build(args.platform, source=args.source, work=args.work, scons_wheel=args.scons_wheel,
                           jobs=args.jobs, twice=args.twice, msys2=args.msys2, recipe_path=args.recipe,
                           allow_other_toolchain=args.allow_other_toolchain, dependencies=dependencies)
            print(json.dumps({key: result[key] for key in ("platform", "identical", "checks_pass", "matches_pin",
                                                            "pinnable")}
                             | {"runs": [{key: run[key] for key in ("tree", "seconds", "size", "sha256", "checks")}
                                         for run in result["runs"]]}, indent=2))
            return 0 if result["checks_pass"] else 1
        chosen = selection(args.platform, choice=args.choice)
        if args.command == "verify":
            check_file(args.file, chosen)
        else:
            path = obtain(args.platform, directory=args.dir, choice="custom")
            print(path)
        print(json.dumps(chosen))
    except TemplateError as error:
        print(f"Refused: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(_main())
