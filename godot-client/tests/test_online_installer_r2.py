"""The online setup for manifest schema 3 and R2-hosted parts (W2).

- online_installer_script treats schema 2 and later as packages: one installed-file
  check per package, whose parts are queued only when it is not current. An R2 row is
  queued at its derived URL with the `<sha256>.bin` basename the setup helper looks
  for in {tmp} (`url.get_file()`).
- online_installer_space counts the download once when the setup helper moves
  verified downloads into its cache (MOVES_VERIFIED_DOWNLOADS), twice when it copies.
- make_online_installer refuses a manifest its embedded helper could not install.
- asset_packages.build: the W2 part cap and the R2 part size.
- Native (Inno Setup 6, no Godot): a compiled setup fetches R2 parts from a local
  mirror of the desktop/v1/ layout, verifies them and hands them to the helper; a
  tampered part stops setup before the helper runs. Inno 6.7.3 against the real
  custom domain was proven by the R2 self-test (R2-A3).
"""
import base64
import functools
import hashlib
import http.server
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading

import pytest

CLIENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLIENT / "tools"))
import asset_packages  # noqa: E402
import client_release  # noqa: E402
import desktop_r2 as r2  # noqa: E402
import package_client  # noqa: E402
import release_manifest  # noqa: E402
import shared_release_assets as shared  # noqa: E402

MIB = 1024 ** 2
MARGIN = 512 * MIB
REPOSITORY = r2.REPOSITORY
COMMIT = "b" * 40
VERSION = "RabbitLands-Windows-20261105-bbbbbbbbb"


