"""Release discovery (W1b) end to end.

Exported updaters (this tree's, and the field updater of release 945042f0)
install from a local server that stands in for R2 and GitHub. The pointers and
manifests are signed by the release tools (release_manifest.py, desktop_r2.py)
with a test key, so the tools' formats and the client's checks are proven
together. The GDScript rules themselves are covered by
test_client_update_discovery.gd (run_client_update_tests.py).

The release key was replaced at release T (docs/desktop-r2-delivery.md, "Key
rotation (2026-11)"): field updaters pin the retired key and cannot verify T.
test_field_updater_refuses_a_release_signed_with_another_key is that production
path; the field handover check before it is pre-rotation history.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from test_asset_packages import (CLIENT, fixture, manifest, source, export_test_updater, older_updater_source,
                                 older_updater_project, r2_hosted, assert_no_transaction, tree)

sys.path.insert(0, str(CLIENT / "tools"))
import client_release
import desktop_r2 as r2
import package_client
import release_manifest as rm

RELEASE_GD = CLIENT / "src/updates/release.gd"
S = 1_762_300_000
FIELD_UPDATER = "945042f0"  # the field updaters before the key rotation (945042f0/4a57cea4 share src/updates)


def gd_const(name, path=RELEASE_GD):
    match = re.search(rf"^const {name} := (.+)$", path.read_text(encoding="utf-8"), re.M)
    assert match, name
    return match.group(1).strip()


def test_client_pointer_rules_match_the_release_tools():
    assert gd_const("POINTER_KIND") == f'"{r2.POINTER_KIND}"'
    assert gd_const("POINTER_SCHEMA") == str(r2.POINTER_SCHEMA)
    assert gd_const("POINTER_CHANNEL") == f'"{r2.CHANNELS[0]}"' and r2.CHANNELS == ("live",)
    assert gd_const("MAX_POINTER_BYTES") == "64 * 1024" and r2.MAX_POINTER_BYTES == 64 * 1024
    assert int(gd_const("MIN_SEQUENCE")) == r2.MIN_SEQUENCE and int(gd_const("MAX_SEQUENCE")) == r2.MAX_SEQUENCE
    assert gd_const("POINTER_TIMEOUT_SEC") == "15.0"
    fields = json.loads(gd_const("POINTER_FIELDS"))
    assert set(fields) == {"kind", "pointer_schema", "repository", "platform", "channel", "sequence", "rollback",
                           "release_id", "run_id", "target"}
    assert set(json.loads(gd_const("POINTER_TARGET_FIELDS"))) == {"commit", "version", "manifest_sequence", "manifest"}
    assert set(json.loads(gd_const("POINTER_MANIFEST_FIELDS"))) == {"url", "sha256", "size"}
    payload = r2.pointer_payload(platform="windows", sequence=S + 200, rollback=False, release_id=1, run_id=2,
                                 commit="b" * 40, version="RabbitLands-Windows-20261104-bbbbbbbbb",
                                 manifest_sequence=S + 100, manifest_sha256="e" * 64, manifest_size=1000)
    assert set(payload) == set(fields) and set(payload["target"]) == set(json.loads(gd_const("POINTER_TARGET_FIELDS")))
    # The derived forms the client builds equal the tools' (pointer and manifest copy).
    assert '"channels/live/%s.json"' in RELEASE_GD.read_text(encoding="utf-8")
    assert r2.pointer_url("windows") == r2.DESKTOP_ASSETS + "channels/live/windows.json"
    assert payload["target"]["manifest"]["url"] == r2.DESKTOP_ASSETS + "manifests/windows/" + "e" * 64 + ".json"
    # The record name the uninstall hook (package_client [UninstallDelete]) must list.
    assert gd_const("INSTALL_RECORD") == '".rabbitlands-release.json"'
    launch = (CLIENT / "src/updates/launch_options.gd").read_text(encoding="utf-8")
    for flag in ("--target-commit=", "--target-manifest-url=", "--handoff-hops="):
        assert f'"{flag}"' in launch


def test_inno_uninstall_removes_the_install_record():
    # HOOK-W1b-1: an Inno uninstall removes the record and the .tmp it is written through.
    script = (CLIENT / "tools/package_client.py").read_text(encoding="utf-8")
    assert 'Type: files; Name: "{{app}}\\\\.rabbitlands-release.json"' in script
    assert 'Type: files; Name: "{{app}}\\\\.rabbitlands-release.json.tmp"' in script


def public_pem(f):
    return f["key"].public_key().public_bytes(serialization.Encoding.PEM,
                                              serialization.PublicFormat.SubjectPublicKeyInfo)


def r2_release(f, payload, identity, sequence, helper, *, helper_bytes=None):
    """`payload` (a fixture manifest) as a schema-3 release of `identity`'s commit:
    every content part at its derived R2 URL, the R2 additions, and helper rows
    in the shared pool for `helper` (or the bytes `helper_bytes`)."""
    release = r2_hosted(payload, f["tmp_path"])
    data = helper.read_bytes() if helper_bytes is None else helper_bytes
    digest = hashlib.sha256(data).hexdigest()
    for kind in ("updater", "uninstall"):
        name = f"RabbitLands-{kind}-{digest}.exe"
        (f["tmp_path"] / name).write_bytes(data)
        release[kind] = {"url": f"https://github.com/{r2.REPOSITORY}/releases/download/client-assets/{name}",
                         "size": len(data), "sha256": digest}
    release.update(schema=3, commit=identity["commit"], ancestors=identity.get("ancestors", [identity["commit"]]),
                   sequence=sequence, helpers_fingerprint="c" * 64, root_files=[],
                   content={"source": "ci", "set": {"sha256": "d" * 64}})
    r2.validate_manifest_additions(release, platform="windows")
    return release


def publish(f, release):
    """Signs `release` as CI does and serves its immutable R2 copy. Returns (envelope bytes, sha256)."""
    data = rm.sign(rm.payload_bytes(release), f["key"])
    digest = hashlib.sha256(data).hexdigest()
    (f["tmp_path"] / f"{digest}.json").write_bytes(data)
    return data, digest


def serve_pointer(f, data, sequence, *, rollback=False):
    """The live pointer (served under its basename, as the fixture transport maps URLs)."""
    pointer = rm.pointer_envelope(platform="windows", sequence=sequence, rollback=rollback, release_id=123456789,
                                  run_id=987654321, manifest=data, private_key=f["key"], public_pem=public_pem(f))
    (f["tmp_path"] / "windows.json").write_bytes(pointer)
    return pointer


def serve_alias(f, data):
    alias = f["tmp_path"] / "RabbitLands-windows.json"
    if data is None:
        alias.unlink(missing_ok=True)
    else:
        alias.write_bytes(data)


def cache_of(f):
    return (f["tmp_path"] / "userdata/Godot/app_userdata/Eloria/client-updates"
            / hashlib.sha256(f["installed"].as_posix().encode()).hexdigest()[:24])


def record(f):
    path = f["installed"] / ".rabbitlands-release.json"
    return json.loads(path.read_text()) if path.is_file() else None


def installed_commit(f):
    """The installed descriptor's commit, or None while an install moves the descriptor."""
    try:
        return json.loads((f["installed"] / "app/client-release.json").read_text()).get("commit")
    except (OSError, ValueError):
        return None


