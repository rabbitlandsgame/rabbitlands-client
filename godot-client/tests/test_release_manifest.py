"""Release payloads, Python signing and pointers (tools/release_manifest.py).

No network, R2, GitHub or Godot: publish_artifacts runs with a fake run_godot,
keys are throwaway RSA keys (never the committed update_public.pem), and the
commits are throwaway Git repositories. test_desktop_release_ci.py reuses the
fixture builders below.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import types

import pytest

GODOT = Path(__file__).resolve().parents[1]
TOOLS = GODOT / "tools"
sys.path.insert(0, str(TOOLS))
import desktop_r2 as r2  # noqa: E402
import release_manifest as rm  # noqa: E402
import upload_desktop_assets as up  # noqa: E402

COMMITTED_PEM = (GODOT / "data/update_public.pem").read_bytes()
COMMIT = "0123456789abcdef0123456789abcdef01234567"
PARENT = "fedcba9876543210fedcba9876543210fedcba98"
SEQUENCE = 1_762_300_000
FINGERPRINT = "f" * 64
NEW_FIELDS = ("sequence", "helpers_fingerprint", "root_files", "content")
CAPS2 = rm.ReaderCapabilities(schema3=False, r2_rows=False, package_limit=850)
CAPS3 = rm.ReaderCapabilities(schema3=True, r2_rows=False, package_limit=850)
CAPS_R2 = rm.ReaderCapabilities(schema3=True, r2_rows=True, package_limit=2000)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pe_bytes(tail: bytes = b"") -> bytes:
    return b"MZ" + b"\0" * 58 + (64).to_bytes(4, "little") + b"PE\0\0" + b"\0" * 64 + tail


def elf_bytes(tail: bytes = b"") -> bytes:
    return b"\x7fELF" + b"\x02\x01\x01" + b"\0" * 9 + tail


def rsa_key(bits=2048):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=bits)
    return types.SimpleNamespace(
        key=key,
        private=key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()),
        public=key.public_key().public_bytes(serialization.Encoding.PEM,
                                             serialization.PublicFormat.SubjectPublicKeyInfo))


@pytest.fixture(scope="session")
def key():
    value = rsa_key()
    assert value.public != COMMITTED_PEM
    return value


@pytest.fixture(scope="session")
def other_key():
    return rsa_key()


def identity(platform="windows", key=None, commit=COMMIT, ancestors=None) -> dict:
    return {"schema": 1, "commit": commit, "platform": platform, "ancestors": ancestors or [commit, PARENT],
            "public_key": key.public.decode("ascii") if key else "", "repository": r2.REPOSITORY,
            "distribution": "github", "release_build": True}


def version(platform="windows", commit=COMMIT, date="20261104") -> str:
    return f"RabbitLands-{platform.title()}-{date}-{commit[:9]}"


CONTENT = {
    "app/RabbitLands.pck": b"GDPC" + bytes(range(256)) * 40,
    "app/assets/actors/wolf/grey/wolf.glb": b"glTF" + b"w" * 3000,
    "app/assets/audio/howl.ogg": b"OggS" + b"a" * 1000,
    "app/assets/ui/Big Banner.png": b"\x89PNG" + b"b" * 300,
    "app/data/items.json": b'{"items": []}',
    "eloria-assets/maps/meadow/data.json": b'{"map": "meadow"}',
    "eloria-assets/maps/meadow/vram/ground.evt": b"EVT1" + b"g" * 700,
}
ENGINE = {"windows": "app/RabbitLands.exe", "linux": "app/RabbitLands.x86_64"}
LIBRARY = {"windows": "client_runtime.dll", "linux": "client_runtime.so"}


def ci_files(platform: str, native: bool = True) -> dict:
    binary = pe_bytes if platform == "windows" else elf_bytes
    files = {ENGINE[platform]: binary(b"engine")}
    if native:
        files.update({f"app/bin/client_runtime/{LIBRARY[platform]}": binary(b"runtime"),
                      "app/bin/client_runtime/client_runtime.gdextension": b"[configuration]\n",
                      "app/bin/client_runtime/runtime-manifest.json": b'{"abi": 1}'})
    return files


HELPER = {"windows": "RabbitLands-updater.exe", "linux": "RabbitLands-updater.x86_64"}
UNINSTALL = {"windows": "RabbitLands-uninstall.exe", "linux": "RabbitLands-uninstall.x86_64"}
LAUNCH_ARGS = ["--server=game.rabbitlandsgame.com", "--port=2001"]


def make_stage(root: Path, platform: str, key, *, native: bool = True, commit: str = COMMIT,
               content: dict | None = None) -> Path:
    """A package_client stage: content, CI binaries, both descriptors, helpers and root files."""
    stage = Path(root) / version(platform, commit)
    meta = json.dumps(identity(platform, key, commit)).encode()
    files = {**(CONTENT if content is None else content), **ci_files(platform, native),
             "app/client-release.json": meta, "app/data/client_release.json": meta}
    for relative, data in files.items():
        path = stage / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (stage / "launcher-defaults.json").write_text(json.dumps({"args": LAUNCH_ARGS}), encoding="utf-8")
    (stage / HELPER[platform]).write_bytes((pe_bytes if platform == "windows" else elf_bytes)(b"updater"))
    os.link(stage / HELPER[platform], stage / UNINSTALL[platform])
    (stage / ".eloria-package").write_text(commit + "\n", encoding="ascii")
    return stage


def view_without_ci(stage: Path, target: Path) -> Path:
    """desktop_content's view: app/ and eloria-assets/ minus the CI-owned paths."""
    for path in stage.rglob("*"):
        relative = path.relative_to(stage).as_posix()
        if path.is_file() and relative.startswith(("app/", "eloria-assets/")) and not r2.is_ci_path(relative):
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.link(path, destination)
    return target


