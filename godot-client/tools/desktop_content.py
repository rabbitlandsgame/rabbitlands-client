"""Pack a qualified local stage into a desktop content set and an R2 upload plan,
and measure installed-file drift against a release.

Modes:
  pack     a hard-link view of a package_client stage without the CI-owned
           paths and the stage-root files -> asset_packages.build -> the split
           PCK layout read with pck_split.py (read_pck_layout: the core pack's
           content pack list equals the built app/packs/ rows) -> derived R2
           part URLs -> desktop_r2.validate_set (with a native-code sniff of
           every file) -> canonical set bytes and upload-plan.json, the input of
           `upload_desktop_assets.py content`
  compare  installed-file SHA-256 drift of a stage or an install root against a
           signed release manifest or a content set

The content set is public. It carries no timestamps, absolute paths or user
names, and a rerun on the same inputs is byte-identical. Package ids, the
ZIP layout, part sizes and codecs come from asset_packages.py, which must equal
its copy at the packaged commit; this tool never re-implements them. Part URLs
are rewritten to the derived R2 form, a pure function of each part's SHA-256.

Trust: the set is unsigned. CI checks it against the dispatched commit, the
owner attests it when approving signing, and players accept only bytes that
match the signed manifest built from it. Reuse decisions read an S3 HEAD (or,
without credentials, an anonymous HEAD): bookkeeping, never integrity. The
uploader HEADs every reused row again and CI GET-verifies every part that the
published manifest does not already name. The previous set is reached only
through a signed manifest (the live pointer, or a manifest file for the first
R2 release) whose `content.set` hash it must match.

Provenance (informational in the set, but refused when wrong): the tools
checkout must be clean, on an origin branch and contain the packaged commit,
with packaging modules equal to the commit's; the stage must carry a release
identity and a finished package_client qualification. The set records the
tools commit, the dirty flag and a digest of the build tree's ignored import
cache. `--dev` admits a dirty or unpublished tools tree, a test identity or an
unqualified stage for local proofs, records that, and writes no upload plan.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import struct
import subprocess
import sys
import time

import desktop_r2 as r2
import pck_split
import upload_desktop_assets as up

TOOLS = Path(__file__).resolve().parent
TOOLS_REPO = TOOLS.parents[1]
PEM_PATH = "godot-client/data/update_public.pem"
# The modules that define package ids, the ZIP layout, part size and part
# names, and the split PCK layout (pck_split) the pack checks the stage with.
# Their copies at the tools commit must equal those at the packaged commit, so
# the set has the formats that commit's updater and game read.
PACKAGING_MODULES = ("asset_packages", "client_release", "pck_split", "release_storage", "shared_release_assets")
STAGE_MARKER = ".eloria-package"            # package_client.MARKER
STAGE_ROOTS = ("app", "eloria-assets")      # what asset_packages.build walks
DESCRIPTOR = "app/client-release.json"
DESCRIPTOR_COPY = "app/data/client_release.json"
ENGINE_BINARIES = {"windows": "app/RabbitLands.exe", "linux": "app/RabbitLands.x86_64"}
PROOF_NAME = "optimization-proof.json"
PROOF_STATUS = "verified_before_signing"
SMOKE_LOGS = (("smoke.log", "legacy"), ("smoke-human-testing.log", "human-testing"))

OUT_MARKER = ".desktop-content.json"
OUT_KIND = "rabbitlands-desktop-content-out"
RECEIPT_KIND = "rabbitlands-desktop-pack-receipt"
COMPARE_KIND = "rabbitlands-desktop-content-compare"
SET_NAME = "set.json"
PLAN_NAME = "upload-plan.json"
RECEIPT_NAME = "pack-receipt.json"
PARTS_DIR = "parts"
VIEW_MARKER = ".desktop-content-view"
MAX_WORKERS = 4
MAX_DESCRIPTOR_BYTES = 16 * 1024 * 1024     # ancestors: up to 100,000 commits
MAX_SMALL_BYTES = 1024 * 1024
FREE_RESERVE_BYTES = 1024 ** 3
GITHUB_LATEST = f"https://github.com/{r2.REPOSITORY}/releases/latest/download/"

_VERSION = re.compile(r"RabbitLands-(Windows|Linux)-([0-9]{8})-([0-9a-f]{9})")
_ORIGIN_URL = re.compile(r"(?:.*[/:])?rabbitlandsgame/rabbitlands-client(?:\.git)?/?")
_VIEW_NAME = re.compile(r"\.v[0-9a-f]{8}")
_TEMP_PART = re.compile(r"\.v[0-9a-f]{8}\.pkg\..+\.zip\.[0-9]{3}")


class ContentError(r2.DesktopR2Error):
    pass


def _emit(message, *, error: bool = False) -> None:
    up.emit(message, error=error)


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_file(path: Path, limit: int, code: str) -> bytes:
    data = None
    try:
        if not path.is_symlink() and path.is_file() and path.stat().st_size <= limit:
            data = path.read_bytes()
    except OSError:
        data = None
    if data is None or len(data) > limit:
        raise ContentError(code, path.name)
    return data


def _digest(path: Path) -> str:
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _json_bytes(value) -> bytes:
    """Private files (plan, receipt, report): stable, readable and ASCII."""
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("ascii")


def _write_if_changed(path: Path, data: bytes) -> bool:
    try:
        if path.is_file() and not path.is_symlink() and path.read_bytes() == data:
            return False
    except OSError:
        pass
    up.write_private(path, data)
    return True


def _is_link(path: Path) -> bool:
    """A symlink, or a Windows junction (os.path.isjunction exists from Python 3.12)."""
    return path.is_symlink() or getattr(os.path, "isjunction", lambda _: False)(path)


# --- Git and provenance ----------------------------------------------------------

def _git_environment() -> dict:
    return {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


def _git(repo: Path, *args, check: bool = True) -> subprocess.CompletedProcess:
    result = None
    try:
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, env=_git_environment(),
                                timeout=900)
    except (OSError, subprocess.SubprocessError):
        result = None
    if result is None:
        raise ContentError("git", "git could not run")
    if check and result.returncode != 0:
        raise ContentError("git", f"git {args[0]} failed in {repo.name}")
    return result


@dataclass(frozen=True)
class Tools:
    commit: str
    dirty: bool
    on_origin: bool
    public_pem: bytes
    problems: tuple = ()


def tools_provenance(repo: Path, commit: str, *, dev: bool = False,
                     modules: tuple = PACKAGING_MODULES) -> Tools:
    """The tools checkout: clean, on an origin branch, containing `commit`,
    with packaging modules equal to `commit`'s. The release key is read from
    `commit` itself (CI checks the set against the same file)."""
    repo = Path(repo)
    if not r2.valid_commit(commit):
        raise ContentError("commit", ascii(commit)[:60])
    head = _git(repo, "rev-parse", "--verify", "HEAD^{commit}").stdout.decode("ascii", "replace").strip()
    if not r2.valid_commit(head):
        raise ContentError("tools-commit", "the tools checkout has no commit")
    if _git(repo, "cat-file", "-e", f"{commit}^{{commit}}", check=False).returncode != 0:
        raise ContentError("tools-missing-commit", "the tools checkout does not have the packaged commit; fetch it")
    problems = []
    if _git(repo, "status", "--porcelain=v1", "--untracked-files=all").stdout.strip():
        problems.append("tools-dirty")
    url = _git(repo, "remote", "get-url", "origin", check=False)
    origin = url.returncode == 0 and _ORIGIN_URL.fullmatch(url.stdout.decode("utf-8", "replace").strip())
    refs = _git(repo, "for-each-ref", f"--contains={head}", "--format=%(refname)", "refs/remotes/origin/").stdout
    on_origin = bool(origin) and bool(refs.split())
    if not on_origin:
        problems.append("tools-not-on-origin")
    if _git(repo, "merge-base", "--is-ancestor", commit, head, check=False).returncode != 0:
        problems.append("tools-lack-commit")
    else:
        paths = [f"godot-client/tools/{name}.py" for name in modules]
        drift = _git(repo, "diff", "--quiet", commit, head, "--", *paths, check=False).returncode
        if drift == 1:
            problems.append("tools-packaging-drift")
        elif drift != 0:
            raise ContentError("git", "git diff failed")
    if problems and not dev:
        raise ContentError(problems[0], {
            "tools-dirty": "commit or remove every change in the tools checkout first",
            "tools-not-on-origin": "run from a checkout whose commit is on an origin branch of the client repository",
            "tools-lack-commit": "the tools commit must contain the packaged commit",
            "tools-packaging-drift": "/".join(modules) + " differ from the packaged commit; run from a "
                                     "checkout at that commit",
        }[problems[0]])
    pem = _git(repo, "show", f"{commit}:{PEM_PATH}").stdout
    r2.public_key_sha256(pem)
    return Tools(head, "tools-dirty" in problems, on_origin, pem, tuple(problems))


def check_module_locations() -> None:
    """The packaging modules this process imported are this checkout's files."""
    import asset_packages
    import client_release
    import release_storage
    import shared_release_assets
    for module in (asset_packages, client_release, pck_split, release_storage, shared_release_assets, r2, up):
        if Path(module.__file__).resolve().parent != TOOLS:
            raise ContentError("tools-module", f"{module.__name__} was not imported from this checkout")