def run_updater(f, *args, timeout=90):
    completed = subprocess.run([str(f["installed"] / "RabbitLands-updater.exe"), "--headless", "--",
                                "--root", str(f["installed"]), "--update-only", *args],
                               env=f["env"], capture_output=True, text=True, timeout=timeout)
    output = completed.stdout + completed.stderr
    assert "SCRIPT ERROR" not in output, output
    return completed.returncode, output


def stage_of(f, identity):
    """A release stage with exactly `identity`'s files (the fixture's installed layout)."""
    stage = f["tmp_path"] / f"RabbitLands-Windows-20261023-{identity['commit'][:9]}"
    if not stage.exists():
        source(stage, identity)
    return stage


@pytest.mark.skipif(os.name != "nt", reason="Exports and runs the Windows updater")
def test_exported_updater_discovers_through_the_pointer_and_guards_downgrades(fixture):
    f = fixture
    updater = export_test_updater(f, "discovery")
    for kind in ("updater", "uninstall"):
        shutil.copyfile(updater, f["installed"] / f"RabbitLands-{kind}.exe")
    newer = r2_release(f, f["payload"], f["newer"], S + 100, updater)
    newer_data, newer_sha = publish(f, newer)
    forward = serve_pointer(f, newer_data, S + 200)
    serve_alias(f, None)  # the pointer alone names the release (as between publish and promote)

    # 1. Pointer -> its manifest copy -> R2 parts. The record and the mark follow.
    code, output = run_updater(f)
    assert code == 0, output
    assert installed_commit(f) == "b" * 40
    assert "Release discovery: R2 pointer %d, commit bbbbbbbbb" % (S + 200) in output, output
    assert record(f) == {"schema": 1, "commit": "b" * 40, "platform": "windows", "sequence": S + 100,
                         "manifest_sha256": newer_sha}
    assert json.loads((cache_of(f) / "release-pointer.json").read_text()) == {"schema": 1, "sequence": S + 200}
    parts = {"/" + part["url"].rsplit("/", 1)[1] for part in newer["parts"]}
    assert f["downloads"][:2] == ["/windows.json", f"/{newer_sha}.json"], f["downloads"]
    assert set(f["downloads"][2:]) <= parts and "/RabbitLands-windows.json" not in f["downloads"]
    assert all(url.startswith(r2.DESKTOP_ASSETS + "parts/") for url in (p["url"] for p in newer["parts"]))
    assert_no_transaction(f["installed"])
    # A check that finds nothing to install (re)writes the record too.
    (f["installed"] / ".rabbitlands-release.json").unlink()
    f["downloads"].clear()
    code, output = run_updater(f)
    assert code == 0 and record(f)["sequence"] == S + 100, output
    assert f["downloads"] == ["/windows.json", f"/{newer_sha}.json"], f["downloads"]

    # 2. An older signed release on the alias (the pointer gone) is refused.
    # (Its packages are b's; the guard refuses it before anything is downloaded.)
    older = r2_release(f, f["payload"], {**f["newer"], "commit": "c" * 40, "ancestors": ["c" * 40]}, S, updater)
    older_data, _ = publish(f, older)
    (f["tmp_path"] / "windows.json").unlink()
    serve_alias(f, older_data)
    f["downloads"].clear()
    code, output = run_updater(f)
    assert code == 1 and "This update is older than the installed game." in output, output
    assert installed_commit(f) == "b" * 40 and record(f)["sequence"] == S + 100
    assert f["downloads"] == ["/windows.json", "/RabbitLands-windows.json"], f["downloads"]
    # An older download prepared earlier (pending.json) is dropped, never installed.
    rollback = r2_release(f, manifest(stage_of(f, f["identity"]), f["identity"]), f["identity"], S - 100, updater)
    rollback_data, rollback_sha = publish(f, rollback)
    pending = cache_of(f) / "pending.json"
    pending.write_bytes(rollback_data)
    code, output = run_updater(f)
    assert not pending.exists() and "A package is missing" not in output, output
    assert installed_commit(f) == "b" * 40 and record(f)["sequence"] == S + 100

    # 3. A signed rollback pointer that names an older release installs exactly it.
    serve_pointer(f, rollback_data, S + 300, rollback=True)
    serve_alias(f, None)
    code, output = run_updater(f)
    assert code == 0, output
    assert installed_commit(f) == "a" * 40 and "(rollback)" in output, output
    assert record(f) == {"schema": 1, "commit": "a" * 40, "platform": "windows", "sequence": S - 100,
                         "manifest_sha256": rollback_sha}

    # 4. The earlier forward pointer replayed: older than the mark, so refused.
    (f["tmp_path"] / "windows.json").write_bytes(forward)
    f["downloads"].clear()
    code, output = run_updater(f)
    assert code == 1 and "older than one this installation has seen" in output, output
    assert installed_commit(f) == "a" * 40
    assert f["downloads"] == ["/windows.json", "/RabbitLands-windows.json"], f["downloads"]

    # 5. A server target the pointer does not name: rediscovery bypasses it and
    # installs the notice's R2 manifest copy (bytes bound to its name).
    serve_pointer(f, rollback_data, S + 400, rollback=True)
    target_url = r2.DESKTOP_ASSETS + f"manifests/windows/{newer_sha}.json"
    f["downloads"].clear()
    code, output = run_updater(f, "--target-commit=" + "b" * 40, "--target-manifest-url=" + target_url)
    assert code == 0, output
    assert installed_commit(f) == "b" * 40 and "Release discovery: server target, commit bbbbbbbbb" in output, output
    assert f["downloads"][:3] == ["/windows.json", "/RabbitLands-windows.json", f"/{newer_sha}.json"], f["downloads"]
    assert record(f)["sequence"] == S + 100

    # 6. The hop guard: a release naming another updater after three handovers.
    other = r2_release(f, f["payload"], f["newer"], S + 150, updater, helper_bytes=b"another updater")
    other_data, _ = publish(f, other)
    (f["tmp_path"] / "windows.json").unlink()
    serve_alias(f, other_data)
    f["downloads"].clear()
    code, output = run_updater(f, "--handoff-hops=3")
    assert code == 1 and "Updater versions disagree; try again later." in output, output
    assert f["downloads"] == ["/windows.json", "/RabbitLands-windows.json"], "a helper was fetched past the hop limit"
    code, output = run_updater(f, "--handoff-hops=x")
    assert code == 1 and "Updater versions disagree" in output, output
    # Below the limit the handover happens, counting one more hop and keeping the
    # request. ("another updater" is no executable: the handover then stops.)
    code, output = run_updater(f, "--handoff-hops=2", "--target-commit=" + "b" * 40)
    assert code == 0, output
    handed = json.loads((cache_of(f) / "bootstrap-manifest.json").read_text())
    assert handed["args"] == ["--update-only", "--target-commit=" + "b" * 40, "--handoff-hops=3"], handed["args"]
    deadline = time.monotonic() + 60
    while (f["installed"] / ".eloria-launcher-lock").exists():
        assert time.monotonic() < deadline, "the handover worker did not finish"
        time.sleep(0.2)