def content_packages(stage: Path, work: Path, source: str = "r2") -> list:
    import asset_packages
    import shared_release_assets
    view = view_without_ci(stage, Path(work) / "view" / stage.name)
    built = asset_packages.build(view, shared_release_assets.base(r2.REPOSITORY), shared="partitioned")
    return r2.rewrite_part_urls(built) if source == "r2" else built


def ci_packages(stage: Path, platform: str, work: Path) -> list:
    import desktop_release_ci as ci
    parts = Path(work) / "ci-parts"
    parts.mkdir(parents=True, exist_ok=True)
    native = sorted(path.relative_to(stage).as_posix() for path in (stage / "app/bin/client_runtime").rglob("*")
                    if path.is_file()) if (stage / "app/bin/client_runtime").is_dir() else []
    packages = [ci.ci_package(stage, "engine", [ENGINE[platform]], parts)]
    if native:
        packages.append(ci.ci_package(stage, "native-runtime", native, parts))
    return packages


def helper_rows(stage: Path, platform: str) -> dict:
    data = (stage / HELPER[platform]).read_bytes()
    return {kind: {"url": rm.helper_url(sha(data), kind, platform), "size": len(data), "sha256": sha(data)}
            for kind in rm.HELPER_KINDS}


ROOT_FILES = [{"name": "README.txt", "size": 12, "sha256": "1" * 64},
              {"name": "RabbitLands.bat", "size": 40, "sha256": "2" * 64}]


def build_payload(stage: Path, platform: str, key, work: Path, *, source="r2", caps=CAPS_R2, **changes) -> dict:
    options = dict(identity=identity(platform, key), version=stage.name,
                   content_packages=content_packages(stage, work, source),
                   ci_packages=ci_packages(stage, platform, work), helpers=helper_rows(stage, platform),
                   launch_args=list(LAUNCH_ARGS), capabilities=caps, source=source, set_sha256="c" * 64,
                   sequence=SEQUENCE, helpers_fingerprint=FINGERPRINT, root_files=ROOT_FILES)
    options.update(changes)
    return rm.payload(**options)


def published_bytes(stage: Path, platform: str, key, logs: Path, *, source: Path = GODOT, **options) -> bytes:
    """client_release.publish_artifacts' release-payload.json bytes (shared pools, fake Godot)."""
    import client_release
    calls = []

    def run_godot(godot, args, log, timeout):
        calls.append(args)
        if "sign" in args:
            Path(args[-1]).write_text("{}", encoding="utf-8")
    logs.mkdir(parents=True, exist_ok=True)
    client_release.publish_artifacts(stage, identity(platform, key), Path("unused-private.pem"), Path("godot"),
                                     source, run_godot, logs, shared="partitioned", **options)
    assert len(calls) == 2
    return (logs / "release-payload.json").read_bytes()


def published_payload(stage: Path, platform: str, key, logs: Path) -> dict:
    """client_release.publish_artifacts' release-payload.json (shared pools, fake Godot)."""
    return json.loads(published_bytes(stage, platform, key, logs))


# --- Equality with publish_artifacts ----------------------------------------------------