# --- Stage identity and qualification ----------------------------------------------

@dataclass(frozen=True)
class Stage:
    path: Path
    platform: str
    commit: str
    version: str
    release_build: bool
    marker_mtime_ns: int


def stage_commit(path) -> str:
    """The commit package_client wrote into the stage marker."""
    stage = Path(path)
    if _is_link(stage) or not stage.is_dir():
        raise ContentError("stage", "the stage is not a directory")
    text = _read_file(stage / STAGE_MARKER, 128, "stage-marker").decode("ascii", "replace")
    # package_client writes `sha + "\n"` in text mode: CRLF on Windows.
    commit = text[:-2] if text.endswith("\r\n") else text[:-1] if text.endswith("\n") else ""
    if not r2.valid_commit(commit):
        raise ContentError("stage-marker", "the stage marker does not hold one commit")
    return commit


def _normal_pem(value) -> str:
    return value.replace("\r\n", "\n").strip() if type(value) is str else ""


def read_stage(path, platform: str, *, public_pem: bytes, dev: bool = False) -> tuple[Stage, list]:
    """Check the stage's name, marker and release descriptor (identity)."""
    stage = Path(path)
    commit = stage_commit(stage)
    stage = stage.resolve()
    match = _VERSION.fullmatch(stage.name)
    if not match or match[1].lower() != platform or match[3] != commit[:9]:
        raise ContentError("stage-name", f"expected RabbitLands-{platform.title()}-<date>-{commit[:9]}")
    data = _read_file(stage / DESCRIPTOR, MAX_DESCRIPTOR_BYTES, "stage-descriptor")
    descriptor = up.strict_json(data)
    if not isinstance(descriptor, dict) or type(descriptor.get("schema")) is not int or descriptor["schema"] != 1:
        raise ContentError("stage-descriptor", "app/client-release.json is not a release identity")
    for name, expected in (("commit", commit), ("platform", platform), ("repository", r2.REPOSITORY)):
        if descriptor.get(name) != expected:
            raise ContentError("stage-identity", f"app/client-release.json {name} differs from the stage")
    if _normal_pem(descriptor.get("public_key")) != _normal_pem(public_pem.decode("ascii", "replace")):
        raise ContentError("stage-public-key", "the stage pins another key than the commit's update_public.pem")
    copy = stage / DESCRIPTOR_COPY
    if copy.exists() and _read_file(copy, MAX_DESCRIPTOR_BYTES, "stage-descriptor") != data:
        raise ContentError("stage-descriptor", "app/data/client_release.json differs from app/client-release.json")
    problems = []
    if descriptor.get("distribution") != "github":
        problems.append("stage-distribution")
    if descriptor.get("release_build") is not True:
        problems.append("stage-not-release-build")
    if problems and not dev:
        raise ContentError(problems[0], "build the stage with --distribution github --release-build")
    marker = (stage / STAGE_MARKER).stat().st_mtime_ns
    return Stage(stage, platform, commit, stage.name, descriptor.get("release_build") is True, marker), problems


def default_logs(stage: Stage) -> Path:
    """package_client's log folder: <out>/.build/logs/<platform>-<date>-<sha9>."""
    return stage.path.parent / ".build" / "logs" / f"{stage.platform}-{stage.version.split('-', 2)[2]}"


def read_qualification(stage: Stage, logs=None, *, dev: bool = False) -> tuple[dict, list]:
    """A finished full-optimization qualification of this stage's build run.

    The proof is written only after every qualification step passed, so it
    must name this commit and platform and be newer than the stage marker,
    which package_client rewrites at the start of every run.
    """
    folder = Path(logs) if logs else default_logs(stage)
    problems, proof_sha256 = [], None
    proof_path = folder / PROOF_NAME
    try:
        data = _read_file(proof_path, MAX_SMALL_BYTES, "qualification-proof")
        newer = proof_path.stat().st_mtime_ns >= stage.marker_mtime_ns
    except (ContentError, OSError):
        data, newer = None, False
    proof = up.strict_json(data) if data is not None else None
    if not isinstance(proof, dict):
        problems.append("qualification-proof")
    elif (proof.get("commit") != stage.commit or proof.get("platform") != stage.platform
          or proof.get("status") != PROOF_STATUS):
        problems.append("qualification-proof-identity")
    elif not newer:
        problems.append("qualification-proof-stale")
    else:
        proof_sha256 = r2.sha256_hex(data)
    smoke = []
    for name, profile in SMOKE_LOGS:
        log = folder / name
        try:
            if log.is_file() and log.stat().st_mtime_ns >= stage.marker_mtime_ns:
                smoke.append(profile)
        except OSError:
            pass
    if len(smoke) != len(SMOKE_LOGS):
        problems.append("qualification-smoke")
    if problems and not dev:
        raise ContentError(problems[0], "the stage has no finished package_client --full-optimizations "
                                        "qualification for this run (pass --logs if the logs moved)")
    # split_pck: what the core pack declares (read_pck_layout, set by pack()), never a folder listing.
    return {"optimization_proof_sha256": proof_sha256, "smoke": smoke, "split_pck": False}, problems


# --- The split PCK layout (W2-UD-06, tools/pck_split.py) ---------------------------------
#
# A split release ships app/RabbitLands.pck as a core pack whose
# data/content_packs.json (pck_split.MANIFEST) lists the content packs
# app/packs/<name>.pck with their bytes, entry count and SHA-256; the game's
# ContentPacks checks only existence and size, the updater hashes every file.
# pck_split.py is the one reader of the format, for this local pack and for CI's
# content checks (desktop_release_ci.py): the declared packs must be exactly
# the set's app/packs/ files with their signed size and SHA-256, and a content
# pack may hold only entries pck_split's rules move into that very pack, none
# of the core's (so no script, identity or extension list can override the
# core's when the pack mounts).

CORE_PCK = "app/RabbitLands.pck"
PACKS_PREFIX = "app/" + pck_split.PACKS_DIRECTORY + "/"
MAX_PCK_ENTRY_BYTES = 16 * 1024 * 1024
_PACK_FILE = re.compile(re.escape(pck_split.PACKS_DIRECTORY) + r"/([a-z0-9][a-z0-9-]*)\.pck")


