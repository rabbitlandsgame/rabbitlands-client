"""Desktop R2 layout, formats and validators (tools/desktop_r2.py). Pure Python: no SDK, network or Godot."""
import base64
import copy
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import traceback

import pytest

GODOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GODOT / "tools"))
import desktop_r2 as r2

PEM = (GODOT / "data/update_public.pem").read_bytes()
KEY_SHA = hashlib.sha256(PEM).hexdigest()
COMMIT = "0123456789abcdef0123456789abcdef01234567"
VERSION = "RabbitLands-Windows-20261104-012345678"
A, B = "a" * 64, "b" * 64


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def package(pid, files, *, parts=1, source="r2", codec=None):
    rows = [{"path": path, "size": size, "sha256": digest(path)} for path, size in files]
    if codec:
        rows[0]["codec"] = codec
    sha = digest("package " + pid)
    url = r2.part_url if source == "r2" else r2.github_pool_url
    if parts == 1:
        part_rows = [{"url": url(sha), "size": 1000, "sha256": sha}]
    else:
        hashes = [digest(f"part {pid} {index}") for index in range(parts)]
        part_rows = [{"url": url(value), "size": 1000, "sha256": value} for value in hashes]
    return {"id": pid, "sha256": sha, "size": 1000 * parts, "unpacked_size": sum(size for _, size in files),
            "file_count": len(rows), "files": rows, "parts": part_rows}


def content_set(source="r2", platform="windows"):
    version = VERSION if platform == "windows" else VERSION.replace("Windows", "Linux")
    return {"kind": r2.SET_KIND, "set_schema": 1, "source": source, "repository": r2.REPOSITORY,
            "commit": COMMIT, "platform": platform, "version": version, "public_key_sha256": KEY_SHA,
            "asset_base": r2.DESKTOP_ASSETS, "ci_paths": [*r2.CI_PATHS, *r2.CI_PREFIXES],
            "packages": [
                package("client", [("app/RabbitLands.pck", 27_000_000)], source=source),
                package("release-descriptor", [("app/client-release.json", 900),
                                               ("app/data/client_release.json", 900)], source=source),
                package("pck-actors", [("app/packs/actors.pck", 5_000_000)], parts=3, source=source),
                package("records-00", [("app/data/items.json", 10), ("app/data/space name.json", 0)],
                        source=source),
                package("map-landfall-00", [("eloria-assets/maps/landfall/world.json", 77)], source=source,
                        codec="zstd"),
            ],
            "optional_packages": [],
            "builder": {"tools_commit": COMMIT, "tools_dirty": False, "package_format": "zstd"},
            "qualification": {"smoke": ["legacy", "human-testing"], "split_pck": True}}


def check(value, **options):
    return r2.validate_set(value, public_key_sha256=KEY_SHA, **options)


def refused(value, code, **options):
    with pytest.raises(r2.SetError) as error:
        check(value, **options)
    assert error.value.code == code, str(error.value)
    return error.value


def add_file(value, path, *, pid="records-00", size=1):
    row = next(item for item in value["packages"] if item["id"] == pid)
    row["files"].append({"path": path, "size": size, "sha256": digest(path)})
    row["file_count"] += 1
    row["unpacked_size"] += size
    return value


# --- Key guard -----------------------------------------------------------------

def test_guard_accepts_exactly_the_desktop_layout():
    for key in (f"desktop/v1/parts/{A}.bin", f"desktop/v1/sets/windows/{A}.json",
                f"desktop/v1/manifests/linux/{B}.json", "desktop/v1/channels/live/windows.json",
                "desktop/v1/channels/live/linux.json"):
        assert r2.guard_key(key) == key
        assert not r2.is_allowed_key(key, selftest=True)


@pytest.mark.parametrize("key", [
    f"browser/assets/{A}.zip", f"browser/assets/{A}.bin", "browser/licenses/godot-cpp-LICENSE.md",
    f"desktop/v1/parts/../../browser/assets/{A}.bin", f"desktop/v1/parts/../parts/{A}.bin",
    f"desktop/v1/parts/%2e%2e/{A}.bin", f"desktop\\v1\\parts\\{A}.bin", f"/desktop/v1/parts/{A}.bin",
    f"desktop//v1/parts/{A}.bin", f"./desktop/v1/parts/{A}.bin",
    f"desktop/v1/parts/{A.upper()}.bin", f"Desktop/v1/parts/{A}.bin", f"desktop/V1/parts/{A}.bin",
    f"desktop/v1/parts/{A}.BIN", "desktop/v1/channels/live/Windows.json",
    f"desktop/v1/parts/{A}.zip", f"desktop/v1/parts/{A}.zip.part", f"desktop/v1/parts/{A}.json",
    f"desktop/v1/sets/windows/{A}.bin", f"desktop/v1/manifests/windows/{A}.json.gz",
    f"desktop/v1/parts/{A}.bin\n", f"desktop/v1/parts/{A}.bin\r", f"desktop/v1/parts/{A}.bin ",
    f" desktop/v1/parts/{A}.bin", "desktop/v1/channels/live/windows.json\n",
    f"desktop/v1/parts/{A[:63]}.bin", f"desktop/v1/parts/{A}a.bin", f"desktop/v1/parts/{'g' * 64}.bin",
    f"desktop/v1/sets/macos/{A}.json", "desktop/v1/channels/test/windows.json",
    "desktop/v1/channels/live/macos.json", f"desktop/v2/parts/{A}.bin", f"desktop/parts/{A}.bin",
    f"desktop/selftest/20261104-0123abcd/parts/{A}.bin", "", "desktop/", None, 7,
    f"desktop/v1/parts/{A}.bin".encode(),
])
def test_guard_refuses_everything_else(key):
    assert not r2.is_allowed_key(key)
    with pytest.raises(r2.KeyGuardError):
        r2.guard_key(key)


def test_selftest_mode_admits_only_its_nonce_prefix():
    prefix = r2.selftest_prefix("20261104", "0123abcd")
    for relative in (f"parts/{A}.bin", f"conflict/{A}.bin", f"lock/{A}.bin", f"sets/linux/{A}.json",
                     f"manifests/windows/{A}.json", "channels/live/linux.json"):
        assert r2.guard_key(prefix + relative, selftest=True) == prefix + relative
        assert not r2.is_allowed_key(prefix + relative)
    for key in (f"desktop/v1/parts/{A}.bin", "desktop/v1/channels/live/windows.json",
                f"desktop/selftest/2026114-0123abcd/parts/{A}.bin",
                f"desktop/selftest/\u0662\u0660\u0662\u0666\u0661\u0661\u0660\u0664-0123abcd/parts/{A}.bin",
                f"desktop/selftest/20261104-0123ABCD/parts/{A}.bin", f"{prefix}other/{A}.bin",
                f"{prefix}parts/{A}.bin\n", f"browser/assets/{A}.bin"):
        assert not r2.is_allowed_key(key, selftest=True)
    assert re.fullmatch(r"desktop/selftest/[0-9]{8}-[0-9a-f]{8}/",
                        r2.new_selftest_prefix(datetime.date(2026, 11, 4)))
    assert r2.new_selftest_prefix() != r2.new_selftest_prefix()
    with pytest.raises(r2.KeyGuardError):
        r2.selftest_prefix("20261104", "../../x")