@pytest.mark.parametrize("platform", ["windows", "linux"])
def test_payload_equals_publish_artifacts_apart_from_schema_and_new_fields(tmp_path, key, platform):
    """ci source, schema-2 reader, no native runtime: byte-for-byte the same rows."""
    stage = make_stage(tmp_path / "published", platform, key, native=False)
    old = published_payload(stage, platform, key, tmp_path / "logs")
    new = build_payload(stage, platform, key, tmp_path / "new", source="ci", caps=CAPS2)
    assert {name: value for name, value in new.items() if name not in NEW_FIELDS} == old
    assert new["schema"] == old["schema"] == 2
    assert new["content"] == {"source": "ci", "set": {"sha256": "c" * 64}}
    assert new["sequence"] == SEQUENCE and new["helpers_fingerprint"] == FINGERPRINT
    assert new["root_files"] == ROOT_FILES


def without_r2_fields(payload: dict) -> dict:
    return {name: value for name, value in payload.items() if name not in NEW_FIELDS}


@pytest.mark.parametrize("platform", ["windows", "linux"])
def test_publish_artifacts_and_payload_share_one_writer_byte_for_byte(tmp_path, key, platform):
    """One manifest writer: equal rows give byte-equal payload bytes on the local/full-CI path
    (publish_artifacts) and the R2 workflow's (payload, apart from its R2 additions)."""
    stage = make_stage(tmp_path / "published", platform, key, native=False)
    old = published_bytes(stage, platform, key, tmp_path / "logs")
    new = build_payload(stage, platform, key, tmp_path / "new", source="ci", caps=CAPS2)
    assert old == rm.payload_bytes(without_r2_fields(new)) == r2.canonical_bytes(json.loads(old))
    # signing is deterministic, so both paths sign the same bytes into the same manifest
    private = rm.load_signing_key(key.private, key.public)
    assert rm.sign(old, private) == rm.sign(rm.payload_bytes(without_r2_fields(new)), private)
    # this tree's reader reads schema 3: the R2 workflow signs 3, the local path the lowest its rows need (2)
    three = build_payload(stage, platform, key, tmp_path / "three", source="ci", caps=CAPS3)
    assert three["schema"] == 3 and json.loads(old)["schema"] == 2
    assert old == rm.payload_bytes({**without_r2_fields(three), "schema": 2})


def _codec_rows(monkeypatch):
    import asset_packages
    real = asset_packages.build

    def build(*args, **options):
        packages = real(*args, **options)
        for package in packages:
            if package["id"] == "client":
                package["files"][0]["codec"] = "zstd"
        return packages
    monkeypatch.setattr(asset_packages, "build", build)


def reader_folder(root: Path, release_gd: str, package_updates_gd: str | None = None) -> Path:
    folder = Path(root) / "godot-client"
    (folder / "src/updates").mkdir(parents=True)
    (folder / "src/updates/release.gd").write_text(release_gd, encoding="utf-8")
    if package_updates_gd is not None:
        (folder / "src/updates/package_updates.gd").write_text(package_updates_gd, encoding="utf-8")
    return folder


def test_publish_artifacts_writes_schema_3_only_for_zstd_rows_its_reader_reads(tmp_path, key, monkeypatch):
    stage = make_stage(tmp_path / "published", "windows", key, native=False)
    _codec_rows(monkeypatch)
    assert json.loads(published_bytes(stage, "windows", key, tmp_path / "logs"))["schema"] == 3
    # a packaged reader without the schema-3 declaration cannot read zstd rows: nothing is signed
    old_reader = reader_folder(tmp_path / "old", RELEASE_GD, CAP_850)
    with pytest.raises(rm.ManifestError) as error:
        published_bytes(stage, "windows", key, tmp_path / "logs-old", source=old_reader)
    assert error.value.code == "codec-needs-schema-3"


def test_publish_artifacts_refuses_more_packages_than_the_packaged_reader_reads(tmp_path, key):
    stage = make_stage(tmp_path / "published", "windows", key, native=False)
    small = reader_folder(tmp_path / "small", RELEASE_GD + SCHEMA3_LINE, CAP_850.replace("850", "2"))
    accepted = []
    with pytest.raises(rm.ManifestError) as error:
        published_bytes(stage, "windows", key, tmp_path / "logs", source=small,
                        accept_part=lambda path, row: accepted.append(Path(path).name))
    assert error.value.code == "reader-cap-exceeded"
    # package parts upload as they are built; the helpers are refused before theirs
    assert accepted and not [name for name in accepted if "updater" in name or "uninstall" in name]
    with pytest.raises(rm.ManifestError) as error:
        rm.folder_capabilities(tmp_path / "nowhere")
    assert error.value.code == "reader"


