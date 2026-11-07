"""The online setup's Inno lines for per-file updates (W2-UD-04, packaging part UD-04i).

- [UninstallDelete] removes everything an interrupted per-file update can leave in
  the installation folder: the stage, the backup of replaced originals, the v2
  journal and the temporary journal files `Release.save_json` writes first.
- The uninstall code removes the game folders first, because those rows cannot reach
  paths over 260 characters.
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
    # The install record (W1b) and the .tmp it is written through, named exactly (no wildcard).
    record = updater_constant("INSTALL_RECORD")
    for leftover in (record, record + ".tmp"):
        assert leftover in files, leftover
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


def test_uninstall_code_removes_every_folder_row_by_name(tmp_path):
    stage = tiny_stage(tmp_path)
    script = package_client.online_installer_script(stage, stage / "RabbitLands-updater.exe", "test", [],
                                                    schema2_payload(stage))
    folders = [name for kind, name in uninstall_delete(script) if kind == "filesandordirs"]
    assert ".eloria-launcher-lock" in folders
    code = script.split("[Code]\n", 1)[1]
    assert package_client.online_uninstall_code() in code
    # Each one by name: {app} itself may hold the player's own files, so it is never a tree to remove.
    assert re.findall(r"RemoveGameFolder\('([^']*)'\)", code) == folders and "" not in folders


def test_uninstall_rows_name_what_the_game_writes_beside_its_folders(tmp_path):
    stage = tiny_stage(tmp_path)
    script = package_client.online_installer_script(stage, stage / "RabbitLands-updater.exe", "test", [],
                                                    schema2_payload(stage))
    files = [name for kind, name in uninstall_delete(script) if kind == "files"]
    for written in ("eloria-debug.log", "eloria-compatibility.log", "eloria-safe-mode.log", ".rabbitlands-install.json.tmp",
                    "RabbitLands-updater.exe.tmp", "RabbitLands-uninstall.exe.tmp"):
        assert any(fnmatch.fnmatchcase(written, pattern) for pattern in files), written
    for kept in ("player-notes.log", "eloria.log", "my-eloria-debug.log"):
        assert not any(fnmatch.fnmatchcase(kept, pattern) for pattern in files), kept


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
    assert "procedure CurUninstallStepChanged" in script
    iss = tmp_path / "online.iss"
    iss.write_text(script, encoding="utf-8-sig")
    result = subprocess.run([str(iscc), "/Q", str(iss)], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (stage.parent / f"{stage.name}-setup.exe").is_file()


def real_inno_install(tmp_path: Path) -> tuple[Path, dict]:
    """A real Inno setup with the generated [Dirs] and [UninstallDelete] rows and uninstall code.

    The test setup registers no uninstall entry (CreateUninstallRegKey=no), closes no
    applications and creates no shortcuts; its temporary files stay under tmp_path.
    """
    iscc = _inno_or_skip()
    stage = tiny_stage(tmp_path)
    generated = package_client.online_installer_script(stage, stage / "RabbitLands-updater.exe", "test", [],
                                                       schema2_payload(stage))

    def section(name: str) -> str:
        return f"[{name}]\n" + generated.split(f"[{name}]\n", 1)[1].split("\n[", 1)[0].strip() + "\n"

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

{section("Dirs")}
[Files]
Source: "{payload}"; DestDir: "{{app}}"

{section("UninstallDelete")}
[Code]
{package_client.online_uninstall_code()}"""
    iss = tmp_path / "uninstall-test.iss"
    iss.write_text(script, encoding="utf-8-sig")
    result = subprocess.run([str(iscc), "/Q", str(iss)], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    temp = tmp_path / "temp"
    temp.mkdir()
    env = {**os.environ, "TEMP": str(temp), "TMP": str(temp)}
    installed = tmp_path / "installed"
    installed.mkdir()  # As the real setup helper does before Inno copies anything.
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
    return installed, env


def run_inno_uninstaller(installed: Path, env: dict, log: Path) -> None:
    uninstall = subprocess.run([str(installed / "unins000.exe"), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                                f"/LOG={log}"], env=env, capture_output=True, timeout=60)
    assert uninstall.returncode == 0, uninstall
    # The uninstaller hands over to a copy of itself in TEMP; its log closes when it has finished.
    deadline = time.monotonic() + 60
    while not (log.is_file() and "Log closed." in log.read_text(errors="replace")):
        assert time.monotonic() < deadline, "The uninstaller did not finish."
        time.sleep(0.1)


def test_inno_uninstaller_removes_an_interrupted_updates_files(tmp_path):
    """A real Inno uninstall with the generated [UninstallDelete] rows."""
    installed, env = real_inno_install(tmp_path)
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
    run_inno_uninstaller(installed, env, tmp_path / "uninstall.log")
    assert sorted(p.name for p in installed.iterdir()) == ["player-notes.tmp"], sorted(
        p.relative_to(installed).as_posix() for p in installed.rglob("*"))
    assert control.read_text() == "keep"


def long_form(path: Path) -> str:
    """Reaches a path over 260 characters whatever this machine's LongPathsEnabled says."""
    return "\\\\?\\" + str(path)


# As a release ships it (R1 9baf44f2): 230-236 characters inside the game folder, so all
# over the limit under a folder of 30 characters or more. The default folder has 48 or more.
PREPARED_WORLD_FILE = "prepared-world/" + "a" * 64 + "/collision/" + "b" * 64 + "/entries/" + "c" * 64 + ".json"


def write_over_260(installed: Path, folder: str) -> Path:
    path = installed / folder / PREPARED_WORLD_FILE
    if len(str(path)) <= 260:  # a very short pytest folder
        path = installed / folder / ("d" * 60) / PREPARED_WORLD_FILE
    assert len(str(path)) > 260
    os.makedirs(os.path.dirname(long_form(path)), exist_ok=True)
    with open(long_form(path), "w", encoding="utf-8") as handle:
        handle.write("{}")
    return path


@pytest.mark.parametrize("player_file", [False, True], ids=["only-game-files", "with-a-player-file"])
def test_inno_uninstaller_removes_paths_over_260_characters(tmp_path, player_file):
    """Inno's own rows leave these (see online_uninstall_code); nothing may stay in the game folder."""
    installed, env = real_inno_install(tmp_path)
    long_files = [write_over_260(installed, folder) for folder in package_client.UNINSTALL_FOLDERS]
    assert all(os.path.isfile(long_form(path)) for path in long_files)
    # A stale lock, and what the debug shortcuts and an interrupted update write beside the folders.
    for name in (".eloria-launcher-lock/owner.json", "eloria-debug.log", "eloria-safe-mode.log", "eloria-compatibility.log",
                 ".rabbitlands-install.json.tmp", "RabbitLands-updater.exe.tmp", "RabbitLands-uninstall.exe.tmp"):
        (installed / name).write_text("left behind")
    # Settings outside the game folder, reached through a junction inside it: never followed.
    settings = tmp_path / "player-settings" / "settings.cfg"
    settings.parent.mkdir()
    settings.write_text("keep my settings")
    linked = subprocess.run(["cmd.exe", "/D", "/C", "mklink", "/J", str(installed / "app" / "external-settings"),
                             str(settings.parent)], capture_output=True, text=True, timeout=15)
    assert linked.returncode == 0, linked.stdout + linked.stderr
    control = installed / "player-notes.txt"
    if player_file:
        control.write_text("keep")
    log = tmp_path / "uninstall.log"
    run_inno_uninstaller(installed, env, log)
    assert settings.read_text() == "keep my settings"
    assert not any(os.path.exists(long_form(path)) for path in long_files), log.read_text(errors="replace")
    if player_file:
        assert sorted(p.name for p in installed.iterdir()) == ["player-notes.txt"]
        assert control.read_text() == "keep"
    else:
        assert not installed.exists(), sorted(p.relative_to(installed).as_posix() for p in installed.rglob("*"))


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
