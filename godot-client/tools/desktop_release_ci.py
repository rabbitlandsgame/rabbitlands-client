"""The Actions side of desktop-release-r2.yml: content checks, executables, signing, installers, staging, e2e.

Subcommands (one per workflow job; every input is an argument or an artifact):

  verify-content  anonymous checks of the dispatched content set on R2: its
                  SHA-256, desktop_r2.validate_set with the module constants and
                  the commit's reader cap, the recomputed release identity
                  against the `release-descriptor` package and the core PCK
                  (res://data/client_release.json, .godot/extension_list.cfg),
                  a HEAD of every part, and a full GET + SHA-256 + member
                  decode and native-magic sniff of every package the published
                  signed release does not already hold; writes artifact content-P
  build-content   the ci content leg (helper-train release, Linux fallback, R2
                  outage): today's hosted content build (the committed source
                  streamed and checked blob by blob, package_client with
                  --no-client-updates and full qualification, exact-key content
                  caches), then desktop_content.py pack --source ci (GitHub pool
                  URLs) and the parts to the GitHub pools through GitHubSink;
                  writes artifact content-P. No signing key, no R2.
  content-cache-key  the exact keys of the ci leg's content caches
  executables     the CI-owned binaries: the native client_runtime (rebuilt, no
                  cache), the engine executable, the updater helper (reused from
                  the previous signed release when its fingerprint is equal),
                  then the root files (launchers with the production --server,
                  the human-testing launchers, AUDIO-CREDITS.txt) and the
                  `engine` / `native-runtime` packages; writes artifact exec-P
  sign            schema-2/3 payloads from content-P and exec-P, signed in
                  Python with the release key (environment secret), each
                  re-verified and held to the 15 MiB envelope gate
  installers      Godot verification of the envelope, then setup.exe (Windows)
                  or download.sh (Linux)
  stage           uploads CI packages and helpers to the GitHub pools and the
                  manifests, alias and installers to the draft
  e2e             a fresh install with the shipped updater from the signed
                  envelope (R2 parts, GitHub CI packages and helpers), both
                  smoke profiles, a zero-download re-check, download.sh / setup.exe
  pointer         sign a release pointer (publish and repoint jobs)
  artifact-digest the content digest of an artifact folder (producers export
                  it, consumers check it)

R2 is untrusted transport: nothing here reads R2 metadata or ETags as integrity,
and nothing holds an R2 credential. The content set's informational fields
(`asset_base`, `ci_paths`, `builder`, `qualification`) never relax a rule.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
import zlib

import desktop_r2 as r2
import desktop_helpers as helpers
import release_manifest as rm
import upload_desktop_assets as up

TOOLS = Path(__file__).resolve().parent
CLIENT = TOOLS.parent
REPO = CLIENT.parent
SERVER = "game.rabbitlandsgame.com:2001"
SIGNING_SECRET = "CLIENT_UPDATE_SIGNING_KEY"
RUNTIME_DESCRIPTOR = "res://bin/client_runtime/client_runtime.gdextension"
EXTENSION_LIST = ".godot/extension_list.cfg"
PCK_IDENTITY = "data/client_release.json"
DESCRIPTOR, DESCRIPTOR_COPY = "app/client-release.json", "app/data/client_release.json"
CORE_PCK = "app/RabbitLands.pck"
CHUNK_BYTES = 8 * 1024 * 1024        # client_release.CHUNK_BYTES: one ZIP entry per 8 MiB of a file
MAX_INVENTORY_BYTES = 64 * 1024 * 1024
MAX_ENTRY_BYTES = 16 * 1024 * 1024    # Release.PayloadArchive.MAX_ENTRY_BYTES: no chunk member is larger
_ZIP_FLAGS = 0x080E                     # the general-purpose flags PayloadArchive accepts (never 0x1, encrypted)
MAX_PCK_ENTRY = 16 * 1024 * 1024
WORKERS = 4
EXEC_KIND, CONTENT_KIND, E2E_KIND = ("rabbitlands-desktop-exec", "rabbitlands-desktop-content-check",
                                     "rabbitlands-desktop-e2e")
ARTIFACT_INDEX = "ARTIFACT-INDEX.json"
HELPER_EXTENSIONS = rm.HELPER_EXTENSIONS
GITHUB_LATEST = f"https://github.com/{r2.REPOSITORY}/releases/latest/download/"
DOWNLOAD_WAIT_SECONDS = 3600
SMOKE_TIMEOUT = 300
PCK_FORMATS = (3, 4)
_PCK_HEADER = struct.Struct("<4sIIIIIQQ")   # magic, format, major, minor, patch, flags, file base, directory
_PCK_TAIL = struct.Struct("<QQ16sI")        # offset, size, md5, flags
_PCK_DIR_ENCRYPTED, _PCK_REL_FILEBASE = 1, 2


class CiError(r2.DesktopR2Error):
    pass


def _emit(message: str, *, error: bool = False) -> None:
    print(message, file=sys.stderr if error else sys.stdout, flush=True)


def _digest(path: Path) -> str:
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _json_bytes(value) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("ascii")


def _write(path: Path, data: bytes) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)
    return path


def _read_json(path: Path, limit: int = MAX_INVENTORY_BYTES):
    data = Path(path).read_bytes()
    if len(data) > limit:
        raise CiError("json-too-large", Path(path).name)
    value = r2._parse_json(data)
    if value is None:
        raise CiError("json", Path(path).name)
    return value


# --- Identity of the dispatched commit --------------------------------------------

def release_identity(repo: Path, commit: str, platform: str, public_pem: bytes, work: Path) -> dict:
    """client_release.identity for a GitHub release build of `commit` (full history needed)."""
    import client_release
    pem = Path(work) / "update_public.pem"
    pem.parent.mkdir(parents=True, exist_ok=True)
    pem.write_bytes(public_pem)
    try:
        return client_release.identity(Path(repo), commit, platform, pem, r2.REPOSITORY, "github", release_build=True)
    except (ValueError, subprocess.CalledProcessError) as error:
        raise CiError("identity", str(error)[:200]) from None


def version_suffix(version: str) -> str:
    """`RabbitLands-Windows-20261104-abc` -> `20261104-abc` (package_client's `version`)."""
    return version.split("-", 2)[2]


# --- Anonymous HTTPS --------------------------------------------------------------

class Fetcher(up.Http):
    """up.Http (GitHub and the custom domain only, no credentials) plus streamed downloads."""

    def download(self, url: str, path: Path, *, limit: int) -> tuple[int, int, str]:
        if not up._allowed_url(url):
            raise CiError("http-url", ascii(url)[:160])
        request = urllib.request.Request(url, headers={**up.UPDATER_HEADERS, "User-Agent": up.USER_AGENT})
        hasher, total = hashlib.sha256(), 0
        failure = None
        try:
            response = self.opener.open(request, timeout=self.timeout)
        except urllib.error.HTTPError as error:
            error.close()
            return error.code, 0, ""
        except Exception as error:  # noqa: BLE001 - reduced to its class name
            raise CiError("http-error", type(error).__name__) from None
        with response, Path(path).open("wb") as output:
            while chunk := response.read(1 << 20):
                total += len(chunk)
                if total > limit:
                    failure = "http-too-large"
                    break
                hasher.update(chunk)
                output.write(chunk)
        if failure:
            Path(path).unlink(missing_ok=True)
            raise CiError(failure, url)
        return response.status, total, hasher.hexdigest()


def head_ok(http, url: str, size: int) -> bool:
    response = http.request("HEAD", url, limit=0)
    length = response.headers.get("content-length")
    return response.status == 200 and length is not None and length.isdigit() and int(length) == size


def fetch_verified(http, url: str, path: Path, *, size: int, sha256: str) -> Path:
    """HEAD (200, exact length), then GET to `path` and check size and SHA-256.

    A 404 for a cacheable key is edge-cached for hours, so a key is never
    fetched before a HEAD proved it present.
    """
    if not head_ok(http, url, size):
        raise CiError("part-head", url)
    status, length, digest = http.download(url, path, limit=size)
    if status != 200 or length != size or digest != sha256:
        Path(path).unlink(missing_ok=True)
        raise CiError("part-hash", url)
    return Path(path)


# --- Package parts and members -----------------------------------------------------

class PartsReader(io.RawIOBase):
    """A seekable, read-only view of part files joined end to end (one package)."""

    def __init__(self, paths: list[Path]):
        super().__init__()
        self.files = [Path(path).open("rb") for path in paths]
        self.sizes = [Path(path).stat().st_size for path in paths]
        self.starts = [sum(self.sizes[:index]) for index in range(len(self.sizes))]
        self.length = sum(self.sizes)
        self.position = 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=io.SEEK_SET):
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self.position, io.SEEK_END: self.length}[whence]
        self.position = max(0, base + offset)
        return self.position

    def readinto(self, buffer):
        view, done = memoryview(buffer), 0
        while done < len(view) and self.position < self.length:
            index = max(i for i, start in enumerate(self.starts) if start <= self.position)
            handle = self.files[index]
            handle.seek(self.position - self.starts[index])
            want = min(len(view) - done, self.sizes[index] - (self.position - self.starts[index]))
            count = handle.readinto(view[done:done + want])
            if not count:
                break
            done += count
            self.position += count
        return done

    def close(self):
        for handle in self.files:
            handle.close()
        super().close()


def _member_names(files: list) -> list[str]:
    names = []
    for index, entry in enumerate(files):
        chunks = (entry["size"] + CHUNK_BYTES - 1) // CHUNK_BYTES
        names.extend(f"files/{index:06d}/{chunk:06d}" for chunk in range(chunks))
    return [*names, "inventory.json"]


def _decode(archive: zipfile.ZipFile, name: str, expected: int, codec: str | None) -> bytes:
    """One chunk member, read as the updater reads it (Release.PayloadArchive and
    package_updates.gd decode_chunk): stored or deflate entries only, no
    encryption, at most MAX_ENTRY_BYTES; a zstd chunk is one stored frame
    decoded into exactly `expected` bytes, never the size its header claims,
    with nothing after the frame."""
    info = archive.getinfo(name)
    if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED) or info.flag_bits & ~_ZIP_FLAGS \
            or info.file_size > MAX_ENTRY_BYTES:
        raise CiError("member-format", name)
    data = b""
    try:
        if codec is None:
            if info.file_size != expected:
                raise CiError("member-size", name)
            data = archive.read(name)
        else:
            import zstandard
            if info.compress_type != zipfile.ZIP_STORED:
                raise CiError("member-codec", f"{name} must be a stored zstd frame")
            frame = archive.read(name)
            try:
                if zstandard.frame_content_size(frame) in (-1, expected):
                    data = zstandard.ZstdDecompressor().decompress(frame, max_output_size=expected,
                                                                   allow_extra_data=False)
            except zstandard.ZstdError:
                data = b""
    except (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError, RuntimeError):
        raise CiError("member-decode", name) from None
    if len(data) != expected:
        raise CiError("member-size", name)
    return data