def test_only_pointers_are_mutable_and_listing_stays_in_desktop():
    assert r2.is_pointer_key("desktop/v1/channels/live/windows.json")
    assert r2.is_pointer_key("desktop/selftest/20261104-0123abcd/channels/live/linux.json")
    assert not r2.is_pointer_key(f"desktop/v1/parts/{A}.bin")
    assert not r2.is_pointer_key(f"desktop/v1/manifests/windows/{A}.json")
    assert r2.guard_list_prefix("desktop/") == "desktop/"
    assert r2.guard_list_prefix("desktop/v1/parts/") == "desktop/v1/parts/"
    assert r2.guard_list_prefix("desktop/selftest/20261104-0123abcd/", selftest=True)
    for prefix in ("", "browser/", "desktop", "desktop/../browser/", "desktop//", "Desktop/", "desktop/v1/\n"):
        with pytest.raises(r2.KeyGuardError):
            r2.guard_list_prefix(prefix)
    with pytest.raises(r2.KeyGuardError):
        r2.guard_list_prefix("desktop/v1/", selftest=True)
    assert r2.ALLOWED_OPERATIONS == {"HeadObject", "GetObject", "PutObject", "ListObjectsV2"}


# --- Keys and URLs ---------------------------------------------------------------

def test_r2_url_derivation():
    assert r2.DESKTOP_ASSETS == "https://assets.rabbitlandsgame.com/desktop/v1/"
    assert r2.part_url(A) == f"https://assets.rabbitlandsgame.com/desktop/v1/parts/{A}.bin"
    assert r2.set_url("linux", B) == f"https://assets.rabbitlandsgame.com/desktop/v1/sets/linux/{B}.json"
    assert r2.manifest_url("windows", A) == r2.DESKTOP_ASSETS + f"manifests/windows/{A}.json"
    assert r2.pointer_url("linux") == r2.DESKTOP_ASSETS + "channels/live/linux.json"
    prefix = r2.selftest_prefix("20261104", "0123abcd")
    assert r2.part_key(A, prefix=prefix) == prefix + f"parts/{A}.bin"
    assert r2.manifest_url("linux", A, prefix=prefix) == r2.PUBLIC_ORIGIN + prefix + f"manifests/linux/{A}.json"
    for url in (r2.part_url(A), r2.set_url("windows", A), r2.manifest_url("linux", B), r2.pointer_url("windows")):
        assert r2.public_url(r2.key_from_url(url)) == url
    for url in (f"https://assets.rabbitlandsgame.com/browser/assets/{A}.bin",
                f"http://assets.rabbitlandsgame.com/desktop/v1/parts/{A}.bin",
                f"https://assets.rabbitlandsgame.com.evil.example/desktop/v1/parts/{A}.bin",
                f"https://evil.example/desktop/v1/parts/{A}.bin",
                r2.part_url(A) + "?x=1", r2.part_url(A) + "#x", r2.part_url(A).upper()):
        with pytest.raises(r2.KeyGuardError):
            r2.key_from_url(url)
    for bad in (A.upper(), A[:-1], "", None):
        with pytest.raises(r2.DesktopR2Error):
            r2.part_url(bad)
    with pytest.raises(r2.DesktopR2Error):
        r2.set_url("macos", A)
    with pytest.raises(r2.KeyGuardError):
        r2.pointer_key("windows", "test")


def test_github_pool_derivation_matches_partwriter_and_released_clients():
    partitioned = f"https://github.com/rabbitlandsgame/rabbitlands-client/releases/download/client-assets-a/RabbitLands-pkg-{A}.zip.part"
    legacy = f"https://github.com/rabbitlandsgame/rabbitlands-client/releases/download/client-assets/RabbitLands-pkg-{A}.zip.part"
    assert r2.github_pool_url(A) == partitioned
    assert r2.github_pool_url(A, partitioned=False) == legacy
    assert r2.derived_part_url(A, "ci") == partitioned and r2.derived_part_url(A, "r2") == r2.part_url(A)
    with pytest.raises(r2.DesktopR2Error):
        r2.derived_part_url(A, "s3")
    for partitioned_form in (True, False):
        for bad in (A.upper(), A[:-1], "../x", None):
            with pytest.raises(r2.DesktopR2Error):
                r2.github_pool_url(bad, partitioned=partitioned_form)
    # The same forms tools/shared_release_assets.py produces and release.gd shared_download accepts.
    import shared_release_assets as shared
    assert shared.download_url(r2.REPOSITORY, shared.name(A)) == partitioned
    assert shared.base(r2.REPOSITORY) + "/" + shared.name(A) == legacy
    for url in (partitioned, legacy):
        assert r2.part_url_matches({"url": url, "sha256": A}, "ci")
        assert not r2.part_url_matches({"url": url, "sha256": A}, "r2")
    per_release = f"https://github.com/{r2.REPOSITORY}/releases/download/client-{COMMIT}/{VERSION}.pkg.client.zip.001"
    for url in (per_release, r2.github_pool_url(B), partitioned.replace("client-assets-a", "client-assets-b"),
                partitioned.replace("rabbitlandsgame/", "someone/")):
        assert not r2.part_url_matches({"url": url, "sha256": A}, "ci")
    assert not r2.part_url_matches({"url": r2.part_url(B), "sha256": A}, "r2")


def test_rewrite_is_idempotent_and_copies():
    original = [package("records-00", [("app/data/x.json", 1)], parts=2, source="ci")]
    before = copy.deepcopy(original)
    once = r2.rewrite_part_urls(original)
    assert original == before
    assert all(part["url"] == r2.part_url(part["sha256"]) for part in once[0]["parts"])
    assert r2.rewrite_part_urls(once) == once


def test_object_headers():
    part = r2.object_headers(f"desktop/v1/parts/{A}.bin", A)
    assert part == {"ContentType": "application/octet-stream", "CacheControl": r2.IMMUTABLE_CACHE_CONTROL,
                    "Metadata": {"sha256": A}}
    assert r2.object_headers(f"desktop/v1/sets/linux/{A}.json", A)["ContentType"] == "application/json"
    pointer = r2.object_headers("desktop/v1/channels/live/windows.json", A, sequence=1762300000)
    assert pointer["CacheControl"] == "no-store" and pointer["Metadata"] == {"sha256": A, "sequence": "1762300000"}
    with pytest.raises(r2.FormatError):
        r2.object_headers("desktop/v1/channels/live/windows.json", A)
    for sequence in (r2.MAX_SEQUENCE, r2.MIN_SEQUENCE - 1, 1762300000123, True, 1762300000.0):
        with pytest.raises(r2.FormatError):   # the same bounds as a signed pointer's sequence
            r2.object_headers("desktop/v1/channels/live/windows.json", A, sequence=sequence)
    with pytest.raises(r2.FormatError):
        r2.object_headers(f"desktop/v1/parts/{A}.bin", A, sequence=1762300000)
    with pytest.raises(r2.KeyGuardError):
        r2.object_headers(f"browser/assets/{A}.bin", A)


