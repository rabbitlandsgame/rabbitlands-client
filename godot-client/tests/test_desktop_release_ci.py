"""The Actions-side release tool (tools/desktop_release_ci.py) with fakes for every outside system.

No network, R2, GitHub, compiler or Godot: HTTPS is a dictionary, Godot,
the native build and the shipped binaries are fake runs, the commit is a
throwaway Git repository and the release key is a throwaway RSA key.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import zipfile

import pytest

GODOT = Path(__file__).resolve().parents[1]
TOOLS = GODOT / "tools"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import desktop_r2 as r2  # noqa: E402
import desktop_release_ci as ci  # noqa: E402
import release_manifest as rm  # noqa: E402
import upload_desktop_assets as up  # noqa: E402
import test_release_manifest as fx  # noqa: E402

key = fx.key
other_key = fx.other_key
SEQUENCE = fx.SEQUENCE


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --- A commit with an R2-aware reader ---------------------------------------------------

def git(cwd, *args) -> str:
    return fx.git(cwd, *args)


def native_inputs() -> dict:
    import client_runtime_package
    files = {"godot-client/native/client_runtime/Cargo.toml": b"[package]\nname = \"client_runtime\"\n",
             "godot-client/native/client_runtime/src/lib.rs": b"// runtime\n",
             "godot-client/native/client_runtime/CMakeLists.txt": b"project(client_runtime)\n"}
    for relative in client_runtime_package.EXTERNAL_SOURCE_INPUTS:
        files[relative.as_posix()] = b"// " + relative.name.encode() + b"\n"
    return files


def helper_sources(*, reader: bool) -> dict:
    files = {}
    for name in ("release.gd", "launcher.gd", "launch_options.gd", "package_updates.gd", "package_download.gd",
                 "update_transport.gd", "bootstrap.gd", "uninstall.gd", "startup_update.gd"):
        data = (GODOT / "src/updates" / name).read_bytes()
        if reader and name == "release.gd":
            data += b"\n" + fx.SCHEMA3_LINE.encode() + fx.R2_LINE.encode()
        if reader and name == "package_updates.gd":
            data = data.replace(b"release.packages.size() > 850", b"release.packages.size() > 2000")
        files[f"godot-client/src/updates/{name}"] = data
    for name in ("rabbitlands-icon.png", "rabbitlands-icon.ico", "rabbitlands-mark-64.png"):
        files[f"godot-client/assets/branding/{name}"] = (GODOT / "assets/branding" / name).read_bytes()
    for name in ("verify_client_release.gd", "install_client_payload.gd"):
        files[f"godot-client/tools/{name}"] = (TOOLS / name).read_bytes()
    return files


@pytest.fixture(scope="module")
def repo(tmp_path_factory, key):
    path = tmp_path_factory.mktemp("repo")
    git(path, "init", "-q", "-b", "develop")
    old = fx.commit_tree(path, {rm.PUBLIC_KEY: key.public, **helper_sources(reader=False), **native_inputs(),
                                "godot-client/assets/audio/CREDITS.txt": b"Audio credits\n",
                                "godot-client/project.godot": b'[application]\nconfig/name="Rabbit Lands"\n'},
                         "reader without R2 rows")
    reader = fx.commit_tree(path, helper_sources(reader=True), "R2-aware reader")
    commit = fx.commit_tree(path, {"godot-client/data/notes.txt": b"release\n"}, "release")
    return type("Repo", (), {"path": path, "old": old, "reader": reader, "commit": commit})


def identity_of(repo, platform, key, tmp_path, commit=None):
    return ci.release_identity(repo.path, commit or repo.commit, platform, key.public, tmp_path / "id")


# --- A Godot PCK and a local stage --------------------------------------------------------------

def make_pck(entries: dict, *, fmt=3, flags=2, magic=b"GDPC") -> bytes:
    base, data, offsets = 112, b"", {}
    for name, content in entries.items():
        offsets[name] = len(data)
        data += content + b"\0" * (-len(content) % 16)
    directory = struct.pack("<I", len(entries))
    for name, content in entries.items():
        raw = ("res://" + name).encode()
        raw += b"\0" * (-len(raw) % 4)
        directory += struct.pack("<I", len(raw)) + raw + struct.pack("<QQ16sI", offsets[name], len(content),
                                                                     hashlib.md5(content).digest(), 0)
    header = struct.pack("<4sIIIIIQQ", magic, fmt, 4, 7, 2, flags, base, base + len(data)) + b"\0" * 64
    return header + b"\0" * (base - len(header)) + data + directory


def core_pck(identity: dict, extensions=None, **extra) -> bytes:
    entries = {"project.binary": b"ECFG", "data/client_release.json": json.dumps(identity).encode(),
               "src/app/main.tscn": b"[gd_scene]\n", **extra}
    if extensions is not None:
        entries[".godot/extension_list.cfg"] = "".join(line + "\n" for line in extensions).encode()
    return make_pck(entries)


def make_stage(root: Path, platform: str, identity: dict, *, pck: bytes | None = None, descriptor=None,
               extra=None) -> Path:
    content = {**fx.CONTENT, "app/RabbitLands.pck": pck if pck is not None else core_pck(identity),
               **(extra or {})}
    stage = fx.make_stage(root, platform, None, commit=identity["commit"], content=content)
    meta = json.dumps(descriptor if descriptor is not None else identity).encode()
    (stage / "app/client-release.json").write_bytes(meta)
    (stage / "app/data/client_release.json").write_bytes(meta)
    return stage


def make_set(stage: Path, platform: str, identity: dict, pem: bytes, work: Path, *, source="r2",
             mutate=None, builder=None) -> tuple[dict, dict]:
    """desktop_content's set for `stage` plus the part bytes, by URL."""
    packages = fx.content_packages(stage, work, source)
    parts = {}
    for path in (work / "view").glob("RabbitLands-pkg-*.zip.part"):
        digest = path.name.removeprefix("RabbitLands-pkg-").removesuffix(".zip.part")
        parts[r2.derived_part_url(digest, source)] = path.read_bytes()
    content_set = {
        "kind": r2.SET_KIND, "set_schema": r2.SET_SCHEMA, "source": source, "repository": r2.REPOSITORY,
        "commit": identity["commit"], "platform": platform, "version": stage.name,
        "public_key_sha256": r2.public_key_sha256(pem), "asset_base": r2.DESKTOP_ASSETS,
        "ci_paths": [*r2.CI_PATHS, *r2.CI_PREFIXES], "packages": packages, "optional_packages": [],
        "builder": builder or {"mode": "release", "tools_commit": identity["commit"], "tools_dirty": False,
                               "release_build": True, "local_engine_sha256": "0" * 64,
                               "local_native_library_sha256": "1" * 64, "package_format": "deflate1"},
        "qualification": {"smoke": ["legacy", "human-testing"], "split_pck": False}}
    if mutate:
        mutate(content_set, parts)
    return content_set, parts


class FakeHttp:
    """Anonymous HTTPS as a dictionary; records every call in order."""

    def __init__(self, objects=None):
        self.objects = dict(objects or {})
        self.calls = []

    def request(self, method, url, *, limit, headers=None, keep_body=True):
        self.calls.append((method, url))
        body = self.objects.get(url)
        if body is None:
            return up.HttpResponse(404, {})
        if method == "HEAD":
            return up.HttpResponse(200, {"content-length": str(len(body))})
        if len(body) > limit:
            raise up.UploadError("http-too-large", url)
        return up.HttpResponse(200, {}, body, sha(body), len(body))

    def download(self, url, path, *, limit):
        self.calls.append(("GET", url))
        body = self.objects.get(url)
        if body is None:
            return 404, 0, ""
        Path(path).write_bytes(body[:limit])
        return 200, min(len(body), limit), sha(body[:limit])

    def gets(self):
        return [url for method, url in self.calls if method == "GET"]