def verify_package(package: dict, part_paths: list[Path], *, extract: dict | None = None, sniff: bool = True) -> dict:
    """Check one package from its downloaded parts, as the updater would install it.

    The joined bytes must hash to the package; the ZIP must hold exactly the
    entries of its signed file rows plus inventory.json, which must equal those
    rows; every member decodes (deflate, or one stored zstd frame per chunk) to
    its row's size and SHA-256; and no member may start like a PE, ELF or Mach-O
    executable. `extract` maps file paths to destinations to write.
    """
    hasher = hashlib.sha256()
    for path in part_paths:
        with Path(path).open("rb") as handle:
            while block := handle.read(1 << 20):
                hasher.update(block)
    if sum(Path(path).stat().st_size for path in part_paths) != package["size"] \
            or hasher.hexdigest() != package["sha256"]:
        raise CiError("package-hash", package["id"])
    files, extract = package["files"], dict(extract or {})
    reader = PartsReader(part_paths)
    try:
        archive = zipfile.ZipFile(reader)
    except zipfile.BadZipFile:
        reader.close()
        raise CiError("package-zip", package["id"]) from None
    with reader, archive:
        names = [info.filename for info in archive.infolist()]
        if len(names) != len(set(names)) or sorted(names) != sorted(_member_names(files)):
            raise CiError("package-members", package["id"])
        if archive.getinfo("inventory.json").file_size > MAX_INVENTORY_BYTES:
            raise CiError("package-inventory", package["id"])
        if r2._parse_json(archive.read("inventory.json")) != files:
            raise CiError("package-inventory", package["id"])
        for index, entry in enumerate(files):
            digest, remaining, chunk = hashlib.sha256(), entry["size"], 0
            output = Path(extract[entry["path"]]).open("wb") if entry["path"] in extract else None
            try:
                while remaining:
                    expected = min(CHUNK_BYTES, remaining)
                    data = _decode(archive, f"files/{index:06d}/{chunk:06d}", expected, entry.get("codec"))
                    if chunk == 0 and sniff:
                        kind = r2.sniff_native(data, entry["size"])
                        if kind:
                            raise CiError("native-magic", f"{entry['path']} ({kind})")
                    digest.update(data)
                    if output:
                        output.write(data)
                    remaining -= expected
                    chunk += 1
            finally:
                if output:
                    output.close()
            if digest.hexdigest() != entry["sha256"]:
                raise CiError("member-hash", entry["path"])
    return {"id": package["id"], "files": len(files), "bytes": package["size"]}


# --- Minimal Godot PCK reader (formats 3 and 4) --------------------------------------

def read_pck(path: Path) -> dict[str, tuple[int, int]]:
    """Entry name (without res://) -> (absolute offset, size) of an unencrypted Godot 4 PCK."""
    path = Path(path)
    size = path.stat().st_size
    with path.open("rb") as handle:
        head = handle.read(_PCK_HEADER.size)
        if len(head) != _PCK_HEADER.size:
            raise CiError("pck", "not a Godot PCK")
        magic, fmt, _major, _minor, _patch, flags, base, directory = _PCK_HEADER.unpack(head)
        if magic != b"GDPC" or fmt not in PCK_FORMATS:
            raise CiError("pck", f"not a Godot 4 PCK (format {fmt})")
        if flags & _PCK_DIR_ENCRYPTED or flags & ~(_PCK_DIR_ENCRYPTED | _PCK_REL_FILEBASE):
            raise CiError("pck", f"pack flags {flags:#x} are not supported")
        if not directory or directory > size - 4:
            raise CiError("pck", "the directory offset is outside the file")
        offset_base = base if flags & _PCK_REL_FILEBASE else 0
        handle.seek(directory)
        count, = struct.unpack("<I", handle.read(4))
        entries = {}
        for _ in range(count):
            raw = handle.read(4)
            if len(raw) != 4:
                raise CiError("pck", "the directory is truncated")
            length, = struct.unpack("<I", raw)
            name_bytes, tail = handle.read(length), handle.read(_PCK_TAIL.size)
            if len(name_bytes) != length or len(tail) != _PCK_TAIL.size:
                raise CiError("pck", "the directory is truncated")
            name = name_bytes.rstrip(b"\0").decode("utf-8", "replace").removeprefix("res://")
            offset, entry_size, _md5, entry_flags = _PCK_TAIL.unpack(tail)
            if entry_flags or not name or name in entries or offset_base + offset + entry_size > size:
                raise CiError("pck", f"entry {name!r} is encrypted, repeated or outside the file")
            entries[name] = (offset_base + offset, entry_size)
    return entries


def pck_entry(path: Path, entries: dict, name: str) -> bytes | None:
    if name not in entries:
        return None
    offset, size = entries[name]
    if size > MAX_PCK_ENTRY:
        raise CiError("pck-entry", name)
    with Path(path).open("rb") as handle:
        handle.seek(offset)
        data = handle.read(size)
    if len(data) != size:
        raise CiError("pck-entry", name)
    return data


def check_core_pck(path: Path, identity: dict) -> dict:
    """The core PCK's embedded identity equals the commit's; it names only the CI runtime extension."""
    entries = read_pck(path)
    embedded = pck_entry(path, entries, PCK_IDENTITY)
    if embedded is None or r2._parse_json(embedded) != identity:
        raise CiError("pck-identity", "res://data/client_release.json differs from the commit's identity")
    listed = pck_entry(path, entries, EXTENSION_LIST)
    extensions = [line.strip() for line in (listed or b"").decode("utf-8", "replace").splitlines() if line.strip()]
    if any(line != RUNTIME_DESCRIPTOR for line in extensions):
        raise CiError("pck-extension-list", "the core PCK loads an extension other than the CI runtime")
    return {"entries": len(entries), "extensions": extensions}


# --- Content summary (what the owner reads before approving desktop-sign) ---------------

def _package_key(package: dict):
    return (package.get("sha256"), package.get("size"),
            json.dumps(package.get("files"), sort_keys=True), package.get("codec"))


def _suffix(path: str) -> str:
    name = path.rsplit("/", 1)[-1].casefold()
    return name.rsplit(".", 1)[1] if "." in name.lstrip(".") else ""


def content_diff(content_set: dict, published: dict | None) -> dict:
    current = {package["id"]: package for package in content_set["packages"]}
    previous = {package["id"]: package for package in (published or {}).get("packages", [])
                if isinstance(package, dict) and package.get("id") not in r2.CI_PACKAGE_IDS}
    added = sorted(set(current) - set(previous))
    removed = sorted(set(previous) - set(current))
    changed = sorted(pid for pid in set(current) & set(previous)
                     if _package_key(current[pid]) != _package_key(previous[pid]))
    old_suffixes = {_suffix(entry["path"]) for package in previous.values() for entry in package.get("files", [])
                    if not r2.is_ci_path(entry["path"])}
    new_suffixes = {_suffix(entry["path"]) for package in current.values() for entry in package["files"]}
    return {"previous_commit": (published or {}).get("commit"), "previous_version": (published or {}).get("version"),
            "added": added, "changed": changed, "removed": removed,
            "unchanged": len(current) - len(added) - len(changed),
            "client_changed": "client" in added or "client" in changed,
            "new_extensions": sorted(new_suffixes - old_suffixes) if published else [],
            "new_bytes": sum(current[pid]["size"] for pid in [*added, *changed]),
            "builder": content_set.get("builder"), "qualification": content_set.get("qualification")}


def summary_markdown(platform: str, set_sha256: str, commit: str, diff: dict) -> str:
    lines = [f"### {platform.title()} content `{set_sha256}`", "",
             f"- commit `{commit}`; compared with the published release "
             f"`{diff['previous_version'] or 'none'}`",
             f"- packages: {len(diff['added'])} added, {len(diff['changed'])} changed, "
             f"{len(diff['removed'])} removed, {diff['unchanged']} unchanged",
             f"- core `client` package changed: {'yes' if diff['client_changed'] else 'no'}",
             f"- new bytes to download: {diff['new_bytes']:,}",
             f"- new file extensions: {', '.join(diff['new_extensions']) or 'none'}"]
    for label in ("added", "changed", "removed"):
        if diff[label]:
            shown = ", ".join(f"`{pid}`" for pid in diff[label][:40])
            lines.append(f"- {label}: {shown}{' ...' if len(diff[label]) > 40 else ''}")
    lines.append(f"- builder (informational, reported by the build machine): `{json.dumps(diff['builder'])}`")
    return "\n".join(lines) + "\n"


# --- verify-content -------------------------------------------------------------------------

def _check_builder(content_set: dict) -> None:
    builder = content_set.get("builder")
    if not isinstance(builder, dict) or builder.get("mode") != "release" or builder.get("tools_dirty") is not False \
            or builder.get("release_build") is not True:
        raise CiError("builder", "the set was not packed by a clean release-mode pack (desktop_content.py)")