def test_release_payload_refusals(tmp_path, key):
    stage = make_stage(tmp_path / "stage", "windows", key)
    rows = dict(schema=2, repository=r2.REPOSITORY, commit=COMMIT, ancestors=[COMMIT, PARENT], platform="windows",
                version=stage.name, packages=content_packages(stage, tmp_path / "work", "ci"),
                helpers=helper_rows(stage, "windows"), launch_args=list(LAUNCH_ARGS), capabilities=CAPS2)
    release = rm.release_payload(**rows)
    assert [package["id"] for package in release["packages"]] == sorted(p["id"] for p in rows["packages"])
    assert rm.release_payload(**{**rows, "packages": list(reversed(rows["packages"]))}) == release
    for change, code in (({"schema": 3}, "schema"), ({"schema": 1}, "schema"), ({"schema": True}, "schema"),
                         ({"capabilities": None}, "reader"), ({"packages": None}, "packages"),
                         ({"helpers": {"updater": rows["helpers"]["updater"]}}, "helpers"),
                         ({"launch_args": "--server"}, "launch-args"),
                         ({"capabilities": rm.ReaderCapabilities(schema3=False, r2_rows=False, package_limit=2)},
                          "reader-cap-exceeded")):
        with pytest.raises(r2.DesktopR2Error) as error:
            rm.release_payload(**{**rows, **change})
        assert error.value.code == code, change
    assert rm.release_payload(**{**rows, "schema": 3, "capabilities": CAPS3})["schema"] == 3
    assert rm.release_schema(rows["packages"], CAPS2) == 2


def test_the_r2_source_needs_the_exact_w1a_reader():
    assert "CODEC_SCHEMA" in rm.r2_source_problem(CAPS2)
    assert "DESKTOP_ASSETS" in rm.r2_source_problem(CAPS3)
    assert "2000" in rm.r2_source_problem(rm.ReaderCapabilities(schema3=True, r2_rows=True, package_limit=850))
    assert rm.r2_source_problem(CAPS_R2) is None
    assert rm.r2_source_problem(None)
    w1a = rm.reader_capabilities(RELEASE_GD + SCHEMA3_LINE + R2_LINE, CAP_2000)
    assert rm.r2_source_problem(w1a) is None
    # the line must be exact: another base, a commented line or a lower limit keep the gate shut
    for release_gd, package_updates_gd in ((RELEASE_GD + SCHEMA3_LINE + R2_LINE.replace("v1/", "v2/"), CAP_2000),
                                           (RELEASE_GD + SCHEMA3_LINE + "# " + R2_LINE, CAP_2000),
                                           (RELEASE_GD + SCHEMA3_LINE + R2_LINE.replace(":=", "="), CAP_2000),
                                           (RELEASE_GD + SCHEMA3_LINE + R2_LINE, CAP_850)):
        assert rm.r2_source_problem(rm.reader_capabilities(release_gd, package_updates_gd)), release_gd


def test_this_trees_updater_opens_the_r2_gate_with_the_w1a_text():
    release_gd = (GODOT / "src/updates/release.gd").read_text(encoding="utf-8")
    package_updates_gd = (GODOT / "src/updates/package_updates.gd").read_text(encoding="utf-8")
    assert release_gd.splitlines().count(R2_LINE.rstrip("\n")) == 1
    assert "release.packages.size() > 2000" in package_updates_gd and "> 850" not in package_updates_gd
    assert rm.r2_source_problem(rm.folder_capabilities(GODOT)) is None
    assert rm.folder_capabilities(GODOT) == rm.reader_capabilities(release_gd, package_updates_gd)


def test_r2_payload_differs_only_in_schema_hosting_and_new_fields(tmp_path, key):
    stage = make_stage(tmp_path / "published", "windows", key, native=False)
    old = published_payload(stage, "windows", key, tmp_path / "logs")
    new = build_payload(stage, "windows", key, tmp_path / "new", source="r2", caps=CAPS_R2)
    assert new["schema"] == 3 and new["content"]["set"]["url"] == r2.set_url("windows", "c" * 64)
    hosted = {part["sha256"]: part for part in new["parts"]}
    for package in old["packages"]:
        for part in package["parts"]:
            if package["id"] == "engine":
                assert hosted[part["sha256"]] == part  # CI packages stay in the GitHub pool
            else:
                assert hosted[part["sha256"]]["url"] == r2.part_url(part["sha256"])
                part["url"] = r2.part_url(part["sha256"])
    old["parts"] = [part for package in old["packages"] for part in package["parts"]]
    old["sha256"] = rm.packages_sha256(old["packages"])
    old["schema"] = 3
    assert {name: value for name, value in new.items() if name not in NEW_FIELDS} == old