# --- Content set -----------------------------------------------------------------

def test_valid_sets_pass_with_summary():
    summary = check(content_set(), commit=COMMIT, platform="windows", source="r2")
    assert summary["packages"] == 5 and summary["parts"] == 7 and summary["files"] == 7
    assert summary["reader_slots"] == 7 + len(r2.CI_PACKAGE_IDS)
    assert check(content_set("ci", "linux"), source="ci", platform="linux")["source"] == "ci"
    assert check(content_set(), reader_cap=r2.READER_CAP_W1A)["reader_cap"] == 2000
    assert r2.public_key_sha256(PEM) == KEY_SHA


def mutate(function):
    value = content_set()
    function(value)
    return value


def first(value, pid="records-00"):
    return next(item for item in value["packages"] if item["id"] == pid)


HEADER_CASES = [
    ("set-kind", lambda v: v.update(kind="rabbitlands-release-pointer")),
    ("set-kind", lambda v: v.update(set_schema=2)),
    ("set-kind", lambda v: v.update(set_schema=True)),
    ("repository", lambda v: v.update(repository="someone/rabbitlands-client")),
    ("commit", lambda v: v.update(commit=COMMIT.upper())),
    ("commit", lambda v: v.update(commit=COMMIT[:39])),
    ("platform", lambda v: v.update(platform="macos")),
    ("source", lambda v: v.update(source="s3")),
    ("version", lambda v: v.update(version="RabbitLands-Windows-2026114-012345678")),
    ("version", lambda v: v.update(version=VERSION.replace("Windows", "Linux"))),   # other platform
    ("version", lambda v: v.update(version=VERSION[:-1] + "9")),                    # other commit
    ("version", lambda v: v.update(version=VERSION + "-steam")),
    ("version", lambda v: v.update(version=VERSION + "\n")),
    ("public-key", lambda v: v.update(public_key_sha256=B)),
    ("packages", lambda v: v.update(packages=[])),
    ("optional-packages", lambda v: v.update(optional_packages={})),
]


@pytest.mark.parametrize("code,change", HEADER_CASES)
def test_header_rules(code, change):
    refused(mutate(change), code)


def test_expected_identity_must_match():
    refused(content_set(), "commit", commit="f" * 40)
    refused(content_set(), "platform", platform="linux")
    refused(content_set(), "source", source="ci")
    refused(content_set(), "reader-cap", reader_cap=900)
    with pytest.raises(r2.SetError):
        r2.validate_set(content_set(), public_key_sha256="")


def replace_part_url(value, url_for):
    for row in value["packages"]:
        for part in row["parts"]:
            part["url"] = url_for(part["sha256"])


def duplicate_part(value):
    row = first(value, "pck-actors")
    row["parts"][1].update(sha256=row["parts"][0]["sha256"], url=row["parts"][0]["url"], size=999)
    row["size"] = 2999


def oversized_part(value):
    row = first(value, "pck-actors")
    row["parts"][0]["size"] = r2.MAX_PART_BYTES + 1
    row["size"] = r2.MAX_PART_BYTES + 2001


PACKAGE_CASES = [
    ("package-id", lambda v: first(v).update(id="Records-00")),
    ("package-id", lambda v: first(v).update(id="r" * 97)),
    ("package-id", lambda v: first(v).update(id="records_00")),
    ("package-duplicate", lambda v: first(v).update(id="client")),
    ("package-ci", lambda v: first(v).update(id="engine")),
    ("package-ci", lambda v: first(v).update(id="native-runtime")),
    ("package-files", lambda v: first(v).update(files=[], file_count=0, unpacked_size=0)),
    ("package-identity", lambda v: first(v).update(sha256="x")),
    ("package-identity", lambda v: first(v).update(size=0)),
    ("package-unpacked-size", lambda v: first(v).update(unpacked_size=11)),
    ("package-file-count", lambda v: first(v).update(file_count=3)),
    ("package-parts", lambda v: first(v).update(parts=[])),
    ("package-size", lambda v: first(v).update(size=999)),
    ("package-single-part", lambda v: first(v)["parts"][0].update(sha256=B, url=r2.part_url(B))),
    ("part-size", lambda v: first(v, "pck-actors")["parts"][0].update(size=0)),
    ("part-size", oversized_part),
    ("part-identity", lambda v: first(v, "pck-actors")["parts"][1].update(sha256="nothex")),
    ("part-conflict", duplicate_part),
    ("file-identity", lambda v: first(v)["files"][0].update(sha256=B.upper())),
    ("file-identity", lambda v: first(v)["files"][0].update(size=-1)),
    ("file-identity", lambda v: first(v)["files"][1].update(size=False)),
    ("codec", lambda v: first(v)["files"][0].update(codec="brotli")),
    ("codec", lambda v: first(v)["files"][0].update(codec=None)),
    ("codec", lambda v: first(v).update(codec="gzip")),
]


@pytest.mark.parametrize("code,change", PACKAGE_CASES)
def test_package_rules(code, change):
    refused(mutate(change), code)


def test_codec_absent_or_zstd_only():
    value = content_set()
    assert first(value, "map-landfall-00")["files"][0]["codec"] == "zstd"
    assert all("codec" not in row for row in first(value)["files"])
    assert check(value)["files"] == 7


def test_part_urls_must_be_the_derived_form_for_the_source():
    for url_for in (lambda sha: r2.github_pool_url(sha),                        # ci form in an r2 set
                    lambda sha: r2.part_url(sha).replace(".bin", ".zip.part"),
                    lambda sha: f"https://assets.rabbitlandsgame.com/browser/assets/{sha}.bin",
                    lambda sha: f"https://evil.example/desktop/v1/parts/{sha}.bin",
                    lambda sha: r2.part_url(sha).replace("https://", "http://"),
                    lambda sha: r2.part_url(B if sha != B else A)):           # another row's key
        refused(mutate(lambda v: replace_part_url(v, url_for)), "part-url")
    ci = content_set("ci")
    replace_part_url(ci, r2.part_url)
    refused(ci, "part-url")
    ci = content_set("ci")
    replace_part_url(ci, lambda sha: r2.github_pool_url(sha, partitioned=False))
    assert check(ci)["source"] == "ci"