def verify_content(*, platform: str, set_sha256: str, commit: str, repo: Path, http, work: Path, out: Path,
                   published="auto") -> dict:
    """The r2 content job: refuse anything CI must not sign. Writes set.json, verified.json, summary.md."""
    if platform not in r2.PLATFORMS or not rm._is_hash(set_sha256) or not r2.valid_commit(commit):
        raise CiError("arguments")
    work, out = Path(work), Path(out)
    public_pem = rm.commit_public_key(repo, commit)
    capabilities = rm.commit_capabilities(repo, commit)
    if not capabilities.r2_rows:
        raise CiError("reader-lacks-r2", "the commit's updater does not read R2 rows; use the ci source")
    url = r2.set_url(platform, set_sha256)
    if not head_ok_any(http, url):
        raise CiError("set-missing", url)
    response = http.request("GET", url, limit=r2.MAX_SET_BYTES)
    if response.status != 200 or r2.sha256_hex(response.body) != set_sha256:
        raise CiError("set-hash", url)
    set_bytes = response.body
    content_set = r2.parse_set_bytes(set_bytes)
    summary = r2.validate_set(content_set, public_key_sha256=r2.public_key_sha256(public_pem), commit=commit,
                              platform=platform, source="r2", reader_cap=capabilities.reader_cap)
    _check_builder(content_set)
    identity = release_identity(repo, commit, platform, public_pem, work / "identity")
    if published == "auto":
        published = helpers.previous_release(http, platform, public_pem)
    previous = [package for package in (published or {}).get("packages", []) if isinstance(package, dict)]
    known_packages = {_package_key(package) for package in previous}
    # A part counts as checked only when the published signed manifest names its
    # exact URL (an R2 release's content job fetched it). The first R2 release
    # follows a GitHub-hosted one, so every R2 part is fetched then.
    named = {part.get("url") for package in previous for part in package.get("parts") or [] if isinstance(part, dict)}

    def known(package) -> bool:
        return _package_key(package) in known_packages and all(part["url"] in named for part in package["parts"])

    parts = {}
    for package in content_set["packages"]:
        for part in package["parts"]:
            parts[part["sha256"]] = part
    with ThreadPoolExecutor(WORKERS) as pool:
        heads = dict(zip(parts, pool.map(lambda part: head_ok(http, part["url"], part["size"]), parts.values())))
    missing = sorted(digest for digest, ok in heads.items() if not ok)
    if missing:
        raise CiError("part-missing", f"{len(missing)} parts, first {parts[missing[0]]['url']}")

    downloads = work / "parts"
    downloads.mkdir(parents=True, exist_ok=True)
    extracted = work / "extracted"
    extracted.mkdir(parents=True, exist_ok=True)
    targets = {DESCRIPTOR: extracted / "client-release.json", DESCRIPTOR_COPY: extracted / "client_release.json",
               CORE_PCK: extracted / "RabbitLands.pck"}
    # Packages the published signed release already holds (same bytes and files)
    # were verified when that release was made: HEAD only. Every other package is
    # downloaded part by part and checked member by member. The descriptor and
    # the core pack are always checked: they carry the identity.
    selected = [package for package in content_set["packages"]
                if package["id"] in r2.REQUIRED_PACKAGES or not known(package)]
    uses = {}
    for package in selected:
        for part in package["parts"]:
            uses[part["sha256"]] = uses.get(part["sha256"], 0) + 1
    verified, fetched = [], set()
    for package in selected:
        paths = []
        for part in package["parts"]:
            path = downloads / f"{part['sha256']}.bin"
            if part["sha256"] not in fetched:
                fetch_verified(http, part["url"], path, size=part["size"], sha256=part["sha256"])
                fetched.add(part["sha256"])
            paths.append(path)
        wanted = {path: target for path, target in targets.items()
                  if any(entry["path"] == path for entry in package["files"])}
        verified.append(verify_package(package, paths, extract=wanted))
        for part in package["parts"]:
            uses[part["sha256"]] -= 1
            if not uses[part["sha256"]]:
                (downloads / f"{part['sha256']}.bin").unlink(missing_ok=True)

    missing = [path for path, target in targets.items() if not target.is_file()]
    if missing:
        raise CiError("descriptor", f"{missing[0]} is not in a checked package")
    descriptor = targets[DESCRIPTOR].read_bytes()
    if r2._parse_json(descriptor) != identity:
        raise CiError("descriptor", "app/client-release.json differs from the commit's recomputed identity")
    if targets[DESCRIPTOR_COPY].read_bytes() != descriptor:
        raise CiError("descriptor", "app/data/client_release.json differs from app/client-release.json")
    pck = check_core_pck(targets[CORE_PCK], identity)
    targets[CORE_PCK].unlink()

    diff = content_diff(content_set, published)
    record = {"kind": CONTENT_KIND, "schema": 1, "platform": platform, "commit": commit, "source": "r2",
              "set_sha256": set_sha256, "set_bytes": len(set_bytes), "summary": summary,
              "reader": {"schema": capabilities.schema, "reader_cap": capabilities.reader_cap},
              "heads": len(heads), "verified_packages": verified, "downloaded_parts": len(fetched),
              "downloaded_bytes": sum(parts[digest]["size"] for digest in fetched),
              "published": {"commit": diff["previous_commit"], "version": diff["previous_version"]},
              "core_pck": pck, "diff": diff}
    out.mkdir(parents=True, exist_ok=True)
    _write(out / "set.json", set_bytes)
    _write(out / "verified.json", _json_bytes(record))
    _write(out / "summary.md", summary_markdown(platform, set_sha256, commit, diff).encode("ascii", "replace"))
    return record


def head_ok_any(http, url: str) -> bool:
    return http.request("HEAD", url, limit=0).status == 200


# --- build-content: the ci content leg ------------------------------------------------------------
#
# The same workflow with GitHub-hosted content (design 4.5): the helper-train
# release T, a Linux fallback and the R2-down emergency. The content job of a
# `ci` platform builds on the runner the way desktop-release.yml's build job
# does (runner_release.build), minus everything that signs, publishes or
# builds an installer: the commit's source is streamed and checked blob by
# blob (package_client's runner mode), package_client runs with
# --no-client-updates and full qualification, desktop_content.py packs the
# stage with --source ci (GitHub pool URLs, no reuse), and the parts go to the
# GitHub pools through runner_release.GitHubSink. Trust is today's: the
# content caches are restored by exact key only. The set then reaches `sign`
# exactly like an R2 set (artifact content-P, digest-checked).

CONTENT_CACHE_PREFIX = "rl-desktop-ci-"
WORLD_CACHE_SCHEMA = 1
# release_world_preparation.producer_inputs starts in src/world and follows
# preloads, mostly into src/actors and src/runtime. Other game scripts leave
# the world key alone: a missed dependency only costs a re-cook, because the
# cook keeps its own producer namespace and per-target source keys.
WORLD_KEY_SCRIPTS = ("godot-client/src/world/", "godot-client/src/actors/", "godot-client/src/runtime/")
POOL_CONFIRM_DELAYS = (0, 5, 15, 30)
_CACHE_KEY = re.compile(r"[A-Za-z0-9._-]{1,400}")
_RELEASE_ID = re.compile(r"0|[1-9][0-9]{0,15}")


def git_runner(repo: Path):
    """git in `repo` (or `cwd`) without the caller's GIT_* environment, as runner_source expects."""
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}

    def run(*args, cwd=None) -> str:
        result = subprocess.run(["git", "-c", "core.longpaths=true", *map(str, args)], cwd=str(cwd or repo),
                                capture_output=True, env=environment, timeout=1800)
        if result.returncode:
            raise CiError("git", f"git {args[0]} failed")
        return result.stdout.decode("utf-8")
    return run


def content_cache_keys(git, commit: str, platform: str) -> dict:
    """The exact GitHub cache keys of the ci leg's content caches (no restore-keys anywhere).

    asset_key: release_asset_cache.input_key, the committed asset and tool inputs
    as the hosted build keys them, in a namespace of its own: the ci leg never
    restores or feeds an entry of desktop-release.yml. world_key: the same rows
    plus the world producer scripts.
    """
    import release_asset_cache
    import runner_source
    if platform not in r2.PLATFORMS or not r2.valid_commit(commit):
        raise CiError("arguments", "content-cache-key needs a platform and a full commit")
    asset = release_asset_cache.input_key(git, commit, platform)
    rows = []
    for row in git("ls-tree", "-r", "-z", commit).split("\0"):
        if not row:
            continue
        path = row.split("\t", 1)[1]
        if not runner_source.selected(path) or path.startswith(("godot-client/tests/", "godot-client/docs/")):
            continue
        if (path.startswith("godot-client/src/") and path.endswith((".gd", ".gd.uid"))
                and not path.startswith(("godot-client/src/updates/", *WORLD_KEY_SCRIPTS))):
            continue
        rows.append(row)
    if not rows:
        raise CiError("cache-key", "the commit has no content inputs")
    digest = hashlib.sha256("\0".join(sorted(rows)).encode("utf-8")).hexdigest()
    keys = {"asset_key": CONTENT_CACHE_PREFIX + asset,
            "world_key": f"{CONTENT_CACHE_PREFIX}world-v{WORLD_CACHE_SCHEMA}-{platform}-{digest}"}
    if not all(_CACHE_KEY.fullmatch(value) for value in keys.values()):
        raise CiError("cache-key", "a cache key holds unexpected characters")
    return keys


def content_cache_dirs(cache: Path, platform: str) -> dict:
    """The folders the content-ci job's cache steps restore and save, exactly."""
    return {"assets": Path(cache) / f"assets-{platform}", "world": Path(cache) / "world"}


@contextmanager
def _environment(values: dict):
    previous = {name: os.environ.get(name) for name in values}
    os.environ.update({name: str(value) for name, value in values.items()})
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


class _NoPackageUploads:
    """package_client's runner sink in the ci leg. With --no-client-updates it
    publishes nothing; parts reach the pools only after desktop_content packs them."""
    uploaded_bytes = reused_bytes = 0

    def accept(self, path, row):
        raise CiError("package-upload", "package_client tried to upload during the ci content build")

    def reuse(self, rows) -> bool:
        return False


def _check_ci_content(directory: Path, *, platform: str, commit: str, set_sha256: str) -> dict:
    """A ci set is signed only as build-content left it: this commit's, every part in the pools."""
    path = Path(directory) / "verified.json"
    record = _read_json(path) if path.is_file() else None
    if (not isinstance(record, dict) or record.get("kind") != CONTENT_KIND or record.get("source") != "ci"
            or record.get("platform") != platform or record.get("commit") != commit
            or record.get("set_sha256") != set_sha256 or record.get("uploaded") is not True):
        raise CiError("ci-content", f"{platform}: the ci content artifact is not a finished build-content "
                                    "upload of this set (a dry run uploads nothing)")
    return record


