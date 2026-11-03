"""The online setup's Inno lines for per-file updates (W2-UD-04, packaging part UD-04i).

- [UninstallDelete] removes everything an interrupted per-file update can leave in
  the installation folder: the stage, the backup of replaced originals, the v2
  journal and the temporary journal files `Release.save_json` writes first.
- ExtraDiskSpaceRequired follows the setup helper's real peak disk use.
"""
import fnmatch
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

import pytest

CLIENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLIENT / "tools"))
import asset_packages
import package_client

MIB = 1024 ** 2
MARGIN = 512 * MIB
TEST_APP_ID = "RabbitLandsUninstallDeleteTest"


def uninstall_delete(script: str) -> list[tuple[str, str]]:
    """(type, name relative to {app}) rows of the script's [UninstallDelete] section."""
    section = script.split("[UninstallDelete]\n", 1)[1].split("\n[", 1)[0]
    rows = []
    for line in section.strip().splitlines():
        match = re.fullmatch(r'Type: (files|filesandordirs); Name: "\{app\}\\([^"]+)"', line)
        assert match, line
        rows.append((match.group(1), match.group(2)))
    return rows


def updater_constant(name: str) -> str:
    source = (CLIENT / "src/updates/release.gd").read_text(encoding="utf-8")
    return re.search(rf'^const {name} := "([^"]+)"$', source, re.M).group(1)


def tiny_stage(tmp_path: Path) -> Path:
    stage = tmp_path / "RabbitLands-Windows-20261103-bbbbbbbbb"
    for relative, data in {"app/client-release.json": b"{}", "app/RabbitLands.exe": b"exe",
                           "app/RabbitLands.pck": b"pack", "eloria-assets/world.json": b"{}"}.items():
        (stage / relative).parent.mkdir(parents=True, exist_ok=True)
        (stage / relative).write_bytes(data)
    branding = stage / "app/assets/branding"
    branding.mkdir(parents=True)
    shutil.copyfile(CLIENT / "assets/branding/rabbitlands-icon.ico", branding / "rabbitlands-icon.ico")
    for name in ("RabbitLands-updater.exe", "RabbitLands-uninstall.exe", "RabbitLands (safe mode).bat"):
        (stage / name).write_bytes(b"fixture root file")
    (stage.parent / f"{stage.name}-online-install.txt").write_text("Online installer fixture.")
    return stage


def schema2_payload(stage: Path) -> dict:
    base = "https://github.com/rabbitlandsgame/rabbitlands-client/releases/download/client-" + "b" * 40
    packages = asset_packages.build(stage, base)
    return {"schema": 2, "commit": "b" * 40, "platform": "windows", "version": stage.name,
            "size": sum(p["size"] for p in packages), "unpacked_size": sum(p["unpacked_size"] for p in packages),
            "packages": packages, "parts": [part for p in packages for part in p["parts"]]}