def publish_set(http: FakeHttp, content_set: dict, parts: dict, platform="windows") -> str:
    data = r2.canonical_bytes(content_set)
    http.objects[r2.set_url(platform, sha(data))] = data
    http.objects.update(parts)
    return sha(data)


@pytest.fixture
def scene(tmp_path, repo, key):
    """A valid r2 content set of `repo.commit` on a fake custom domain."""
    identity = identity_of(repo, "windows", key, tmp_path)
    stage = make_stage(tmp_path / "local", "windows", identity)
    content_set, parts = make_set(stage, "windows", identity, key.public, tmp_path / "pack")
    http = FakeHttp()
    digest = publish_set(http, content_set, parts)
    return type("Scene", (), {"identity": identity, "stage": stage, "set": content_set, "parts": parts,
                              "http": http, "sha256": digest})


def run_verify(scene, repo, tmp_path, **changes):
    options = dict(platform="windows", set_sha256=scene.sha256, commit=repo.commit, repo=repo.path,
                   http=scene.http, work=tmp_path / "work", out=tmp_path / "content-windows", published=None)
    options.update(changes)
    return ci.verify_content(**options)


# --- verify-content -------------------------------------------------------------------------

def test_verify_content_accepts_a_valid_set_and_writes_the_artifact(scene, repo, tmp_path):
    record = run_verify(scene, repo, tmp_path)
    out = tmp_path / "content-windows"
    assert (out / "set.json").read_bytes() == r2.canonical_bytes(scene.set)
    assert record["set_sha256"] == scene.sha256 and record["reader"] == {"schema": 3, "reader_cap": 2000}
    assert len(record["verified_packages"]) == len(scene.set["packages"])
    assert record["core_pck"]["extensions"] == []
    summary = (out / "summary.md").read_text(encoding="ascii")
    assert scene.sha256 in summary and "core `client` package changed: yes" in summary
    assert json.loads((out / "verified.json").read_text())["kind"] == ci.CONTENT_KIND
    assert not list((tmp_path / "work/parts").iterdir())  # downloaded parts are released after checking


def test_head_comes_before_every_get(scene, repo, tmp_path):
    run_verify(scene, repo, tmp_path)
    seen = set()
    for method, url in scene.http.calls:
        if method == "HEAD":
            seen.add(url)
        else:
            assert url in seen, url
    assert len([1 for method, _ in scene.http.calls if method == "HEAD"]) >= len(scene.parts) + 1


def test_only_packages_the_published_release_lacks_are_downloaded(scene, repo, tmp_path):
    known = [package for package in scene.set["packages"] if package["id"] not in r2.REQUIRED_PACKAGES][:3]
    assert known
    # an R2-era published release names the same R2 part URLs: those parts were fetched by its content job
    published = {"commit": fx.PARENT, "version": "RabbitLands-Windows-20261101-fedcba987", "packages": known}
    record = run_verify(scene, repo, tmp_path, published=published)
    known_urls = {part["url"] for package in known for part in package["parts"]}
    assert not known_urls & set(scene.http.gets())
    assert set(scene.http.gets()) - known_urls  # the new packages are fetched
    heads = {url for method, url in scene.http.calls if method == "HEAD"}
    assert known_urls <= heads  # still present on R2
    assert len(record["verified_packages"]) == len(scene.set["packages"]) - len(known)
    assert record["diff"]["unchanged"] == len(known) and record["diff"]["previous_commit"] == fx.PARENT
    # a GitHub-hosted published release (the first R2 release follows one) names no R2 URL: fetch everything
    hosted = {"packages": [dict(package, parts=[dict(part, url=r2.github_pool_url(part["sha256"]))
                                                for part in package["parts"]]) for package in known]}
    scene.http.calls.clear()
    first = run_verify(scene, repo, tmp_path / "first", published=hosted)
    assert known_urls <= set(scene.http.gets()) and len(first["verified_packages"]) == len(scene.set["packages"])
    assert first["diff"]["unchanged"] == len(known)  # the same bytes: players download nothing again
    # same URLs but other file rows (a set claiming new rows for old bytes) is not "known"
    relabelled = json.loads(json.dumps(known))
    relabelled[0]["files"][0]["sha256"] = "0" * 64
    scene.http.calls.clear()
    run_verify(scene, repo, tmp_path / "relabelled", published={"packages": relabelled})
    assert {part["url"] for part in known[0]["parts"]} <= set(scene.http.gets())
    # the descriptor and the core pack are always checked, known or not
    required = [package for package in scene.set["packages"] if package["id"] in r2.REQUIRED_PACKAGES]
    again = run_verify(scene, repo, tmp_path / "again", published={"packages": required})
    assert {item["id"] for item in again["verified_packages"]} >= set(r2.REQUIRED_PACKAGES)


def _refused(code, scene_or_http, repo, tmp_path, **changes):
    with pytest.raises(r2.DesktopR2Error) as error:
        run_verify(scene_or_http, repo, tmp_path, **changes)
    assert error.value.code == code, error.value
    return error.value


def test_wrong_commit_is_refused(scene, repo, tmp_path):
    _refused("commit", scene, repo, tmp_path, commit=repo.reader)


def test_a_commit_without_the_r2_reader_is_refused(scene, repo, tmp_path):
    _refused("reader-lacks-r2", scene, repo, tmp_path, commit=repo.old)


def test_wrong_platform_is_refused(scene, repo, tmp_path):
    data = r2.canonical_bytes(scene.set)
    scene.http.objects[r2.set_url("linux", scene.sha256)] = data  # a Windows set at the Linux key
    _refused("platform", scene, repo, tmp_path, platform="linux")


def test_wrong_key_is_refused(repo, key, other_key, tmp_path):
    identity = identity_of(repo, "windows", key, tmp_path)
    stage = make_stage(tmp_path / "local", "windows", identity)
    content_set, parts = make_set(stage, "windows", identity, other_key.public, tmp_path / "pack")
    http = FakeHttp()
    digest = publish_set(http, content_set, parts)
    with pytest.raises(r2.SetError) as error:
        ci.verify_content(platform="windows", set_sha256=digest, commit=repo.commit, repo=repo.path, http=http,
                          work=tmp_path / "w", out=tmp_path / "o", published=None)
    assert error.value.code == "public-key"


def _scene_with(repo, key, tmp_path, *, platform="windows", descriptor=None, pck=None, extra=None, mutate=None,
                builder=None):
    identity = identity_of(repo, platform, key, tmp_path)
    stage = make_stage(tmp_path / "local", platform, identity, descriptor=descriptor,
                       pck=pck(identity) if callable(pck) else pck, extra=extra)
    content_set, parts = make_set(stage, platform, identity, key.public, tmp_path / "pack", mutate=mutate,
                                  builder=builder)
    http = FakeHttp()
    digest = publish_set(http, content_set, parts, platform)
    return type("Scene", (), {"identity": identity, "http": http, "sha256": digest, "set": content_set})


def test_a_descriptor_that_is_not_the_commits_identity_is_refused(repo, key, tmp_path):
    identity = identity_of(repo, "windows", key, tmp_path)
    for index, descriptor in enumerate((dict(identity, release_build=False), dict(identity, ancestors=[repo.commit]),
                                        dict(identity, distribution="standalone"))):
        scene = _scene_with(repo, key, tmp_path / str(index), descriptor=descriptor)
        _refused("descriptor", scene, repo, tmp_path / str(index))


def test_a_core_pack_with_another_identity_is_refused(repo, key, tmp_path):
    scene = _scene_with(repo, key, tmp_path, pck=lambda identity: core_pck(dict(identity, commit=fx.PARENT)))
    _refused("pck-identity", scene, repo, tmp_path)
    missing = _scene_with(repo, key, tmp_path / "m", pck=make_pck({"project.binary": b"ECFG"}))
    _refused("pck-identity", missing, repo, tmp_path / "m")