class ContentLeg:
    """build-content for one platform. Methods named as seams reach outside
    systems (tools, graphics, the native toolchain, package_client, GitHub);
    tests replace those and run the rest, desktop_content.pack included."""

    PREFLIGHT_BYTES = 7_000_000_000   # runner_release.build's reservation before any source exists
    CACHE_SAVE_SCRATCH = 64 * 1024 ** 2

    def __init__(self, *, platform: str, commit: str, release_id, dry_run: bool, repo: Path, work: Path, out: Path,
                 cache: Path, http=None, published="auto", runner_temp: Path | None = None, sleep=time.sleep):
        self.platform, self.commit, self.dry_run = platform, commit, dry_run
        self.release_id = release_id
        self.repo, self.work, self.out, self.cache = (Path(value).resolve() for value in (repo, work, out, cache))
        self.http = http if http is not None else Fetcher()
        self.published = published
        self.runner_temp = Path(runner_temp or os.environ.get("RUNNER_TEMP") or self.work).resolve()
        self.native_tool_root = self.runner_temp / "rabbitlands-native-toolchain"
        self.sleep = sleep
        self.git = git_runner(self.repo)

    # --- seams ---------------------------------------------------------------------------------

    def install_tools(self, root: Path) -> dict:
        """The pinned editor and export template (no Inno: this leg builds no installer)."""
        import setup_runner_tools
        return setup_runner_tools.install(self.platform, root, installers=False)

    def prepare_graphics(self, godot: Path, check, root: Path) -> None:
        """Software rendering for the headless imports, cooks and smokes, proved by a tiny probe first."""
        import release_graphics_preflight
        import release_software_graphics
        folder = Path(godot).resolve().parent
        try:
            config = release_software_graphics.prepare_graphics(self.platform, folder, folder, check)
        except ValueError as error:
            _write(root / "graphics-configuration-failure.json",
                   _json_bytes({"status": "failed", "error": str(error)[:500]}))
            raise
        release_graphics_preflight.run_preflight(config, Path(godot), root / "graphics-preflight", check)

    def prepare_native(self, native_cache: Path, check, root: Path) -> dict:
        """The native runtime package_client qualifies with, compiled from the commit's
        exact blobs into a cache that starts empty; then the job's Rust homes retire."""
        import release_native_runtime
        import runner_retirement
        if not self.native_tool_root.is_dir():
            raise CiError("native-toolchain", "install the pinned Rust toolchain in RUNNER_TEMP first")
        runner_retirement.claim_native_sdk(self.native_tool_root, self.runner_temp, self.commit, self.platform)
        bootstrap = release_native_runtime.prewarm_cache(self.repo, self.commit, self.platform, native_cache,
                                                         native_cache.parent / f"bootstrap-{self.platform}", check)
        _write(root / "native-bootstrap.json", _json_bytes(bootstrap))
        runner_retirement.retire_native_sdk(self.native_tool_root, self.runner_temp, self.commit, self.platform,
                                            bootstrap, check, root / "native-toolchain-retirement.json")
        return bootstrap

    def package(self, argv: list, storage) -> int:
        """package_client in runner mode: a --no-checkout build worktree whose committed
        files runner_source streams from the commit's archive and checks blob by blob."""
        import package_client
        return package_client.main(argv, storage)

    def sink(self):
        import runner_release
        return runner_release.GitHubSink(self.release_id)

    def previous(self, public_pem: bytes):
        return helpers.previous_release(self.http, self.platform, public_pem)

    # --- the leg -------------------------------------------------------------------------------

    def _check_arguments(self) -> None:
        if self.platform not in r2.PLATFORMS or not r2.valid_commit(self.commit) or type(self.dry_run) is not bool:
            raise CiError("arguments", "platform, commit or dry run")
        if not _RELEASE_ID.fullmatch(str(self.release_id)) or (str(self.release_id) == "0") != self.dry_run:
            raise CiError("arguments", "a dry run has release id 0; any other run names its draft")
        self.release_id = int(self.release_id)
        if SIGNING_SECRET in os.environ:
            raise CiError("signing-key-present", "the ci content leg never sees the release key")
        for label, path in (("work", self.work), ("out", self.out), ("cache", self.cache)):
            if path.is_relative_to(self.repo) or self.repo.is_relative_to(path):
                raise CiError("location", f"--{label} must be outside the checkout")
        if self.out.exists() and (not self.out.is_dir() or any(self.out.iterdir())):
            raise CiError("out-not-empty", "the content artifact folder must start empty")

    def package_arguments(self, *, godot: Path, source: Path, output: Path, vram: Path, pem: Path,
                          native_cache: Path, world_cache: Path) -> list:
        """runner_release.build's package_client call without the signing key, the
        shared-release upload, the installer or the archive: content only."""
        return ["--platform", self.platform, "--ref", self.commit, "--distribution", "github", "--release-build",
                "--no-client-updates", "--no-zip", "--no-fetch", "--godot", str(godot), "--build-dir", str(source),
                "--out", str(output), "--vram-cache", str(vram), "--update-public-key", str(pem),
                "--server", SERVER, "--full-optimizations", "--native-runtime-cache", str(native_cache),
                "--prepared-world", "--world-preparation-cache", str(world_cache)]

    def _stage(self, output: Path, identity: dict) -> Path:
        import package_client
        stages = [path for path in output.iterdir() if path.is_dir() and (path / package_client.MARKER).is_file()]
        if len(stages) != 1:
            raise CiError("stage", "package_client left no single stage")
        stage = stages[0]
        descriptor = stage / DESCRIPTOR
        if not descriptor.is_file() or r2._parse_json(descriptor.read_bytes()) != identity:
            raise CiError("descriptor", "the stage's app/client-release.json is not the commit's identity")
        return stage

    def _pool_rows(self, content_set: dict, parts: Path) -> list:
        """Every distinct part, named and placed exactly as GitHubSink stores it."""
        import shared_release_assets
        rows = {}
        for package in content_set["packages"]:
            for part in package["parts"]:
                name = shared_release_assets.name(part["sha256"])
                if part["url"] != r2.github_pool_url(part["sha256"]) \
                        or part["url"] != shared_release_assets.download_url(r2.REPOSITORY, name):
                    raise CiError("pool-url", part["url"])
                row = {"name": name, "size": part["size"], "sha256": part["sha256"], "url": part["url"]}
                if rows.setdefault(part["sha256"], row) != row:
                    raise CiError("pool-url", f"{name} is named with two sizes")
        for row in rows.values():
            path = parts / row["name"]
            if path.is_symlink() or not path.is_file() or path.stat().st_size != row["size"]:
                raise CiError("local-part", row["name"])
        return sorted(rows.values(), key=lambda row: row["name"])

    def _confirm_pool(self, rows: list) -> None:
        """Anonymous HEADs (200, exact length): what players and the e2e will download."""
        def present(row) -> bool:
            try:
                return head_ok(self.http, row["url"], row["size"])
            except r2.DesktopR2Error:
                return False
        pending = list(rows)
        for delay in POOL_CONFIRM_DELAYS:
            if delay:
                self.sleep(delay)
            with ThreadPoolExecutor(WORKERS) as pool:
                found = list(pool.map(present, pending))
            pending = [row for row, ok in zip(pending, found) if not ok]
            if not pending:
                return
        raise CiError("pool-missing", f"{len(pending)} uploaded parts are not downloadable, "
                                      f"first {pending[0]['url']}")

    def _upload(self, rows: list, parts: Path) -> dict:
        record = {"uploaded": False, "parts": len(rows), "bytes": sum(row["size"] for row in rows),
                  "uploaded_bytes": 0, "reused_bytes": 0,
                  "rows": [{key: row[key] for key in ("name", "size", "sha256")} for row in rows]}
        if self.dry_run:
            for row in rows:  # a dry run sends nothing: release the disk
                (parts / row["name"]).unlink()
            return record
        sink = self.sink()
        for row in rows:
            path = parts / row["name"]
            # GitHubSink re-hashes the file and returns only once GitHub records this exact size and SHA-256.
            sink.accept(path, {"name": row["name"], "size": row["size"], "sha256": row["sha256"]})
            path.unlink()
        self._confirm_pool(rows)
        record.update(uploaded=True, uploaded_bytes=getattr(sink, "uploaded_bytes", None),
                      reused_bytes=getattr(sink, "reused_bytes", None))
        return record

    def _cleanup(self, root: Path, stage: Path) -> None:
        """This build's worktree and stage only (runner_release.RunnerStorage.cleanup's rule)."""
        import package_client
        source = root / "source"
        marker = (stage / package_client.MARKER).read_text(encoding="utf-8").strip()
        owner = r2._parse_json((root / ".runner-release.json").read_bytes())
        if (stage.resolve().parent != (root / "downloads").resolve() or marker != self.commit
                or owner != {"repository": r2.REPOSITORY, "commit": self.commit}):
            raise CiError("cleanup", "the cleanup targets do not belong to this build")
        if source.exists():
            self.git("worktree", "remove", "--force", str(source))
        shutil.rmtree(stage)

    def run(self) -> dict:
        import release_asset_cache
        import runner_release
        from release_storage import DiskBudget, unique_bytes
        self._check_arguments()
        public_pem = rm.commit_public_key(self.repo, self.commit)
        capabilities = rm.commit_capabilities(self.repo, self.commit)
        root = self.work / f"content-{self.platform}-{self.commit}"
        root.mkdir(parents=True, exist_ok=False)
        _write(root / ".runner-release.json", _json_bytes({"repository": r2.REPOSITORY, "commit": self.commit}))
        identity = release_identity(self.repo, self.commit, self.platform, public_pem, root / "identity")
        keys = content_cache_keys(self.git, self.commit, self.platform)
        dirs = content_cache_dirs(self.cache, self.platform)
        for folder in dirs.values():
            folder.mkdir(parents=True, exist_ok=True)
        asset_cache = release_asset_cache.AssetCache(dirs["assets"], keys["asset_key"])
        native_cache = self.work / "native-cache" / self.platform
        if native_cache.exists():
            raise CiError("native-cache", "the native cache must start empty: no cached native build")
        native_cache.parent.mkdir(parents=True, exist_ok=True)
        tool_root = self.work / "toolchain"
        config = self.install_tools(tool_root)
        godot = Path(config["godot"]).resolve()
        git_dir = Path(self.git("rev-parse", "--path-format=absolute", "--git-common-dir").strip())
        roots = [self.repo, git_dir, root, godot, tool_root, native_cache.parent, self.cache]
        budget = DiskBudget([*roots, *([self.native_tool_root] if self.native_tool_root.is_dir() else [])])
        budget.check("preflight", self.PREFLIGHT_BYTES)
        storage = runner_release.RunnerStorage(root, budget, _NoPackageUploads(), asset_cache)
        source, output = root / "source", root / "downloads"
        storage.source = source / "godot-client"
        storage.previous_packages = {}
        pem = root / "update_public.pem"
        pem.write_bytes(public_pem)
        argv = self.package_arguments(godot=godot, source=source, output=output, vram=asset_cache.vram, pem=pem,
                                      native_cache=native_cache, world_cache=dirs["world"])
        with _environment(config.get("env") or {}):
            self.prepare_graphics(godot, storage.check, root)
            storage.native_bootstrap = self.prepare_native(native_cache, storage.check, root)
            storage.check("native cache verified before runtime source materialization")
            try:
                code = self.package(argv, storage)
            except RuntimeError as error:  # package_client.PackageError
                raise CiError("package", str(error)[:300]) from None
        if code:
            raise CiError("package", "package_client failed; see the content build logs")
        stage = self._stage(output, identity)
        pck = check_core_pck(stage / CORE_PCK, identity)
        asset_cache.built_packages = 0
        asset_cache.finish(b"{}\n")  # the ci leg reuses no package through the cache: pack rebuilds in full
        storage.check("content stage qualified")

        import desktop_content
        free = shutil.disk_usage(root).free
        result = desktop_content.pack(stage, platform=self.platform, out=root / "content-pack", source="ci",
                                      build_dir=source, godot=godot, tools_repo=self.repo, workers=WORKERS)
        set_bytes = result.set_path.read_bytes()
        content_set = r2.parse_set_bytes(set_bytes)
        summary = r2.validate_set(content_set, public_key_sha256=r2.public_key_sha256(public_pem),
                                  commit=self.commit, platform=self.platform, source="ci",
                                  reader_cap=capabilities.reader_cap)
        _check_builder(content_set)
        rows = self._pool_rows(content_set, result.set_path.parent / "parts")
        pool = self._upload(rows, result.set_path.parent / "parts")
        published = self.previous(public_pem) if self.published == "auto" else self.published
        diff = content_diff(content_set, published)
        set_sha256 = r2.sha256_hex(set_bytes)
        record = {"kind": CONTENT_KIND, "schema": 1, "platform": self.platform, "commit": self.commit,
                  "source": "ci", "set_sha256": set_sha256, "set_bytes": len(set_bytes), "summary": summary,
                  "reader": {"schema": capabilities.schema, "reader_cap": capabilities.reader_cap},
                  "dry_run": self.dry_run, "uploaded": pool["uploaded"], "pool": pool,
                  "caches": {"asset_key": keys["asset_key"], "asset_hit": asset_cache.hit,
                             "world_key": keys["world_key"]},
                  "published": {"commit": diff["previous_commit"], "version": diff["previous_version"]},
                  "core_pck": pck, "diff": diff,
                  "disk": {"free_before_pack": free, "budget_peak": budget.peak}}
        hosting = ("dry run: built and packed, nothing uploaded" if self.dry_run else
                   f"{pool['parts']} parts in the GitHub pools ({pool['uploaded_bytes'] or 0:,} bytes uploaded, "
                   f"{pool['reused_bytes'] or 0:,} bytes already there)")
        self.out.mkdir(parents=True, exist_ok=True)
        _write(self.out / "set.json", set_bytes)
        _write(self.out / "verified.json", _json_bytes(record))
        _write(self.out / "summary.md", (summary_markdown(self.platform, set_sha256, self.commit, diff)
                                         + f"- source: ci, built on this runner; {hosting}\n"
                                         ).encode("ascii", "replace"))
        self._cleanup(root, stage)
        try:
            storage.check("before cache save",
                          unique_bytes([dirs["assets"], dirs["world"]]) + self.CACHE_SAVE_SCRATCH)
        except ValueError as error:
            _emit(f"warning: {error} The content cache save may fail; it is optional.", error=True)
        return record