def test_native_runtime_files_move_to_their_own_ci_package(tmp_path, key):
    stage = make_stage(tmp_path / "published", "windows", key, native=True)
    old = published_payload(stage, "windows", key, tmp_path / "logs")
    new = build_payload(stage, "windows", key, tmp_path / "new", source="ci", caps=CAPS3)

    def rows(payload):
        return sorted((e["path"], e["size"], e["sha256"]) for p in payload["packages"] for e in p["files"])
    assert rows(new) == rows(old)
    native = next(package for package in new["packages"] if package["id"] == "native-runtime")
    assert [entry["path"] for entry in native["files"]] == sorted(
        path for path in ci_files("windows") if path.startswith("app/bin/client_runtime/"))
    old_ids = {package["id"]: package for package in old["packages"]}
    for package in new["packages"]:
        if package["id"] in ("engine", "native-runtime") or not package["id"].startswith("records-"):
            if package["id"] not in ("native-runtime",):
                assert package["sha256"] == old_ids[package["id"]]["sha256"], package["id"]
            continue
        before = [entry for entry in old_ids[package["id"]]["files"] if not r2.is_ci_path(entry["path"])]
        assert package["files"] == before
    assert all(not r2.is_ci_path(entry["path"]) for package in new["packages"]
               if package["id"] not in r2.CI_PACKAGE_IDS for entry in package["files"])


# --- Shape, totals and overlap ------------------------------------------------------------

def test_schema_3_payload_shape_sequence_and_totals(tmp_path, key):
    stage = make_stage(tmp_path / "stage", "linux", key)
    payload = build_payload(stage, "linux", key, tmp_path / "work")
    assert payload["schema"] == 3 and payload["bootstrap_schema"] == 1 and payload["sequence"] == SEQUENCE
    ids = [package["id"] for package in payload["packages"]]
    assert ids == sorted(ids) and {"engine", "native-runtime", "client", "release-descriptor"} <= set(ids)
    assert payload["parts"] == [part for package in payload["packages"] for part in package["parts"]]
    assert payload["size"] == sum(package["size"] for package in payload["packages"])
    assert payload["unpacked_size"] == sum(package["unpacked_size"] for package in payload["packages"])
    assert payload["file_count"] == sum(package["file_count"] for package in payload["packages"])
    assert payload["sha256"] == hashlib.sha256(json.dumps(payload["packages"], sort_keys=True,
                                                          separators=(",", ":")).encode()).hexdigest()
    assert payload["updater"]["url"].startswith(f"https://github.com/{r2.REPOSITORY}/releases/download/client-assets/")
    content_paths = {entry["path"].casefold() for package in payload["packages"]
                     if package["id"] not in r2.CI_PACKAGE_IDS for entry in package["files"]}
    ci_paths = {entry["path"].casefold() for package in payload["packages"]
                if package["id"] in r2.CI_PACKAGE_IDS for entry in package["files"]}
    assert content_paths and ci_paths and not content_paths & ci_paths
    assert all(r2.is_ci_path(path) for path in ci_paths)
    # canonical, deterministic bytes
    assert rm.payload_bytes(payload) == r2.canonical_bytes(json.loads(rm.payload_bytes(payload)))
    assert rm.check_payload(json.loads(rm.payload_bytes(payload)), identity("linux", key), CAPS_R2)


def _variant(tmp_path, key, mutate, **options):
    stage = make_stage(tmp_path / "stage", "windows", key)
    rows = options.get("source", "r2") if options.get("source", "r2") in r2.SOURCES else "r2"
    content = content_packages(stage, tmp_path / "work", rows)
    ci = ci_packages(stage, "windows", tmp_path / "work")
    mutate(content, ci)
    base = dict(identity=identity("windows", key), version=stage.name, content_packages=content, ci_packages=ci,
                helpers=helper_rows(stage, "windows"), launch_args=list(LAUNCH_ARGS), capabilities=CAPS_R2,
                source="r2", set_sha256="c" * 64, sequence=SEQUENCE, helpers_fingerprint=FINGERPRINT,
                root_files=ROOT_FILES)
    base.update(options)
    return rm.payload(**base)


def _move_file(source_id, target_id, copy=False):
    def mutate(content, ci):
        everything = {package["id"]: package for package in [*content, *ci]}
        source = everything[source_id]["files"]
        moved = dict(source[-1]) if copy else source.pop()
        everything[target_id]["files"].append(moved)
        for package in (everything[source_id], everything[target_id]):
            package["file_count"] = len(package["files"])
            package["unpacked_size"] = sum(entry["size"] for entry in package["files"])
    return mutate