def test_extension_list_may_name_only_the_ci_runtime(repo, key, tmp_path):
    good = _scene_with(repo, key, tmp_path / "good", pck=lambda identity: core_pck(identity, [ci.RUNTIME_DESCRIPTOR]))
    assert run_verify(good, repo, tmp_path / "good")["core_pck"]["extensions"] == [ci.RUNTIME_DESCRIPTOR]
    evil = _scene_with(repo, key, tmp_path / "evil", pck=lambda identity: core_pck(
        identity, [ci.RUNTIME_DESCRIPTOR, "res://addons/evil/evil.gdextension"]))
    _refused("pck-extension-list", evil, repo, tmp_path / "evil")


@pytest.mark.parametrize("url_for", [
    lambda part: r2.github_pool_url(part["sha256"]),
    lambda part: f"{r2.PUBLIC_ORIGIN}browser/assets/{part['sha256']}.bin",
    lambda part: r2.part_url(part["sha256"]).replace(".bin", ".zip.part"),
    lambda part: r2.part_url("0" * 64),
])
def test_a_non_derived_part_url_is_refused(repo, key, tmp_path, url_for):
    def mutate(content_set, parts):
        part = content_set["packages"][0]["parts"][0]
        part["url"] = url_for(part)
    scene = _scene_with(repo, key, tmp_path, mutate=mutate)
    _refused("part-url", scene, repo, tmp_path)


def _add_row(path, *, package_index=0):
    def mutate(content_set, parts):
        package = content_set["packages"][package_index]
        package["files"].append({"path": path, "size": 0, "sha256": "e" * 64})
        package["file_count"] += 1
    return mutate


@pytest.mark.parametrize("path, code", [
    ("app/RabbitLands.exe", "ci-path"),
    ("app/bin/Client_Runtime/client_runtime.dll", "ci-path"),
    ("APP/RabbitLands.EXE", "path-unsafe"),
    ("app/assets/ui/BIG BANNER.PNG", "path-duplicate"),
    ("app/tools/helper.dll", "native-extension"),
])
def test_ci_paths_and_case_collisions_are_refused(repo, key, tmp_path, path, code):
    scene = _scene_with(repo, key, tmp_path, mutate=_add_row(path))
    _refused(code, scene, repo, tmp_path)


@pytest.mark.parametrize("data, kind", [(fx.pe_bytes(b"tool"), "pe"), (fx.elf_bytes(b"tool"), "elf"),
                                        (bytes.fromhex("cffaedfe") + b"\0" * 28, "macho")])
def test_native_magic_in_a_new_package_is_refused(repo, key, tmp_path, data, kind):
    scene = _scene_with(repo, key, tmp_path, extra={"app/assets/ui/innocent.dat": data})
    error = _refused("native-magic", scene, repo, tmp_path)
    assert kind in str(error) and "innocent.dat" in str(error)


def test_a_dev_mode_set_is_refused(repo, key, tmp_path):
    scene = _scene_with(repo, key, tmp_path, builder={"mode": "dev", "tools_dirty": True, "release_build": True})
    _refused("builder", scene, repo, tmp_path)


def test_fetch_verified_never_gets_before_a_matching_head(tmp_path):
    url, body = r2.part_url("a" * 64), b"part bytes"
    for objects, served_length in (({}, None), ({url: body}, len(body) + 1)):
        http = FakeHttp(objects)
        if served_length:
            http.request = lambda method, address, **kw: up.HttpResponse(200, {"content-length": str(served_length)})
        with pytest.raises(ci.CiError) as error:
            ci.fetch_verified(http, url, tmp_path / "p.bin", size=len(body), sha256=sha(body))
        assert error.value.code == "part-head" and not [c for c in http.calls if c[0] == "GET"]
    http = FakeHttp({url: body})
    with pytest.raises(ci.CiError) as error:
        ci.fetch_verified(http, url, tmp_path / "p.bin", size=len(body), sha256="0" * 64)
    assert error.value.code == "part-hash" and not (tmp_path / "p.bin").exists()
    assert http.calls == [("HEAD", url), ("GET", url)]
    assert ci.fetch_verified(http, url, tmp_path / "p.bin", size=len(body), sha256=sha(body)).read_bytes() == body


def test_tampered_or_missing_parts_and_sets_are_refused(scene, repo, tmp_path):
    _refused("set-missing", scene, repo, tmp_path, set_sha256="9" * 64)
    url = next(iter(scene.parts))
    scene.http.objects[url] = bytes([scene.parts[url][0] ^ 1]) + scene.parts[url][1:]
    _refused("part-hash", scene, repo, tmp_path / "tampered")
    del scene.http.objects[url]
    _refused("part-missing", scene, repo, tmp_path / "missing")


# --- Package member checks and the PCK reader ------------------------------------------------