# --- executables -----------------------------------------------------------------------------

def default_template(godot: Path, platform: str) -> Path:
    """The export template setup_runner_tools.install extracted beside the editor."""
    data = Path(godot).resolve().parent / "data"
    folder = (data / "Godot") if platform == "windows" else (data / "godot")
    name = {"windows": "windows_release_x86_64.exe", "linux": "linux_release.x86_64"}[platform]
    return folder / "export_templates" / "4.7.2.stable" / name


def build_native(repo: Path, commit: str, platform: str, work: Path) -> Path:
    """The client_runtime payload, compiled in this run from a fresh, empty cache."""
    import release_native_runtime

    def check(label, upcoming_bytes=0):
        if shutil.disk_usage(work).free < upcoming_bytes + 512 * 1024 ** 2:
            raise CiError("disk", "native disk reserve exhausted: " + label)
    work.mkdir(parents=True, exist_ok=True)
    cache = work / "native-cache"
    if cache.exists():
        raise CiError("native-cache", "the native build cache must start empty: no shipped binary from a cache")
    receipt = release_native_runtime.prepare_runtime(repo, commit, platform, cache, work / "native-payload",
                                                     work / "native-work", check)
    if receipt.get("cache_hit") is not False:
        raise CiError("native-cache", "the native payload came from a cache")
    return work / "native-payload"