def test_validators_ignore_the_sets_own_asset_base_and_ci_paths():
    evil = "https://evil.example/desktop/v1/"
    value = content_set()
    value["asset_base"] = evil
    replace_part_url(value, lambda sha: f"{evil}parts/{sha}.bin")
    refused(value, "part-url")
    value = add_file(content_set(), "app/RabbitLands.exe")
    value["ci_paths"] = []
    refused(value, "ci-path")
    value = add_file(content_set(), "app/bin/client_runtime/runtime-manifest.json")
    value["ci_paths"] = ["app/other/"]
    refused(value, "ci-path")
    value = content_set()
    value["ci_paths"] = ["app/data/", "app/RabbitLands.pck"]   # would exclude real content if it were used
    value["asset_base"] = evil
    assert check(value)["files"] == 7
    del value["ci_paths"], value["asset_base"], value["builder"], value["qualification"]
    assert check(value)["files"] == 7


PATH_CASES = {
    "path-unsafe": ["app", "/app/data/x.json", "app/../app/data/x.json", "app/./x.json", "app//x.json",
                    "other/x.json", "App/data/x.json", "app/data/x.json.", "app/data/x.json ", "app/ data/x.json",
                    "app/data/CON.json", "app/data/lpt1", "app\\data\\x.json", "app/data/c:x.json",
                    "app/data/x?.json", "app/data/x*.json", "app/data/x\n.json", "app/data/x\x00.json",
                    "app/data/x\ty.json", "app/" + "x" * 1024],
    "path-tilde": ["app/RABBIT~1.EXE", "app/data/PROGRA~1/x.json", "eloria-assets/maps/~x.json"],
    "path-ascii": ["app/data/\u017fpell.json", "app/Rabbitland\u017f.exe", "app/data/caf\u00e9.json",
                   "app/data/x\u200b.json", "app/data/x\u0131.json", "app/data/x+y.json", "app/data/x#y.json",
                   "app/data/x%2e.json", "app/data/x'y.json", "app/data/x,y.json", "app/data/x;y.json",
                   "app/data/x@y.json", "app/data/x(1).json", "app/data/x!y.json"],
    "ci-path": ["app/RabbitLands.exe", "app/rabbitlands.EXE", "app/RABBITLANDS.X86_64", "app/RabbitLands.x86_64",
                "app/bin/client_runtime/client_runtime.dll", "app/BIN/Client_Runtime/runtime-manifest.json",
                "app/bin/client_runtime/client_runtime.gdextension", "app/bin/client_runtime",
                "app/bin", "app/RabbitLands.exe/inside.json"],
    "gdextension": ["app/bin/other/x.gdextension", "app/x.GDExtension", "eloria-assets/maps/a/b.gdextension"],
    "native-extension": ["app/data/plugin.dll", "app/data/x.DLL", "app/data/libx.so", "app/data/libx.so.1",
                         "app/data/libx.so.1.2", "app/data/x.dylib", "app/tools/other.exe",
                         "app/tools/server.x86_64", "eloria-assets/maps/a/b.Exe", "app/tools/run.com",
                         "app/tools/RUN.COM"],
    "engine-file": ["app/override.cfg", "app/Override.CFG", "app/.godot/extension_list.cfg",
                    "app/.GODOT/global_script_class_cache.cfg", "eloria-assets/maps/a/.godot/x.cfg"],
}


@pytest.mark.parametrize("code,path", [(code, path) for code, paths in PATH_CASES.items() for path in paths])
def test_path_rules(code, path):
    assert r2.path_problem(path) == code
    with pytest.raises(r2.SetError) as error:
        check(add_file(content_set(), path))
    # Absolute and backslash paths already fail the set-wide local-path rule.
    local = path.startswith("/") or "\\" in path
    assert error.value.code == ("set-local-path" if local else code)


def test_real_content_paths_pass():
    for path in ("app/data/space name.json", "app/packs/actors.pck", "app/assets/actors/x/y_z-1.glb",
                 "eloria-assets/maps/landfall/vram/ground.evt", "app/prepared-world/abc/catalog.json",
                 "app/data/libso.json", "app/data/x.so.json", "app/RabbitLands.pck", "app/bin/other.json",
                 "app/data/override.cfg", "app/data/x.godot", "app/data/.gdignore", "app/data/x.com.json"):
        assert r2.path_problem(path) is None, path


def test_paths_are_unique_by_casefold_across_packages_and_optional_packages():
    refused(add_file(content_set(), "app/data/ITEMS.json"), "path-duplicate")
    refused(add_file(content_set(), "app/DATA/Items.json", pid="client"), "path-duplicate")
    value = content_set()
    value["optional_packages"] = [{**package("prepared-content-00", [("app/data/items.json", 1)]),
                                   "feature": "prepared-content"}]
    refused(value, "path-duplicate")
    refused(add_file(content_set(), "app/data/items.json/inner.json"), "path-file-dir-conflict")
    refused(add_file(content_set(), "app/packs"), "path-file-dir-conflict")


def test_optional_packages_get_the_same_checks():
    value = content_set()
    value["optional_packages"] = [{**package("prepared-content-00", [("app/prepared/a.json", 1)]),
                                   "feature": "prepared-content"}]
    summary = check(value)
    assert summary["optional_packages"] == 1 and summary["parts"] == 8
    value["optional_packages"][0]["feature"] = "Prepared Content"
    refused(value, "package-feature")
    del value["optional_packages"][0]["feature"]
    refused(value, "package-feature")
    value = content_set()
    value["optional_packages"] = [{**package("prepared-content-00", [("app/prepared/a.exe", 1)]),
                                   "feature": "prepared-content"}]
    refused(value, "native-extension")
    value = content_set()
    value["optional_packages"] = [{**package("client", [("app/prepared/a.json", 1)]), "feature": "x"}]
    refused(value, "package-duplicate")


def test_required_packages_and_their_files():
    value = content_set()
    value["packages"] = [row for row in value["packages"] if row["id"] != "release-descriptor"]
    refused(value, "required-package")
    value = content_set()
    first(value, "client")["files"][0]["path"] = "app/Other.pck"
    refused(value, "required-package")
    value = content_set()
    client = first(value, "client")
    value["packages"].remove(client)
    value["optional_packages"] = [{**client, "feature": "core"}]
    refused(value, "required-package")


def many_parts(count):
    value = content_set()
    value["packages"].append(package("map-big-00", [("eloria-assets/maps/big/world.json", 1)], parts=count))
    return value


def test_reader_cap_counts_parts_and_reserved_ci_packages():
    base = check(content_set())["parts"]
    fits = r2.READER_CAP - len(r2.CI_PACKAGE_IDS) - base
    assert check(many_parts(fits))["reader_slots"] == r2.READER_CAP
    refused(many_parts(fits + 1), "reader-cap-exceeded")
    assert check(many_parts(fits + 1), reader_cap=r2.READER_CAP_W1A)["reader_slots"] == r2.READER_CAP + 1
    value = many_parts(fits)
    value["optional_packages"] = [{**package("prepared-content-00", [("app/prepared/a.json", 1)]),
                                   "feature": "prepared-content"}]
    refused(value, "reader-cap-exceeded")   # optional parts count too