@pytest.mark.parametrize("mutate, code", [
    (_move_file("native-runtime", "client"), "ci-path"),
    (_move_file("client", "engine", copy=True), "ci-package-path"),
    (_move_file("native-runtime", "engine"), "ci-package-path"),
    (lambda content, ci: content.append(dict(content[0], id="engine")), "package-ci"),
    (lambda content, ci: content.append(dict(ci[0], id="records-99")), "ci-path"),
    (lambda content, ci: ci.append(dict(ci[0], id="extra-ci")), "ci-package-id"),
    (lambda content, ci: ci.pop(0), "ci-engine-missing"),
    (lambda content, ci: content.remove(next(p for p in content if p["id"] == "client")), "required-package"),
    (lambda content, ci: content[0]["files"].append(dict(content[1]["files"][0],
                                                         path=content[1]["files"][0]["path"].upper())),
     "path-upper"),
    (lambda content, ci: content[0]["parts"][0].update(url=r2.github_pool_url(content[0]["parts"][0]["sha256"])),
     "part"),
    (lambda content, ci: ci[0]["parts"][0].update(url=r2.part_url(ci[0]["parts"][0]["sha256"])), "ci-part-url"),
    (lambda content, ci: ci[0]["parts"][0].update(url=r2.github_pool_url(ci[0]["parts"][0]["sha256"],
                                                                         partitioned=False)), "ci-part-url"),
    (lambda content, ci: content[0].update(size=content[0]["size"] + 1), "package-size"),
    (lambda content, ci: content[0].update(file_count=99), "package-totals"),
])
def test_overlap_and_row_refusals(tmp_path, key, mutate, code):
    with pytest.raises(rm.ManifestError) as error:
        _variant(tmp_path, key, mutate)
    if code == "path-upper":
        assert error.value.code in ("path-duplicate", "path-unsafe", "path-ascii")
    else:
        assert error.value.code == code


@pytest.mark.parametrize("change, code", [
    ({"version": version("linux")}, "version"),
    ({"version": "RabbitLands-Windows-20261104-abcdef012"}, "version"),
    ({"launch_args": ["x"] * 33}, "launch-args"),
    ({"identity": dict(identity(), ancestors=[PARENT, COMMIT])}, "identity-ancestors"),
    ({"identity": dict(identity(), repository="someone/else")}, "identity-repository"),
    ({"root_files": [{"name": f"f{i}.txt", "size": 1, "sha256": "1" * 64} for i in range(65)]}, "root-files"),
    ({"source": "web"}, "source"),
    ({"optional_packages": [{"id": "x"}]}, "optional-packages"),
    ({"capabilities": rm.ReaderCapabilities(schema3=True, r2_rows=True, package_limit=3)}, "reader-cap-exceeded"),
])
def test_argument_refusals(tmp_path, key, change, code):
    if "identity" in change:
        change["identity"]["public_key"] = key.public.decode()
    with pytest.raises(r2.DesktopR2Error) as error:
        _variant(tmp_path, key, lambda content, ci: None, **change)
    assert error.value.code == code


def test_helper_rows_must_be_legacy_pool_rows(tmp_path, key):
    stage = make_stage(tmp_path / "stage", "windows", key)
    rows = helper_rows(stage, "windows")
    for bad in ({**rows["updater"], "url": rows["updater"]["url"].replace("client-assets/", "client-assets-a/")},
                {**rows["updater"], "url": rows["updater"]["url"].replace(".exe", ".x86_64")},
                {**rows["updater"], "size": 600 * 1024 * 1024}, {**rows["updater"], "extra": 1}):
        with pytest.raises(rm.ManifestError):
            _variant(tmp_path / str(len(str(bad))), key, lambda c, i: None, helpers={**rows, "updater": bad})


def test_codec_rows_need_schema_3(tmp_path, key):
    def zstd(content, ci):
        content[0]["files"][0]["codec"] = "zstd"
    with pytest.raises(rm.ManifestError) as error:
        _variant(tmp_path / "a", key, zstd, source="ci", capabilities=CAPS2)
    assert error.value.code == "codec-needs-schema-3"
    assert _variant(tmp_path / "b", key, zstd, source="ci", capabilities=CAPS3)["schema"] == 3


# --- Schema follows the commit's reader ---------------------------------------------------

RELEASE_GD = "extends RefCounted\nconst CHUNK_BYTES := 8 * 1024 * 1024\n"
SCHEMA3_LINE = "const CODEC_SCHEMA := 3\n"
R2_LINE = f'const DESKTOP_ASSETS := "{r2.DESKTOP_ASSETS}"\n'
CAP_850 = "\tif not release.get(\"packages\") is Array or release.packages.size() > 850:\n"
CAP_2000 = CAP_850.replace("850", "2000")