def export_engine(repo: Path, platform: str, godot: Path, template: Path, run_godot, work: Path, target: Path) -> Path:
    """The game executable without a pack: the template copy on Linux; on Windows an
    export of a tiny project with the game's preset (embed_pck=false, branding)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if platform == "linux":
        shutil.copyfile(template, target)
        target.chmod(0o755)
        return target
    import package_client
    project = Path(work) / "engine-project"
    if project.exists():
        raise CiError("engine-project", "the engine project folder must be new")
    branding = project / "assets" / "branding"
    branding.mkdir(parents=True)
    for name in ("rabbitlands-icon.ico", "rabbitlands-icon.png"):
        shutil.copyfile(Path(repo) / "godot-client/assets/branding" / name, branding / name)
    settings = (Path(repo) / "godot-client/project.godot").read_text(encoding="utf-8")
    application = [line for line in settings.split("[application]", 1)[-1].split("\n[", 1)[0].splitlines()
                   if line.startswith(("config/name=", "config/version=", "config/description=",
                                       "config/icon=", "config/windows_native_icon="))]
    (project / "project.godot").write_text("config_version=5\n[application]\n" + "\n".join(application) + "\n",
                                           encoding="utf-8")
    (project / "export_presets.cfg").write_text(package_client.EXPORT_PRESETS, encoding="utf-8")
    if 'binary_format/embed_pck=false' not in package_client.EXPORT_PRESETS.split("[preset.1]", 1)[0]:
        raise CiError("engine-preset", "the game's Windows preset must not embed its pack")
    logs = Path(work) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    exported = Path(work) / "engine-export" / "RabbitLands.exe"
    exported.parent.mkdir(parents=True, exist_ok=True)
    run_godot(godot, ["--headless", "--path", str(project), "--import"], logs / "engine-import.log", timeout=300)
    run_godot(godot, ["--headless", "--path", str(project), "--export-release", "Windows Desktop", str(exported)],
              logs / "engine-export.log", timeout=300)
    if not exported.is_file():
        raise CiError("engine-export", "the engine export is incomplete")
    shutil.copyfile(exported, target)  # the tiny project's own .pck stays behind: content ships the game's
    return target


def ci_package(stage: Path, package_id: str, paths: list[str], parts_dir: Path) -> dict:
    """One CI package, written exactly like asset_packages.build writes a package."""
    import asset_packages
    import client_release
    import shared_release_assets
    from release_storage import PartWriter
    files = [{"path": relative, "size": (stage / relative).stat().st_size,
              "sha256": client_release.digest(stage / relative)}
             for relative in sorted(paths, key=lambda value: Path(stage / value))]
    archive = Path(parts_dir) / f"ci.pkg.{package_id}.zip"
    with PartWriter(archive, shared_release_assets.base(r2.REPOSITORY), client_release.PART_BYTES,
                    shared="partitioned") as writer:
        asset_packages.write_payload(stage, files, writer)
    return {"id": package_id, "sha256": writer.sha256, "size": writer.size,
            "unpacked_size": sum(entry["size"] for entry in files), "file_count": len(files), "files": files,
            "parts": writer.parts}


def write_root_files(root: Path, repo: Path, platform: str, version: str, commit: str) -> tuple[list, list]:
    """Launchers (after the helper exists, so they start it with --launch-only), the
    human-testing launchers and AUDIO-CREDITS.txt. Returns launch args and rows."""
    import client_runtime_package
    import package_client
    binary = root / helpers.BINARIES[platform]
    if not binary.is_file():
        raise CiError("root-order", "root files are written after the helper exists")
    launch_args = package_client.write_launchers(root, SERVER, Path(repo), version_suffix(version),
                                                 package_client.PLATFORMS[platform])
    client_runtime_package.write_launchers(root, platform)
    # The committed bytes, as the local stage copies them (no checkout line-ending conversion).
    credits = helpers.git_reader(Path(repo), commit)("assets/audio/CREDITS.txt")
    if credits is None:
        raise CiError("audio-credits", "assets/audio/CREDITS.txt is missing at the commit")
    (root / "AUDIO-CREDITS.txt").write_bytes(credits)
    if platform == "linux":
        for script in root.glob("RabbitLands*.sh"):
            script.chmod(0o755)
    skipped = {helpers.BINARIES[platform], helpers.UNINSTALLERS[platform]}
    rows = [{"name": path.name, "size": path.stat().st_size, "sha256": _digest(path)}
            for path in sorted(root.iterdir(), key=lambda item: item.name)
            if path.is_file() and path.name not in skipped]
    return launch_args, rows


def executables(*, platform: str, commit: str, repo: Path, godot: Path, content_dir: Path, out: Path, work: Path,
                template: Path | None = None, run_godot=None, native_builder=build_native,
                engine_exporter=export_engine,
                http=None, previous="auto") -> dict:
    """The build job: every CI-owned binary and root file of one platform -> artifact exec-P."""
    import client_runtime_package
    if run_godot is None:
        import package_client
        run_godot = package_client.run_godot
    out, work, repo = Path(out), Path(work), Path(repo)
    template = Path(template) if template else default_template(godot, platform)
    content_set = r2.parse_set_bytes((Path(content_dir) / "set.json").read_bytes())
    if content_set["commit"] != commit or content_set["platform"] != platform:
        raise CiError("content", "the content artifact is for another commit or platform")
    version = content_set["version"]
    public_pem = rm.commit_public_key(repo, commit)
    identity = release_identity(repo, commit, platform, public_pem, work / "identity")
    if out.exists() and any(out.iterdir()):
        raise CiError("out-not-empty", "exec output must start empty")
    staged, root, parts = work / "ci-stage", out / "root", out / "parts"
    for folder in (staged / "app", root, parts):
        folder.mkdir(parents=True, exist_ok=True)

    payload = native_builder(repo, commit, platform, work / "native")
    native = client_runtime_package.stage_payload(Path(payload), repo, staged / "app", platform)
    engine = engine_exporter(repo, platform, Path(godot), template, run_godot, work / "engine",
                             staged / rm.ENGINE_PATHS[platform])

    if previous == "auto":
        previous = helpers.previous_release(http, platform, public_pem) if http else None
    helper = helpers.provide(None, identity, platform=platform, godot=Path(godot), template=template,
                             run_godot=run_godot, work=work / "helper", out=root, previous=previous, http=http,
                             read=helpers.git_reader(repo, commit))
    launch_args, root_files = write_root_files(root, repo, platform, version, commit)

    native_paths = sorted(path.relative_to(staged).as_posix() for path in (staged / rm.NATIVE_PREFIX).rglob("*")
                          if path.is_file())
    packages = [ci_package(staged, rm.ENGINE_PACKAGE, [rm.ENGINE_PATHS[platform]], parts),
                ci_package(staged, rm.NATIVE_PACKAGE, native_paths, parts)]
    builder = content_set.get("builder") or {}
    library = staged / rm.NATIVE_PREFIX / client_runtime_package.LIBRARIES[platform]
    comparison = {"engine_sha256": _digest(engine), "local_engine_sha256": builder.get("local_engine_sha256"),
                  "native_library_sha256": _digest(library),
                  "local_native_library_sha256": builder.get("local_native_library_sha256")}
    comparison["engine_equal"] = comparison["engine_sha256"] == comparison["local_engine_sha256"]
    comparison["native_equal"] = comparison["native_library_sha256"] == comparison["local_native_library_sha256"]
    record = {"kind": EXEC_KIND, "schema": 1, "platform": platform, "commit": commit, "version": version,
              "ci_packages": packages, "helpers": {kind: helper.rows[kind] for kind in rm.HELPER_KINDS},
              "helpers_fingerprint": helper.fingerprint, "helpers_reused": helper.reused,
              "root_files": root_files, "launch_args": launch_args, "comparison": comparison,
              "native": {"source_digest": native.get("source_digest"), "cache_hit": False}}
    for package in packages:
        for part in package["parts"]:
            local = parts / part["url"].rsplit("/", 1)[1]
            if not local.is_file() or local.stat().st_size != part["size"] or _digest(local) != part["sha256"]:
                raise CiError("ci-part", local.name)
    _write(out / "exec.json", _json_bytes(record))
    if not comparison["engine_equal"]:
        _emit(f"warning: the CI {platform} engine differs from the local build's (QA record, not a trust gate)")
    return record


# --- sign -----------------------------------------------------------------------------------

def _load_exec(directory: Path, platform: str, commit: str) -> dict:
    record = _read_json(Path(directory) / "exec.json")
    if (not isinstance(record, dict) or record.get("kind") != EXEC_KIND or record.get("platform") != platform
            or record.get("commit") != commit):
        raise CiError("exec", f"the {platform} executables artifact is for another build")
    return record


def sign(*, commit: str, repo: Path, inputs: dict, key_pem: bytes, out: Path, sequence: int | None = None) -> dict:
    """Sign both platforms. `inputs[platform] = {source, set_sha256, content, exec}`.

    The set bytes come from content-P and must hash to the dispatched input (r2;
    for ci the leg's own set). The schema is the commit's reader's. The key
    stays in memory and is never written to disk.
    """
    if not inputs or not set(inputs) <= set(r2.PLATFORMS):
        raise CiError("arguments", "sign needs at least one platform")
    public_pem = rm.commit_public_key(repo, commit)
    private = rm.load_signing_key(key_pem, public_pem)
    capabilities = rm.commit_capabilities(repo, commit)
    sequence = int(time.time()) if sequence is None else sequence
    out = Path(out)
    records, envelopes = {}, {}
    for platform, item in sorted(inputs.items()):
        source = item["source"]
        set_bytes = (Path(item["content"]) / "set.json").read_bytes()
        digest = r2.sha256_hex(set_bytes)
        expected = item.get("set_sha256") or None
        if source == "r2" and expected is None:
            raise CiError("set-hash", f"{platform}: an r2 source needs the dispatched set SHA-256")
        if expected is not None and digest != expected:
            raise CiError("set-hash", f"{platform}: the content artifact is not the dispatched set")
        if source == "ci":
            _check_ci_content(item["content"], platform=platform, commit=commit, set_sha256=digest)
        content_set = r2.parse_set_bytes(set_bytes)
        r2.validate_set(content_set, public_key_sha256=r2.public_key_sha256(public_pem), commit=commit,
                        platform=platform, source=source, reader_cap=capabilities.reader_cap)
        executables_record = _load_exec(item["exec"], platform, commit)
        if executables_record["version"] != content_set["version"]:
            raise CiError("version", f"{platform}: executables and content name different versions")
        with tempfile.TemporaryDirectory(prefix="rl-identity-") as scratch:
            identity = release_identity(repo, commit, platform, public_pem, Path(scratch))
        release = rm.payload(identity=identity, version=content_set["version"],
                             content_packages=content_set["packages"], ci_packages=executables_record["ci_packages"],
                             helpers=executables_record["helpers"], launch_args=executables_record["launch_args"],
                             capabilities=capabilities, source=source, set_sha256=digest, sequence=sequence,
                             helpers_fingerprint=executables_record["helpers_fingerprint"],
                             root_files=executables_record["root_files"],
                             optional_packages=content_set.get("optional_packages") or None)
        envelope, gate = rm.sign_manifest(release, identity, capabilities, private, public_pem)
        name = f"{content_set['version']}-{platform}.json"
        envelopes[platform] = (name, envelope)
        records[platform] = {"manifest": name, "sha256": r2.sha256_hex(envelope), "bytes": len(envelope),
                             "margin": gate["margin"], "schema": release["schema"], "sequence": sequence,
                             "source": source, "set_sha256": digest}
    # Nothing is written unless every platform signed: a partial artifact never reaches `stage`.
    for platform, (name, envelope) in envelopes.items():
        _write(out / name, envelope)
        _write(out / f"RabbitLands-{platform}.json", envelope)
    _write(out / "sign.json", _json_bytes({"commit": commit, "platforms": records}))
    return records


def pointer(*, platform: str, manifest: Path, release_id: int, run_id: int, rollback: bool, key_pem: bytes,
            repo: Path, commit: str, out: Path, sequence: int | None = None) -> Path:
    """Sign a pointer to `manifest`. A forward pointer (publish) names this commit's
    own release; only a rollback pointer (repoint) may name an older commit's."""
    public_pem = rm.commit_public_key(repo, commit)
    private = rm.load_signing_key(key_pem, public_pem)
    data = Path(manifest).read_bytes()
    _, release = rm.verify(data, public_pem, limit=r2.MAX_ENVELOPE_BYTES)
    if type(rollback) is not bool or (not rollback and release.get("commit") != commit):
        raise CiError("pointer-commit", "a forward pointer names the dispatched commit's own manifest")
    envelope = rm.pointer_envelope(platform=platform, sequence=int(time.time()) if sequence is None else sequence,
                                   rollback=rollback, release_id=release_id, run_id=run_id, manifest=data,
                                   private_key=private, public_pem=public_pem)
    return _write(Path(out) / r2.pointer_asset_name(platform), envelope)


# --- installers -------------------------------------------------------------------------------

class VerifiedRows:
    """package_client.STORAGE shim for make_online_installer: rows signed in the envelope
    (content verified in content-P, CI parts staged and verified by GitHub) need no local copy."""

    def __init__(self, release: dict, source: Path):
        self.rows = {part["url"].rsplit("/", 1)[1]: (part["size"], part["sha256"]) for part in release["parts"]}
        self.source = source

    def part_matches(self, name: str, part: dict) -> bool:
        return self.rows.get(name) == (part["size"], part["sha256"])


def installer_preconditions(release: dict, repo: Path, commit: str) -> None:
    """setup.exe for a schema-3 or R2-hosted manifest needs the W2 Inno script and the
    HOOK-B8 setup helper; refuse rather than build an installer that cannot install."""
    import package_client
    script_schemas = getattr(package_client, "ONLINE_INSTALLER_SCHEMAS", (1, 2))
    if release["schema"] not in script_schemas:
        raise CiError("installer-schema", f"package_client's online installer lacks schema {release['schema']} (W2)")
    helper = rm._git_show(Path(repo), commit, "godot-client/tools/install_client_payload.gd") or ""
    if release["schema"] == rm.SCHEMA_CODEC and "Release.package_manifest(manifest)" not in helper:
        raise CiError("installer-helper", "install_client_payload.gd lacks the schema-3 gate (HOOK-B8)")
    hosted = any(part["url"].startswith(r2.DESKTOP_ASSETS) for part in release["parts"])
    if hosted and not getattr(package_client, "ONLINE_INSTALLER_R2_ROWS", False):
        raise CiError("installer-r2", "package_client's online installer does not accept R2 rows yet (W2)")


def godot_verify(envelope: Path, identity: dict, *, godot: Path, run_godot, work: Path, repo: Path,
                 commit: str) -> None:
    """The commit's own verify_client_release.gd and updater scripts on the envelope (public key only)."""
    read = helpers.git_reader(Path(repo), commit)
    files = helpers.project_files(None, identity, identity["platform"], read=read)
    project = helpers.write_project(files, Path(work) / "verify-project")
    script, request = Path(work) / "verify_client_release.gd", Path(work) / "verify-request.json"
    verifier = read("tools/verify_client_release.gd")
    if verifier is None:
        raise CiError("verifier", "tools/verify_client_release.gd is missing at the commit")
    script.write_bytes(verifier)
    request.write_text(json.dumps({"manifest": str(Path(envelope).resolve()), "identity": identity}), encoding="utf-8")
    run_godot(godot, ["--headless", "--path", str(project), "--import"], Path(work) / "verify-import.log", timeout=300)
    run_godot(godot, ["--headless", "--path", str(project), "--script", str(script), "--", str(request)],
              Path(work) / "verify.log", timeout=300)


def installers(*, platform: str, commit: str, repo: Path, envelope: Path, exec_dir: Path, out: Path, work: Path,
               godot: Path | None = None, iscc: Path | None = None, run_godot=None, online_installer=None,
               verify_with_godot: bool = True) -> Path:
    public_pem = rm.commit_public_key(repo, commit)
    data = Path(envelope).read_bytes()
    _, release = rm.verify(data, public_pem, limit=r2.MAX_ENVELOPE_BYTES)
    if release.get("commit") != commit or release.get("platform") != platform:
        raise CiError("envelope", "the envelope is for another commit or platform")
    identity = release_identity(repo, commit, platform, public_pem, Path(work) / "identity")
    if run_godot is None:
        import package_client
        run_godot = package_client.run_godot
    if verify_with_godot:
        godot_verify(Path(envelope), identity, godot=godot, run_godot=run_godot, work=Path(work) / "verify",
                     repo=repo, commit=commit)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    version = release["version"]
    if platform == "linux":
        import linux_download_helper
        script = linux_download_helper.bootstrap_script(release["updater"], json.loads(data))
        return _write(out / f"{version}-download.sh", script.encode("utf-8"))
    import package_client
    installer_preconditions(release, repo, commit)
    stage = Path(work) / version
    stage.mkdir(parents=True)
    for path in (Path(exec_dir) / "root").iterdir():
        shutil.copyfile(path, stage / path.name)
    (stage / "app" / "assets" / "branding").mkdir(parents=True)
    (stage / DESCRIPTOR).write_text(json.dumps(identity), encoding="utf-8")
    for name in ("rabbitlands-icon.ico", "rabbitlands-mark-64.png"):
        shutil.copyfile(Path(repo) / "godot-client/assets/branding" / name, stage / "app/assets/branding" / name)
    shutil.copyfile(envelope, stage.parent / f"{version}-windows.json")
    build = online_installer or package_client.make_online_installer
    previous_storage = package_client.STORAGE
    package_client.STORAGE = VerifiedRows(release, Path(repo) / "godot-client")
    try:
        setup = build(stage, godot, iscc, version_suffix(version), release["launch_args"], Path(work) / "logs")
    finally:
        package_client.STORAGE = previous_storage
    target = out / f"{version}-setup.exe"
    shutil.copyfile(setup, target)
    return target


# --- stage (GitHub uploads; no R2) ------------------------------------------------------------

def stage_uploads(*, commit: str, exec_dirs: dict, envelopes: Path, installer_dirs: dict, work: Path,
                  public_pem: bytes) -> list[tuple[Path, dict]]:
    """(local file, {name, size, sha256}) for every upload, checked before any is sent.

    Pool uploads are exactly the CI rows of the signed manifests (engine and
    native-runtime parts, the helpers); the draft gets those manifests, their
    alias and the installers (checked by the workflow's artifact digests).
    """
    import shared_release_assets
    uploads, signed = [], _read_json(Path(envelopes) / "sign.json")["platforms"]
    links = Path(work) / "pool"
    links.mkdir(parents=True, exist_ok=True)
    for platform, directory in sorted(exec_dirs.items()):
        manifest = Path(envelopes) / signed[platform]["manifest"]
        data = manifest.read_bytes()
        if r2.sha256_hex(data) != signed[platform]["sha256"]:
            raise CiError("stage-file", manifest.name)
        _, release = rm.verify(data, public_pem, limit=r2.MAX_ENVELOPE_BYTES)
        if release.get("platform") != platform or release.get("commit") != commit:
            raise CiError("stage-manifest", manifest.name)
        for package in release["packages"]:
            if package["id"] in r2.CI_PACKAGE_IDS:
                for part in package["parts"]:
                    uploads.append((Path(directory) / "parts" / part["url"].rsplit("/", 1)[1], part))
        binary = Path(directory) / "root" / helpers.BINARIES[platform]
        for kind in rm.HELPER_KINDS:
            row = release[kind]
            name = shared_release_assets.name(row["sha256"], kind, HELPER_EXTENSIONS[platform])
            link = links / name
            if not link.exists():
                try:
                    os.link(binary, link)
                except OSError:
                    shutil.copyfile(binary, link)
            uploads.append((link, row))
        for path in (manifest, Path(envelopes) / f"RabbitLands-{platform}.json"):
            uploads.append((path, {"size": len(data), "sha256": signed[platform]["sha256"]}))
        version = release["version"]
        installer = Path(installer_dirs[platform]) / (f"{version}-setup.exe" if platform == "windows"
                                                      else f"{version}-download.sh")
        uploads.append((installer, {"size": installer.stat().st_size, "sha256": _digest(installer)}))
    rows = []
    for path, row in uploads:
        if not path.is_file() or path.stat().st_size != row["size"] or _digest(path) != row["sha256"]:
            raise CiError("stage-file", path.name)
        rows.append((path, {"name": path.name, "size": row["size"], "sha256": row["sha256"]}))
    return rows


def stage(*, commit: str, release_id: int, exec_dirs: dict, envelopes: Path, installer_dirs: dict, work: Path,
          public_pem: bytes, sink=None) -> dict:
    rows = stage_uploads(commit=commit, exec_dirs=exec_dirs, envelopes=envelopes, installer_dirs=installer_dirs,
                         work=work, public_pem=public_pem)
    if sink is None:
        import runner_release
        sink = runner_release.GitHubSink(release_id)
    for path, row in rows:
        sink.accept(path, row)
    return {"uploads": [row for _, row in rows], "uploaded_bytes": getattr(sink, "uploaded_bytes", None),
            "reused_bytes": getattr(sink, "reused_bytes", None)}


# --- e2e ---------------------------------------------------------------------------------------

def run_logged(command: list, log: Path, *, timeout: int, env: dict | None = None,
               cwd: Path | None = None) -> tuple[int, str]:
    """Run a command with stdout+stderr to `log`; a timeout kills it (and its group on Linux)."""
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("wb") as output:
        process = subprocess.Popen([str(item) for item in command], stdout=output, stderr=subprocess.STDOUT,
                                   env=env, cwd=cwd, start_new_session=os.name != "nt")
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                if os.name != "nt":
                    os.killpg(process.pid, 9)  # a sudo'd child may refuse: the job timeout is the backstop
                else:
                    process.kill()
            except (PermissionError, ProcessLookupError):
                process.kill()
            process.wait()
            code = -9
    return code, log.read_text(encoding="utf-8", errors="replace")


class E2E:
    """The e2e job for one platform. `run(command, log, timeout=, env=, cwd=) -> (code, text)` is injectable."""

    def __init__(self, *, platform: str, envelope: Path, exec_dir: Path, work: Path, public_pem: bytes, run=run_logged,
                 user: str | None = None, alive=None, clock=time.monotonic, sleep=time.sleep):
        self.platform, self.envelope, self.exec_dir, self.work = platform, Path(envelope), Path(exec_dir), Path(work)
        _, self.release = rm.verify(self.envelope.read_bytes(), public_pem, limit=r2.MAX_ENVELOPE_BYTES)
        if self.release.get("platform") != platform:
            raise CiError("envelope", "the envelope is for another platform")
        self.run, self.user = run, user
        self.alive = alive or self._alive
        self.clock, self.sleep = clock, sleep
        self.root = self.work / "install" / "RabbitLands"
        self.logs = self.work / "logs"
        self.receipt = {"kind": E2E_KIND, "schema": 1, "platform": platform, "commit": self.release["commit"],
                        "version": self.release["version"], "steps": []}

    # Linux runs everything as an unprivileged throwaway user under xvfb-run.
    def command(self, argv: list, env: dict | None = None, *, display: bool = True) -> list:
        if self.platform != "linux":
            return [str(item) for item in argv]
        home = self.work / "home"
        variables = {"HOME": str(home), "XDG_DATA_HOME": str(home / ".local/share"),
                     "XDG_CONFIG_HOME": str(home / ".config"), "XDG_CACHE_HOME": str(home / ".cache"),
                     "PATH": "/usr/local/bin:/usr/bin:/bin", **(env or {})}
        prefix = ["sudo", "-n", "-u", self.user, "--"] if self.user else []
        return [*prefix, "env", "-i", *(f"{key}={value}" for key, value in sorted(variables.items())),
                *(["xvfb-run", "-a"] if display else []), *[str(item) for item in argv]]

    def environment(self, extra: dict | None = None) -> dict | None:
        import full_optimization_package
        if self.platform == "linux":
            return None  # `env -i` in command() sets everything the child sees
        scratch = self.work / "userdata"
        scratch.mkdir(parents=True, exist_ok=True)
        return {**full_optimization_package.clean_environment(), "APPDATA": str(scratch),
                "LOCALAPPDATA": str(scratch), **(extra or {})}

    def _alive(self) -> bool:
        if self.platform == "linux":
            if not self.user:
                return False
            return subprocess.run(["pgrep", "-u", self.user], capture_output=True).returncode == 0
        listing = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
        return any(name.strip('"').lower().startswith(("handoff-", "rabbitlands-updater", "rabbitlands-uninstall"))
                   for name in (line.split(",", 1)[0] for line in listing.splitlines()))

    def prepare_user(self) -> None:
        if self.platform != "linux" or not self.user:
            return
        # The user owns only what the shipped binaries write: the install, its home
        # and the download.sh target. Logs stay with the runner, outside its reach.
        # It must be able to reach them: every parent of --work needs o+x (use for
        # example /mnt/rl-e2e on a hosted runner, not the runner's own home).
        for parent in self.work.resolve().parents:
            if not os.stat(parent).st_mode & 0o001:
                raise CiError("e2e-work", f"{parent} is not traversable by the unprivileged e2e user")
        owned = [str(self.work / name) for name in ("install", "home", "download-sh")]
        for command in (["sudo", "-n", "useradd", "--no-create-home", "--home-dir", str(self.work / "home"),
                         "--shell", "/bin/sh", self.user],
                        ["sudo", "-n", "chown", "-R", f"{self.user}:{self.user}", *owned]):
            code, _ = self.run(command, self.logs / "user.log", timeout=60)
            if code:
                raise CiError("e2e-user", "the unprivileged e2e user could not be prepared")

    def step(self, name: str, ok: bool, **detail) -> None:
        self.receipt["steps"].append({"step": name, "ok": ok, **detail})
        if not ok:
            raise CiError("e2e-" + name, json.dumps(detail)[:300])

    def stage_inputs(self, installer: Path | None) -> Path | None:
        """Copy the shipped updater, the envelope and the installer into the e2e folder,
        before it is handed to the unprivileged user (inputs only from artifacts)."""
        source = self.exec_dir / "root" / helpers.BINARIES[self.platform]
        updater = self.work / "bin" / source.name
        updater.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, updater)
        row = self.release["updater"]
        self.step("updater-row", updater.stat().st_size == row["size"] and _digest(updater) == row["sha256"])
        if self.platform == "linux":
            updater.chmod(0o755)
        shutil.copyfile(self.envelope, self.work / "install-manifest.json")
        for folder in (self.root.parent, self.work / "home", self.work / "download-sh", self.logs):
            folder.mkdir(parents=True, exist_ok=True)
        if installer is None:
            return None
        copy = self.work / "bin" / Path(installer).name
        shutil.copyfile(installer, copy)
        return copy

    def install(self) -> None:
        updater = self.work / "bin" / helpers.BINARIES[self.platform]
        manifest = self.work / "install-manifest.json"
        argv = [updater, "--headless", "--", "--root", self.root, "--install-update", "--update-only",
                "--install-manifest", manifest]
        code, text = self.run(self.command(argv), self.logs / "install.log", timeout=DOWNLOAD_WAIT_SECONDS,
                              env=self.environment())
        self.step("install-started", code == 0, code=code)
        self.wait_installed()

    def wait_installed(self, timeout: int = DOWNLOAD_WAIT_SECONDS) -> None:
        """A first install hands over to the downloaded helper, which finishes alone."""
        deadline, quiet = self.clock() + timeout, 0
        while self.clock() < deadline:
            quiet = 0 if self.alive() else quiet + 1
            if quiet >= 3:
                break
            self.sleep(5)
        installed = self.root / DESCRIPTOR
        descriptor = r2._parse_json(installed.read_bytes()) if installed.is_file() else None
        self.step("installed", isinstance(descriptor, dict) and descriptor.get("commit") == self.release["commit"],
                  quiet_polls=quiet)

    def check_files(self) -> None:
        rows = [(entry["path"], entry["size"], entry["sha256"]) for package in self.release["packages"]
                for entry in package["files"]]

        def bad(row):
            path = self.root / row[0]
            return row[0] if not path.is_file() or path.stat().st_size != row[1] or _digest(path) != row[2] else None
        with ThreadPoolExecutor(WORKERS) as pool:
            problems = [item for item in pool.map(bad, rows) if item]
        helper = self.root / helpers.BINARIES[self.platform]
        helper_ok = helper.is_file() and _digest(helper) == self.release["updater"]["sha256"]
        self.step("installed-files", not problems and helper_ok, files=len(rows), problems=problems[:10])

    def smoke(self, profile: str) -> dict:
        import full_optimization_package
        import package_client
        binary = self.root / rm.ENGINE_PATHS[self.platform]
        argv = [binary, "--headless", "--quit-after", "600"]
        if profile == "human-testing":
            argv += ["--", "--optimization-profile=human-testing"]
        before = self._snapshot()
        code, text = self.run(self.command(argv, {"ELORIA_VRAM_SELF_TEST": "1"}, display=False),
                              self.logs / f"smoke-{profile}.log", timeout=SMOKE_TIMEOUT,
                              env=self.environment({"ELORIA_VRAM_SELF_TEST": "1"}), cwd=self.root / "app")
        failures = [line for line in text.splitlines() if any(item in line for item in package_client.SMOKE_FAILURES)]
        self.step(f"smoke-{profile}", code == 0 and not failures and package_client.VRAM_SELF_TEST_OK in text,
                  code=code, failures=failures[:10])
        value, problem = None, None
        try:
            value = full_optimization_package.validate_startup(text, profile=profile)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            problem = str(error)[:200]
        runtime = value.get("runtime", {}) if isinstance(value, dict) else {}
        # validate_startup already pins legacy to the legacy backend; the opt-in
        # profile must run the CI-built native library (D-NATIVE loads it for everyone).
        native = runtime.get("native_available") is True and runtime.get("mode") == "rust"
        self.step(f"startup-{profile}", problem is None and (native or profile == "legacy"), error=problem,
                  runtime=runtime)
        self.step(f"smoke-{profile}-clean", self._snapshot() == before)
        return value

    def _snapshot(self) -> dict:
        return {path.relative_to(self.root).as_posix(): (stat.st_size, stat.st_mtime_ns)
                for path in self.root.rglob("*") if path.is_file()
                for stat in (path.stat(),) if not path.relative_to(self.root).as_posix().startswith(".")}

    def recheck(self) -> None:
        helper = self.root / helpers.BINARIES[self.platform]
        before = self._snapshot()
        argv = [helper, "--headless", "--", "--root", self.root, "--update-only", "--install-manifest",
                self.work / "install-manifest.json"]
        code, text = self.run(self.command(argv), self.logs / "recheck.log", timeout=1800, env=self.environment())
        total = len(self.release["packages"])
        quiet = f"0 of {total} packages needed downloads" in text and "Downloading changed packages" not in text
        self.step("recheck", code == 0 and quiet and self._snapshot() == before, code=code)

    def download_script(self, script: Path) -> None:
        text = Path(script).read_text(encoding="utf-8")
        row = self.release["updater"]
        embedded = text.split("<<'RABBITLANDS_MANIFEST'\n", 1)[-1].split("\nRABBITLANDS_MANIFEST", 1)[0]
        ok = (row["url"] in text and f"printf '%s  %s\\n' '{row['sha256']}'" in text
              and json.loads(embedded) == json.loads(self.envelope.read_bytes()))
        self.step("download-sh-content", ok)
        target = self.work / "download-sh"
        # download.sh starts the game after installing; the timeout ends it.
        code, _ = self.run(self.command(["timeout", "-k", "10", "900", "sh", script, target]),
                           self.logs / "download-sh.log", timeout=1000)
        installed = target / "RabbitLands" / DESCRIPTOR
        value = r2._parse_json(installed.read_bytes()) if installed.is_file() else None
        self.step("download-sh-run", isinstance(value, dict) and value.get("commit") == self.release["commit"],
                  code=code)

    def setup(self, installer: Path) -> None:
        import package_client
        need = int(1.25 * package_client.online_installer_space(self.release))
        target = self.work / "setup-install"
        free = shutil.disk_usage(self.work).free
        if free < need:
            self.receipt["steps"].append({"step": "setup-exe", "ok": None, "skipped": "disk", "free": free,
                                          "need": need, "note": "run the local pre-promote setup check"})
            return
        code, _ = self.run([installer, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", f"/DIR={target}",
                            f"/LOG={self.logs / 'setup.log'}"], self.logs / "setup-run.log",
                           timeout=DOWNLOAD_WAIT_SECONDS)
        value = r2._parse_json((target / DESCRIPTOR).read_bytes()) if (target / DESCRIPTOR).is_file() else None
        self.step("setup-exe", code == 0 and isinstance(value, dict) and value.get("commit") == self.release["commit"],
                  code=code)

    def run_all(self, *, installer: Path | None = None) -> dict:
        started = self.clock()
        installer = self.stage_inputs(installer)
        self.prepare_user()
        self.install()
        self.check_files()
        for profile in ("legacy", "human-testing"):
            self.smoke(profile)
        self.recheck()
        if installer and self.platform == "linux":
            self.download_script(installer)
        elif installer:
            self.setup(installer)
        self.receipt["seconds"] = round(self.clock() - started, 1)
        self.receipt["disk_free"] = shutil.disk_usage(self.work).free
        return self.receipt