def package(size: int, parts: int) -> dict:
    return {"size": size, "parts": [{"size": size // parts}] * parts}


# --- [UninstallDelete] ------------------------------------------------------------------------------------------

def test_uninstall_delete_covers_every_per_file_update_leftover(tmp_path):
    stage = tiny_stage(tmp_path)
    script = package_client.online_installer_script(stage, stage / "RabbitLands-updater.exe", "test", [],
                                                    schema2_payload(stage))
    rows = uninstall_delete(script)
    folders = {name for kind, name in rows if kind == "filesandordirs"}
    files = [name for kind, name in rows if kind == "files"]
    # The updater's own names (release.gd constants), so a renamed constant fails here.
    stage_dir, journal, backup = (updater_constant(n) for n in ("STAGE", "JOURNAL_V2", "BACKUP_V2"))
    assert {stage_dir, backup, ".eloria-previous"} <= folders
    # Release.save_json writes <name>.tmp and renames it; a stop in between leaves the .tmp.
    for leftover in (journal, journal + ".tmp", ".eloria-update-journal.json", ".eloria-update-journal.json.tmp"):
        assert any(fnmatch.fnmatchcase(leftover, pattern) for pattern in files), leftover
    # The wildcard is anchored to the journal names: it cannot reach the install marker or game files.
    for kept in (".rabbitlands-install.json", "player-notes.tmp", "eloria-update-journal.tmp"):
        assert not any(fnmatch.fnmatchcase(kept, pattern) for pattern in files if "*" in pattern), kept
    # Wave-1 rows are unchanged and keep their order (an ordered subsequence, so a later chunk's
    # row, such as UD-05u's optional-content record, does not have to edit this test).
    wave1 = [("filesandordirs", "app"), ("filesandordirs", "eloria-assets"), ("filesandordirs", ".eloria-previous"),
             ("filesandordirs", ".eloria-update-stage"), ("filesandordirs", ".rabbitlands-bootstrap-previous"),
             ("files", ".rabbitlands-install.json"), ("files", ".eloria-update-journal.json")]
    remaining = iter(rows)
    assert all(row in remaining for row in wave1), rows


def _inno_or_skip():
    iscc = package_client.find_iscc(None)
    if os.name != "nt" or not iscc:
        pytest.skip("Inno Setup 6 is needed for this native check.")
    return iscc


def test_production_online_installer_script_compiles_with_its_uninstall_section(tmp_path):
    """Compile only (never run): the package tests strip [Icons] to [Code] before compiling."""
    iscc = _inno_or_skip()
    stage = tiny_stage(tmp_path)
    script = package_client.online_installer_script(stage, stage / "RabbitLands-updater.exe", "test", [],
                                                    schema2_payload(stage))
    assert '\\.eloria-update-backup"' in script and "ExtraDiskSpaceRequired=" in script
    iss = tmp_path / "online.iss"
    iss.write_text(script, encoding="utf-8-sig")
    result = subprocess.run([str(iscc), "/Q", str(iss)], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (stage.parent / f"{stage.name}-setup.exe").is_file()


def test_inno_uninstaller_removes_an_interrupted_updates_files(tmp_path):
    """A real Inno uninstall with the generated [UninstallDelete] rows.

    The test setup registers no uninstall entry (CreateUninstallRegKey=no), closes no
    applications and creates no shortcuts; its temporary files stay under tmp_path.
    """
    iscc = _inno_or_skip()
    stage = tiny_stage(tmp_path)
    rows = package_client.online_installer_script(stage, stage / "RabbitLands-updater.exe", "test", [],
                                                  schema2_payload(stage)).split("[UninstallDelete]\n", 1)[1]
    section = "[UninstallDelete]\n" + rows.split("\n[", 1)[0].strip() + "\n"
    payload = tmp_path / "payload.txt"
    payload.write_text("installed by the test setup")
    output = tmp_path / "setup-out"
    script = f"""[Setup]
AppId={TEST_APP_ID}
AppName=Rabbit Lands uninstall test
AppVersion=1
DefaultDirName={tmp_path / 'unused-default'}
PrivilegesRequired=lowest
Uninstallable=yes
CreateUninstallRegKey=no
UpdateUninstallLogAppName=no
CloseApplications=no
RestartApplications=no
DisableProgramGroupPage=yes
OutputDir={output}
OutputBaseFilename=uninstall-test-setup

[Files]
Source: "{payload}"; DestDir: "{{app}}"

{section}"""
    iss = tmp_path / "uninstall-test.iss"
    iss.write_text(script, encoding="utf-8-sig")
    result = subprocess.run([str(iscc), "/Q", str(iss)], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    temp = tmp_path / "temp"
    temp.mkdir()
    env = {**os.environ, "TEMP": str(temp), "TMP": str(temp)}
    installed = tmp_path / "installed"
    setup = subprocess.run([str(output / "uninstall-test-setup.exe"), "/VERYSILENT", "/SUPPRESSMSGBOXES",
                            "/NORESTART", "/SP-", f"/DIR={installed}", f"/LOG={tmp_path / 'setup.log'}"],
                           env=env, capture_output=True, timeout=60)
    assert setup.returncode == 0, (tmp_path / "setup.log").read_text(errors="replace")
    assert (installed / "unins000.exe").is_file() and (installed / "payload.txt").is_file()
    if os.name == "nt":
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            with pytest.raises(OSError):
                winreg.OpenKey(hive, rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{TEST_APP_ID}_is1")
    # A per-file update stopped mid-apply (release.gd apply_operations), plus older-updater leftovers.
    leftovers = {
        "app/RabbitLands.pck": "new pack", "eloria-assets/maps/a/world.glb": "new map",
        ".eloria-update-stage/app/assets/added.bin": "staged",
        ".eloria-update-backup/app/RabbitLands.pck": "original pack",
        ".eloria-update-backup/eloria-assets/maps/a/old.glb": "retired",
        ".eloria-update-journal-v2.json": json.dumps({"schema": 2, "operations": []}),
        ".eloria-update-journal-v2.json.tmp": "{",
        ".eloria-update-journal.json": "{}", ".eloria-update-journal.json.tmp": "{",
        ".eloria-previous/app/RabbitLands.pck": "older updater backup",
        ".rabbitlands-install.json": "{}",
    }
    for relative, text in leftovers.items():
        (installed / relative).parent.mkdir(parents=True, exist_ok=True)
        (installed / relative).write_text(text)
    control = installed / "player-notes.tmp"  # not an updater file: must survive
    control.write_text("keep")
    uninstall = subprocess.run([str(installed / "unins000.exe"), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                                f"/LOG={tmp_path / 'uninstall.log'}"], env=env, capture_output=True, timeout=60)
    assert uninstall.returncode == 0, uninstall
    # The uninstaller hands over to a copy of itself in TEMP; wait for it to finish.
    deadline = time.monotonic() + 30
    while sorted(p.name for p in installed.iterdir()) != ["player-notes.tmp"]:
        assert time.monotonic() < deadline, sorted(p.relative_to(installed).as_posix() for p in installed.rglob("*"))
        time.sleep(0.1)
    assert control.read_text() == "keep"


# --- ExtraDiskSpaceRequired ------------------------------------------------------------------------------------

def test_schema1_space_is_unchanged():
    payload = {"schema": 1, "size": 3 * 1024 ** 3, "unpacked_size": 5 * 1024 ** 3}
    assert package_client.online_installer_space(payload) == 5 * 1024 ** 3 + 2 * 3 * 1024 ** 3 + MARGIN


def test_schema2_space_is_two_downloads_plus_the_larger_of_unpacked_and_one_join():
    # A release shaped like 4a57cea4: the unpacked files outweigh any one package.
    packages = [package(700 * MIB, 3), package(200 * MIB, 1), package(3000 * MIB, 12), package(90 * MIB, 1)]
    size = sum(p["size"] for p in packages)
    payload = {"schema": 2, "size": size, "unpacked_size": 6000 * MIB, "packages": packages}
    # The join (one package beside its parts) ends before unpacking starts, so it never adds to it:
    # the value equals the formula before W2-UD-04 for any real release.
    assert package_client.online_installer_space(payload) == 6000 * MIB + 2 * size + MARGIN


def test_schema2_space_covers_a_join_larger_than_the_unpacked_files():
    # One incompressible multi-part package: its ZIP is a little larger than its files.
    packages = [package(1030 * MIB, 5)]
    payload = {"schema": 2, "size": 1030 * MIB, "unpacked_size": 1024 * MIB, "packages": packages}
    assert package_client.online_installer_space(payload) == 2 * 1030 * MIB + 1030 * MIB + MARGIN


def test_schema2_single_part_packages_are_renamed_not_joined():
    packages = [package(900 * MIB, 1), package(100 * MIB, 1)]
    payload = {"schema": 2, "size": 1000 * MIB, "unpacked_size": 800 * MIB, "packages": packages}
    assert package_client.online_installer_space(payload) == 2 * 1000 * MIB + 800 * MIB + MARGIN


def test_generated_script_carries_the_space(tmp_path):
    stage = tiny_stage(tmp_path)
    payload = schema2_payload(stage)
    script = package_client.online_installer_script(stage, stage / "RabbitLands-updater.exe", "test", [], payload)
    assert f"\nExtraDiskSpaceRequired={package_client.online_installer_space(payload)}\n" in script
    assert package_client.online_installer_space(payload) == (
        payload["unpacked_size"] + 2 * payload["size"] + MARGIN)