def test_reader_capabilities_from_declarations():
    assert rm.reader_capabilities(RELEASE_GD, CAP_850) == CAPS2
    assert rm.reader_capabilities(RELEASE_GD + SCHEMA3_LINE, CAP_850) == CAPS3
    assert rm.reader_capabilities(RELEASE_GD + SCHEMA3_LINE + R2_LINE, CAP_2000).reader_cap == 2000
    assert rm.reader_capabilities(RELEASE_GD + SCHEMA3_LINE + R2_LINE, CAP_850).reader_cap == 850
    assert rm.reader_capabilities(RELEASE_GD + SCHEMA3_LINE + R2_LINE, "").package_limit == 850
    # R2 rows alone (no schema 3) are not an R2-aware reader; comments and other values do not count
    assert not rm.reader_capabilities(RELEASE_GD + R2_LINE).r2_rows
    assert not rm.reader_capabilities(RELEASE_GD + "# const CODEC_SCHEMA := 3\n").schema3
    assert not rm.reader_capabilities(RELEASE_GD + "const CODEC_SCHEMA := 4\n").schema3
    assert not rm.reader_capabilities(RELEASE_GD + SCHEMA3_LINE + R2_LINE.replace("desktop/v1", "desktop/v2")).r2_rows
    assert rm.reader_capabilities(RELEASE_GD + "const CODEC_SCHEMA := 3 # zstd rows\n").schema3


def test_this_checkouts_reader_matches_its_declarations():
    text = (GODOT / "src/updates/release.gd").read_text(encoding="utf-8")
    caps = rm.reader_capabilities(text, (GODOT / "src/updates/package_updates.gd").read_text(encoding="utf-8"))
    assert caps.schema3 == ("const CODEC_SCHEMA := 3" in text)
    assert caps.r2_rows == (rm.reader_capabilities(text).r2_rows)


def git(cwd, *args) -> str:
    environment = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=RL Test", "-c", "user.email=test@example.invalid",
                           *args], check=True, capture_output=True, env=environment).stdout.decode().strip()


def commit_tree(repo: Path, files: dict, message: str) -> str:
    for relative, data in files.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        git(repo, "add", "--", relative)
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def test_schema_2_is_emitted_and_r2_refused_when_the_commits_reader_lacks_schema_3(tmp_path, key):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "develop")
    before = commit_tree(repo, {rm.RELEASE_GD: RELEASE_GD.encode(), rm.PACKAGE_UPDATES_GD: CAP_850.encode(),
                                rm.PUBLIC_KEY: key.public}, "reader without schema 3")
    after = commit_tree(repo, {rm.RELEASE_GD: (RELEASE_GD + SCHEMA3_LINE + R2_LINE).encode(),
                               rm.PACKAGE_UPDATES_GD: CAP_2000.encode()}, "R2-aware reader")
    old, new = rm.commit_capabilities(repo, before), rm.commit_capabilities(repo, after)
    assert (old.schema, old.r2_rows) == (2, False) and (new.schema, new.r2_rows, new.reader_cap) == (3, True, 2000)
    assert rm.commit_public_key(repo, before) == key.public
    with pytest.raises(rm.ManifestError) as error:
        _variant(tmp_path / "r2", key, lambda c, i: None, capabilities=old)
    assert error.value.code == "r2-needs-schema-3"
    with pytest.raises(rm.ManifestError) as error:
        _variant(tmp_path / "b8", key, lambda c, i: None, capabilities=CAPS3)
    assert error.value.code == "reader-lacks-r2"
    assert _variant(tmp_path / "ci", key, lambda c, i: None, source="ci", capabilities=old)["schema"] == 2
    assert _variant(tmp_path / "ok", key, lambda c, i: None, capabilities=new)["schema"] == 3
    with pytest.raises(rm.ManifestError):
        rm.commit_capabilities(repo, "0" * 40)


def test_check_payload_refuses_a_schema_other_than_the_readers(tmp_path, key):
    payload = _variant(tmp_path, key, lambda c, i: None, source="ci", capabilities=CAPS2)
    with pytest.raises(rm.ManifestError) as error:
        rm.check_payload(dict(payload, schema=3), identity("windows", key), CAPS2)
    assert error.value.code == "schema"
    with pytest.raises(rm.ManifestError):
        rm.check_payload(dict(payload, parts=payload["parts"][:-1]), identity("windows", key), CAPS2)
    with pytest.raises(rm.ManifestError):
        rm.check_payload(dict(payload, packages=list(reversed(payload["packages"]))), identity("windows", key), CAPS2)


# --- Signing ---------------------------------------------------------------------------------