# --- Artifact digests ---------------------------------------------------------------------------

def tree_digest(directory: Path) -> str:
    """SHA-256 over the (path, size, SHA-256) rows of every file in an artifact folder.

    Rows are ordered by their POSIX path string, never by Path objects: Windows
    compares paths case-insensitively and by component, so a Windows producer
    and an ubuntu consumer would otherwise order README.txt and RabbitLands.bat
    differently and disagree on the digest of the same files.
    """
    directory = Path(directory)
    rows = []
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise CiError("artifact-link", path.name)
        if path.is_file():
            rows.append([path.relative_to(directory).as_posix(), path.stat().st_size, _digest(path)])
    rows.sort(key=lambda row: row[0])
    return hashlib.sha256(r2.canonical_bytes(rows)).hexdigest()


def check_artifact(directory: Path, expected: str) -> str:
    actual = tree_digest(directory)
    if not rm._is_hash(expected) or actual != expected:
        raise CiError("artifact-digest", f"{Path(directory).name} differs from what its producer exported")
    return actual


# --- CLI ------------------------------------------------------------------------------------------

def _pop_key() -> bytes:
    value = os.environ.pop(SIGNING_SECRET, "")
    if not value:
        raise CiError("signing-key-missing", f"{SIGNING_SECRET} is not available to this job")
    if not value.isascii():
        raise CiError("signing-key", "the signing key is not an ASCII PEM key")  # never echo the offending text
    return value.encode("ascii")