@pytest.mark.skipif(os.name != "nt", reason="Exports the Windows setup helper")
def test_setup_helper_seeds_the_install_record(fixture):
    """A fresh setup.exe install starts with the installed-release record (its
    embedded helper installs through Packages.install), so the first R2-aware
    discovery already has a high-water mark."""
    f = fixture
    stage = f["stage"]
    release = r2_release(f, f["payload"], f["newer"], S + 100, None, helper_bytes=b"helper rows only")
    (stage.parent / f"{stage.name}-windows.json").write_bytes(rm.sign(rm.payload_bytes(release), f["key"]))
    branding = stage / "app/assets/branding"
    branding.mkdir(parents=True)
    for name in ("rabbitlands-icon.ico", "rabbitlands-mark-64.png"):
        shutil.copyfile(CLIENT / "assets/branding" / name, branding / name)
    logs = f["tmp_path"] / "setup-logs"
    logs.mkdir()

    def run_godot(godot, args, log, timeout):
        result = subprocess.run([str(godot), "--log-file", str(log.with_suffix(".godot.log")), *args],
                                capture_output=True, text=True, timeout=timeout)
        log.write_text(result.stdout + result.stderr)
        assert result.returncode == 0 and "SCRIPT ERROR" not in log.read_text(), log.read_text()

    client_release.export_installer_helper(stage, f["godot"], CLIENT, package_client.EXPORT_PRESETS, run_godot, logs)
    parts = f["tmp_path"] / "setup-tmp"
    parts.mkdir()
    for part in release["parts"]:
        name = part["url"].rsplit("/", 1)[1]
        shutil.copyfile(f["tmp_path"] / name, parts / name)
    installed = f["tmp_path"] / "setup-installed"
    result = subprocess.run([str(f["godot"]), "--headless", "--log-file", str(logs / "helper-run.log"), "--path",
                             str(logs / "installer-project"), "--", "--root", str(installed), "--parts", str(parts)],
                            env=f["env"], capture_output=True, text=True, timeout=120)
    output = result.stdout + result.stderr
    assert result.returncode == 0 and "SCRIPT ERROR" not in output and "installation verified" in output, output
    seeded = json.loads((installed / ".rabbitlands-release.json").read_text())
    assert {key: seeded[key] for key in ("schema", "commit", "platform", "sequence")} == {
        "schema": 1, "commit": "b" * 40, "platform": "windows", "sequence": S + 100}, seeded