def read_pck(path: Path) -> pck_split.Pack:
    """The directory of a Godot 4 PCK, read by pck_split.read_pack (format 3 or 4,
    relative file base, unencrypted)."""
    try:
        return pck_split.read_pack(Path(path))
    except OSError as error:
        # An OSError's text quotes the full path (escaped on Windows): name the file only.
        raise ContentError("pck", f"{Path(path).name}: {error.strerror or type(error).__name__}") from None
    except (pck_split.SplitError, ValueError, struct.error) as error:
        raise ContentError("pck", str(error).replace(str(path), Path(path).name)[:200]) from None


def pck_entry(pack: pck_split.Pack, name: str, limit: int = MAX_PCK_ENTRY_BYTES) -> bytes | None:
    """One small entry of `pack`, or None when it has none of that name."""
    entry = pack.entries.get(name)
    if entry is None:
        return None
    if entry.size > limit:
        raise ContentError("pck-entry", f"{name} is larger than {limit} bytes")
    try:
        return pack.read(name)
    except (pck_split.SplitError, OSError) as error:
        raise ContentError("pck-entry", f"{name}: {type(error).__name__}") from None


def pack_layout_rows(core: pck_split.Pack) -> list | None:
    """The content packs the core declares, or None for a single (monolithic) PCK."""
    data = pck_entry(core, pck_split.MANIFEST)
    if data is None:
        return None
    value = up.strict_json(data[:-1] if data.endswith(b"\n") else data)
    if (not isinstance(value, dict) or set(value) != {"schema", "packs"}
            or type(value["schema"]) is not int or value["schema"] != pck_split.MANIFEST_SCHEMA
            or type(value["packs"]) is not list):
        raise ContentError("pck-layout", f"{pck_split.MANIFEST} is not a schema-{pck_split.MANIFEST_SCHEMA} "
                                         "content pack list")
    rows, seen = [], set()
    for row in value["packs"]:
        if (not isinstance(row, dict) or set(row) != {"file", "bytes", "entries", "sha256", "feature"}
                or type(row["file"]) is not str or not _PACK_FILE.fullmatch(row["file"]) or row["file"] in seen
                or type(row["bytes"]) is not int or row["bytes"] <= 0
                or type(row["entries"]) is not int or row["entries"] <= 0
                or not r2._is_hash(row["sha256"]) or type(row["feature"]) is not str):
            raise ContentError("pck-layout", f"{pck_split.MANIFEST} has a malformed or repeated pack row")
        seen.add(row["file"])
        rows.append(dict(row))
    return rows


def check_split_layout(rows: list | None, files: dict) -> dict:
    """The declared packs against the release's file rows (`files`: path -> {size,
    sha256}): exactly the app/packs/ files, each with the declared bytes and SHA-256.
    A single PCK has no app/packs/ file at all."""
    present = sorted(path for path in files if path.startswith(PACKS_PREFIX))
    if rows is None:
        if present:
            raise ContentError("pck-layout", f"{present[0]} ships beside a core pack that lists no content packs")
        return {"split": False, "packs": 0, "bytes": 0, "features": []}
    listed = {"app/" + row["file"]: row for row in rows}
    missing = sorted(set(listed) - set(present))
    if missing:
        raise ContentError("pck-layout", f"{missing[0]} is declared by the core pack but not shipped")
    extra = sorted(set(present) - set(listed))
    if extra:
        raise ContentError("pck-layout", f"{extra[0]} is shipped but the core pack does not declare it")
    for path, row in sorted(listed.items()):
        entry = files[path]
        if entry.get("size") != row["bytes"] or entry.get("sha256") != row["sha256"]:
            raise ContentError("pck-layout", f"{path} differs from the size and SHA-256 the core pack declares")
    return {"split": True, "packs": len(rows), "bytes": sum(row["bytes"] for row in rows),
            "features": sorted({row["feature"] for row in rows if row["feature"]})}


def check_content_pack(path: Path, row: dict, core: pck_split.Pack) -> dict:
    """One content pack's directory: the core's format and engine version, the
    declared entry count, and only entries pck_split's rules put in this pack
    (pck_split.classify), none of which the core holds too."""
    name = _PACK_FILE.fullmatch(row["file"])[1]
    pack = read_pck(path)
    if (pack.format, pack.version) != (core.format, core.version):
        raise ContentError("pck-content-pack", f"{row['file']} has another PCK format or engine version than the "
                                               "core pack")
    if len(pack.entries) != row["entries"]:
        raise ContentError("pck-content-pack", f"{row['file']} holds {len(pack.entries)} entries, the core pack "
                                               f"declares {row['entries']}")
    for entry in sorted(pack.entries):
        target = pck_split.classify(entry)
        if target != (name, row["feature"]):
            raise ContentError("pck-content-pack", f"{row['file']} holds {entry}, which belongs "
                                                   f"{'in the core pack' if target is None else 'in ' + target[0]}")
        if entry in core.entries:
            raise ContentError("pck-content-pack", f"{row['file']} holds {entry}, which the core pack holds too")
    return {"file": row["file"], "entries": len(pack.entries)}


def read_pck_layout(stage_path: Path, files: dict) -> dict:
    """The split layout of a local stage: the core pack's declaration against the
    built file rows, and the directory of every content pack."""
    core = read_pck(Path(stage_path) / CORE_PCK)
    rows = pack_layout_rows(core)
    layout = check_split_layout(rows, files)
    for row in rows or []:
        check_content_pack(Path(stage_path) / "app" / row["file"], row, core)
    return layout


def import_cache(build_dir, commit: str, *, dev: bool = False) -> tuple[dict, list]:
    """A digest of the build tree's ignored files (the reused import cache):
    sorted `path NUL size NUL mtime_ns` lines. Paths stay inside the digest."""
    build = Path(build_dir).resolve()
    head = _git(build, "rev-parse", "--verify", "HEAD^{commit}").stdout.decode("ascii", "replace").strip()
    problems = [] if head == commit else ["build-dir-commit"]
    if problems and not dev:
        raise ContentError("build-dir-commit", "the build tree is not at the packaged commit")
    listing = _git(build, "ls-files", "-z", "--others", "--ignored", "--exclude-standard").stdout
    hasher, count = hashlib.sha256(), 0
    for relative in sorted(item for item in listing.split(b"\0") if item):
        try:
            info = os.lstat(build / os.fsdecode(relative))
        except OSError:
            raise ContentError("import-cache-changing", "the import cache changed while it was read") from None
        hasher.update(relative + b"\0" + f"{info.st_size}\0{info.st_mtime_ns}\n".encode("ascii"))
        count += 1
    return {"digest": hasher.hexdigest(), "files": count}, problems


# --- Hard-link view ----------------------------------------------------------------

def make_view(stage: Path, view: Path) -> dict:
    """Hard links to the stage's content files: app/ and eloria-assets/ without
    the CI-owned paths (in any spelling). Root files are never linked. No copy
    fallback: a view on another volume is refused, not silently duplicated."""
    import release_storage
    stage = Path(stage)
    view.mkdir(exist_ok=False)
    (view / VIEW_MARKER).write_bytes(b"")
    size = 0
    linked, ci_files = [], []
    for root in STAGE_ROOTS:
        base = stage / root
        if _is_link(base):
            raise ContentError("stage-link", root)
        if not base.exists():
            continue
        for directory, names, files in os.walk(base):
            folder = Path(directory)
            for name in names:
                if _is_link(folder / name):
                    raise ContentError("stage-link", (folder / name).relative_to(stage).as_posix())
            names.sort()
            for name in sorted(files):
                source = folder / name
                relative = source.relative_to(stage).as_posix()
                if _is_link(source) or not source.is_file():
                    raise ContentError("stage-link", relative)
                if r2.is_ci_path(relative):
                    ci_files.append(relative)
                    continue
                try:
                    size += release_storage.link_file(source, view / relative)
                except (OSError, ValueError):
                    raise ContentError("view-link", "hard links need a new output folder on the stage's volume "
                                                    "(no copy fallback)") from None
                linked.append(relative)
    return {"files": len(linked), "bytes": size, "ci_files": sorted(ci_files), "paths": sorted(linked)}