def _summary(text: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with Path(path).open("a", encoding="utf-8") as output:
            output.write(text)


def _output(name: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with Path(path).open("a", encoding="utf-8") as output:
            output.write(f"{name}={value}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    content = commands.add_parser("verify-content")
    content.add_argument("--platform", choices=r2.PLATFORMS, required=True)
    content.add_argument("--sha256", required=True)
    content.add_argument("--commit", required=True)
    content.add_argument("--work", type=Path, required=True)
    content.add_argument("--out", type=Path, required=True)
    leg = commands.add_parser("build-content")
    leg.add_argument("--platform", choices=r2.PLATFORMS, required=True)
    leg.add_argument("--commit", required=True)
    leg.add_argument("--release-id", required=True)
    leg.add_argument("--dry-run", choices=("true", "false"), required=True)
    leg.add_argument("--cache", type=Path, required=True)
    leg.add_argument("--work", type=Path, required=True)
    leg.add_argument("--out", type=Path, required=True)
    keys = commands.add_parser("content-cache-key")
    keys.add_argument("--platform", choices=r2.PLATFORMS, required=True)
    keys.add_argument("--commit", required=True)
    build = commands.add_parser("executables")
    build.add_argument("--platform", choices=r2.PLATFORMS, required=True)
    build.add_argument("--commit", required=True)
    build.add_argument("--godot", type=Path, required=True)
    build.add_argument("--template", type=Path)
    build.add_argument("--content", type=Path, required=True)
    build.add_argument("--work", type=Path, required=True)
    build.add_argument("--out", type=Path, required=True)
    signing = commands.add_parser("sign")
    signing.add_argument("--commit", required=True)
    for platform in r2.PLATFORMS:
        signing.add_argument(f"--{platform}-source", choices=r2.SOURCES)
        signing.add_argument(f"--{platform}-set-sha256", default="")
        signing.add_argument(f"--{platform}-content", type=Path)
        signing.add_argument(f"--{platform}-exec", type=Path)
    signing.add_argument("--out", type=Path, required=True)
    point = commands.add_parser("pointer")
    point.add_argument("--platform", choices=r2.PLATFORMS, required=True)
    point.add_argument("--commit", required=True)
    point.add_argument("--manifest", type=Path, required=True)
    point.add_argument("--release-id", type=int, required=True)
    point.add_argument("--run-id", type=int, required=True)
    point.add_argument("--rollback", action="store_true")
    point.add_argument("--out", type=Path, required=True)
    setup = commands.add_parser("installers")
    setup.add_argument("--platform", choices=r2.PLATFORMS, required=True)
    setup.add_argument("--commit", required=True)
    setup.add_argument("--envelope", type=Path, required=True)
    setup.add_argument("--exec", type=Path, required=True)
    setup.add_argument("--godot", type=Path, required=True)
    setup.add_argument("--iscc", type=Path)
    setup.add_argument("--work", type=Path, required=True)
    setup.add_argument("--out", type=Path, required=True)
    upload = commands.add_parser("stage")
    upload.add_argument("--commit", required=True)
    upload.add_argument("--release-id", type=int, required=True)
    upload.add_argument("--envelopes", type=Path, required=True)
    for platform in r2.PLATFORMS:
        upload.add_argument(f"--{platform}-exec", type=Path, required=True)
        upload.add_argument(f"--{platform}-installer", type=Path, required=True)
    upload.add_argument("--work", type=Path, required=True)
    test = commands.add_parser("e2e")
    test.add_argument("--platform", choices=r2.PLATFORMS, required=True)
    test.add_argument("--envelope", type=Path, required=True)
    test.add_argument("--exec", type=Path, required=True)
    test.add_argument("--installer", type=Path)
    test.add_argument("--work", type=Path, required=True)
    test.add_argument("--receipt", type=Path, required=True)
    digest = commands.add_parser("artifact-digest")
    digest.add_argument("--dir", type=Path, required=True)
    digest.add_argument("--expect", default="")
    digest.add_argument("--output-name", default="")
    return parser


def _dispatch(args) -> dict | str:
    if args.command == "verify-content":
        record = verify_content(platform=args.platform, set_sha256=args.sha256, commit=args.commit, repo=REPO,
                                http=Fetcher(), work=args.work, out=args.out)
        _summary((args.out / "summary.md").read_text(encoding="ascii"))
        return record
    if args.command == "content-cache-key":
        keys = content_cache_keys(git_runner(REPO), args.commit, args.platform)
        for name, value in keys.items():
            _output(name, value)
        return keys
    if args.command == "build-content":
        import actions_release
        dispatched = actions_release.dispatch_commit(actions_release.R2_WORKFLOW)
        actions_release.no_signing_key()
        if args.commit != dispatched:
            raise CiError("commit", "build-content builds the dispatched commit only")
        record = ContentLeg(platform=args.platform, commit=args.commit, release_id=args.release_id,
                            dry_run=args.dry_run == "true", repo=REPO, work=args.work, out=args.out,
                            cache=args.cache).run()
        _summary((args.out / "summary.md").read_text(encoding="ascii"))
        return {key: record[key] for key in ("platform", "commit", "source", "set_sha256", "uploaded")}
    if args.command == "executables":
        return executables(platform=args.platform, commit=args.commit, repo=REPO, godot=args.godot,
                           template=args.template, content_dir=args.content, out=args.out, work=args.work,
                           http=Fetcher())
    if args.command == "sign":
        inputs = {platform: {"source": getattr(args, f"{platform}_source"),
                             "set_sha256": getattr(args, f"{platform}_set_sha256"),
                             "content": getattr(args, f"{platform}_content"), "exec": getattr(args, f"{platform}_exec")}
                  for platform in r2.PLATFORMS if getattr(args, f"{platform}_source")}
        return sign(commit=args.commit, repo=REPO, inputs=inputs, key_pem=_pop_key(), out=args.out)
    if args.command == "pointer":
        return str(pointer(platform=args.platform, manifest=args.manifest, release_id=args.release_id,
                           run_id=args.run_id, rollback=args.rollback, key_pem=_pop_key(), repo=REPO,
                           commit=args.commit, out=args.out))
    if args.command == "installers":
        return str(installers(platform=args.platform, commit=args.commit, repo=REPO, envelope=args.envelope,
                              exec_dir=args.exec, out=args.out, work=args.work, godot=args.godot, iscc=args.iscc))
    if args.command == "stage":
        return stage(commit=args.commit, release_id=args.release_id, envelopes=args.envelopes, work=args.work,
                     public_pem=rm.commit_public_key(REPO, args.commit),
                     exec_dirs={p: getattr(args, f"{p}_exec") for p in r2.PLATFORMS},
                     installer_dirs={p: getattr(args, f"{p}_installer") for p in r2.PLATFORMS})
    if args.command == "e2e":
        user = f"rl-e2e-{secrets.token_hex(4)}" if args.platform == "linux" else None
        runner = E2E(platform=args.platform, envelope=args.envelope, exec_dir=args.exec, work=args.work,
                     public_pem=(CLIENT / "data/update_public.pem").read_bytes(), user=user)
        try:
            return runner.run_all(installer=args.installer)
        finally:
            _write(args.receipt, _json_bytes(runner.receipt))
    value = tree_digest(args.dir) if not args.expect else check_artifact(args.dir, args.expect)
    if args.output_name:
        _output(args.output_name, value)
    return value


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = _dispatch(args)
    except r2.DesktopR2Error as error:
        _emit(f"Refused: {error}", error=True)
        return 2
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        _emit(f"Failed: {type(error).__name__}: {str(error)[:300]}", error=True)
        return 1
    _emit(result if isinstance(result, str) else json.dumps(result, sort_keys=True, default=str)[:4000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
