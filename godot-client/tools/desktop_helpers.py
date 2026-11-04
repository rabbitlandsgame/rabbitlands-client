"""The updater/uninstaller helper for desktop releases: fixed project, fingerprint, reuse, export.

The helper is the small Godot program players install beside the game
(RabbitLands-updater.exe / .x86_64, with the uninstaller as the same bytes under
another name). Released bootstraps compare its SHA-256 with the signed rows and
download it again when it differs, so an unchanged helper must keep its bytes.

  project_files()  the generated helper project: the updater scripts of the
                   commit, the trust file (no commit, so asset-only releases keep
                   it), branding, project.godot, main.tscn and a FIXED minimal
                   export preset that does not depend on the game's preset
  fingerprint()    SHA-256 over every project file, the platform, the preset name,
                   the editor and export-template SHA-256s and TOOL_VERSION
  reuse()          when the previous signed release has the same fingerprint, its
                   helper rows are downloaded and accepted only if size and SHA-256
                   equal the signed row (the bytes are reused, not rebuilt)
  export()         otherwise a headless import and export of the project

Nothing here signs or uploads. The caller verifies the previous manifest's
signature (previous_release) before its rows are trusted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import desktop_r2 as r2
import release_manifest as rm

TOOL_VERSION = 1
KIND = "rabbitlands-helpers-fingerprint"
HELPER_SCRIPTS = ("release.gd", "launcher.gd", "launch_options.gd", "package_updates.gd",
                  "package_download.gd", "update_transport.gd", "bootstrap.gd", "uninstall.gd")
HELPER_BRANDING = ("rabbitlands-icon.png", "rabbitlands-icon.ico", "rabbitlands-mark-64.png")
TRUST_FIELDS = ("schema", "platform", "public_key", "repository", "distribution")
PRESET_NAMES = {"windows": "Windows Desktop", "linux": "Linux"}
BINARIES = {"windows": "RabbitLands-updater.exe", "linux": "RabbitLands-updater.x86_64"}
UNINSTALLERS = {"windows": "RabbitLands-uninstall.exe", "linux": "RabbitLands-uninstall.x86_64"}
MAX_HELPER_BYTES = rm.MAX_HELPER_BYTES
EXPORT_TIMEOUT = 300
_SCRIPT_REFERENCE = re.compile(r"""["']res://(src/[A-Za-z0-9_./-]+\.gd)["']""")

PROJECT_GODOT = (
    'config_version=5\n[application]\nconfig/name="Rabbit Lands"\n'
    'config/icon="res://assets/branding/rabbitlands-icon.png"\n'
    'boot_splash/image="res://assets/branding/rabbitlands-mark-64.png"\n'
    'boot_splash/bg_color=Color(0.035, 0.043, 0.055, 1)\nconfig/use_custom_user_dir=true\n'
    'config/custom_user_dir_name="Godot/app_userdata/Eloria"\n'
    'config/custom_user_dir_name.linuxbsd="godot/app_userdata/Eloria"\nrun/main_scene="res://main.tscn"\n'
    '[display]\nwindow/size/viewport_width=440\nwindow/size/viewport_height=100\n'
    '[rendering]\nrenderer/rendering_method="gl_compatibility"\n')
MAIN_TSCN = (
    '[gd_scene load_steps=2 format=3]\n[ext_resource type="Script" path="res://src/updates/launcher.gd" id="1"]\n'
    '[node name="Launcher" type="Node"]\nscript=ExtResource("1")\n'
    '[node name="Status" type="Label" parent="."]\ntext="Preparing game updates\u2026"\n')

# The helper's own export presets. Frozen here: a change to the game's preset
# (package_client.EXPORT_PRESETS, its filters, a new texture format) must not
# change helper bytes. The branding fields equal the game's, so the installed
# helper looks the same in Explorer. The helper embeds its pack: the installed
# templates disable path overrides, and its working directory is app/, where
# the game's own RabbitLands.pck lives.
_PRESET_HEADER = """[preset.0]

name="{name}"
platform="{name}"
runnable=true
advanced_options=false
dedicated_server=false
custom_features=""
export_filter="all_resources"
include_filter="*.json"
exclude_filter=""
export_path=""
patches=PackedStringArray()
encryption_include_filters=""
encryption_exclude_filters=""
seed=0
encrypt_pck=false
encrypt_directory=false
script_export_mode=2

[preset.0.options]

custom_template/debug=""
custom_template/release=""
"""
HELPER_PRESETS = {
    "windows": _PRESET_HEADER.format(name="Windows Desktop") + """debug/export_console_wrapper=2
binary_format/embed_pck=true
texture_format/s3tc_bptc=true
texture_format/etc2_astc=false
binary_format/architecture="x86_64"
application/modify_resources=true
application/icon="res://assets/branding/rabbitlands-icon.ico"
application/console_wrapper_icon="res://assets/branding/rabbitlands-icon.ico"
application/icon_interpolation=4
application/file_version=""
application/product_version=""
application/company_name="Rabbit Lands"
application/product_name="Rabbit Lands"
application/file_description="Rabbit Lands Client"
application/copyright=""
application/trademarks=""
application/export_angle=0
application/export_d3d12=0
application/d3d12_agility_sdk_multiarch=true
ssh_remote_deploy/enabled=false
""",
    "linux": _PRESET_HEADER.format(name="Linux").replace("runnable=true", "runnable=false")
    + """debug/export_console_wrapper=0
binary_format/embed_pck=true
texture_format/s3tc_bptc=true
texture_format/etc2_astc=false
binary_format/architecture="x86_64"
ssh_remote_deploy/enabled=false
""",
}


class HelperError(r2.DesktopR2Error):
    pass


def _digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _platform(platform: str) -> str:
    if platform not in PRESET_NAMES:
        raise HelperError("platform", ascii(platform))
    return platform


def trust_file(identity: dict) -> bytes:
    """The updater's embedded trust: the identity without commit or ancestors."""
    if not isinstance(identity, dict) or any(field not in identity for field in TRUST_FIELDS):
        raise HelperError("identity", "the identity lacks a trust field")
    if identity["repository"] != r2.REPOSITORY or identity["distribution"] != "github":
        raise HelperError("identity", "helpers serve the GitHub distribution of this repository")
    return json.dumps({field: identity[field] for field in TRUST_FIELDS}, sort_keys=True).encode("utf-8")


def folder_reader(source: Path):
    """Read helper inputs from a godot-client folder (local tools and tests)."""
    def read(relative: str) -> bytes | None:
        path = Path(source) / relative
        return path.read_bytes() if path.is_file() and not path.is_symlink() else None
    return read


def git_reader(repo: Path, commit: str):
    """Read helper inputs as committed blobs of `commit`: the bytes do not depend on a
    checkout's line-ending conversion (Windows runners default to core.autocrlf=true)."""
    if not r2.valid_commit(commit):
        raise HelperError("commit", ascii(commit))

    def read(relative: str) -> bytes | None:
        result = subprocess.run(["git", "-C", str(repo), "show", f"{commit}:godot-client/{relative}"],
                                capture_output=True)
        return result.stdout if result.returncode == 0 else None
    return read


def project_files(source: Path | None, identity: dict, platform: str, *, read=None) -> dict[str, bytes]:
    """Every file of the generated helper project, keyed by its project path.

    Inputs come from `read(relative)` (a git_reader in CI) or, by default, the
    godot-client folder `source`. Scripts outside HELPER_SCRIPTS that the
    helper references (res://src/....gd) are refused: a new dependency must be
    listed here, never silently left out of the export.
    """
    _platform(platform)
    if identity.get("platform") != platform:
        raise HelperError("identity", "the identity is for another platform")
    read = read or folder_reader(Path(source))
    files = {}
    for name in HELPER_SCRIPTS:
        data = read(f"src/updates/{name}")
        if data is None:
            raise HelperError("helper-script", f"src/updates/{name} is missing")
        files[f"src/updates/{name}"] = data
    for name in HELPER_BRANDING:
        data = read(f"assets/branding/{name}")
        if data is None:
            raise HelperError("helper-branding", f"assets/branding/{name} is missing")
        files[f"assets/branding/{name}"] = data
    files["data/client_release.json"] = trust_file(identity)
    files["project.godot"] = PROJECT_GODOT.encode("ascii")
    files["main.tscn"] = MAIN_TSCN.encode("utf-8")
    files["export_presets.cfg"] = HELPER_PRESETS[platform].encode("ascii")
    check_dependencies(files)
    return files


def check_dependencies(files: dict) -> None:
    for name, data in files.items():
        if not name.endswith((".gd", ".tscn")):
            continue
        for reference in _SCRIPT_REFERENCE.findall(data.decode("utf-8", "replace")):
            if reference not in files:
                raise HelperError("helper-dependency", f"{name} needs res://{reference}, which the helper lacks")


def fingerprint(files: dict, *, platform: str, editor_sha256: str, template_sha256: str) -> str:
    """The helpers_fingerprint: equal inputs give an equal helper, so its bytes are reused."""
    _platform(platform)
    for value in (editor_sha256, template_sha256):
        if type(value) is not str or not re.fullmatch("[0-9a-f]{64}", value):
            raise HelperError("tool-hash", "editor and template SHA-256s are required")
    record = {"kind": KIND, "tool_version": TOOL_VERSION, "platform": platform, "preset": PRESET_NAMES[platform],
              "editor_sha256": editor_sha256, "template_sha256": template_sha256,
              "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}}
    return hashlib.sha256(r2.canonical_bytes(record)).hexdigest()


def write_project(files: dict, project: Path) -> Path:
    project = Path(project)
    if project.exists() and any(project.iterdir()):
        raise HelperError("helper-project", "the helper project folder must be new or empty")
    for name, data in files.items():
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return project


def _place(binary: Path, out: Path, platform: str) -> dict:
    """Put the updater and its uninstaller name (the same bytes) in `out`; return the rows."""
    out.mkdir(parents=True, exist_ok=True)
    updater, uninstaller = out / BINARIES[platform], out / UNINSTALLERS[platform]
    for path in (updater, uninstaller):
        if path.exists() or path.is_symlink():
            raise HelperError("helper-exists", path.name)
    shutil.copyfile(binary, updater)
    os.link(updater, uninstaller)
    if platform == "linux":
        updater.chmod(0o755)
    size, digest = updater.stat().st_size, _digest(updater)
    if not 0 < size <= MAX_HELPER_BYTES:
        raise HelperError("helper-size", str(size))
    return {kind: {"url": rm.helper_url(digest, kind, platform), "size": size, "sha256": digest}
            for kind in rm.HELPER_KINDS}


def export(files: dict, *, platform: str, godot: Path, run_godot, work: Path, out: Path) -> dict:
    """Import and export the helper project headless; return the signed-row shapes."""
    project = write_project(files, Path(work) / "helper-project")
    logs = Path(work) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    binary = Path(work) / "export" / BINARIES[platform]
    binary.parent.mkdir(parents=True, exist_ok=True)
    run_godot(godot, ["--headless", "--path", str(project), "--import"], logs / "helper-import.log",
              timeout=EXPORT_TIMEOUT)
    run_godot(godot, ["--headless", "--path", str(project), "--export-release", PRESET_NAMES[platform],
                      str(binary)], logs / "helper-export.log", timeout=EXPORT_TIMEOUT)
    if not binary.is_file():
        raise HelperError("helper-export", "the helper export is incomplete")
    return _place(binary, Path(out), platform)


def previous_release(http, platform: str, public_pem: bytes) -> dict | None:
    """The newest published signed manifest: the live R2 pointer first, else the
    GitHub `latest` alias. Signature-verified against `public_pem`; None when
    neither verifies (the helper is then exported)."""
    import desktop_content
    try:
        return desktop_content.live_release(http, platform, public_pem).manifest
    except r2.DesktopR2Error:
        pass
    url = f"{desktop_content.GITHUB_LATEST}RabbitLands-{platform}.json"
    try:
        response = http.request("GET", url, limit=r2.CLIENT_MANIFEST_LIMIT)
        if response.status != 200:
            return None
        _, release = rm.verify(response.body, public_pem)
    except r2.DesktopR2Error:
        return None
    return release if release.get("platform") == platform and release.get("repository") == r2.REPOSITORY else None


def reuse(previous: dict | None, expected_fingerprint: str, *, platform: str, http, out: Path) -> dict | None:
    """The previous signed release's helper rows and bytes when its fingerprint is
    equal; None when it differs or is absent. Downloads are refused unless their
    size and SHA-256 equal the signed rows."""
    _platform(platform)
    if not isinstance(previous, dict) or previous.get("helpers_fingerprint") != expected_fingerprint \
            or previous.get("platform") != platform:
        return None
    rows = {}
    for kind in rm.HELPER_KINDS:
        problem = rm.helper_row_problem(previous.get(kind), kind, platform)
        if problem:
            raise HelperError(problem, f"the previous release's {kind} row is not a legacy pool row")
        rows[kind] = dict(previous[kind])
    if rows["updater"]["sha256"] != rows["uninstall"]["sha256"]:
        return None  # not this tool's shape (one binary, two names): export instead
    row = rows["updater"]
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    download = out / (".download-" + row["sha256"])
    response = http.request("GET", row["url"], limit=row["size"], keep_body=True)
    if response.status != 200 or response.length != row["size"] or response.sha256 != row["sha256"] \
            or hashlib.sha256(response.body).hexdigest() != row["sha256"]:
        raise HelperError("helper-hash", f"the reused {platform} helper does not match its signed row")
    download.write_bytes(response.body)
    try:
        placed = _place(download, out, platform)
    finally:
        download.unlink(missing_ok=True)
    if placed != rows:
        raise HelperError("helper-hash", "the reused helper changed after its download")
    return rows


class HelperResult:
    def __init__(self, fingerprint: str, rows: dict, reused: bool, paths: list[Path]):
        self.fingerprint, self.rows, self.reused, self.paths = fingerprint, rows, reused, paths

    def record(self) -> dict:
        return {"helpers_fingerprint": self.fingerprint, "reused": self.reused, **self.rows}


def provide(source: Path | None, identity: dict, *, platform: str, godot: Path, template: Path, run_godot,
            work: Path, out: Path, previous: dict | None, http=None, read=None) -> HelperResult:
    """Reuse the previous helper when its fingerprint is equal, else export it."""
    files = project_files(source, identity, platform, read=read)
    value = fingerprint(files, platform=platform, editor_sha256=_digest(Path(godot)),
                        template_sha256=_digest(Path(template)))
    rows = reuse(previous, value, platform=platform, http=http, out=out) if previous and http else None
    reused = rows is not None
    if not reused:
        rows = export(files, platform=platform, godot=Path(godot), run_godot=run_godot, work=work, out=out)
    paths = [Path(out) / BINARIES[platform], Path(out) / UNINSTALLERS[platform]]
    return HelperResult(value, rows, reused, paths)


def _main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("fingerprint",))
    parser.add_argument("--source", type=Path, required=True, help="the commit's godot-client folder")
    parser.add_argument("--identity", type=Path, required=True, help="the release identity JSON")
    parser.add_argument("--platform", choices=tuple(PRESET_NAMES), required=True)
    parser.add_argument("--godot", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        identity = json.loads(args.identity.read_text(encoding="utf-8"))
        files = project_files(args.source, identity, args.platform)
        print(fingerprint(files, platform=args.platform, editor_sha256=_digest(args.godot),
                          template_sha256=_digest(args.template)))
    except (OSError, ValueError) as error:
        print(f"Refused: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(_main())