def remove_view(view: Path) -> bool:
    """Unlink the view's links and folders (never the stage's files: a hard
    link's removal leaves the other name). Attributes are never changed.

    A view holds only hard links and real folders. One that holds a symlink
    or junction (a stale view someone changed) is left alone: os.walk
    descends into junctions, and unlinking there would delete files outside
    the view.
    """
    if _is_link(view) or not (view / VIEW_MARKER).is_file():
        return False
    folders, files = [], []
    try:
        for directory, names, entries in os.walk(view):
            folder = Path(directory)
            if any(_is_link(folder / name) for name in (*names, *entries)):
                return False
            folders.append(folder)
            files.extend(folder / name for name in entries)
        for path in files:
            os.unlink(path)
        for folder in reversed(folders):  # top-down order, so children come first when reversed
            os.rmdir(folder)
    except OSError:
        return False
    return True


def clean_stale(parts: Path) -> int:
    """Leftovers of an interrupted run of this tool only: temporary part files
    and marked views."""
    removed = 0
    for entry in sorted(parts.iterdir()):
        if entry.is_file() and not entry.is_symlink() and _TEMP_PART.fullmatch(entry.name):
            entry.unlink()
            removed += 1
        elif entry.is_dir() and not _is_link(entry) and _VIEW_NAME.fullmatch(entry.name):
            if not remove_view(entry):
                _emit(f"Warning: could not remove the old view {entry.name}; delete it by hand", error=True)
            removed += 1
    return removed