def test_total_file_cap(monkeypatch):
    monkeypatch.setattr(r2, "MAX_FILES", 7)
    assert check(content_set())["files"] == 7
    refused(add_file(content_set(), "app/data/extra.json"), "file-count")


def test_set_must_not_carry_local_paths_or_floats():
    for leak in ("C:/Users/Someone/stage", "c:\\x", "/home/someone/stage", "~/stage", "file:///C:/x", "a\\b"):
        value = content_set()
        value["builder"]["stage"] = leak
        refused(value, "set-local-path")
        value = content_set()
        value["builder"][leak] = "stage"   # keys are public too
        refused(value, "set-local-path")
    value = content_set()
    value["qualification"]["seconds"] = 1.5
    refused(value, "canonical-float")
    value = content_set()
    first(value)["files"][0]["size"] = 2 ** 53
    refused(value, "canonical-int-range")


# --- Native magic -----------------------------------------------------------------

def pe(offset=0x80, total=0x200):
    data = bytearray(total)
    data[:2] = b"MZ"
    data[0x3C:0x40] = offset.to_bytes(4, "little")
    data[offset:offset + 4] = b"PE\0\0"
    return bytes(data)


def write_stage(tmp_path, value, overrides=None):
    for row in value["packages"] + value.get("optional_packages", []):
        for entry in row["files"]:
            target = tmp_path / entry["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((overrides or {}).get(entry["path"], b'{"plain": "json"}\n'))
    return r2.stage_sniffer(tmp_path)


@pytest.mark.parametrize("head,kind", [
    (pe(), "pe"), (b"\x7fELF\x02\x01\x01" + bytes(64), "elf"),
    (bytes.fromhex("cffaedfe") + bytes(60), "macho"), (bytes.fromhex("feedfacf") + bytes(60), "macho"),
    (bytes.fromhex("cefaedfe") + bytes(60), "macho"), (bytes.fromhex("cafebabe") + bytes(60), "macho"),
])
def test_native_magic_is_refused_whatever_the_name(tmp_path, head, kind):
    assert r2.sniff_native(head) == kind
    value = content_set()
    sniff = write_stage(tmp_path, value, {"app/data/items.json": head})
    error = refused(value, "native-magic", sniff=sniff)
    assert kind in str(error) and "items.json" in str(error)


def test_magic_sniff_edges(tmp_path):
    value = content_set()
    assert check(value, sniff=write_stage(tmp_path, value))["files"] == 7
    bare = b"MZ" + bytes(200)   # MZ without a PE signature is data
    assert r2.sniff_native(bare) is None
    assert r2.sniff_native(b"MZ") is None and r2.sniff_native(b"") is None
    far = pe(offset=6000, total=6100)
    assert r2.sniff_native(far[:r2.SNIFF_BYTES]) == "pe"            # unknown: conservative
    assert r2.sniff_native(far[:r2.SNIFF_BYTES], size=5000) is None  # header cannot fit
    (tmp_path / "far.bin").write_bytes(far)
    assert r2.sniff_file(tmp_path / "far.bin") == "pe"
    (tmp_path / "far-data.bin").write_bytes(far[:6000] + b"DATA" + far[6004:])
    assert r2.sniff_file(tmp_path / "far-data.bin") is None
    (tmp_path / "short.bin").write_bytes(pe(offset=0x80, total=0x200)[:0x82])  # header past the end
    assert r2.sniff_file(tmp_path / "short.bin") is None
    (tmp_path / "far-past-end.bin").write_bytes(far[:5000])
    assert r2.sniff_file(tmp_path / "far-past-end.bin") is None
    sniff = r2.stage_sniffer(tmp_path)
    with pytest.raises(r2.SetError):
        sniff("app/data/missing.json")
    with pytest.raises(r2.SetError):
        sniff("../outside.json")


# --- Canonical bytes -------------------------------------------------------------

def reorder(value):
    if isinstance(value, dict):
        return {key: reorder(value[key]) for key in reversed(list(value))}
    if isinstance(value, list):
        return [reorder(item) for item in value]
    return value


def test_canonical_bytes_are_stable():
    value = content_set()
    shuffled = reorder(value)
    assert list(shuffled) != list(value)
    data = r2.canonical_bytes(value)
    assert data == r2.canonical_bytes(shuffled) == r2.canonical_bytes(copy.deepcopy(value))
    assert r2.parse_set_bytes(data) == value
    assert data.isascii() and b" " not in data.replace(b"space name", b"") and not data.endswith(b"\n")
    golden = {"kind": r2.SET_KIND, "b": [1, True, None, "\u017f"], "a": {"z": 0, "y": "x"}}
    assert r2.canonical_bytes(golden) == (b'{"a":{"y":"x","z":0},"b":[1,true,null,"\\u017f"],'
                                          b'"kind":"rabbitlands-desktop-content-set"}')
    assert r2.sha256_hex(r2.canonical_bytes(golden)) == hashlib.sha256(r2.canonical_bytes(golden)).hexdigest()


def test_non_canonical_or_hostile_set_bytes_are_refused():
    value = content_set()
    for data in (json.dumps(value, indent=1).encode(), json.dumps(value).encode(),
                 r2.canonical_bytes(value) + b"\n", b"\xef\xbb\xbf" + r2.canonical_bytes(value),
                 b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1.0}', b"[]", b"not json", b"\xff"):
        with pytest.raises(r2.SetError):
            r2.parse_set_bytes(data)
    with pytest.raises(r2.SetError):
        r2.parse_set_bytes(b" " * (r2.MAX_SET_BYTES + 1))
    for bad in ({"a": 1.5}, {"a": float("nan")}, {1: "x"}, {"a": (1, 2)}, {"a": 2 ** 53}, {"a": b"x"}):
        with pytest.raises(r2.FormatError):
            r2.canonical_bytes(bad)


# --- Pointer ---------------------------------------------------------------------

def pointer(**changes):
    options = {"platform": "windows", "sequence": 1762300000, "rollback": False, "release_id": 123456789,
               "run_id": 987654321, "commit": COMMIT, "version": VERSION, "manifest_sequence": 1762290000,
               "manifest_sha256": A, "manifest_size": 8470917}
    options.update(changes)
    return r2.pointer_payload(**options)


def valid_commit(value):
    return isinstance(value, str) and re.fullmatch("[0-9a-f]{40}", value) is not None


# Python fixture copies of the released verifiers' identity checks (after a
# valid signature). Each mirrors the GDScript pinned in
# test_fixture_copies_match_the_released_verifiers.
def published_identity(release, trust):  # startup_update.gd published_identity
    if not valid_commit(release.get("commit")) or release.get("platform") != trust["platform"] \
            or release.get("repository", trust["repository"]) != trust["repository"]:
        return {"error": "The published release identity is invalid."}
    return release


def bootstrap_verify(release, identity):  # bootstrap.gd verify
    if release.get("bootstrap_schema") != 1 or release.get("repository") != identity["repository"] \
            or release.get("platform") != identity["platform"] or not valid_commit(release.get("commit")):
        return {"error": "The updater release identity is invalid."}
    return release


def verify_manifest(release, identity):  # release.gd verify_manifest
    if release.get("schema") not in (1, 2, 3):
        return {"error": "The update format is unsupported."}
    if not valid_commit(release.get("commit")) or release.get("platform") != identity["platform"]:
        return {"error": "The release is for a different client."}
    return release


def test_pointer_payload_shape():
    payload = pointer()
    assert payload["kind"] == "rabbitlands-release-pointer" and payload["pointer_schema"] == 1
    assert payload["target"]["commit"] == COMMIT
    assert payload["target"]["manifest"]["url"] == r2.manifest_url("windows", A)
    assert not r2.RELEASE_ONLY_FIELDS & set(payload)
    assert "commit" not in payload and "schema" not in payload and "packages" not in payload
    assert set(payload) == {"kind", "pointer_schema", "repository", "platform", "channel", "sequence", "rollback",
                            "release_id", "run_id", "target"}
    assert json.loads(r2.pointer_bytes(payload)) == payload
    assert pointer(rollback=True, platform="linux", version=VERSION.replace("Windows", "Linux"))["rollback"]
    prefix = r2.selftest_prefix("20261104", "0123abcd")
    selftest = pointer(prefix=prefix)
    assert selftest["target"]["manifest"]["url"] == r2.manifest_url("windows", A, prefix=prefix)
    # The self-test signs its pointer too: the signing bytes honour the prefix.
    assert json.loads(r2.pointer_bytes(selftest, platform="windows", prefix=prefix)) == selftest
    with pytest.raises(r2.PointerError):
        r2.pointer_bytes(selftest)
    with pytest.raises(r2.PointerError):
        r2.pointer_bytes(payload, prefix=prefix)
    with pytest.raises(r2.PointerError):
        r2.pointer_bytes(payload, platform="linux")


def test_released_verifiers_refuse_a_pointer_payload():
    payload = pointer()
    identity = {"repository": r2.REPOSITORY, "platform": "windows"}
    for verifier in (published_identity, bootstrap_verify, verify_manifest):
        assert "error" in verifier(payload, identity)
    # A payload that WOULD pass them is refused by the pointer verifier.
    release_like = {**payload, "commit": COMMIT, "schema": 3, "bootstrap_schema": 1}
    assert "error" not in published_identity(release_like, identity)
    with pytest.raises(r2.PointerError) as error:
        r2.validate_pointer(release_like)
    assert error.value.code == "pointer-release-field"


def test_fixture_copies_match_the_released_verifiers():
    updates = GODOT / "src/updates"

    def body(name, function):
        text = (updates / name).read_text(encoding="utf-8")
        start = text.index(f"static func {function}(")
        end = text.find("\nstatic func ", start + 1)
        return text[start:end if end > 0 else len(text)]
    assert 'not Release.valid_commit(release.get("commit"))' in body("startup_update.gd", "published_identity")
    assert 'release.get("bootstrap_schema") != 1' in body("bootstrap.gd", "verify")
    assert 'not Release.valid_commit(release.get("commit"))' in body("bootstrap.gd", "verify")
    assert 'valid_commit(release.get("commit"))' in body("release.gd", "verify_manifest")
    # The old API fallback picks the first asset ending in "-<platform>.json".
    assert 'name.ends_with("-%s.json" % platform)' in (updates / "startup_update.gd").read_text(encoding="utf-8")


def test_pointer_asset_name_never_looks_like_a_manifest():
    for platform in r2.PLATFORMS:
        name = r2.pointer_asset_name(platform)
        assert name == f"RabbitLands-{platform}-pointer.json"
        assert not any(name.endswith(f"-{other}.json") for other in r2.PLATFORMS)
        assert name != f"RabbitLands-{platform}.json"
    with pytest.raises(r2.PointerError):
        r2.pointer_asset_name("macos")


POINTER_CASES = [
    ("pointer-kind", lambda p: p.update(kind="rabbitlands-release")),
    ("pointer-kind", lambda p: p.pop("kind")),
    ("pointer-release-field", lambda p: p.update(commit=COMMIT)),
    ("pointer-release-field", lambda p: p.update(schema=3)),
    ("pointer-release-field", lambda p: p.update(bootstrap_schema=1)),
    ("pointer-release-field", lambda p: p.update(packages=[])),
    ("pointer-fields", lambda p: p.update(expires=1)),
    ("pointer-fields", lambda p: p.pop("run_id")),
    ("pointer-schema", lambda p: p.update(pointer_schema=2)),
    ("repository", lambda p: p.update(repository="someone/x")),
    ("platform", lambda p: p.update(platform="linux")),
    ("channel", lambda p: p.update(channel="test")),
    ("sequence", lambda p: p.update(sequence=1762300000123)),   # milliseconds
    ("sequence", lambda p: p.update(sequence=1762300000.0)),
    ("rollback", lambda p: p.update(rollback=0)),
    ("release-run", lambda p: p.update(run_id=0)),
    ("release-run", lambda p: p.update(release_id=True)),
    ("target", lambda p: p["target"].update(packages=[])),
    ("target-commit", lambda p: p["target"].update(commit="z" * 40)),
    ("target-version", lambda p: p["target"].update(version=VERSION.replace("012345678", "fedcba987"))),
    ("sequence-order", lambda p: p["target"].update(manifest_sequence=1762300000)),
    ("target-manifest", lambda p: p["target"]["manifest"].update(sha256=A.upper())),
    ("target-manifest-size", lambda p: p["target"]["manifest"].update(size=r2.MAX_ENVELOPE_BYTES + 1)),
    ("target-manifest-url", lambda p: p["target"]["manifest"].update(url=r2.manifest_url("windows", B))),
    ("target-manifest-url", lambda p: p["target"]["manifest"].update(url=r2.manifest_url("linux", A))),
    ("target-manifest-url", lambda p: p["target"]["manifest"].update(
        url=f"https://github.com/{r2.REPOSITORY}/releases/download/client-{COMMIT}/{VERSION}-windows.json")),
]


@pytest.mark.parametrize("code,change", POINTER_CASES)
def test_pointer_rules(code, change):
    payload = copy.deepcopy(pointer())
    change(payload)
    with pytest.raises(r2.PointerError) as error:
        r2.validate_pointer(payload, platform="windows")
    assert error.value.code == code


def test_pointer_is_bound_to_platform_and_layout():
    with pytest.raises(r2.PointerError):
        r2.validate_pointer(pointer(), platform="linux")
    with pytest.raises(r2.PointerError):   # a production pointer is not a self-test pointer
        r2.validate_pointer(pointer(), prefix=r2.selftest_prefix("20261104", "0123abcd"))
    with pytest.raises(r2.PointerError):
        pointer(platform="linux")   # the version names Windows


# --- Envelope gate -----------------------------------------------------------------

def envelope_of(total: int) -> bytes:
    """An envelope of exactly `total` bytes."""
    skeleton = json.dumps({"payload": "", "signature": base64.b64encode(b"s" * 512).decode()}).encode()
    room = (total - len(skeleton)) // 4 * 3
    data = json.dumps({"payload": base64.b64encode(b"p" * room).decode(),
                       "signature": base64.b64encode(b"s" * 512).decode()}).encode()
    return data + b" " * (total - len(data))   # JSON allows trailing whitespace


def test_envelope_must_be_at_most_15_mib():
    limit = 15 * 1024 * 1024
    assert r2.MAX_ENVELOPE_BYTES == limit and r2.CLIENT_MANIFEST_LIMIT == 16 * 1024 * 1024
    exact = envelope_of(limit)
    assert len(exact) == limit and r2.check_envelope(exact)["margin"] == 0
    with pytest.raises(r2.EnvelopeError) as error:
        r2.check_envelope(envelope_of(limit + 1))
    assert error.value.code == "envelope-too-large"
    small = envelope_of(4096)
    assert r2.check_pointer_envelope(small)["limit"] == r2.MAX_POINTER_BYTES
    with pytest.raises(r2.EnvelopeError):
        r2.check_pointer_envelope(envelope_of(r2.MAX_POINTER_BYTES + 1))


def test_envelope_shape():
    good = {"payload": base64.b64encode(b"{}").decode(), "signature": base64.b64encode(b"sig").decode()}
    assert r2.check_envelope(json.dumps(good).encode())["payload_bytes"] == 2
    for bad in ({**good, "extra": "x"}, {"payload": good["payload"]}, {**good, "payload": "!!!"},
                {**good, "payload": ""}, {**good, "signature": 5}, [good]):
        with pytest.raises(r2.EnvelopeError):
            r2.check_envelope(json.dumps(bad).encode())
    for data in (b"", b"{", b'{"payload":"e30=","payload":"e30=","signature":"c2ln"}'):
        with pytest.raises(r2.EnvelopeError):
            r2.check_envelope(data)


# --- Manifest additions ------------------------------------------------------------

def test_manifest_additions():
    roots = [{"name": "RabbitLands.bat", "size": 120, "sha256": A},
             {"name": "AUDIO-CREDITS.txt", "size": 5, "sha256": B}]
    added = r2.manifest_additions(platform="windows", sequence=1762290000, helpers_fingerprint=A,
                                  root_files=roots, source="r2", set_sha256=B)
    assert added["content"] == {"source": "r2", "set": {"sha256": B, "url": r2.set_url("windows", B)}}
    assert added["sequence"] == 1762290000 and added["root_files"] == roots
    ci = r2.manifest_additions(platform="linux", sequence=1762290000, helpers_fingerprint=A, root_files=[],
                               source="ci", set_sha256=B)
    assert ci["content"] == {"source": "ci", "set": {"sha256": B}}
    release = {"schema": 3, "commit": COMMIT, **added}
    assert r2.validate_manifest_additions(release, platform="windows") is release
    for change in ({"sequence": 1762290000000}, {"sequence": None}, {"helpers_fingerprint": "x"},
                   {"root_files": [{"name": "../x", "size": 1, "sha256": A}]},
                   {"root_files": [{"name": "a.bat", "size": 1, "sha256": A}, {"name": "A.BAT", "size": 1, "sha256": A}]},
                   {"root_files": [{"name": "CON.txt", "size": 1, "sha256": A}]},
                   {"root_files": [{"name": "a.bat", "size": 1, "sha256": A, "path": "/x"}]},
                   {"content": {"source": "r2", "set": {"sha256": B, "url": r2.set_url("linux", B)}}},
                   {"content": {"source": "r2", "set": {"sha256": B}}},
                   {"content": {"source": "s3", "set": {"sha256": B}}}):
        with pytest.raises(r2.ManifestError):
            r2.validate_manifest_additions({**release, **change}, platform="windows")


@pytest.mark.parametrize("platform", r2.PLATFORMS)
def test_root_files_admit_the_real_launcher_names(tmp_path, platform):
    # CI records every stage-root file, the profile launchers among them
    # (tools/client_runtime_package.write_launchers, read only here).
    import client_runtime_package
    client_runtime_package.write_launchers(tmp_path, platform)
    names = sorted(path.name for path in tmp_path.iterdir())
    assert any("(" in name for name in names)
    names += ["RabbitLands.bat", "RabbitLands (debug console).bat", "RabbitLands.sh", "RabbitLands-debug.sh",
              "README.txt", "AUDIO-CREDITS.txt", "launcher-defaults.json"]
    roots = [{"name": name, "size": 1, "sha256": digest(name)} for name in names]
    added = r2.manifest_additions(platform=platform, sequence=1762290000, helpers_fingerprint=A,
                                  root_files=roots, source="ci", set_sha256=B)
    assert [row["name"] for row in added["root_files"]] == names
    for bad in ("app/RabbitLands.bat", "a:b.bat", "x\\y.bat", ".eloria-package-marker", "x?.bat", "COM1.bat",
                "x.bat.", "(x).bat", "x~1.bat", "xé.bat"):
        with pytest.raises(r2.ManifestError):
            r2.manifest_additions(platform=platform, sequence=1762290000, helpers_fingerprint=A,
                                  root_files=[{"name": bad, "size": 1, "sha256": A}], source="ci", set_sha256=B)


# --- R2 configuration --------------------------------------------------------------

ACCOUNT = "0123456789abcdef0123456789abcdef"
KEY_ID = "feedfacecafebeef0123456789abcdef"
SECRET = "5ecre7" + "9" * 58
CONFIG = {"endpoint_url": f"https://{ACCOUNT}.r2.cloudflarestorage.com", "bucket": "rabbit-lands-assets",
          "access_key_id": KEY_ID, "secret_access_key": SECRET,
          "public_base_url": "https://assets.rabbitlandsgame.com/browser/assets/"}
SECRETS = (ACCOUNT, KEY_ID, SECRET, "cloudflarestorage", "5ecre7")


def write_config(tmp_path, value, name="r2.json"):
    path = tmp_path / name
    path.write_bytes(value if isinstance(value, bytes) else json.dumps(value).encode())
    return path


def test_config_loads_and_hides_its_secrets(tmp_path):
    config = r2.load_r2_config(write_config(tmp_path, CONFIG))
    assert config.bucket == "rabbit-lands-assets" and config.public_base_url == CONFIG["public_base_url"]
    assert config.client_kwargs() == {"endpoint_url": CONFIG["endpoint_url"], "aws_access_key_id": KEY_ID,
                                      "aws_secret_access_key": SECRET, "region_name": "auto"}
    for text in (repr(config), str(config), f"{config}"):
        assert not any(secret in text for secret in SECRETS)
    assert set(config.secret_values()) >= {ACCOUNT, KEY_ID, SECRET, CONFIG["endpoint_url"]}
    assert r2.contains_secret(f"error at {ACCOUNT.upper()}.r2", config)
    assert not r2.contains_secret("bucket rabbit-lands-assets " + CONFIG["public_base_url"], config)
    with pytest.raises(TypeError):
        import pickle
        pickle.dumps(config)
    bom = write_config(tmp_path, b"\xef\xbb\xbf" + json.dumps({**CONFIG, "endpoint_url": CONFIG["endpoint_url"] + "/ ",
                                                                  "public_base_url": None}).encode(), "bom.json")
    assert r2.load_r2_config(bom).public_base_url is None
    eu = r2.load_r2_config(write_config(tmp_path, {**CONFIG, "endpoint_url": f"https://{ACCOUNT}.eu.r2.cloudflarestorage.com:443"}, "eu.json"))
    assert eu.client_kwargs()["endpoint_url"] == f"https://{ACCOUNT}.eu.r2.cloudflarestorage.com"
    assert set(r2.SECRET_CONFIG_FIELDS) == {"endpoint_url", "access_key_id", "secret_access_key"}
    assert set(r2.NON_SECRET_CONFIG_FIELDS) == {"bucket", "public_base_url"}


MALFORMED = {
    "config-not-json": [b"{" + SECRET.encode(), f'{{"secret_access_key": "{SECRET}", }}'.encode(),
                        json.dumps([CONFIG]).encode(), b"\xff\xfe" + SECRET.encode(),
                        f'{{"secret_access_key": "{SECRET}", "secret_access_key": "{SECRET}"}}'.encode(),
                        f'{{"secret_access_key": "{SECRET}", "x": NaN}}'.encode()],
    "config-endpoint": [{**CONFIG, "endpoint_url": f"https://{ACCOUNT}.r2.cloudflarestorage.com:{SECRET}"},
                        {**CONFIG, "endpoint_url": f"https://{ACCOUNT}.r2.cloudflarestorage.com:99999"},
                        {**CONFIG, "endpoint_url": f"https://[{ACCOUNT}.r2.cloudflarestorage.com"},
                        {**CONFIG, "endpoint_url": f"http://{ACCOUNT}.r2.cloudflarestorage.com"},
                        {**CONFIG, "endpoint_url": f"https://{KEY_ID}:{SECRET}@{ACCOUNT}.r2.cloudflarestorage.com"},
                        {**CONFIG, "endpoint_url": f"https://{ACCOUNT}.r2.cloudflarestorage.com/{SECRET}"},
                        {**CONFIG, "endpoint_url": f"https://{ACCOUNT}.r2.cloudflarestorage.com?k={SECRET}"},
                        {**CONFIG, "endpoint_url": f"https://{ACCOUNT}.r2.cloudflarestorage.com.evil.example"},
                        {**CONFIG, "endpoint_url": f"https://{ACCOUNT[:-1]}.r2.cloudflarestorage.com"},
                        {**CONFIG, "endpoint_url": f"https://{ACCOUNT}.r2.cloudflare storage.com"},
                        {**CONFIG, "endpoint_url": 12345}, {k: v for k, v in CONFIG.items() if k != "endpoint_url"}],
    "config-bucket": [{**CONFIG, "bucket": "other-bucket"}, {**CONFIG, "bucket": SECRET},
                      {**CONFIG, "bucket": None}],
    "config-access-key": [{**CONFIG, "access_key_id": ""}, {**CONFIG, "access_key_id": KEY_ID + " x"},
                          {**CONFIG, "access_key_id": 5}, {**CONFIG, "access_key_id": KEY_ID + "\n" + SECRET}],
    "config-secret": [{**CONFIG, "secret_access_key": ""}, {**CONFIG, "secret_access_key": SECRET + "\u00e9"},
                      {**CONFIG, "secret_access_key": ["x"]}, {**CONFIG, "secret_access_key": "short"}],
    "config-public-base": [{**CONFIG, "public_base_url": f"https://evil.example/{SECRET}"},
                           {**CONFIG, "public_base_url": 5}],
}


@pytest.mark.parametrize("code,value", [(code, value) for code, values in MALFORMED.items() for value in values])
def test_malformed_configs_raise_only_sanitized_errors(tmp_path, code, value):
    path = write_config(tmp_path, value)
    with pytest.raises(r2.ConfigError) as caught:
        r2.load_r2_config(path)
    error = caught.value
    assert error.code == code
    assert error.__cause__ is None and error.__context__ is None
    rendered = "".join(traceback.format_exception(error)) + repr(error) + str(error) + repr(error.args)
    assert not any(secret in rendered for secret in SECRETS)
    assert str(path) not in rendered and str(error) == f"{code}: {r2.ConfigError.MESSAGES[code]}"


def test_unreadable_or_oversized_configs(tmp_path):
    for path, code in ((tmp_path / "missing.json", "config-unreadable"), (tmp_path, "config-unreadable"),
                       (write_config(tmp_path, b" " * (r2.MAX_CONFIG_BYTES + 1)), "config-too-large")):
        with pytest.raises(r2.ConfigError) as caught:
            r2.load_r2_config(path)
        assert caught.value.code == code and caught.value.__context__ is None
        assert str(tmp_path) not in str(caught.value)


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def test_private_path_rules(tmp_path):
    outside = tmp_path / "outside" / "receipt.json"
    assert r2.require_private_path(outside) == outside.resolve()
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / ".gitignore").write_text("ignored/\n*.receipt.json\n", encoding="utf-8")
    assert r2.require_private_path(repo / "ignored" / "deep" / "plan.json")
    assert r2.require_private_path(repo / "x.receipt.json")
    for path in (repo / "receipt.json", repo / "sub" / "set.json", repo / ".gitignore"):
        with pytest.raises(r2.OutputPathError):
            r2.require_private_path(path)
    tracked = repo / "ignored" / "tracked.json"
    tracked.parent.mkdir(exist_ok=True)
    tracked.write_text("{}", encoding="utf-8")
    git(repo, "add", "-f", "--", "ignored/tracked.json")
    with pytest.raises(r2.OutputPathError):
        r2.require_private_path(tracked)
    config = write_config(repo, CONFIG, "r2.json")
    with pytest.raises(r2.ConfigError) as caught:
        r2.load_r2_config(config)
    assert caught.value.code == "config-location"
    assert r2.load_r2_config(config, check_location=False).bucket == r2.BUCKET
    (repo / "ignored").mkdir(exist_ok=True)
    assert r2.load_r2_config(write_config(repo / "ignored", CONFIG, "r2.json")).bucket == r2.BUCKET