def noise(seed: str, size: int) -> bytes:
    """Deterministic bytes that do not compress, so a package spans several small parts."""
    data = b"".join(hashlib.sha256(f"{seed}/{index}".encode()).digest() for index in range(size // 32 + 1))
    return data[:size]


FILES = {
    "app/client-release.json": json.dumps({"commit": COMMIT}).encode(),
    "app/RabbitLands.exe": noise("engine", 3000),
    "app/RabbitLands.pck": noise("core pack", 9000),
    "app/assets/ui/icon.png": noise("icon", 700),
    "app/assets/actors/native/creatures/rabbit.glb": noise("rabbit", 5000),
    "eloria-assets/maps/landfall/world.json": b'{"map": "landfall"}',
}
ROOT_FILES = ("RabbitLands-updater.exe", "RabbitLands-uninstall.exe", "RabbitLands (safe mode).bat")


def make_stage(tmp_path: Path) -> Path:
    stage = tmp_path / VERSION
    for relative, data in FILES.items():
        (stage / relative).parent.mkdir(parents=True, exist_ok=True)
        (stage / relative).write_bytes(data)
    branding = stage / "app/assets/branding"
    branding.mkdir(parents=True)
    shutil.copyfile(CLIENT / "assets/branding/rabbitlands-icon.ico", branding / "rabbitlands-icon.ico")
    for name in ROOT_FILES:
        (stage / name).write_bytes(b"fixture root file " + name.encode())
    (stage.parent / f"{stage.name}-online-install.txt").write_text("Online installer R2 fixture.")
    return stage


def r2_payload(stage: Path, *, schema=3, part_bytes=4096) -> dict:
    """A manifest shaped like the R2 workflow's: content rows at derived R2 URLs (some
    with the zstd codec mark), the engine package at a GitHub pool URL (CI-built)."""
    built = asset_packages.build(stage, shared.base(REPOSITORY), shared="partitioned", part_bytes=part_bytes)
    content = r2.rewrite_part_urls([p for p in built if p["id"] != "engine"])
    for package in content:
        for entry in package["files"]:
            if entry["path"].endswith((".glb", ".pck")):
                entry["codec"] = "zstd"
    packages = sorted([*content, *(p for p in built if p["id"] == "engine")], key=lambda p: p["id"])
    return {"schema": schema, "bootstrap_schema": 1, "commit": COMMIT, "platform": "windows",
            "repository": REPOSITORY, "version": stage.name, "sha256": "a" * 64,
            "size": sum(p["size"] for p in packages),
            "unpacked_size": sum(p["unpacked_size"] for p in packages),
            "file_count": sum(p["file_count"] for p in packages),
            "packages": packages, "parts": [part for p in packages for part in p["parts"]]}


def local_part(stage: Path, part: dict) -> Path:
    return stage.parent / shared.name(part["sha256"])


def queued(script: str) -> list[tuple[str, str, str]]:
    return re.findall(r"DownloadPage\.Add\('([^']*)', '([^']*)', '([^']*)'\);", script)


# --- The setup script ------------------------------------------------------------------------------

def test_the_online_installer_declares_schema_3_and_r2_rows():
    # desktop_release_ci.installer_preconditions reads these two declarations.
    assert package_client.ONLINE_INSTALLER_SCHEMAS == (1, 2, 3)
    assert package_client.ONLINE_INSTALLER_R2_ROWS is True


def test_schema_3_checks_and_queues_each_package_at_its_r2_url(tmp_path):
    stage = make_stage(tmp_path)
    payload = r2_payload(stage)
    assert any(len(p["parts"]) > 1 for p in payload["packages"]), "the fixture needs a multi-part package"
    script = package_client.online_installer_script(stage, stage / "helper.exe", "test", [], payload)
    # One installed-file check per package, never the whole-archive download of schema 1.
    for index, package in enumerate(payload["packages"]):
        function = script.split(f"function PackageCurrent{index}: Boolean;", 1)[1].split("end;", 1)[0]
        for entry in package["files"]:
            name = entry["path"].replace("/", "\\")
            # The signed file hash: for a zstd row, the hash of the decoded file as installed.
            assert f"InstalledFileMatches(ExpandConstant('{{app}}') + '\\{name}', '{entry['sha256']}')" in function
        block = script.split(f"  if not PackageCurrent{index} then begin\n", 1)[1].split("  end;", 1)[0]
        assert queued(block) == [(part["url"], part["url"].rsplit("/", 1)[1], part["sha256"]) for part in package["parts"]]
    rows = queued(script)
    assert len(rows) == len(payload["parts"])
    for (url, basename, digest), part in zip(rows, payload["parts"]):
        if url.startswith(r2.DESKTOP_ASSETS):
            # The derived R2 form only, and the basename the helper derives from the same URL.
            assert url == r2.part_url(part["sha256"]) and basename == f"{part['sha256']}.bin" == url.rsplit("/", 1)[1]
        else:
            assert shared.matches(part, REPOSITORY) and basename == shared.name(part["sha256"])
        assert digest == part["sha256"]
    assert sum(url.startswith(r2.DESKTOP_ASSETS) for url, _, _ in rows) == sum(
        len(p["parts"]) for p in payload["packages"] if p["id"] != "engine")


def test_a_float_schema_from_json_is_still_a_package_manifest(tmp_path):
    stage = make_stage(tmp_path)
    payload = {**r2_payload(stage), "schema": 3.0}
    assert "function PackageCurrent0" in package_client.online_installer_script(
        stage, stage / "helper.exe", "test", [], payload)
    # As Release.package_manifest: schemas 2 and 3 by value, nothing else.
    for schema in (2, 3, 2.0):
        assert package_client.online_package_manifest({"schema": schema})
    for schema in (1, 4, 2.5, True, "3", None):
        assert not package_client.online_package_manifest({"schema": schema})


def test_pascal_strings_are_quoted():
    line = package_client._download_line({"url": "https://example.invalid/it's.bin", "sha256": "0" * 64}, "  ")
    assert line == "  DownloadPage.Add('https://example.invalid/it''s.bin', 'it''s.bin', '" + "0" * 64 + "');"


# --- ExtraDiskSpaceRequired ------------------------------------------------------------------------

def sized(schema, size, unpacked, packages):
    return {"schema": schema, "size": size, "unpacked_size": unpacked,
            "packages": [{"size": s, "parts": [{}] * n} for s, n in packages]}


def test_schema_3_space_is_the_package_formula():
    payload = sized(3, 1000 * MIB, 1800 * MIB, [(900 * MIB, 4), (100 * MIB, 1)])
    assert package_client.online_installer_space(payload) == 2 * 1000 * MIB + 1800 * MIB + MARGIN
    assert package_client.online_installer_space({**payload, "schema": 2}) == package_client.online_installer_space(payload)


def test_a_helper_that_moves_downloads_counts_them_once():
    payload = sized(3, 1000 * MIB, 1800 * MIB, [(900 * MIB, 4), (100 * MIB, 1)])
    assert package_client.online_installer_space(payload, moves_downloads=True) == 1000 * MIB + 1800 * MIB + MARGIN
    # The join of the largest multi-part package still counts when it outweighs the files.
    joined = sized(3, 1030 * MIB, 1024 * MIB, [(1030 * MIB, 5)])
    assert package_client.online_installer_space(joined, moves_downloads=True) == 2 * 1030 * MIB + MARGIN
    # Schema 1 copies its parts into numbered cache files: no move, its formula is unchanged.
    archive = {"schema": 1, "size": 3 * 1024 ** 3, "unpacked_size": 5 * 1024 ** 3}
    assert package_client.online_installer_space(archive, moves_downloads=True) == 5 * 1024 ** 3 + 6 * 1024 ** 3 + MARGIN


def test_the_script_carries_the_space_for_its_helper(tmp_path):
    stage = make_stage(tmp_path)
    payload = r2_payload(stage)
    for moves in (False, True):
        script = package_client.online_installer_script(stage, stage / "helper.exe", "test", [], payload,
                                                        moves_downloads=moves)
        expected = package_client.online_installer_space(payload, moves_downloads=moves)
        assert f"\nExtraDiskSpaceRequired={expected}\n" in script
    assert package_client.online_installer_space(payload, moves_downloads=True) < package_client.online_installer_space(payload)


# --- What the embedded setup helper installs ---------------------------------------------------------

RELEASE_GD = (CLIENT / "src/updates/release.gd").read_text(encoding="utf-8")
PACKAGE_UPDATES_GD = (CLIENT / "src/updates/package_updates.gd").read_text(encoding="utf-8")
INSTALL_GD = (CLIENT / "tools/install_client_payload.gd").read_text(encoding="utf-8")
SCHEMA3_LINE = "const CODEC_SCHEMA := 3\n"
R2_LINE = f'const DESKTOP_ASSETS := "{r2.DESKTOP_ASSETS}"\n'
MOVES_LINE = "const MOVES_VERIFIED_DOWNLOADS := true\n"


def helper_source(root: Path, *, schema3=True, r2_rows=False, gate=True, moves=False, limit=850) -> Path:
    """A client tree holding only the scripts export_installer_helper embeds."""
    release = re.sub(r"^const (CODEC_SCHEMA|DESKTOP_ASSETS) :=.*$\n?", "", RELEASE_GD, flags=re.M)
    release += (SCHEMA3_LINE if schema3 else "") + (R2_LINE if r2_rows else "")
    install = re.sub(r"^const MOVES_VERIFIED_DOWNLOADS :=.*$\n?", "", INSTALL_GD, flags=re.M)
    if not gate:
        install = install.replace(package_client.SETUP_HELPER_PACKAGE_GATE, 'manifest.get("schema") == 2')
    if moves:
        install = install.replace("var _lock := \"\"\n", MOVES_LINE + "var _lock := \"\"\n", 1)
        assert MOVES_LINE in install
    files = {"src/updates/release.gd": release, "tools/install_client_payload.gd": install,
             "src/updates/package_updates.gd": re.sub(r"release\.packages\.size\(\) > \d+",
                                                      f"release.packages.size() > {limit}", PACKAGE_UPDATES_GD)}
    for relative, text in files.items():
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_text(text, encoding="utf-8")
    return root


def test_the_helper_declarations_are_read_from_its_own_scripts(tmp_path):
    reads = package_client.setup_helper_reads
    assert reads(helper_source(tmp_path / "a")) == {"schema3": True, "r2_rows": False, "package_limit": 850,
                                                    "moves_downloads": False}
    assert reads(helper_source(tmp_path / "b", r2_rows=True, moves=True, limit=2000)) == {
        "schema3": True, "r2_rows": True, "package_limit": 2000, "moves_downloads": True}
    # Schema 3 needs both the reader's declaration and the HOOK-B8 gate in the helper.
    assert reads(helper_source(tmp_path / "c", gate=False))["schema3"] is False
    assert reads(helper_source(tmp_path / "d", schema3=False, r2_rows=True)) == {
        "schema3": False, "r2_rows": False, "package_limit": 850, "moves_downloads": False}
    # A commented-out declaration is not one.
    commented = helper_source(tmp_path / "e")
    path = commented / "tools/install_client_payload.gd"
    path.write_text(path.read_text(encoding="utf-8").replace("var _lock", "# " + MOVES_LINE + "var _lock", 1),
                    encoding="utf-8")
    assert reads(commented)["moves_downloads"] is False
    assert reads(tmp_path / "missing") == {"schema3": False, "r2_rows": False, "package_limit": 850,
                                           "moves_downloads": False}


def test_the_tree_helper_reads_what_its_declarations_say():
    reads = package_client.setup_helper_reads(CLIENT)
    reader = release_manifest.reader_capabilities(RELEASE_GD, PACKAGE_UPDATES_GD)
    # HOOK-B8 (stage B): the setup helper sends schema 3 to the package path.
    assert reads["schema3"] is True and reader.schema3
    assert reads["r2_rows"] is reader.r2_rows and reads["package_limit"] == reader.package_limit
    assert reads["moves_downloads"] is (package_client.SETUP_HELPER_MOVES_DOWNLOADS.search(INSTALL_GD) is not None)


# --- make_online_installer ----------------------------------------------------------------------------

class Built:
    """make_online_installer up to its Inno compile: export and ISCC are fakes."""

    def __init__(self, tmp_path, monkeypatch, payload_change=None, source=None, storage=None):
        self.stage = make_stage(tmp_path)
        self.payload = r2_payload(self.stage)
        if payload_change:
            payload_change(self.payload)
        manifest = self.stage.parent / f"{self.stage.name}-windows.json"
        raw = json.dumps(self.payload, separators=(",", ":")).encode()
        manifest.write_text(json.dumps({"payload": base64.b64encode(raw).decode(), "signature": ""}))
        (self.stage / "app/client-release.json").write_text(json.dumps({"commit": COMMIT, "repository": REPOSITORY}))
        self.logs = tmp_path / "logs"
        self.logs.mkdir()
        self.exports, self.compiled = [], []
        helper = self.logs / "RabbitLands-install-test.exe"

        def export(stage, godot, tools_source, presets, run_godot, logs):
            self.exports.append(Path(tools_source))
            helper.write_bytes(b"helper")
            return helper

        def iscc(command, **kwargs):
            self.compiled.append(Path(command[1]).read_text(encoding="utf-8-sig"))
            (self.stage.parent / f"{self.stage.name}-setup.exe").write_bytes(b"MZ")
            return subprocess.CompletedProcess(command, 0)
        monkeypatch.setattr(client_release, "export_installer_helper", export)
        monkeypatch.setattr(package_client.subprocess, "run", iscc)
        monkeypatch.setattr(package_client, "CLIENT", source or helper_source(tmp_path / "client", r2_rows=True))
        monkeypatch.setattr(package_client, "STORAGE", storage)

    def run(self, **kwargs):
        return package_client.make_online_installer(self.stage, Path("godot.exe"), Path("iscc.exe"), "test", [],
                                                    self.logs, **kwargs)


def r2_rows(payload):
    return [part for part in payload["parts"] if part["url"].startswith(r2.DESKTOP_ASSETS)]


def test_r2_rows_are_accepted_when_verified_and_the_helper_reads_them(tmp_path, monkeypatch):
    built = Built(tmp_path, monkeypatch)
    hosted = r2_rows(built.payload)
    for part in hosted:
        local_part(built.stage, part).unlink()  # R2 rows are not local; CI verified them from R2
    seen = []

    def verified(row):
        seen.append(row["sha256"])
        return row in hosted
    setup = built.run(verified=verified)
    assert setup.read_bytes() == b"MZ" and built.exports == [package_client.CLIENT]
    assert set(seen) >= {part["sha256"] for part in hosted}
    script = built.compiled[0]
    assert [row[0] for row in queued(script)] == [part["url"] for part in built.payload["parts"]]
    receipt = json.loads((built.stage.parent / f"{built.stage.name}-setup-downloads.json").read_text())
    assert {row["name"] for row in receipt["parts"]} >= {f"{part['sha256']}.bin" for part in hosted}
    # This helper copies its downloads: the conservative space.
    assert f"\nExtraDiskSpaceRequired={package_client.online_installer_space(built.payload)}\n" in script


def test_a_moving_helper_gets_the_lower_space(tmp_path, monkeypatch):
    built = Built(tmp_path, monkeypatch, source=helper_source(tmp_path / "client", r2_rows=True, moves=True))
    built.run(verified=lambda row: row in r2_rows(built.payload))
    space = package_client.online_installer_space(built.payload, moves_downloads=True)
    assert f"\nExtraDiskSpaceRequired={space}\n" in built.compiled[0]


def test_the_storage_shim_still_answers_for_signed_rows(tmp_path, monkeypatch):
    class Rows:
        source = helper_source(tmp_path / "ci-checkout", r2_rows=True)

        def __init__(self, payload):
            self.rows = {part["url"].rsplit("/", 1)[1]: (part["size"], part["sha256"]) for part in payload["parts"]}

        def part_matches(self, name, part):
            return self.rows.get(name) == (part["size"], part["sha256"])
    built = Built(tmp_path, monkeypatch)
    package_client.STORAGE = Rows(built.payload)
    for part in built.payload["parts"]:
        local_part(built.stage, part).unlink()
    built.run()
    assert built.exports == [Rows.source]


def test_an_unverified_r2_row_without_local_bytes_is_refused(tmp_path, monkeypatch):
    built = Built(tmp_path, monkeypatch)
    hosted = r2_rows(built.payload)
    local_part(built.stage, hosted[0]).unlink()
    with pytest.raises(package_client.PackageError, match="changed after signing"):
        built.run(verified=lambda row: False)
    assert not built.exports and not built.compiled


def r2_url_on_another_sha(payload):
    part = r2_rows(payload)[0]
    part["url"] = r2.part_url("0" * 64)


def r2_url_with_pool_name(payload):
    part = r2_rows(payload)[0]
    part["url"] = r2.DESKTOP_ASSETS + "parts/" + shared.name(part["sha256"])


def r2_url_on_another_host(payload):
    part = r2_rows(payload)[0]
    part["url"] = "https://assets.example.invalid/desktop/v1/parts/" + part["sha256"] + ".bin"


@pytest.mark.parametrize("change", [r2_url_on_another_sha, r2_url_with_pool_name, r2_url_on_another_host])
def test_r2_urls_must_be_the_derived_form(tmp_path, monkeypatch, change):
    def apply(payload):
        change(payload)
        payload["parts"] = [part for package in payload["packages"] for part in package["parts"]]
    built = Built(tmp_path, monkeypatch, apply)
    with pytest.raises(package_client.PackageError, match="Unexpected online installer download URL"):
        built.run(verified=lambda row: True)
    assert not built.exports


def schema(value):
    return lambda payload: payload.update(schema=value)


def drop_last_part(payload):
    payload["parts"] = payload["parts"][:-1]


@pytest.mark.parametrize(("change", "source", "message"), [
    (schema(4), {}, "does not support this manifest schema"),
    (schema(2), {}, "R2 download rows need a schema 3 manifest"),
    (None, {"r2_rows": False}, r"cannot read R2 download rows yet \(W1a\)"),
    (None, {"gate": False}, r"cannot install manifest schema 3 yet"),
    (None, {"limit": 3}, "more packages than the setup helper reads"),
    (drop_last_part, {}, "does not match its packages"),
])
def test_a_manifest_the_helper_cannot_install_is_refused_before_export(tmp_path, monkeypatch, change, source, message):
    built = Built(tmp_path, monkeypatch, change,
                  source=helper_source(tmp_path / "client", **{"r2_rows": True, **source}))
    with pytest.raises(package_client.PackageError, match=message):
        built.run(verified=lambda row: True)
    assert not built.exports and not built.compiled


def test_github_hosted_schema_2_and_3_need_no_r2_reader(tmp_path, monkeypatch):
    def github_rows(payload):
        for package in payload["packages"]:
            package["parts"] = [{**part, "url": shared.download_url(REPOSITORY, shared.name(part["sha256"]))}
                                for part in package["parts"]]
            for entry in package["files"]:
                entry.pop("codec", None)
        payload["parts"] = [part for package in payload["packages"] for part in package["parts"]]
    for value in (2, 3):
        root = tmp_path / f"schema-{value}"
        root.mkdir()
        built = Built(root, monkeypatch, lambda payload: (github_rows(payload), payload.update(schema=value)),
                      source=helper_source(root / "client", r2_rows=False))
        built.run()  # every part is the local file beside the stage
        assert len(queued(built.compiled[0])) == len(built.payload["parts"])


# --- asset_packages.build: part cap and part size ----------------------------------------------------

def single_file_stage(tmp_path: Path, size: int) -> Path:
    stage = tmp_path / "stage"
    (stage / "app").mkdir(parents=True)
    (stage / "app/RabbitLands.pck").write_bytes(noise("pack", size))
    return stage


def test_the_part_cap_is_the_r2_reader_cap_for_partitioned_parts(tmp_path):
    assert asset_packages.MAX_PARTS == r2.READER_CAP_W1A == 2000
    assert asset_packages.MAX_RELEASE_PARTS == 850
    # 900 parts of 1 KiB: more than the old cap of 850.
    stage = single_file_stage(tmp_path, 900 * 1024)
    packages = asset_packages.build(stage, shared.base(REPOSITORY), shared="partitioned", part_bytes=1024)
    assert 850 < len(packages[0]["parts"]) <= asset_packages.MAX_PARTS
    # One GitHub release holds at most 1,000 assets: a versioned release and the single
    # legacy pool keep the older bound.
    for base, mode in (("https://github.com/o/r/releases/download/client-x", False), (shared.base(REPOSITORY), True)):
        for old in stage.parent.glob("stage.pkg.*"):
            old.unlink()
        for old in stage.parent.glob("RabbitLands-pkg-*"):
            old.unlink()
        with pytest.raises(ValueError, match="Invalid package count"):
            asset_packages.build(stage, base, shared=mode, part_bytes=1024)


def test_more_parts_than_the_cap_are_refused(tmp_path):
    stage = single_file_stage(tmp_path, 2001 * 512)
    with pytest.raises(ValueError, match="Invalid package count"):
        asset_packages.build(stage, shared.base(REPOSITORY), shared="partitioned", part_bytes=512)


def test_the_package_limit_is_the_updater_s_own(tmp_path):
    # This tree: whatever package_updates.gd declares (850 before W1a, 2000 with it).
    reader = release_manifest.reader_capabilities(RELEASE_GD, PACKAGE_UPDATES_GD)
    assert asset_packages.package_limit() == reader.package_limit
    assert asset_packages.package_limit() in (r2.READER_CAP, r2.READER_CAP_W1A)
    for declared, expected in (("850", 850), ("2000", 2000), ("5000", 2000), ("3", 3), (None, 850)):
        root = tmp_path / f"limit-{declared}"
        if declared is not None:
            helper_source(root, limit=int(declared))
        assert asset_packages.package_limit(root) == expected, declared


def test_never_more_packages_than_the_updater_reads(tmp_path, monkeypatch):
    stage = make_stage(tmp_path)
    count = len(asset_packages.build(stage, shared.base(REPOSITORY), shared="partitioned"))
    monkeypatch.setattr(asset_packages, "package_limit", lambda: count - 1)
    with pytest.raises(ValueError, match="Invalid package count"):
        asset_packages.build(stage, shared.base(REPOSITORY), shared="partitioned")


def test_r2_parts_are_64_mib_and_github_parts_keep_their_size():
    assert client_release.R2_PART_BYTES == 64 * MIB
    assert client_release.PART_BYTES == 256 * MIB == client_release.MAX_PART_BYTES == r2.MAX_PART_BYTES


def test_build_writes_parts_of_the_requested_size(tmp_path, monkeypatch):
    stage = single_file_stage(tmp_path, 10 * 1024)
    packages = asset_packages.build(stage, shared.base(REPOSITORY), shared="partitioned", part_bytes=4096)
    assert [part["size"] for part in packages[0]["parts"]][:-1] == [4096] * (len(packages[0]["parts"]) - 1)
    # The default follows client_release.PART_BYTES when the build runs.
    monkeypatch.setattr(client_release, "PART_BYTES", 2048)
    packages = asset_packages.build(stage, shared.base(REPOSITORY), shared="partitioned")
    assert max(part["size"] for part in packages[0]["parts"]) == 2048
    for bad in (0, -1, client_release.MAX_PART_BYTES + 1, True, 4096.0):
        with pytest.raises(ValueError, match="part size"):
            asset_packages.build(stage, shared.base(REPOSITORY), shared="partitioned", part_bytes=bad)
    assert asset_packages.build(stage, shared.base(REPOSITORY), shared="partitioned",
                                part_bytes=client_release.R2_PART_BYTES)[0]["parts"][0]["size"] < 64 * MIB


def test_a_reused_package_keeps_its_earlier_parts(tmp_path):
    stage = single_file_stage(tmp_path, 10 * 1024)
    first = asset_packages.build(stage, shared.base(REPOSITORY), shared="partitioned", part_bytes=4096)
    again = asset_packages.build(stage, shared.base(REPOSITORY), shared="partitioned", part_bytes=8192,
                                 previous_packages={p["id"]: p for p in first}, reuse_package=lambda row: True)
    assert again == first


# --- Native: a compiled setup against a local mirror of desktop/v1/ (Inno Setup 6, no Godot) -----------

# The setup helper's stand-in: Inno's ExecAndLogOutput runs a .cmd through cmd.exe with the
# helper's arguments (--headless --log-file <log> -- --root <app> --parts <tmp>). It keeps a
# copy of what setup handed it, since setup deletes {tmp} when it exits.
STUB_HELPER = "\r\n".join([
    "@echo off",
    'if not "%~5"=="--root" exit /b 3',
    'if not "%~7"=="--parts" exit /b 4',
    'mkdir "%~6\\seen" || exit /b 5',
    'copy /b "%~8\\*.bin" "%~6\\seen\\" >nul',
    'copy /b "%~8\\*.zip.part" "%~6\\seen\\" >nul',
    "echo RL_PROGRESS^|100^|Stub helper received the downloads",
    "exit /b 0", ""])


class Mirror:
    """HTTP on 127.0.0.1 serving r2/<desktop key> and github/<release path>, logging requests."""

    def __init__(self, root: Path):
        self.root, self.requests = root, []
        requests = self.requests

        class Handler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                requests.append(("GET", self.path))
                super().do_GET()

            def do_HEAD(self):
                requests.append(("HEAD", self.path))
                super().do_HEAD()

            def log_message(self, *_args):
                pass
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=root))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.server.server_port}/"

    def path_for(self, url: str) -> str:
        if url.startswith(r2.PUBLIC_ORIGIN):
            return "r2/" + r2.key_from_url(url)
        prefix = "https://github.com/"
        assert url.startswith(prefix), url
        return "github/" + url[len(prefix):]

    def publish(self, url: str, data: bytes) -> None:
        path = self.root / self.path_for(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def localise(self, script: str) -> str:
        """Only the origins change: the paths keep the R2 key layout and GitHub release paths."""
        return (script.replace(f"DownloadPage.Add('{r2.PUBLIC_ORIGIN}", f"DownloadPage.Add('{self.origin}r2/")
                .replace("DownloadPage.Add('https://github.com/", f"DownloadPage.Add('{self.origin}github/"))

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


@pytest.fixture
def inno(tmp_path):
    iscc = package_client.find_iscc(None)
    if os.name != "nt" or not iscc:
        pytest.skip("Inno Setup 6 is needed for this native check.")
    stage = make_stage(tmp_path)
    payload = r2_payload(stage)
    mirror = Mirror(tmp_path / "mirror")
    for part in payload["parts"]:
        mirror.publish(part["url"], local_part(stage, part).read_bytes())
    helper = tmp_path / "helper" / "stub-helper.cmd"
    helper.parent.mkdir()
    helper.write_bytes(STUB_HELPER.encode("ascii"))
    # Setup's {tmp} under the system temp folder, as for a player: Inno moves each download
    # to {tmp}\<basename> with MoveFile, which fails past MAX_PATH, so a deep test folder
    # would fail on the 89-character pool names (an R2 basename is 68 characters).
    temp = Path(tempfile.mkdtemp(prefix="rl-w2-"))
    env = {**os.environ, "TEMP": str(temp), "TMP": str(temp)}

    def compile_setup():
        script = package_client.online_installer_script(stage, helper, "test", [], payload)
        # The production URLs are in the script; only their origin moves to the mirror.
        assert {url for url, _, _ in queued(script)} == {part["url"] for part in payload["parts"]}
        script = mirror.localise(script)
        assert "DownloadPage.Add('https://" not in script
        # No registration, shortcuts, uninstaller or game launch (as the other setup tests).
        script = script.replace("AppId=" + package_client.INSTALLER_APP_ID.replace("{", "{{"),
                                "AppId=RabbitLandsR2SetupTest\nUninstallable=no")
        script = script.split("[Icons]")[0] + "[Code]" + script.split("[Code]", 1)[1]
        iss = tmp_path / "setup.iss"
        iss.write_text(script, encoding="utf-8-sig")
        result = subprocess.run([str(iscc), "/Q", str(iss)], capture_output=True, text=True, timeout=180)
        assert result.returncode == 0, result.stdout + result.stderr
        return stage.parent / f"{stage.name}-setup.exe"

    def run_setup(setup, target, name):
        log = tmp_path / f"{name}.log"
        result = subprocess.run([str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
                                 f"/DIR={target}", f"/LOG={log}"], env=env, capture_output=True, timeout=120)
        return result.returncode, log.read_text(errors="replace") if log.is_file() else ""

    yield locals()
    mirror.close()
    shutil.rmtree(temp, ignore_errors=True)


def got(mirror: Mirror) -> list[str]:
    return sorted(path for method, path in mirror.requests if method == "GET")


def test_setup_fetches_r2_parts_from_the_mirror_and_hands_them_to_the_helper(inno):
    stage, payload, mirror = inno["stage"], inno["payload"], inno["mirror"]
    setup = inno["compile_setup"]()
    installed = inno["tmp_path"] / "installed"
    code, log = inno["run_setup"](setup, installed, "fresh")
    assert code == 0, log
    # Every row was fetched once from its R2 key (or GitHub path) and arrived in {tmp}
    # under the URL's basename, with the signed bytes.
    assert got(mirror) == sorted("/" + mirror.path_for(part["url"]) for part in payload["parts"])
    seen = installed / "seen"
    assert sorted(path.name for path in seen.iterdir()) == sorted(part["url"].rsplit("/", 1)[1] for part in payload["parts"])
    for part in payload["parts"]:
        data = (seen / part["url"].rsplit("/", 1)[1]).read_bytes()
        assert len(data) == part["size"] and hashlib.sha256(data).hexdigest() == part["sha256"]
    assert "Stub helper received the downloads" in log
    for name in ROOT_FILES:
        assert (installed / name).read_bytes() == (stage / name).read_bytes()

    # A package whose files are already installed is current: its parts are not fetched again.
    current = next(p for p in payload["packages"] if p["id"].startswith("actors-"))
    again = inno["tmp_path"] / "repair"
    for entry in current["files"]:
        (again / entry["path"]).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(stage / entry["path"], again / entry["path"])
    mirror.requests.clear()
    code, log = inno["run_setup"](setup, again, "repair")
    assert code == 0, log
    skipped = {"/" + mirror.path_for(part["url"]) for part in current["parts"]}
    assert skipped and not skipped & set(got(mirror))
    assert len(got(mirror)) == len(payload["parts"]) - len(current["parts"])


def test_a_tampered_r2_part_stops_setup_before_the_helper(inno):
    payload, mirror = inno["payload"], inno["mirror"]
    part = next(p for p in payload["parts"] if p["url"].startswith(r2.DESKTOP_ASSETS))
    path = mirror.root / mirror.path_for(part["url"])
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 0x01
    path.write_bytes(bytes(data))
    setup = inno["compile_setup"]()
    installed = inno["tmp_path"] / "installed"
    code, log = inno["run_setup"](setup, installed, "tampered")
    assert code != 0, log
    assert "hash" in log.lower(), log
    # The helper never ran and nothing was installed.
    assert not (installed / "seen").exists()
    assert not any((installed / name).exists() for name in ROOT_FILES)


def test_a_missing_r2_part_stops_setup_before_the_helper(inno):
    # A part not on R2 yet (404): setup reports it and stops; there is no other host for the row.
    payload, mirror = inno["payload"], inno["mirror"]
    part = next(p for p in payload["parts"] if p["url"].startswith(r2.DESKTOP_ASSETS))
    (mirror.root / mirror.path_for(part["url"])).unlink()
    setup = inno["compile_setup"]()
    installed = inno["tmp_path"] / "installed"
    code, log = inno["run_setup"](setup, installed, "missing")
    assert code != 0, log
    assert "404" in log, log
    assert ("GET", "/" + mirror.path_for(part["url"])) in mirror.requests
    assert not (installed / "seen").exists()
    assert not any((installed / name).exists() for name in ROOT_FILES)