FIELD_GAME = '''extends SceneTree
const Release = preload("res://src/updates/release.gd")
const Startup = preload("res://src/updates/startup_update.gd")
const Bootstrap = preload("res://src/updates/bootstrap.gd")
func _initialize() -> void:
    _run.call_deferred()
func _run() -> void:
    var request := Release.read_json(OS.get_cmdline_user_args()[0])
    var trust: Dictionary = request.trust
    var release := Startup.published_identity(request.release, trust)
    var result := {"release": release.get("commit", release.get("error", "")),
        "relation": Startup.relationship(request.installed, release) if not release.has("error") else "",
        "pointer_as_release": Startup.published_identity(request.pointer, trust).get("error", "accepted"),
        "pointer_as_bootstrap": Bootstrap.verify(request.pointer, trust).get("error", "accepted"),
        "pointer_as_manifest": Release.verify_manifest(request.pointer, trust).get("error", "accepted")}
    Release.save_json(request.result, result)
    quit()
'''


@pytest.mark.skipif(os.name != "nt", reason="Exports and runs the Windows updater")
def test_field_updater_hands_off_to_the_r2_aware_updater_which_uses_the_pointer(fixture):
    """Pre-rotation history: both updaters and the release share one test key, so
    this proves the bootstrap schema 1 handover, not a production path. Since the
    key rotation the field updaters pin the retired key and refuse T (the test
    below)."""
    f = fixture
    older = older_updater_source(f, FIELD_UPDATER)
    if older is None:
        pytest.skip(f"The field updater revision {FIELD_UPDATER} is not available here.")
    old = export_test_updater(f, "old", source=older)
    new = export_test_updater(f, "new")
    for kind in ("updater", "uninstall"):
        shutil.copyfile(old, f["installed"] / f"RabbitLands-{kind}.exe")
    release = r2_release(f, f["payload"], f["newer"], S + 100, new)
    data, digest = publish(f, release)
    serve_pointer(f, data, S + 200)
    serve_alias(f, data)  # field updaters read only the alias

    # The field game offers a schema-3 alias release and refuses a pointer.
    project = older_updater_project(f, FIELD_UPDATER)
    (project / "field-game.gd").write_text(FIELD_GAME)
    trust = {**f["identity"], "distribution": "github"}
    request, result = f["tmp_path"] / "field-request.json", f["tmp_path"] / "field-result.json"
    request.write_text(json.dumps({"trust": trust, "installed": f["identity"], "result": str(result),
                                   "release": json.loads(data), "pointer": json.loads((f["tmp_path"] / "windows.json").read_bytes())}))
    completed = subprocess.run([str(f["godot"]), "--headless", "--path", str(project), "--script",
                                str(project / "field-game.gd"), "--", str(request)],
                               env=f["env"], capture_output=True, text=True, timeout=60)
    assert completed.returncode == 0 and "SCRIPT ERROR" not in completed.stdout + completed.stderr, completed.stderr
    field = json.loads(result.read_text())
    assert field["release"] == "b" * 40 and field["relation"] == "behind", field
    assert "accepted" not in (field["pointer_as_release"], field["pointer_as_bootstrap"], field["pointer_as_manifest"]), field

    # The field updater verifies the bootstrap rows, fetches the new helper and
    # hands over; the new helper discovers through the pointer and installs.
    log = f["tmp_path"] / "field-updater.log"
    with log.open("w") as output:
        process = subprocess.Popen([str(f["installed"] / "RabbitLands-updater.exe"), "--headless", "--",
                                    "--root", str(f["installed"]), "--update-only"],
                                   env=f["env"], stdout=output, stderr=subprocess.STDOUT)
    assert process.wait(timeout=60) == 0, log.read_text()
    deadline = time.monotonic() + 60
    while True:
        proof = f["installed"] / "updater-test-version.txt"
        if (installed_commit(f) == "b" * 40 and proof.is_file() and proof.read_text() == "new"
                and not (f["installed"] / ".eloria-launcher-lock").exists() and record(f) is not None):
            break
        assert time.monotonic() < deadline, log.read_text() + "\n" + str(f["downloads"])
        time.sleep(0.2)
    for kind in ("updater", "uninstall"):
        assert client_release.digest(f["installed"] / f"RabbitLands-{kind}.exe") == client_release.digest(new)
    assert record(f) == {"schema": 1, "commit": "b" * 40, "platform": "windows", "sequence": S + 100,
                         "manifest_sha256": digest}
    assert json.loads((cache_of(f) / "release-pointer.json").read_text())["sequence"] == S + 200
    downloads = f["downloads"]
    helper = "/" + release["updater"]["url"].rsplit("/", 1)[1]
    # Field updater: alias, then the helper. New updater: pointer, manifest copy, parts.
    assert downloads[0] == "/RabbitLands-windows.json" and downloads.count(helper) == 1, downloads
    after = downloads[downloads.index(helper) + 1:]
    assert after[:2] == ["/windows.json", f"/{digest}.json"], downloads
    parts = {"/" + part["url"].rsplit("/", 1)[1] for part in release["parts"]}
    assert set(after[2:]) <= parts and len(after[2:]) == len(set(after[2:])), downloads
    assert_no_transaction(f["installed"])