def _zip_package(tmp_path, files: dict, *, codec=None, stored_ok=True) -> tuple[dict, Path]:
    import zstandard
    rows, path = [], tmp_path / "package.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for index, (name, data) in enumerate(files.items()):
            row = {"path": name, "size": len(data), "sha256": sha(data)}
            if codec:
                row["codec"] = codec
            rows.append(row)
            for chunk in range((len(data) + ci.CHUNK_BYTES - 1) // ci.CHUNK_BYTES):
                piece = data[chunk * ci.CHUNK_BYTES:(chunk + 1) * ci.CHUNK_BYTES]
                if codec:
                    frame = zstandard.ZstdCompressor(level=3).compress(piece)
                    archive.writestr(f"files/{index:06d}/{chunk:06d}", frame,
                                     compress_type=zipfile.ZIP_STORED if stored_ok else zipfile.ZIP_DEFLATED)
                else:
                    archive.writestr(f"files/{index:06d}/{chunk:06d}", piece, compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("inventory.json", json.dumps(rows, separators=(",", ":")))
    data = path.read_bytes()
    first, second = tmp_path / "p1", tmp_path / "p2"
    first.write_bytes(data[:100])
    second.write_bytes(data[100:])
    package = {"id": "map-x-00", "sha256": sha(data), "size": len(data), "files": rows}
    return package, [first, second]


def test_verify_package_reads_split_parts_deflate_and_zstd(tmp_path):
    files = {"eloria-assets/maps/x/a.bin": os.urandom(9 * 1024 * 1024), "eloria-assets/maps/x/b.json": b"{}",
             "eloria-assets/maps/x/empty.txt": b""}
    for codec in (None, "zstd"):
        folder = tmp_path / str(codec)
        folder.mkdir()
        package, parts = _zip_package(folder, files, codec=codec)
        target = folder / "a.bin"
        assert ci.verify_package(package, parts, extract={"eloria-assets/maps/x/a.bin": target})["files"] == 3
        assert target.read_bytes() == files["eloria-assets/maps/x/a.bin"]
    folder = tmp_path / "deflated-zstd"
    folder.mkdir()
    package, parts = _zip_package(folder, files, codec="zstd", stored_ok=False)
    with pytest.raises(ci.CiError) as error:
        ci.verify_package(package, parts)
    assert error.value.code == "member-codec"


def test_verify_package_refuses_inventory_and_member_tampering(tmp_path):
    package, parts = _zip_package(tmp_path, {"app/data/a.json": b'{"a": 1}', "app/data/b.json": b'{"b": 2}'})
    for change, code in ((lambda p: p["files"][0].update(sha256="0" * 64), "package-inventory"),
                         (lambda p: p["files"].pop(), "package-members"),
                         (lambda p: p.update(sha256="0" * 64), "package-hash")):
        variant = json.loads(json.dumps(package))
        change(variant)
        with pytest.raises(ci.CiError) as error:
            ci.verify_package(variant, parts)
        assert error.value.code == code


def _one_member_package(tmp_path, data: bytes, member: bytes, *, codec=None, compress_type=zipfile.ZIP_STORED,
                        flag_bits=0) -> tuple[dict, list]:
    """A one-file package whose only chunk entry holds `member` (written as given)."""
    row = {"path": "eloria-assets/maps/x/a.bin", "size": len(data), "sha256": sha(data)}
    if codec:
        row["codec"] = codec
    path = tmp_path / "member.zip"
    with zipfile.ZipFile(path, "w") as archive:
        info = zipfile.ZipInfo("files/000000/000000")
        info.compress_type = compress_type
        archive.writestr(info, member)
        archive.writestr("inventory.json", json.dumps([row], separators=(",", ":")))
    raw = bytearray(path.read_bytes())
    if flag_bits:
        central = raw.find(bytes.fromhex("504b0102"))  # the first central directory record
        raw[central + 8:central + 10] = struct.pack("<H", flag_bits)
        path.write_bytes(bytes(raw))
    return {"id": "map-x-00", "sha256": sha(bytes(raw)), "size": len(raw), "files": [row]}, [path]


def test_verify_package_reads_members_as_the_updater_does(tmp_path):
    """Stored or deflate entries only, no encryption flag, and a zstd chunk is one frame decoded
    into exactly the chunk size (package_updates.gd decode_chunk): never the size a frame header
    claims, and nothing after the frame."""
    import zstandard
    data = b"rabbit lands " * 1000
    frame = zstandard.ZstdCompressor().compress(data)
    cases = {
        "ok": (frame, {}, None),
        "extra-after-frame": (frame + b"junk", {}, "member-size"),
        "second-frame": (frame + zstandard.ZstdCompressor().compress(b"x"), {}, "member-size"),
        "header-claims-more": (zstandard.ZstdCompressor().compress(data + bytes(64 << 20)), {}, "member-size"),
        "unknown-size-longer": (zstandard.ZstdCompressor(write_content_size=False).compress(data + b"!"), {},
                                "member-size"),
        "lzma": (frame, {"compress_type": zipfile.ZIP_LZMA}, "member-format"),
        "encrypted-flag": (frame, {"flag_bits": 1}, "member-format"),
    }
    for name, (member, options, code) in cases.items():
        folder = tmp_path / name
        folder.mkdir()
        package, parts = _one_member_package(folder, data, member, codec="zstd", **options)
        if code is None:
            assert ci.verify_package(package, parts)["files"] == 1, name
            continue
        with pytest.raises(ci.CiError) as error:
            ci.verify_package(package, parts)
        assert error.value.code == code, name
    # a deflate entry that declares another size than its row is refused before it is inflated
    folder = tmp_path / "deflate-size"
    folder.mkdir()
    package, parts = _one_member_package(folder, data, data + b"!", compress_type=zipfile.ZIP_DEFLATED)
    with pytest.raises(ci.CiError) as error:
        ci.verify_package(package, parts)
    assert error.value.code == "member-size"


def test_pck_reader_formats_and_refusals(tmp_path):
    entries = {"data/client_release.json": b'{"commit": "x"}', "a/b.txt": b"hello"}
    for fmt in (3, 4):
        path = tmp_path / f"v{fmt}.pck"
        path.write_bytes(make_pck(entries, fmt=fmt))
        found = ci.read_pck(path)
        assert set(found) == set(entries) and ci.pck_entry(path, found, "a/b.txt") == b"hello"
    for name, data in (("magic", make_pck(entries, magic=b"XXXX")), ("v2", make_pck(entries, fmt=2)),
                       ("encrypted", make_pck(entries, flags=3)), ("short", b"GDPC")):
        path = tmp_path / f"{name}.pck"
        path.write_bytes(data)
        with pytest.raises(ci.CiError):
            ci.read_pck(path)


def test_content_diff_reports_changes_extensions_and_bytes(scene):
    previous = json.loads(json.dumps(scene.set))
    previous["packages"] = [package for package in previous["packages"] if package["id"] != "audio-00"
                            and not package["id"].startswith("audio")]
    for package in previous["packages"]:
        package["files"] = [entry for entry in package["files"] if not entry["path"].endswith(".ogg")]
    changed = next(package for package in previous["packages"] if package["id"] == "client")
    changed["sha256"] = "0" * 64
    previous["packages"].append({"id": "gone-00", "sha256": "1" * 64, "size": 1, "files": [], "parts": []})
    diff = ci.content_diff(scene.set, previous)
    assert diff["client_changed"] and "client" in diff["changed"] and diff["removed"] == ["gone-00"]
    assert any(pid.startswith("audio") for pid in diff["added"]) and "ogg" in diff["new_extensions"]
    assert diff["new_bytes"] == sum(package["size"] for package in scene.set["packages"]
                                    if package["id"] in diff["added"] + diff["changed"])
    text = ci.summary_markdown("windows", "a" * 64, fx.COMMIT, diff)
    assert "`gone-00`" in text and "new file extensions: ogg" in text


# --- executables: native runtime, engine, helper, then root files --------------------------------

def fake_native(repo_path: Path, platform: str):
    import client_runtime_package

    def build(repo, commit, platform_, work):
        payload = Path(work) / "native-payload"
        payload.mkdir(parents=True)
        library = payload / client_runtime_package.LIBRARIES[platform_]
        library.write_bytes((fx.pe_bytes if platform_ == "windows" else fx.elf_bytes)(b"runtime"))
        descriptor = payload / "client_runtime.gdextension"
        descriptor.write_bytes(b"[configuration]\nentry_symbol = \"client_runtime_init\"\n")
        (payload / "runtime-manifest.json").write_text(json.dumps({
            "abi": client_runtime_package.ABI, "engine_major": 4, "engine_minor": 7, "platform": platform_,
            "architecture": "x86_64", "library": library.name,
            "source_digest": client_runtime_package.source_digest(Path(repo)),
            "library_sha256": sha(library.read_bytes()), "descriptor_sha256": sha(descriptor.read_bytes())}))
        return payload
    return build


def fake_engine(repo, platform, godot, template, run_godot, work, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((fx.pe_bytes if platform == "windows" else fx.elf_bytes)(b"engine"))
    return target


def fake_godot(calls):
    def run_godot(godot, args, log, timeout):
        calls.append(list(args))
        if "--export-release" in args:
            Path(args[-1]).write_bytes(b"MZ-helper-" + args[args.index("--export-release") + 1].encode())
    return run_godot


@pytest.fixture
def checkout(repo, tmp_path):
    """The workflow's checkout of the dispatched commit."""
    path = tmp_path / "checkout"
    # Windows runners default to core.autocrlf=true: the tool must read committed bytes anyway
    git(tmp_path, "-c", "core.autocrlf=true", "clone", "-q", str(repo.path), str(path))
    git(path, "checkout", "-q", "--detach", repo.commit)
    return path


def run_executables(repo, checkout, key, tmp_path, platform="windows", *, set_override=None):
    identity = identity_of(repo, platform, key, tmp_path)
    stage = make_stage(tmp_path / "local", platform, identity)
    content_set, _ = make_set(stage, platform, identity, key.public, tmp_path / "pack")
    content = tmp_path / f"content-{platform}"
    content.mkdir()
    (content / "set.json").write_bytes(r2.canonical_bytes(set_override or content_set))
    godot, template = tmp_path / "godot", tmp_path / "template"
    godot.write_bytes(b"editor")
    template.write_bytes(b"template")
    calls = []
    record = ci.executables(platform=platform, commit=repo.commit, repo=checkout, godot=godot, template=template,
                            content_dir=content, out=tmp_path / f"exec-{platform}", work=tmp_path / "work",
                            run_godot=fake_godot(calls), native_builder=fake_native(checkout, platform),
                            engine_exporter=fake_engine, http=None, previous=None)
    return record, calls, content_set, content


def test_root_files_come_after_the_helper_with_the_production_server(repo, checkout, key, tmp_path):
    record, calls, content_set, _ = run_executables(repo, checkout, key, tmp_path)
    root = tmp_path / "exec-windows/root"
    assert [args[args.index("--path") + 2] for args in calls] == ["--import", "--export-release"]
    launcher = (root / "RabbitLands.bat").read_text(encoding="ascii")
    assert "RabbitLands-updater.exe" in launcher and "app\\RabbitLands.exe" not in launcher
    assert "-- --launch-only --server=game.rabbitlandsgame.com --port=2001" in launcher
    assert json.loads((root / "launcher-defaults.json").read_text()) == {"args": fx.LAUNCH_ARGS}
    assert record["launch_args"] == fx.LAUNCH_ARGS
    testing = (root / "RabbitLands (optimization testing).bat").read_text(encoding="utf-8")
    assert "RABBITLANDS_OPTIMIZATION_PROFILE=human-testing" in testing and "RabbitLands.bat" in testing
    for name in ("RabbitLands (legacy runtime).bat", "RabbitLands (debug console).bat",
                 "RabbitLands (compatibility).bat", "RabbitLands (safe mode).bat", "README.txt"):
        assert (root / name).is_file(), name
    assert (root / "AUDIO-CREDITS.txt").read_bytes() == b"Audio credits\n"
    names = [row["name"] for row in record["root_files"]]
    assert names == sorted(names) and "AUDIO-CREDITS.txt" in names and "RabbitLands-updater.exe" not in names
    for row in record["root_files"]:
        assert sha((root / row["name"]).read_bytes()) == row["sha256"]
    rm._check_launch_args(record["launch_args"])
    r2.manifest_additions(platform="windows", sequence=SEQUENCE, helpers_fingerprint=record["helpers_fingerprint"],
                          root_files=record["root_files"], source="r2", set_sha256="a" * 64)


def test_linux_launchers_start_the_updater_and_are_executable(repo, checkout, key, tmp_path):
    record, _, _, _ = run_executables(repo, checkout, key, tmp_path, "linux")
    root = tmp_path / "exec-linux/root"
    script = (root / "RabbitLands.sh").read_text(encoding="ascii")
    assert "../RabbitLands-updater.x86_64 -- --launch-only --server=game.rabbitlandsgame.com --port=2001" in script
    assert (root / "RabbitLands (optimization testing).sh").is_file()
    assert record["helpers"]["updater"]["url"].endswith(".x86_64")


def test_executables_write_ci_packages_and_helper_rows(repo, checkout, key, tmp_path):
    record, _, content_set, _ = run_executables(repo, checkout, key, tmp_path)
    ids = [package["id"] for package in record["ci_packages"]]
    assert ids == ["engine", "native-runtime"]
    engine, native = record["ci_packages"]
    assert [entry["path"] for entry in engine["files"]] == ["app/RabbitLands.exe"]
    assert {entry["path"] for entry in native["files"]} == {
        "app/bin/client_runtime/client_runtime.dll", "app/bin/client_runtime/client_runtime.gdextension",
        "app/bin/client_runtime/runtime-manifest.json"}
    for package in record["ci_packages"]:
        for part in package["parts"]:
            assert part["url"] == r2.github_pool_url(part["sha256"])
            assert sha((tmp_path / "exec-windows/parts" / part["url"].rsplit("/", 1)[1]).read_bytes()) == part["sha256"]
    helper = (tmp_path / "exec-windows/root/RabbitLands-updater.exe").read_bytes()
    assert record["helpers"]["updater"] == {"url": rm.helper_url(sha(helper), "updater", "windows"),
                                            "size": len(helper), "sha256": sha(helper)}
    assert record["helpers_reused"] is False and record["native"]["cache_hit"] is False
    assert record["comparison"]["engine_equal"] is False  # a QA record, not a gate
    assert record["version"] == content_set["version"]


def test_root_files_refuse_to_run_before_the_helper_exists(checkout, tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(ci.CiError) as error:
        ci.write_root_files(root, checkout, "windows", fx.version(), fx.COMMIT)
    assert error.value.code == "root-order"


def test_native_builds_never_come_from_a_cache(tmp_path, monkeypatch):
    import release_native_runtime
    (tmp_path / "native" / "native-cache").mkdir(parents=True)
    with pytest.raises(ci.CiError) as error:
        ci.build_native(tmp_path, fx.COMMIT, "windows", tmp_path / "native")
    assert error.value.code == "native-cache"
    monkeypatch.setattr(release_native_runtime, "prepare_runtime", lambda *args, **kwargs: {"cache_hit": True})
    with pytest.raises(ci.CiError):
        ci.build_native(tmp_path, fx.COMMIT, "windows", tmp_path / "fresh")


def test_windows_engine_export_uses_the_game_preset_without_its_pack(checkout, tmp_path):
    import package_client
    calls = []

    def run_godot(godot, args, log, timeout):
        calls.append(args)
        if "--export-release" in args:
            Path(args[-1]).write_bytes(b"MZ-engine")
            Path(args[-1]).with_suffix(".pck").write_bytes(b"GDPC-tiny")
    target = tmp_path / "stage/app/RabbitLands.exe"
    ci.export_engine(checkout, "windows", tmp_path / "godot", tmp_path / "template", run_godot, tmp_path / "work",
                     target)
    assert target.read_bytes() == b"MZ-engine" and not target.with_suffix(".pck").exists()
    project = tmp_path / "work/engine-project"
    assert (project / "export_presets.cfg").read_text(encoding="utf-8") == package_client.EXPORT_PRESETS
    assert 'config/name="Rabbit Lands"' in (project / "project.godot").read_text(encoding="utf-8")
    assert calls[1][calls[1].index("--export-release") + 1] == "Windows Desktop"
    template = tmp_path / "linux-template"
    template.write_bytes(b"\x7fELF-template")
    linux = ci.export_engine(checkout, "linux", tmp_path / "godot", template, run_godot, tmp_path / "w2",
                             tmp_path / "stage/app/RabbitLands.x86_64")
    assert linux.read_bytes() == b"\x7fELF-template" and len(calls) == 2


# --- sign ---------------------------------------------------------------------------------------

def sign_inputs(repo, checkout, key, tmp_path, platform="windows", **changes):
    record, _, content_set, content = run_executables(repo, checkout, key, tmp_path, platform, **changes)
    return {platform: {"source": "r2", "set_sha256": sha((content / "set.json").read_bytes()), "content": content,
                       "exec": tmp_path / f"exec-{platform}"}}, content_set, record


def test_sign_builds_and_signs_the_schema_3_manifest(repo, checkout, key, tmp_path):
    inputs, content_set, record = sign_inputs(repo, checkout, key, tmp_path)
    out = tmp_path / "envelopes"
    result = ci.sign(commit=repo.commit, repo=checkout, inputs=inputs, key_pem=key.private, out=out,
                     sequence=SEQUENCE)
    manifest = out / f"{content_set['version']}-windows.json"
    assert (out / "RabbitLands-windows.json").read_bytes() == manifest.read_bytes()
    _, payload = rm.verify(manifest.read_bytes(), key.public)
    assert payload["schema"] == 3 and payload["sequence"] == SEQUENCE
    digest = inputs["windows"]["set_sha256"]
    assert payload["content"] == {"source": "r2", "set": {"sha256": digest, "url": r2.set_url("windows", digest)}}
    assert payload["helpers_fingerprint"] == record["helpers_fingerprint"]
    assert payload["root_files"] == record["root_files"] and payload["launch_args"] == fx.LAUNCH_ARGS
    assert result["windows"]["margin"] == r2.MAX_ENVELOPE_BYTES - manifest.stat().st_size
    assert json.loads((out / "sign.json").read_text())["platforms"]["windows"]["schema"] == 3
    assert key.private not in b"".join(path.read_bytes() for path in out.rglob("*") if path.is_file())


def test_sign_refuses_a_set_other_than_the_dispatched_one(repo, checkout, key, tmp_path):
    inputs, _, _ = sign_inputs(repo, checkout, key, tmp_path)
    for value in ("0" * 64, ""):
        with pytest.raises(ci.CiError) as error:
            ci.sign(commit=repo.commit, repo=checkout, key_pem=key.private, out=tmp_path / "o", sequence=SEQUENCE,
                    inputs={"windows": {**inputs["windows"], "set_sha256": value}})
        assert error.value.code == "set-hash"
    assert not (tmp_path / "o").exists()


def test_sign_refuses_another_key_and_another_build(repo, checkout, key, other_key, tmp_path):
    inputs, _, _ = sign_inputs(repo, checkout, key, tmp_path)
    with pytest.raises(rm.SigningError):
        ci.sign(commit=repo.commit, repo=checkout, inputs=inputs, key_pem=other_key.private, out=tmp_path / "o")
    with pytest.raises(r2.DesktopR2Error):
        ci.sign(commit=repo.reader, repo=checkout, inputs=inputs, key_pem=key.private, out=tmp_path / "o2")


def test_sign_applies_the_envelope_gate(repo, checkout, key, tmp_path):
    identity = identity_of(repo, "windows", key, tmp_path)
    stage = make_stage(tmp_path / "local", "windows", identity)
    content_set, _ = make_set(stage, "windows", identity, key.public, tmp_path / "pack")
    rows = [{"path": f"eloria-assets/maps/huge/f{index:06d}.bin", "size": 0, "sha256": "e" * 64}
            for index in range(99000)]
    package = next(p for p in content_set["packages"] if p["id"].startswith("map-"))
    package["files"], package["file_count"], package["unpacked_size"] = rows, len(rows), 0
    inputs, _, _ = sign_inputs(repo, checkout, key, tmp_path / "x", set_override=content_set)
    with pytest.raises(r2.EnvelopeError) as error:
        ci.sign(commit=repo.commit, repo=checkout, inputs=inputs, key_pem=key.private, out=tmp_path / "o",
                sequence=SEQUENCE)
    assert error.value.code == "envelope-too-large"


def test_pointer_subcommand_signs_a_pointer_to_the_envelope(repo, checkout, key, tmp_path):
    inputs, content_set, _ = sign_inputs(repo, checkout, key, tmp_path)
    ci.sign(commit=repo.commit, repo=checkout, inputs=inputs, key_pem=key.private, out=tmp_path / "env",
            sequence=SEQUENCE)
    manifest = tmp_path / "env" / f"{content_set['version']}-windows.json"
    path = ci.pointer(platform="windows", manifest=manifest, release_id=11, run_id=12, rollback=False,
                      key_pem=key.private, repo=checkout, commit=repo.commit, out=tmp_path / "ptr",
                      sequence=SEQUENCE + 900)
    assert path.name == "RabbitLands-windows-pointer.json"
    checked = up.check_release_pair(path.read_bytes(), lambda p, v: manifest.read_bytes(), platform="windows",
                                    public_pem=key.public, commit=repo.commit, release_id=11)
    assert checked.pointer["run_id"] == 12 and checked.pointer["sequence"] == SEQUENCE + 900
    # a forward pointer names the dispatched commit's own manifest; only a rollback may name an older one
    with pytest.raises(ci.CiError) as error:
        ci.pointer(platform="windows", manifest=manifest, release_id=11, run_id=13, rollback=False,
                   key_pem=key.private, repo=checkout, commit=repo.reader, out=tmp_path / "ptr-other",
                   sequence=SEQUENCE + 900)
    assert error.value.code == "pointer-commit" and not (tmp_path / "ptr-other").exists()
    back = ci.pointer(platform="windows", manifest=manifest, release_id=11, run_id=14, rollback=True,
                      key_pem=key.private, repo=checkout, commit=repo.reader, out=tmp_path / "ptr-back",
                      sequence=SEQUENCE + 960)
    _, value = rm.verify(back.read_bytes(), key.public, limit=r2.MAX_POINTER_BYTES)
    assert value["rollback"] is True and value["target"]["commit"] == repo.commit


def test_key_comes_only_from_the_environment_and_is_removed(monkeypatch):
    monkeypatch.delenv(ci.SIGNING_SECRET, raising=False)
    with pytest.raises(ci.CiError) as error:
        ci._pop_key()
    assert error.value.code == "signing-key-missing"
    monkeypatch.setenv(ci.SIGNING_SECRET, "-----BEGIN PRIVATE KEY-----")
    assert ci._pop_key().startswith(b"-----BEGIN") and ci.SIGNING_SECRET not in os.environ
    # a mangled secret is refused without echoing any of its text
    monkeypatch.setenv(ci.SIGNING_SECRET, "-----BEGIN PRIVATE KEY-----\nsecr\u00e9t\n")
    with pytest.raises(ci.CiError) as error:
        ci._pop_key()
    assert error.value.code == "signing-key" and "secr" not in str(error.value)
    assert ci.SIGNING_SECRET not in os.environ


# --- installers and stage -------------------------------------------------------------------------

def signed(repo, checkout, key, tmp_path, platform="windows", source="r2"):
    inputs, content_set, record = sign_inputs(repo, checkout, key, tmp_path, platform)
    ci.sign(commit=repo.commit, repo=checkout, inputs=inputs, key_pem=key.private, out=tmp_path / "envelopes",
            sequence=SEQUENCE)
    return tmp_path / "envelopes" / f"{content_set['version']}-{platform}.json", content_set, record


def test_linux_installer_is_the_checksum_verifying_download_script(repo, checkout, key, tmp_path):
    envelope, content_set, record = signed(repo, checkout, key, tmp_path, "linux")
    calls = []
    script = ci.installers(platform="linux", commit=repo.commit, repo=checkout, envelope=envelope,
                           exec_dir=tmp_path / "exec-linux", out=tmp_path / "installers", work=tmp_path / "iw",
                           godot=tmp_path / "godot", run_godot=fake_godot(calls))
    text = script.read_text(encoding="utf-8")
    assert script.name == f"{content_set['version']}-download.sh"
    assert record["helpers"]["updater"]["url"] in text and record["helpers"]["updater"]["sha256"] in text
    embedded = text.split("<<'RABBITLANDS_MANIFEST'\n", 1)[1].split("\nRABBITLANDS_MANIFEST", 1)[0]
    assert json.loads(embedded) == json.loads(envelope.read_bytes())
    verify = calls[-1]
    assert "--script" in verify and verify[verify.index("--script") + 1].endswith("verify_client_release.gd")
    request = json.loads(Path(verify[-1]).read_text())
    assert request["identity"]["commit"] == repo.commit and request["manifest"] == str(envelope.resolve())


def test_windows_setup_waits_for_the_w2_and_b8_hooks(repo, checkout, key, tmp_path, monkeypatch):
    import package_client
    envelope, _, _ = signed(repo, checkout, key, tmp_path, "windows")
    with pytest.raises(ci.CiError) as error:
        ci.installers(platform="windows", commit=repo.commit, repo=checkout, envelope=envelope,
                      exec_dir=tmp_path / "exec-windows", out=tmp_path / "i", work=tmp_path / "iw",
                      verify_with_godot=False)
    assert error.value.code == "installer-schema"
    monkeypatch.setattr(package_client, "ONLINE_INSTALLER_SCHEMAS", (1, 2, 3), raising=False)
    with pytest.raises(ci.CiError) as error:
        ci.installers(platform="windows", commit=repo.commit, repo=checkout, envelope=envelope,
                      exec_dir=tmp_path / "exec-windows", out=tmp_path / "i", work=tmp_path / "iw2",
                      verify_with_godot=False)
    assert error.value.code == "installer-helper"


def test_windows_setup_is_built_from_a_skeleton_stage(repo, checkout, key, tmp_path, monkeypatch):
    import package_client
    envelope, content_set, record = signed(repo, checkout, key, tmp_path, "windows")
    monkeypatch.setattr(ci, "installer_preconditions", lambda release, repo_, commit: None)
    seen = {}

    def online_installer(stage, godot, iscc, version, launch_args, logs):
        seen.update(stage=stage, version=version, launch_args=launch_args, storage=package_client.STORAGE,
                    files=sorted(path.relative_to(stage).as_posix() for path in stage.rglob("*") if path.is_file()))
        manifest = stage.parent / f"{stage.name}-windows.json"
        assert manifest.read_bytes() == envelope.read_bytes()
        setup = stage.parent / f"{stage.name}-setup.exe"
        setup.write_bytes(b"MZ-setup")
        return setup
    previous = package_client.STORAGE
    setup = ci.installers(platform="windows", commit=repo.commit, repo=checkout, envelope=envelope,
                          exec_dir=tmp_path / "exec-windows", out=tmp_path / "i", work=tmp_path / "iw",
                          verify_with_godot=False, online_installer=online_installer)
    assert setup.read_bytes() == b"MZ-setup" and package_client.STORAGE is previous
    assert seen["version"] == content_set["version"].split("-", 2)[2] and seen["launch_args"] == fx.LAUNCH_ARGS
    assert {"RabbitLands-updater.exe", "RabbitLands.bat", "app/client-release.json",
            "app/assets/branding/rabbitlands-icon.ico"} <= set(seen["files"])
    part = record["ci_packages"][0]["parts"][0]
    assert seen["storage"].part_matches(part["url"].rsplit("/", 1)[1], part)
    assert not seen["storage"].part_matches(part["url"].rsplit("/", 1)[1], dict(part, sha256="0" * 64))


class FakeSink:
    def __init__(self):
        self.accepted = []

    def accept(self, path, row):
        self.accepted.append((path.name, row))


def test_stage_uploads_pool_parts_helpers_and_draft_files(repo, checkout, key, tmp_path):
    exec_dirs, installer_dirs = {}, {}
    for platform in ("windows", "linux"):
        envelope, content_set, _ = signed(repo, checkout, key, tmp_path / platform, platform)
        exec_dirs[platform] = tmp_path / platform / f"exec-{platform}"
        installer_dirs[platform] = tmp_path / platform / "installers"
        installer_dirs[platform].mkdir()
        suffix = "setup.exe" if platform == "windows" else "download.sh"
        name = f"{content_set['version']}-{suffix}"
        (installer_dirs[platform] / name).write_bytes(b"installer " + platform.encode())
    envelopes = tmp_path / "envelopes"
    envelopes.mkdir()
    signs = {}
    for platform in ("windows", "linux"):
        for path in (tmp_path / platform / "envelopes").iterdir():
            if path.name != "sign.json":
                shutil.copyfile(path, envelopes / path.name)
        signs.update(json.loads((tmp_path / platform / "envelopes/sign.json").read_text())["platforms"])
    (envelopes / "sign.json").write_text(json.dumps({"platforms": signs}))
    sink = FakeSink()
    result = ci.stage(commit=repo.commit, release_id=5, exec_dirs=exec_dirs, envelopes=envelopes,
                      installer_dirs=installer_dirs, work=tmp_path / "stage-work", sink=sink, public_pem=key.public)
    names = [name for name, _ in sink.accepted]
    assert len(names) == len(result["uploads"])
    assert sum(name.startswith("RabbitLands-pkg-") and name.endswith(".zip.part") for name in names) >= 4
    for platform, extension in (("windows", "exe"), ("linux", "x86_64")):
        assert any(name.startswith("RabbitLands-updater-") and name.endswith("." + extension) for name in names)
        assert any(name.startswith("RabbitLands-uninstall-") and name.endswith("." + extension) for name in names)
        assert f"RabbitLands-{platform}.json" in names
    assert any(name.endswith("-setup.exe") for name in names) and any(name.endswith("-download.sh") for name in names)
    import shared_release_assets
    for name, row in sink.accepted:
        if shared_release_assets.is_name(name):
            assert shared_release_assets.NAME.fullmatch(name)[2] == row["sha256"]
    # a CI part or a manifest changed after signing stops the job before anything is uploaded
    part = next((exec_dirs["linux"] / "parts").iterdir())
    original = part.read_bytes()
    part.write_bytes(original + b"!")
    late = FakeSink()
    with pytest.raises(ci.CiError):
        ci.stage(commit=repo.commit, release_id=5, exec_dirs=exec_dirs, envelopes=envelopes,
                 installer_dirs=installer_dirs, work=tmp_path / "stage-work2", sink=late, public_pem=key.public)
    part.write_bytes(original)
    # manifests signed for another commit are never staged into this commit's draft
    with pytest.raises(ci.CiError) as error:
        ci.stage(commit=repo.reader, release_id=5, exec_dirs=exec_dirs, envelopes=envelopes,
                 installer_dirs=installer_dirs, work=tmp_path / "stage-other", sink=late, public_pem=key.public)
    assert error.value.code == "stage-manifest"
    manifest = next(path for path in envelopes.iterdir() if path.name.endswith("-windows.json")
                    and path.name.startswith("RabbitLands-Windows-"))
    manifest.write_bytes(manifest.read_bytes().replace(b'"signature":"', b'"signature":"A'))
    with pytest.raises(ci.CiError):
        ci.stage(commit=repo.commit, release_id=5, exec_dirs=exec_dirs, envelopes=envelopes,
                 installer_dirs=installer_dirs, work=tmp_path / "stage-work3", sink=late, public_pem=key.public)
    assert late.accepted == []


# --- e2e ------------------------------------------------------------------------------------------

def startup_line(profile: str, *, native=None) -> str:
    import full_optimization_package as full
    testing = profile == "human-testing"
    value = {"profile": {"features": full.FEATURES if testing else full.DEFAULT_FEATURES, "profile": profile,
                         "human_testing": testing, "reason": "human_testing_selected" if testing else "default_legacy"},
             "runtime": {"mode": "rust" if testing else "legacy",
                         "native_available": testing if native is None else native},
             "remote": {"backend": "rust" if testing else "legacy"},
             "admission": {"mode": "rust" if testing else "legacy", "worker_limit": 1},
             "prepared": {"catalog_present": True, "mode": "auto" if testing else "raw",
                          "node_policy": "lazy-source-v1" if testing else "retain"},
             "effects": {"requested": "heat_bolt" if testing else "legacy"}}
    return "RABBITLANDS_OPTIMIZATION_STARTUP " + json.dumps(value)


class FakeRuns:
    """The shipped binaries, simulated: the updater installs the signed files, the game prints startup lines."""

    def __init__(self, release, stage: Path, helper: Path, *, native=None, recheck_downloads=0):
        self.release, self.stage, self.helper = release, stage, helper
        self.native, self.recheck_downloads = native, recheck_downloads
        self.commands = []

    def __call__(self, command, log, *, timeout, env=None, cwd=None):
        command = [str(item) for item in command]
        self.commands.append(command)
        text = ""
        if "--install-update" in command:
            root = Path(command[command.index("--root") + 1])
            for package in self.release["packages"]:
                for entry in package["files"]:
                    target = root / entry["path"]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(self.stage / entry["path"], target)
            shutil.copyfile(self.helper, root / self.helper.name)
            text = "RL_PROGRESS|100|Installing verified game files\n"
        elif any(item.endswith(("RabbitLands.exe", "RabbitLands.x86_64")) for item in command):
            import package_client
            profile = "human-testing" if "--optimization-profile=human-testing" in command else "legacy"
            text = f"{package_client.VRAM_SELF_TEST_OK}\n{startup_line(profile, native=self.native)}\n"
        elif "--update-only" in command:
            total = len(self.release["packages"])
            text = (f"RL_PROGRESS|100|Changed packages ready: {self.recheck_downloads} of {total} "
                    "packages needed downloads\n")
        elif "sh" in command:  # download.sh
            target = Path(command[-1]) / "RabbitLands"
            (target / "app").mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.stage / "app/client-release.json", target / "app/client-release.json")
        Path(log).parent.mkdir(parents=True, exist_ok=True)
        Path(log).write_text(text, encoding="utf-8")
        return 0, text


def e2e_scene(repo, checkout, key, tmp_path, platform, **fake):
    envelope, content_set, record = signed(repo, checkout, key, tmp_path, platform)
    _, release = rm.verify(envelope.read_bytes(), key.public)
    stage = tmp_path / "e2e-stage"
    (stage / "app/bin/client_runtime").mkdir(parents=True)
    local = tmp_path / "local" / content_set["version"]
    for package in release["packages"]:
        for entry in package["files"]:
            source = (tmp_path / "work/ci-stage" if r2.is_ci_path(entry["path"]) else local) / entry["path"]
            target = stage / entry["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    exec_dir = tmp_path / f"exec-{platform}"
    runs = FakeRuns(release, stage, exec_dir / "root" / ci.helpers.BINARIES[platform], **fake)
    runner = ci.E2E(platform=platform, envelope=envelope, exec_dir=exec_dir, work=tmp_path / "e2e",
                    public_pem=key.public, run=runs, user="rl-e2e-test" if platform == "linux" else None,
                    alive=lambda: False, sleep=lambda seconds: None)
    return runner, runs, release


def test_e2e_linux_installs_from_the_envelope_as_an_unprivileged_user_under_xvfb(repo, checkout, key, tmp_path):
    runner, runs, release = e2e_scene(repo, checkout, key, tmp_path, "linux")
    import linux_download_helper
    script = tmp_path / "download.sh"
    script.write_text(linux_download_helper.bootstrap_script(
        release["updater"], json.loads((tmp_path / "envelopes" / f"{release['version']}-linux.json").read_bytes())),
        encoding="utf-8")
    receipt = runner.run_all(installer=script)
    install = next(command for command in runs.commands if "--install-update" in command)
    assert install[:5] == ["sudo", "-n", "-u", "rl-e2e-test", "--"] and "env" in install and "-i" in install
    assert install[install.index("xvfb-run"):install.index("xvfb-run") + 2] == ["xvfb-run", "-a"]
    assert install[install.index("--install-manifest") + 1].endswith("install-manifest.json")
    assert "--update-only" in install
    assert any(command[:3] == ["sudo", "-n", "useradd"] for command in runs.commands)
    smokes = [command for command in runs.commands if any(item.endswith("RabbitLands.x86_64") for item in command)]
    assert len(smokes) == 2 and all(command[:4] == ["sudo", "-n", "-u", "rl-e2e-test"] for command in smokes)
    assert all("ELORIA_VRAM_SELF_TEST=1" in command for command in smokes)
    assert "--optimization-profile=human-testing" in smokes[1]
    steps = {step["step"]: step for step in receipt["steps"]}
    for name in ("updater-row", "install-started", "installed", "installed-files", "smoke-legacy",
                 "startup-legacy", "smoke-human-testing", "startup-human-testing", "recheck",
                 "download-sh-content", "download-sh-run"):
        assert steps[name]["ok"] is True, name
    assert steps["startup-human-testing"]["runtime"] == {"mode": "rust", "native_available": True}
    recheck = next(command for command in runs.commands
                   if "--update-only" in command and "--install-update" not in command)
    assert "--install-manifest" in recheck and "xvfb-run" in recheck


def test_e2e_windows_runs_the_shipped_binaries_with_throwaway_user_dirs(repo, checkout, key, tmp_path):
    runner, runs, _ = e2e_scene(repo, checkout, key, tmp_path, "windows")
    receipt = runner.run_all()
    install = next(command for command in runs.commands if "--install-update" in command)
    assert install[0].endswith("RabbitLands-updater.exe") and "--install-manifest" in install
    assert not any("sudo" in command or "xvfb-run" in command for command in runs.commands)
    assert all(step["ok"] for step in receipt["steps"])


def test_e2e_fails_when_the_opt_in_profile_lacks_the_native_runtime(repo, checkout, key, tmp_path):
    runner, _, _ = e2e_scene(repo, checkout, key, tmp_path, "windows", native=False)
    with pytest.raises(ci.CiError) as error:
        runner.run_all()
    assert error.value.code == "e2e-startup-human-testing"
    assert runner.receipt["steps"][-1]["ok"] is False


def test_e2e_recheck_must_download_nothing(repo, checkout, key, tmp_path):
    runner, _, _ = e2e_scene(repo, checkout, key, tmp_path, "windows", recheck_downloads=1)
    with pytest.raises(ci.CiError) as error:
        runner.run_all()
    assert error.value.code == "e2e-recheck"


def test_e2e_refuses_a_shipped_updater_that_is_not_the_signed_row(repo, checkout, key, tmp_path):
    runner, _, _ = e2e_scene(repo, checkout, key, tmp_path, "windows")
    helper = tmp_path / "exec-windows/root/RabbitLands-updater.exe"
    helper.write_bytes(helper.read_bytes() + b"!")
    with pytest.raises(ci.CiError) as error:
        runner.run_all()
    assert error.value.code == "e2e-updater-row"


# --- Artifacts and the CLI -------------------------------------------------------------------------

def test_artifact_digest_detects_changed_extra_and_missing_files(tmp_path):
    folder = tmp_path / "content-windows"
    (folder / "sub").mkdir(parents=True)
    (folder / "set.json").write_bytes(b"{}")
    (folder / "sub/verified.json").write_bytes(b"[]")
    digest = ci.tree_digest(folder)
    assert ci.check_artifact(folder, digest) == digest
    (folder / "extra").write_bytes(b"")
    with pytest.raises(ci.CiError):
        ci.check_artifact(folder, digest)
    (folder / "extra").unlink()
    (folder / "set.json").write_bytes(b"{ }")
    with pytest.raises(ci.CiError):
        ci.check_artifact(folder, digest)


def test_artifact_digest_orders_rows_by_path_text_on_every_system(tmp_path):
    """A Windows producer and an ubuntu consumer must agree. Windows sorts Path objects
    case-insensitively and by component; the digest orders rows by the POSIX path string."""
    folder = tmp_path / "exec-windows"
    names = ["root/README.txt", "root/RabbitLands.bat", "root/rabbitlands-icon.ico", "sub-y", "sub/x"]
    for index, name in enumerate(names):
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(bytes([index]))
    rows = [[name, 1, sha(bytes([index]))] for index, name in enumerate(names)]
    assert sorted(rows) == rows  # the names above are already in path-text order
    assert ci.tree_digest(folder) == sha(r2.canonical_bytes(rows))


def test_cli_refusals_exit_2_and_print_no_key(tmp_path, monkeypatch, capsys, key):
    monkeypatch.setenv(ci.SIGNING_SECRET, key.private.decode())
    code = ci.main(["sign", "--commit", "0" * 40, "--windows-source", "r2", "--windows-set-sha256", "a" * 64,
                    "--windows-content", str(tmp_path), "--windows-exec", str(tmp_path), "--out", str(tmp_path / "o")])
    output = capsys.readouterr()
    assert code == 2 and "PRIVATE" not in output.out + output.err and ci.SIGNING_SECRET not in os.environ
    assert ci.main(["artifact-digest", "--dir", str(tmp_path), "--expect", "0" * 64]) == 2


def test_source_is_ascii_without_machine_paths_or_r2_writes():
    text = (TOOLS / "desktop_release_ci.py").read_bytes().decode("ascii")
    for needle in ("C:/", "C:\\", "/Users/", "scratchpad", "AppData/Local/Temp", "put_object", "delete_object",
                   "boto3", "load_r2_config", "r2-upload"):
        assert needle not in text, needle
    assert subprocess.run(["git", "--version"], capture_output=True).returncode == 0