def local_rows(view: Path, ids) -> dict:
    """asset_packages.build's file rows for the given package ids (same walk,
    order and row form), used only to choose between reuse candidates."""
    import asset_packages
    import client_release
    rows = {}
    for root in STAGE_ROOTS:
        for path in sorted((view / root).rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(view).as_posix()
            name = asset_packages.package_id(relative)
            if name in ids:
                rows.setdefault(name, []).append({"path": relative, "size": path.stat().st_size,
                                                  "sha256": client_release.digest(path)})
    return rows


# --- Previous release, cross-platform set, probes -------------------------------------

def _package_rows(document) -> list:
    rows = []
    for group in ("packages", "optional_packages"):
        packages = document.get(group) or []
        if type(packages) is not list:
            raise ContentError("rows", group)
        for package in packages:
            if not isinstance(package, dict) or type(package.get("id")) is not str:
                raise ContentError("rows", group)
            rows.append(package)
    return rows


def _check_rows(rows: list) -> list:
    """The structure probing and candidate choice rely on (signed rows of a ci release)."""
    for row in rows:
        files, parts = row.get("files"), row.get("parts")
        if (type(files) is not list or not files or type(parts) is not list or not parts
                or any(not isinstance(entry, dict) or type(entry.get("path")) is not str for entry in files)
                or any(not isinstance(part, dict) or not r2._is_hash(part.get("sha256"))
                       or not r2._is_int(part.get("size"), 1, r2.MAX_PART_BYTES) for part in parts)):
            raise ContentError("previous-rows", row["id"])
        r2.canonical_bytes(files)
    return rows


def _projection(row) -> dict | None:
    """What binds a package's bytes (part URLs excepted: they are derived)."""
    if not isinstance(row, dict):
        return None
    keep = {name: row.get(name) for name in ("id", "sha256", "size", "unpacked_size", "file_count", "files",
                                             "codec", "feature")}
    keep["parts"] = [(part.get("sha256"), part.get("size")) for part in row.get("parts") or []
                     if isinstance(part, dict)]
    return keep


def _get(http, url: str, limit: int, code: str) -> bytes:
    response = http.request("GET", url, limit=limit)
    if response.status == 404:
        raise ContentError(f"{code}-missing", f"HTTP 404 for {url}")
    if response.status != 200:
        raise ContentError(code, f"HTTP {response.status} for {url}")
    return response.body


def live_release(http, platform: str, public_pem: bytes) -> up.CheckedRelease:
    """The live signed pointer and the manifest it names, both verified."""
    pointer_bytes = _get(http, r2.pointer_url(platform), r2.MAX_POINTER_BYTES, "live-pointer")
    _, peek = up.verify_envelope(pointer_bytes, public_pem, limit=r2.MAX_POINTER_BYTES)
    r2.validate_pointer(peek, platform=platform)
    target = peek["target"]["manifest"]

    def manifest_for(_platform, _version):
        return _get(http, target["url"], target["size"], "live-manifest")
    return up.check_release_pair(pointer_bytes, manifest_for, platform=platform, public_pem=public_pem,
                                 rollback=peek["rollback"] is True)


def manifest_from_bytes(data: bytes, platform: str, public_pem: bytes) -> dict:
    """A signed schema-3 release manifest of this repository and platform."""
    _, manifest = up.verify_envelope(data, public_pem, limit=r2.MAX_ENVELOPE_BYTES)
    if (type(manifest.get("schema")) is not int or manifest["schema"] != 3 or manifest.get("bootstrap_schema") != 1
            or manifest.get("repository") != r2.REPOSITORY or manifest.get("platform") != platform
            or not r2.valid_commit(manifest.get("commit"))):
        raise ContentError("previous-manifest", "not a schema-3 release manifest of this platform")
    r2.validate_manifest_additions(manifest, platform=platform)
    return manifest


def previous_rows(previous, *, platform: str, public_pem: bytes, http=None, set_file=None) -> tuple[list, dict]:
    """Package rows of the previous release's content set, reached only through
    its signed manifest: `none`, `live` (pointer -> manifest -> set on R2) or a
    signed manifest file (the first R2 release names T's)."""
    if previous == "none":
        if set_file is not None:
            raise ContentError("previous-set-file", "--previous-set-file needs --previous")
        return [], {"source": "none"}
    if previous == "live":
        if http is None:
            raise ContentError("previous-live", "no HTTPS client")
        release = live_release(http, platform, public_pem)
        manifest, manifest_bytes = release.manifest, release.manifest_bytes
        info = {"source": "live", "pointer_sequence": release.sequence}
    else:
        manifest_bytes = _read_file(Path(previous), r2.MAX_ENVELOPE_BYTES, "previous-manifest")
        manifest = manifest_from_bytes(manifest_bytes, platform, public_pem)
        info = {"source": "manifest-file"}
    content = manifest["content"]
    info.update(commit=manifest["commit"], version=manifest.get("version"), manifest_sha256=r2.sha256_hex(
        manifest_bytes), content_source=content["source"], set_sha256=content["set"]["sha256"])
    signed = {}
    for row in _package_rows(manifest):
        if row["id"] not in r2.CI_PACKAGE_IDS:
            if row["id"] in signed:
                raise ContentError("previous-manifest", f"package {row['id']} twice")
            signed[row["id"]] = row
    if set_file is not None:
        data = _read_file(Path(set_file), r2.MAX_SET_BYTES, "previous-set-file")
    elif content["source"] == "r2":
        if http is None:
            raise ContentError("previous-set", "pass --previous-set-file or allow the anonymous set download")
        data = _get(http, content["set"]["url"], r2.MAX_SET_BYTES, "previous-set")
    else:
        # A `ci` release keeps its set as a CI artifact; its signed rows are the same rows.
        info["rows"] = "signed-manifest"
        return _check_rows(list(signed.values())), info
    if r2.sha256_hex(data) != content["set"]["sha256"]:
        raise ContentError("previous-set-sha256", "the set bytes differ from the signed manifest's content.set")
    previous_set = r2.parse_set_bytes(data)
    r2.validate_set(previous_set, public_key_sha256=r2.public_key_sha256(public_pem), commit=manifest["commit"],
                    platform=platform, source=content["source"], reader_cap=r2.READER_CAP_W1A)
    rows = _package_rows(previous_set)
    if {row["id"] for row in rows} != set(signed) or any(
            _projection(row) != _projection(signed[row["id"]]) for row in rows):
        raise ContentError("previous-set-mismatch", "the set's packages differ from the signed manifest's rows")
    info["rows"] = "content-set"
    return rows, info


def reuse_set_rows(path, *, commit: str, public_key_sha256: str) -> tuple[list, dict]:
    """Rows of another platform's set of the same commit (cross-platform reuse)."""
    data = _read_file(Path(path), r2.MAX_SET_BYTES, "reuse-set")
    other = r2.parse_set_bytes(data)
    r2.validate_set(other, public_key_sha256=public_key_sha256, commit=commit, source="r2",
                    reader_cap=r2.READER_CAP_W1A)
    return _package_rows(other), {"platform": other["platform"], "set_sha256": r2.sha256_hex(data)}


class HeadOnlyGuard(up.SdkGuard):
    """The uploader's SDK guard, narrowed to HEAD: the probe's client cannot
    write, read bodies or list, whatever code later reaches it."""

    def inspect(self, name, params) -> dict:
        if name != "HeadObject":
            self._refuse("sdk-operation", ascii(name)[:80])
        return super().inspect(name, params)


class S3Probe:
    """S3 HEAD through the uploader's guarded client: the uploader's own reuse
    rule (length, sha256 metadata, content type, cache control)."""

    name = "s3"

    def __init__(self, bucket):
        self.bucket = bucket

    def available(self, part: dict) -> bool:
        key = r2.part_key(part["sha256"])
        try:
            up.verify_reused(self.bucket, key, size=part["size"], sha256=part["sha256"])
        except up.UploadError as error:
            if error.code in ("reused-missing", "reused-mismatch"):
                return False
            raise
        return True


class PublicProbe:
    """Anonymous HEAD on the custom domain (no credentials, for example inside
    WSL): status and length only, and only for rows already in the derived R2
    form. The uploader repeats the full S3 check on every reused row."""

    name = "public"

    def __init__(self, http):
        self.http = http

    def available(self, part: dict) -> bool:
        if part.get("url") != r2.part_url(part["sha256"]):
            return False
        response = self.http.request("HEAD", part["url"], limit=0)
        if response.status == 404:
            return False
        if response.status != 200:
            raise ContentError("probe-public", f"HTTP {response.status}")
        return response.headers.get("content-length") == str(part["size"])


def probe_parts(probe, rows, *, workers: int = MAX_WORKERS) -> dict:
    """{part sha256: available} for every distinct part of the candidate rows."""
    parts = {}
    for row in rows:
        for part in row.get("parts") or []:
            parts.setdefault(part["sha256"], part)
    if not parts:
        return {}
    with ThreadPoolExecutor(max_workers=min(workers, MAX_WORKERS)) as pool:
        results = pool.map(lambda part: (part["sha256"], bool(probe.available(part))), parts.values())
        return dict(results)


def choose_candidates(view: Path, candidates, available: dict) -> dict:
    """One reuse candidate per package id: every part available, and, where
    candidates disagree about the files, the one equal to the local files."""
    by_id = {}
    for row in candidates:
        if row.get("parts") and all(available.get(part["sha256"]) for part in row["parts"]):
            by_id.setdefault(row["id"], []).append(row)
    conflicts = {pid for pid, rows in by_id.items()
                 if len({r2.canonical_bytes(row["files"]) for row in rows}) > 1}
    local = local_rows(view, conflicts) if conflicts else {}
    chosen = {}
    for pid, rows in by_id.items():
        if pid in conflicts:
            match = next((row for row in rows if row["files"] == local.get(pid)), None)
            if match is not None:
                chosen[pid] = match
        else:
            chosen[pid] = rows[0]
    return chosen


# --- Pack ------------------------------------------------------------------------------

@dataclass
class PackResult:
    ok: bool
    set_sha256: str
    set_path: Path
    plan_path: Path | None
    summary: dict
    counts: dict
    dispatch: dict = field(default_factory=dict)


def _prepare_out(out: Path, stage: Stage, source: str) -> Path:
    out = up.private_path(out, "out")
    if out.is_relative_to(stage.path):
        raise ContentError("out-location", "the output must not be inside the stage")
    marker = {"kind": OUT_KIND, "platform": stage.platform, "commit": stage.commit, "source": source}
    if out.exists():
        if _is_link(out) or not out.is_dir():
            raise ContentError("out-location", "the output is not a directory")
        existing = out / OUT_MARKER
        if existing.is_file():
            if up.strict_json(_read_file(existing, MAX_SMALL_BYTES, "out-marker")) != marker:
                raise ContentError("out-other", "the output folder belongs to another platform, commit or source")
        elif any(out.iterdir()):
            raise ContentError("out-not-empty", "use a new or empty output folder")
    out.mkdir(parents=True, exist_ok=True)
    _write_if_changed(out / OUT_MARKER, _json_bytes(marker))
    parts = out / PARTS_DIR
    parts.mkdir(exist_ok=True)
    if os.stat(parts).st_dev != os.stat(stage.path).st_dev:
        raise ContentError("out-volume", "the output must be on the stage's volume (hard links, no copies)")
    return out


def _local_ci_hashes(stage: Stage, ci_files: list) -> tuple[list, str | None, str | None]:
    rows = []
    for relative in ci_files:
        path = stage.path / relative
        rows.append({"path": relative, "size": path.stat().st_size, "sha256": _digest(path)})
    engine = next((row["sha256"] for row in rows if row["path"] == ENGINE_BINARIES[stage.platform]), None)
    libraries = [row for row in rows if r2.has_native_suffix(row["path"])
                 and row["path"].casefold().startswith(r2.CI_PREFIXES[0].casefold())]
    return rows, engine, libraries[0]["sha256"] if len(libraries) == 1 else None


def _package_format(packages: list) -> str:
    coded = any(package.get("codec") == "zstd" or any(entry.get("codec") == "zstd" for entry in package["files"])
                for package in packages)
    return "zstd" if coded else "deflate1"


def _zstandard_version() -> str | None:
    try:
        import zstandard
    except ImportError:
        return None
    version = getattr(zstandard, "__version__", None)
    return version if type(version) is str and re.fullmatch(r"[0-9][0-9A-Za-z.+-]{0,31}", version) else None


def _privacy_check(data: bytes, paths) -> None:
    """The public set names no local path of this machine (validate_set already
    refuses drive letters, leading slashes, `~` and backslashes)."""
    text = data.decode("ascii").casefold()
    for path in paths:
        if path is None:
            continue
        for form in {str(path), Path(path).as_posix()}:
            if len(form) >= 4 and form.casefold() in text:
                raise ContentError("set-local-path", "the set names a local path")


def pack(stage, *, platform: str, out, previous: str = "none", previous_set_file=None, reuse_set=None,
         probe=None, build_dir=None, godot=None, logs=None, source: str = "r2", dev: bool = False,
         tools_repo=None, http=None, workers: int = MAX_WORKERS, check_modules: bool = True) -> PackResult:
    """Pack a qualified stage; see the module docstring. Returns a PackResult."""
    started = time.monotonic()
    timings = {}
    if platform not in r2.PLATFORMS or source not in r2.SOURCES:
        raise ContentError("arguments", "platform or source")
    if source == "ci" and (previous != "none" or reuse_set is not None or probe is not None):
        raise ContentError("arguments", "a ci set is rebuilt in full: no --previous, --reuse-set or --probe")
    if (previous != "none" or reuse_set is not None) and probe is None:
        raise ContentError("arguments", "reuse needs a probe: --probe s3 --credentials <file>, or --probe public")
    if build_dir is None and not dev:
        raise ContentError("import-cache-required", "pass package_client's --build-dir (the reused import cache)")
    if check_modules:
        check_module_locations()
    editor_sha256 = None
    if godot is not None:
        if _is_link(Path(godot)) or not Path(godot).is_file():
            raise ContentError("godot", "the --godot editor is not a file")
        editor_sha256 = _digest(Path(godot))
    import asset_packages
    import client_release
    import shared_release_assets

    commit = stage_commit(stage)
    tools = tools_provenance(Path(tools_repo) if tools_repo else TOOLS_REPO, commit, dev=dev)
    info, stage_problems = read_stage(stage, platform, public_pem=tools.public_pem, dev=dev)
    qualification, qualification_problems = read_qualification(info, logs, dev=dev)
    cache, cache_problems = import_cache(build_dir, commit, dev=dev) if build_dir is not None else (None, [])
    problems = [*tools.problems, *stage_problems, *qualification_problems, *cache_problems]
    timings["checks"] = round(time.monotonic() - started, 3)
    out = _prepare_out(Path(out), info, source)
    parts = out / PARTS_DIR
    receipt = {"kind": RECEIPT_KIND, "receipt_schema": 1, "started_utc": _utc_now(),
               "mode": "dev" if dev else "release", "source": source, "platform": platform, "commit": commit,
               "version": info.version, "stage": str(info.path), "out": str(out), "dev_problems": problems,
               "result": "failed"}
    view = None
    try:
        stale = clean_stale(parts)
        public_key_sha256 = r2.public_key_sha256(tools.public_pem)
        candidates, previous_info, reuse_info = [], {"source": "none"}, None
        if reuse_set is not None:
            rows, reuse_info = reuse_set_rows(reuse_set, commit=commit, public_key_sha256=public_key_sha256)
            candidates.extend(rows)
        rows, previous_info = previous_rows(previous, platform=platform, public_pem=tools.public_pem, http=http,
                                            set_file=previous_set_file)
        candidates.extend(rows)
        receipt.update(previous=previous_info, reuse_set=reuse_info, stale_removed=stale)

        view = parts / f".v{secrets.token_hex(4)}"
        moment = time.monotonic()
        view_info = make_view(info.path, view)
        timings["view"] = round(time.monotonic() - moment, 3)
        if shutil.disk_usage(parts).free < view_info["bytes"] + FREE_RESERVE_BYTES:
            raise ContentError("disk-space", "not enough free space for the new parts")
        ci_rows, engine_sha256, library_sha256 = _local_ci_hashes(info, view_info["ci_files"])
        receipt.update(view={"files": view_info["files"], "bytes": view_info["bytes"]}, ci_files=ci_rows,
                       root_files=sorted(entry.name for entry in info.path.iterdir()
                                         if entry.name not in STAGE_ROOTS))

        moment = time.monotonic()
        available = probe_parts(probe, candidates, workers=workers) if candidates else {}
        chosen = choose_candidates(view, candidates, available)
        timings["probe"] = round(time.monotonic() - moment, 3)
        receipt["probes"] = {"kind": getattr(probe, "name", None), "parts": len(available),
                             "available": sum(available.values()), "candidates": len(chosen)}
        reuse_ids = {id(row) for row in chosen.values()}
        reused = set()

        def reuse_package(row) -> bool:
            if id(row) in reuse_ids:
                reused.add(row["id"])
                return True
            return False
        moment = time.monotonic()
        try:
            # R2 parts are 64 MiB (design Q10); GitHub-hosted (ci) parts keep 256 MiB. A reused
            # package keeps its earlier parts.
            built = asset_packages.build(view, shared_release_assets.base(r2.REPOSITORY), shared="partitioned",
                                         previous_packages=dict(chosen), reuse_package=reuse_package,
                                         part_bytes=client_release.R2_PART_BYTES if source == "r2" else None)
        except ValueError as error:
            raise ContentError("package-build", str(error)[:200]) from None
        timings["build"] = round(time.monotonic() - moment, 3)
        # build() skips what is no longer a file when it walks, so a view file
        # that vanished (another run's clean-up, a stage rebuilt meanwhile)
        # would silently leave the set. Every linked file is in exactly one package.
        if sorted(entry["path"] for package in built for entry in package["files"]) != view_info["paths"]:
            raise ContentError("view-changed", "the packages do not hold exactly the view's files; pack again")
        moment = time.monotonic()
        layout = read_pck_layout(view, {entry["path"]: entry for package in built for entry in package["files"]})
        qualification = {**qualification, "split_pck": layout["split"]}
        receipt["pck_layout"] = layout
        timings["pck_layout"] = round(time.monotonic() - moment, 3)

        plan_rows, counts = {}, {"new": 0, "reused": 0, "new_bytes": 0, "reused_bytes": 0}
        for package in built:
            kind = "reused" if package["id"] in reused and package is chosen.get(package["id"]) else "new"
            counts[kind] += 1
            counts[f"{kind}_bytes"] += package["size"]
            for part in package["parts"]:
                row = {"key": r2.part_key(part["sha256"]), "sha256": part["sha256"], "size": part["size"],
                       "kind": kind}
                if kind == "new":
                    local = parts / shared_release_assets.name(part["sha256"])
                    if _is_link(local) or not local.is_file() or local.stat().st_size != part["size"]:
                        raise ContentError("local-part", local.name)
                    row["local_path"] = f"{PARTS_DIR}/{local.name}"
                if part["sha256"] not in plan_rows or kind == "new":
                    plan_rows[part["sha256"]] = row
        packages = r2.rewrite_part_urls(built) if source == "r2" else [dict(package) for package in built]

        content_set = {
            "kind": r2.SET_KIND, "set_schema": r2.SET_SCHEMA, "source": source, "repository": r2.REPOSITORY,
            "commit": commit, "platform": platform, "version": info.version, "public_key_sha256": public_key_sha256,
            "asset_base": r2.DESKTOP_ASSETS if source == "r2" else r2.GITHUB_DOWNLOADS,
            "ci_paths": [*r2.CI_PATHS, *r2.CI_PREFIXES],
            "packages": packages, "optional_packages": [],
            "builder": {"mode": "dev" if dev else "release", "tools_commit": tools.commit,
                        "tools_dirty": tools.dirty, "tools_on_origin": tools.on_origin,
                        "import_cache_digest": cache["digest"] if cache else None,
                        "import_cache_files": cache["files"] if cache else None,
                        "godot_editor_sha256": editor_sha256,
                        "zstandard": _zstandard_version(), "package_format": _package_format(packages),
                        "release_build": info.release_build,
                        "local_engine_sha256": engine_sha256, "local_native_library_sha256": library_sha256},
            "qualification": qualification,
        }
        moment = time.monotonic()
        summary = r2.validate_set(content_set, public_key_sha256=public_key_sha256, commit=commit,
                                  platform=platform, source=source, reader_cap=r2.READER_CAP_W1A,
                                  sniff=r2.stage_sniffer(view))
        timings["validate"] = round(time.monotonic() - moment, 3)
        set_bytes = r2.canonical_bytes(content_set)
        _privacy_check(set_bytes, (info.path, out, Path.home(), build_dir and Path(build_dir).resolve(),
                                   tools_repo and Path(tools_repo).resolve(), TOOLS_REPO))
        set_sha256 = r2.sha256_hex(set_bytes)
        set_path, plan_path = out / SET_NAME, None
        _write_if_changed(set_path, set_bytes)
        if source == "r2" and not dev:
            plan = {"kind": up.PLAN_KIND, "plan_schema": up.PLAN_SCHEMA, "platform": platform,
                    "set_sha256": set_sha256, "set_bytes_path": SET_NAME,
                    "rows": [plan_rows[digest] for digest in sorted(plan_rows)]}
            plan_path = out / PLAN_NAME
            _write_if_changed(plan_path, _json_bytes(plan))
            up.load_plan(plan_path, public_key_sha256=public_key_sha256)  # the uploader's own contract check
        else:
            stale_plan = out / PLAN_NAME
            if stale_plan.is_file() and not stale_plan.is_symlink():
                stale_plan.unlink()  # a plan of an earlier set must never outlive it
        referenced = {row.get("local_path", "").rsplit("/", 1)[-1] for row in plan_rows.values()}
        unreferenced = sum(1 for entry in parts.iterdir() if entry.is_file() and entry.name not in referenced
                           and shared_release_assets.is_name(entry.name))
        dispatch = {f"{platform}_source": source, f"{platform}_set_sha256": set_sha256} if source == "r2" else {}
        timings["total"] = round(time.monotonic() - started, 3)
        receipt.update(result="complete", set_sha256=set_sha256, set_bytes=len(set_bytes), summary=summary,
                       counts=counts, plan_rows=len(plan_rows), unreferenced_local_parts=unreferenced,
                       timings=timings, dispatch=dispatch, finished_utc=_utc_now())
        return PackResult(True, set_sha256, set_path, plan_path, summary, counts, dispatch)
    except Exception as error:
        receipt.update(error_code=up.error_code(error), finished_utc=_utc_now())
        raise
    finally:
        if view is not None and view.exists() and not remove_view(view):
            _emit(f"Warning: could not remove the hard-link view {view}; delete it by hand (links only)", error=True)
        up.write_private(out / RECEIPT_NAME, up.redact(_json_bytes(receipt).decode("ascii")).encode("ascii"))


# --- Compare ---------------------------------------------------------------------------

def _tree_files(root: Path) -> list:
    files = []
    for top in STAGE_ROOTS:
        base = root / top
        if _is_link(base):
            raise ContentError("tree-link", top)
        if not base.exists():
            continue
        for directory, names, entries in os.walk(base):
            folder = Path(directory)
            for name in names:
                if _is_link(folder / name):
                    raise ContentError("tree-link", (folder / name).relative_to(root).as_posix())
            for name in entries:
                path = folder / name
                relative = path.relative_to(root).as_posix()
                if _is_link(path):
                    raise ContentError("tree-link", relative)
                if not r2.is_ci_path(relative):
                    files.append(relative)
    return sorted(files)


def hash_tree(root, *, workers: int = MAX_WORKERS) -> dict:
    """{relative path: (size, sha256)} of app/ and eloria-assets/ without CI paths."""
    root = Path(root)
    files = _tree_files(root)

    def one(relative):
        path = root / relative
        return relative, (path.stat().st_size, _digest(path))
    with ThreadPoolExecutor(max_workers=min(workers, MAX_WORKERS)) as pool:
        return dict(pool.map(one, files))


def reference_rows(data: bytes, kind: str, *, platform: str, public_pem: bytes | None) -> tuple[list, dict]:
    """Package rows of a signed release manifest (any schema) or a content set."""
    if kind == "manifest":
        if public_pem is None:
            raise ContentError("reference", "a manifest needs the release public key")
        _, document = up.verify_envelope(data, public_pem, limit=r2.CLIENT_MANIFEST_LIMIT)
        info = {"kind": "manifest", "schema": document.get("schema")}
    elif kind == "set":
        document = r2.parse_set_bytes(data)
        if document.get("kind") != r2.SET_KIND:
            raise ContentError("reference", "not a content set")
        info = {"kind": "set", "source": document.get("source")}
    else:
        raise ContentError("reference", ascii(kind)[:20])
    if document.get("platform") != platform or document.get("repository") != r2.REPOSITORY:
        raise ContentError("reference-identity", "the reference names another platform or repository")
    info.update(sha256=r2.sha256_hex(data), commit=document.get("commit"), version=document.get("version"))
    rows = [row for row in _package_rows(document) if row["id"] not in r2.CI_PACKAGE_IDS]
    for row in rows:
        if type(row.get("files")) is not list or any(
                not isinstance(entry, dict) or type(entry.get("path")) is not str for entry in row["files"]):
            raise ContentError("reference-rows", row["id"])
    return rows, info


def compare(root, *, platform: str, reference: bytes, kind: str, public_pem: bytes | None = None,
            workers: int = MAX_WORKERS) -> dict:
    """Installed-file drift of a stage or install root against a reference.

    Files: equal, changed, only local, only in the reference (CI-owned paths
    excluded on both sides). Packages: grouped with asset_packages.package_id
    as a pack at this checkout would group them; a package is unchanged when
    its files equal the reference package of the same id, which is what reuse
    needs (players would download every other package again).
    """
    import asset_packages
    root = Path(root).resolve()
    if _is_link(root) or not root.is_dir():
        raise ContentError("tree", "not a directory")
    rows, info = reference_rows(reference, kind, platform=platform, public_pem=public_pem)
    local = hash_tree(root, workers=workers)
    expected, reference_packages = {}, {}
    for row in rows:
        files = {entry["path"]: (entry.get("size"), entry.get("sha256")) for entry in row["files"]
                 if not r2.is_ci_path(entry["path"])}
        reference_packages[row["id"]] = (files, row.get("size"))
        expected.update(files)
    changed, local_only, same, same_bytes = [], [], 0, 0
    for relative, (size, digest) in local.items():
        if relative not in expected:
            local_only.append({"path": relative, "size": size, "sha256": digest})
        elif expected[relative] != (size, digest):
            changed.append({"path": relative, "size": size, "sha256": digest,
                            "reference_size": expected[relative][0], "reference_sha256": expected[relative][1]})
        else:
            same += 1
            same_bytes += size
    reference_only = [{"path": path, "size": size, "sha256": digest}
                      for path, (size, digest) in sorted(expected.items()) if path not in local]
    groups = {}
    for relative, value in local.items():
        groups.setdefault(asset_packages.package_id(relative), {})[relative] = value
    unchanged, different, new = [], [], []
    for pid in sorted(groups):
        files = groups[pid]
        unpacked = sum(size for size, _ in files.values())
        if pid not in reference_packages:
            new.append({"id": pid, "files": len(files), "unpacked_size": unpacked})
        elif reference_packages[pid][0] == files:
            unchanged.append({"id": pid, "size": reference_packages[pid][1]})
        else:
            before = reference_packages[pid][0]
            drift = sum(1 for path, value in files.items() if before.get(path) != value) + sum(
                1 for path in before if path not in files)
            different.append({"id": pid, "files": len(files), "unpacked_size": unpacked, "differing_files": drift})
    removed = sorted(pid for pid in reference_packages if pid not in groups)
    root_commit = None
    descriptor = root / DESCRIPTOR
    if descriptor.is_file():
        value = up.strict_json(_read_file(descriptor, MAX_DESCRIPTOR_BYTES, "descriptor"))
        root_commit = value.get("commit") if isinstance(value, dict) else None
    return {"kind": COMPARE_KIND, "compare_schema": 1, "platform": platform, "reference": info,
            "local": {"name": root.name, "commit": root_commit, "files": len(local),
                      "bytes": sum(size for size, _ in local.values())},
            "files": {"same": same, "same_bytes": same_bytes, "changed": sorted(changed, key=lambda r: r["path"]),
                      "local_only": sorted(local_only, key=lambda r: r["path"]), "reference_only": reference_only},
            "packages": {"unchanged": len(unchanged), "unchanged_bytes": sum(r["size"] or 0 for r in unchanged),
                         "changed": different, "new": new, "removed": removed,
                         "download_unpacked_bytes": sum(r["unpacked_size"] for r in different + new)}}


def _reference_from_argument(args, http) -> tuple[bytes, str]:
    if args.set is not None:
        return _read_file(args.set, r2.MAX_SET_BYTES, "reference"), "set"
    if args.manifest == "live":
        return live_release(http, args.platform, up.committed_public_key()).manifest_bytes, "manifest"
    if args.manifest == "github-latest":
        url = f"{GITHUB_LATEST}RabbitLands-{args.platform}.json"
        return _get(http, url, r2.CLIENT_MANIFEST_LIMIT, "github-latest"), "manifest"
    return _read_file(Path(args.manifest), r2.CLIENT_MANIFEST_LIMIT, "reference"), "manifest"


# --- Command line ----------------------------------------------------------------------

def _workers(value: str) -> int:
    number = int(value)
    if not 1 <= number <= MAX_WORKERS:
        raise argparse.ArgumentTypeError(f"use 1 to {MAX_WORKERS} workers")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="desktop_content.py", description=__doc__.split("\n\n")[0])
    modes = parser.add_subparsers(dest="mode", required=True)
    pack_mode = modes.add_parser("pack", help="pack a qualified stage into a content set and an upload plan")
    pack_mode.add_argument("--stage", required=True, type=Path, help="package_client's stage folder")
    pack_mode.add_argument("--platform", required=True, choices=r2.PLATFORMS)
    pack_mode.add_argument("--out", required=True, type=Path,
                           help="new or earlier output folder, outside every worktree, on the stage's volume")
    pack_mode.add_argument("--previous", required=True,
                           help="none, live (the R2 pointer), or a signed release manifest file")
    pack_mode.add_argument("--previous-set-file", type=Path, help="a local copy of the previous manifest's set")
    pack_mode.add_argument("--reuse-set", type=Path, help="the other platform's set of the same commit")
    pack_mode.add_argument("--probe", choices=("s3", "public"), help="how reuse candidates are checked on R2")
    pack_mode.add_argument("--credentials", type=Path, help="private R2 config (with --probe s3; HEAD only)")
    pack_mode.add_argument("--build-dir", type=Path, help="package_client's --build-dir (import cache digest)")
    pack_mode.add_argument("--godot", type=Path, help="the Godot editor used for the build (hash recorded)")
    pack_mode.add_argument("--logs", type=Path, help="package_client's log folder, if it moved")
    pack_mode.add_argument("--source", choices=r2.SOURCES, default="r2")
    pack_mode.add_argument("--workers", type=_workers, default=MAX_WORKERS)
    pack_mode.add_argument("--dev", action="store_true",
                           help="local proof: admit a dirty/unpublished tools tree or an unqualified stage; no plan")
    compare_mode = modes.add_parser("compare", help="installed-file drift against a release manifest or a set")
    compare_mode.add_argument("--stage", required=True, type=Path, help="a stage or an install root")
    compare_mode.add_argument("--platform", required=True, choices=r2.PLATFORMS)
    reference = compare_mode.add_mutually_exclusive_group(required=True)
    reference.add_argument("--manifest", help="live, github-latest, or a signed manifest file")
    reference.add_argument("--set", type=Path, help="a content set file")
    compare_mode.add_argument("--report", type=Path, help="private JSON report path")
    compare_mode.add_argument("--workers", type=_workers, default=MAX_WORKERS)
    return parser