def test_sign_verify_round_trip_and_envelope_format(tmp_path, key, other_key):
    payload = _variant(tmp_path, key, lambda c, i: None)
    private = rm.load_signing_key(key.private, key.public)
    envelope, gate = rm.sign_manifest(payload, identity("windows", key), CAPS_R2, private, key.public)
    assert gate["margin"] == r2.MAX_ENVELOPE_BYTES - len(envelope)
    data, value = rm.verify(envelope, key.public)
    assert value == payload and data == rm.payload_bytes(payload)
    # the uploader's self-test signer and this one write the same bytes (deterministic PKCS#1 v1.5)
    assert envelope == up.sign_envelope(data, key.private)
    assert list(json.loads(envelope)) == ["payload", "signature"] and b" " not in envelope
    with pytest.raises(rm.SigningError):
        rm.verify(envelope, other_key.public)
    tampered = json.loads(envelope)
    tampered["payload"] = base64.b64encode(data.replace(b'"schema":3', b'"schema":2')).decode()
    with pytest.raises(rm.SigningError):
        rm.verify(json.dumps(tampered).encode(), key.public)


def test_signing_key_must_match_the_commits_public_key(key, other_key):
    with pytest.raises(rm.SigningError) as error:
        rm.load_signing_key(key.private, other_key.public)
    assert error.value.code == "signing-key-mismatch"
    with pytest.raises(rm.SigningError) as error:
        rm.load_signing_key(b"-----BEGIN PRIVATE KEY-----\nnot a key\n-----END PRIVATE KEY-----\n", key.public)
    assert error.value.code == "signing-key" and "not a key" not in str(error.value)


def test_envelope_gate_refuses_more_than_15_mib(tmp_path, key):
    def huge(content, ci):
        rows = [{"path": f"eloria-assets/maps/huge/f{index:06d}.bin", "size": 0, "sha256": "e" * 64}
                for index in range(99000)]
        package = next(p for p in content if p["id"].startswith("map-"))
        package["files"] = rows
        package["file_count"], package["unpacked_size"] = len(rows), 0
    payload = _variant(tmp_path, key, huge)
    private = rm.load_signing_key(key.private, key.public)
    with pytest.raises(r2.EnvelopeError) as error:
        rm.sign_manifest(payload, identity("windows", key), CAPS_R2, private, key.public)
    assert error.value.code == "envelope-too-large"


# --- Pointer ------------------------------------------------------------------------------------

def test_pointer_names_the_signed_manifest_and_is_domain_separated(tmp_path, key):
    payload = _variant(tmp_path, key, lambda c, i: None)
    private = rm.load_signing_key(key.private, key.public)
    manifest, _ = rm.sign_manifest(payload, identity("windows", key), CAPS_R2, private, key.public)
    envelope = rm.pointer_envelope(platform="windows", sequence=SEQUENCE + 600, rollback=False, release_id=7,
                                   run_id=9, manifest=manifest, private_key=private, public_pem=key.public)
    data, pointer = rm.verify(envelope, key.public, limit=r2.MAX_POINTER_BYTES)
    assert data == r2.pointer_bytes(pointer, platform="windows")
    assert not r2.RELEASE_ONLY_FIELDS & set(pointer) and pointer["kind"] == r2.POINTER_KIND
    target = pointer["target"]
    assert target["commit"] == COMMIT and target["manifest_sequence"] == SEQUENCE
    assert target["manifest"] == {"url": r2.manifest_url("windows", sha(manifest)), "sha256": sha(manifest),
                                  "size": len(manifest)}
    # the uploader's publish check accepts exactly this pair
    checked = up.check_release_pair(envelope, lambda platform, version: manifest, platform="windows",
                                    public_pem=key.public, commit=COMMIT, release_id=7)
    assert checked.manifest_sha256 == sha(manifest)
    with pytest.raises(r2.PointerError):
        rm.pointer_envelope(platform="windows", sequence=SEQUENCE, rollback=False, release_id=7, run_id=9,
                            manifest=manifest, private_key=private, public_pem=key.public)
    schema2 = _variant(tmp_path / "s2", key, lambda c, i: None, source="ci", capabilities=CAPS2)
    manifest2, _ = rm.sign_manifest(schema2, identity("windows", key), CAPS2, private, key.public)
    with pytest.raises(rm.SigningError):
        rm.pointer_envelope(platform="windows", sequence=SEQUENCE + 600, rollback=False, release_id=7, run_id=9,
                            manifest=manifest2, private_key=private, public_pem=key.public)


def test_source_has_no_machine_paths_and_no_private_key_writes():
    text = (TOOLS / "release_manifest.py").read_text(encoding="ascii")
    for needle in ("C:/", "C:\\", "/Users/", "scratchpad", "AppData", "write_bytes", "write_text", "open("):
        assert needle not in text, needle
    assert shutil.which("git")