@pytest.mark.skipif(os.name != "nt", reason="Exports and runs the Windows updater")
def test_field_updater_refuses_a_release_signed_with_another_key(fixture):
    """The key rotation as installed games meet it. The field game and updater pin
    the fixture key (the retired key); release T, its pointer and everything after
    are signed with another key. The game offers nothing, the updater stops with
    a signature error before it fetches any helper, and the installation is
    unchanged: its player reinstalls from T's installer."""
    f = fixture
    older = older_updater_source(f, FIELD_UPDATER)
    if older is None:
        pytest.skip(f"The field updater revision {FIELD_UPDATER} is not available here.")
    old = export_test_updater(f, "old", source=older)
    for kind in ("updater", "uninstall"):
        shutil.copyfile(old, f["installed"] / f"RabbitLands-{kind}.exe")
    rotated = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rotated_pem = rotated.public_key().public_bytes(serialization.Encoding.PEM,
                                                    serialization.PublicFormat.SubjectPublicKeyInfo)
    assert rotated_pem != public_pem(f)
    release = r2_release(f, f["payload"], f["newer"], S + 100, None, helper_bytes=b"the rotated release's updater")
    data = rm.sign(rm.payload_bytes(release), rotated)
    rm.verify(data, rotated_pem)  # a valid release under the new key
    with pytest.raises(rm.SigningError):
        rm.verify(data, public_pem(f))
    (f["tmp_path"] / f"{hashlib.sha256(data).hexdigest()}.json").write_bytes(data)
    pointer = rm.pointer_envelope(platform="windows", sequence=S + 200, rollback=False, release_id=123456789,
                                  run_id=987654321, manifest=data, private_key=rotated, public_pem=rotated_pem)
    (f["tmp_path"] / "windows.json").write_bytes(pointer)
    serve_alias(f, data)
    before = tree(f["installed"])
    helpers = {kind: client_release.digest(f["installed"] / f"RabbitLands-{kind}.exe")
               for kind in ("updater", "uninstall")}

    # The field game: the alias release fails its signature check, so it is never offered.
    project = older_updater_project(f, FIELD_UPDATER)
    (project / "field-game.gd").write_text(FIELD_GAME)
    trust = {**f["identity"], "distribution": "github"}
    request, result = f["tmp_path"] / "field-request.json", f["tmp_path"] / "field-result.json"
    request.write_text(json.dumps({"trust": trust, "installed": f["identity"], "result": str(result),
                                   "release": json.loads(data), "pointer": json.loads(pointer)}))
    completed = subprocess.run([str(f["godot"]), "--headless", "--path", str(project), "--script",
                                str(project / "field-game.gd"), "--", str(request)],
                               env=f["env"], capture_output=True, text=True, timeout=60)
    assert completed.returncode == 0 and "SCRIPT ERROR" not in completed.stdout + completed.stderr, completed.stderr
    field = json.loads(result.read_text())
    assert field["release"] == "The release signature could not be verified." and field["relation"] == "", field
    assert "accepted" not in (field["pointer_as_release"], field["pointer_as_bootstrap"], field["pointer_as_manifest"]), field

    # The field updater, run explicitly: alias only, a signature error, nothing changed.
    f["downloads"].clear()
    code, output = run_updater(f)
    assert code == 1 and "The release signature could not be verified." in output, output
    assert f["downloads"] == ["/RabbitLands-windows.json"], f["downloads"]
    assert installed_commit(f) == "a" * 40 and record(f) is None
    assert tree(f["installed"]) == before
    for kind, digest in helpers.items():
        assert client_release.digest(f["installed"] / f"RabbitLands-{kind}.exe") == digest
    assert not (f["installed"] / ".eloria-launcher-lock").exists()
    assert_no_transaction(f["installed"])