def _probe_from_arguments(args, http):
    if args.credentials is not None and args.probe != "s3":
        raise ContentError("arguments", "--credentials is used only with --probe s3")
    if args.probe == "s3":
        if args.credentials is None:
            raise ContentError("arguments", "--probe s3 needs --credentials")
        config = up.load_config(args.credentials)
        client = up.create_client(config, HeadOnlyGuard(bucket=config.bucket))
        return S3Probe(up.Bucket(client, config.bucket))
    if args.probe == "public":
        return PublicProbe(http)
    return None


def _run_pack(args) -> dict:
    http = up.Http() if args.previous == "live" or args.probe == "public" or (
        args.previous != "none" and args.previous_set_file is None) else None
    probe = _probe_from_arguments(args, http)
    result = pack(args.stage, platform=args.platform, out=args.out, previous=args.previous,
                  previous_set_file=args.previous_set_file, reuse_set=args.reuse_set, probe=probe,
                  build_dir=args.build_dir, godot=args.godot, logs=args.logs, source=args.source, dev=args.dev,
                  http=http, workers=args.workers)
    summary, counts = result.summary, result.counts
    _emit(f"Packed {summary['packages']} packages, {summary['parts']} parts, {summary['bytes']:,} bytes "
          f"({summary['files']} files); reader slots {summary['reader_slots']}/{summary['reader_cap']}")
    _emit(f"  reused {counts['reused']} packages ({counts['reused_bytes']:,} bytes), "
          f"new {counts['new']} packages ({counts['new_bytes']:,} bytes) in {PARTS_DIR}/")
    _emit(f"Set: {result.set_path}")
    _emit(f"Set SHA-256: {result.set_sha256}")
    if result.plan_path is not None:
        _emit(f"Upload plan: {result.plan_path}")
        _emit("Dispatch inputs: " + " ".join(f"{key}={value}" for key, value in result.dispatch.items()))
        _emit(f"Next: python godot-client/tools/upload_desktop_assets.py content --plan {result.plan_path} "
              "--credentials <private R2 config> --receipt <private receipt path>")
    elif args.dev:
        _emit("Dev mode: no upload plan was written; this set is for local proofs only.")
    return {"ok": True}


def _run_compare(args) -> dict:
    http = up.Http() if args.manifest in ("live", "github-latest") else None
    report_path = up.private_path(args.report, "report") if args.report else None
    data, kind = _reference_from_argument(args, http)
    report = compare(args.stage, platform=args.platform, reference=data, kind=kind,
                     public_pem=up.committed_public_key() if kind == "manifest" else None, workers=args.workers)
    files, packages = report["files"], report["packages"]
    _emit(f"Compared {report['local']['files']} local files with {report['reference']['kind']} "
          f"{report['reference']['version']} ({report['reference']['sha256']})")
    _emit(f"  files: {files['same']} equal, {len(files['changed'])} changed, {len(files['local_only'])} only local, "
          f"{len(files['reference_only'])} only in the reference")
    _emit(f"  packages: {packages['unchanged']} unchanged, {len(packages['changed'])} changed, "
          f"{len(packages['new'])} new, {len(packages['removed'])} removed; "
          f"{packages['download_unpacked_bytes']:,} unpacked bytes to download again")
    if report_path is not None:
        up.write_private(report_path, _json_bytes(report))
        _emit(f"Report: {report_path}")
    return {"ok": True}


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = _run_pack(args) if args.mode == "pack" else _run_compare(args)
    except r2.DesktopR2Error as error:
        _emit(f"Refused: {error}", error=True)
        return 2
    except KeyboardInterrupt:
        _emit("Interrupted.", error=True)
        return 130
    except OSError as error:
        _emit(f"Failed: {type(error).__name__}: {error.strerror or ''}", error=True)
        return 1
    except Exception as error:  # noqa: BLE001 - never print SDK text (it can name the endpoint)
        _emit(f"Failed: {up.error_code(error)}", error=True)
        return 1
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
