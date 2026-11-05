"""The updater helper: fixed project, fingerprint, signed-row reuse (tools/desktop_helpers.py).

No network or Godot: exports and downloads are fakes; keys are throwaway.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

import pytest

GODOT = Path(__file__).resolve().parents[1]
TOOLS = GODOT / "tools"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import desktop_helpers as helpers  # noqa: E402
import desktop_r2 as r2  # noqa: E402
import release_manifest as rm  # noqa: E402
import upload_desktop_assets as up  # noqa: E402
import test_release_manifest as fx  # noqa: E402

EDITOR, TEMPLATE = "a" * 64, "b" * 64
key = fx.key
other_key = fx.other_key


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def source(tmp_path):
    """A copy of this checkout's helper inputs (src/updates and branding)."""
    root = tmp_path / "godot-client"
    shutil.copytree(GODOT / "src/updates", root / "src/updates")
    (root / "assets/branding").mkdir(parents=True)
    for name in helpers.HELPER_BRANDING:
        shutil.copyfile(GODOT / "assets/branding" / name, root / "assets/branding" / name)
    return root


def files_of(source, key, platform="windows", **identity):
    return helpers.project_files(source, {**fx.identity(platform, key), **identity}, platform)


def fingerprint_of(files, platform="windows", editor=EDITOR, template=TEMPLATE):
    return helpers.fingerprint(files, platform=platform, editor_sha256=editor, template_sha256=template)


# --- Fingerprint -----------------------------------------------------------------------

def test_a_game_preset_only_change_keeps_the_fingerprint(source, key, monkeypatch, tmp_path):
    import client_release
    import package_client
    before = fingerprint_of(files_of(source, key))
    changed = package_client.EXPORT_PRESETS.replace('include_filter="*.json,', 'include_filter="*.json,*.csv,')
    assert changed != package_client.EXPORT_PRESETS
    monkeypatch.setattr(package_client, "EXPORT_PRESETS", changed)
    assert fingerprint_of(files_of(source, key)) == before
    assert b"*.csv" not in files_of(source, key)["export_presets.cfg"]
    # export_launcher (local and full-CI builds) delegates here: the same edit
    # keeps its cached helper, so no player downloads the helper again
    godot, template = tmp_path / "godot.exe", tmp_path / "template.exe"
    godot.write_bytes(b"editor")
    template.write_bytes(b"template")
    names, exports = [], []
    for preset in (package_client.EXPORT_PRESETS.replace(',*.csv', ''), changed):
        stage, cache = tmp_path / f"stage{len(names)}", tmp_path / "cache"
        stage.mkdir()

        def run_godot(godot, args, log, timeout):
            exports.append(args)
            if "--export-release" in args:
                Path(args[-1]).write_bytes(b"helper")
        client_release.export_launcher(stage, fx.identity("windows", key), godot, source, preset, "Windows Desktop",
                                       run_godot, tmp_path / f"logs{len(names)}", cache=cache, template=template)
        names.append(sorted(path.name for path in cache.iterdir()))
    value = helpers.fingerprint(files_of(source, key), platform="windows", editor_sha256=sha(b"editor"),
                                template_sha256=sha(b"template"))
    assert names[0] == names[1] == [f"{value}.bin"]
    assert len(exports) == 2  # one import and one export; the second build linked the cached helper
    assert os.path.samefile(tmp_path / "stage1/RabbitLands-updater.exe", tmp_path / "cache" / f"{value}.bin")


def test_a_src_updates_change_alters_the_fingerprint(source, key):
    before = fingerprint_of(files_of(source, key))
    launcher = source / "src/updates/launcher.gd"
    launcher.write_bytes(launcher.read_bytes() + b"\n# a helper change\n")
    after = fingerprint_of(files_of(source, key))
    assert after != before
    # the game-side update scripts are not part of the helper
    startup = source / "src/updates/startup_update.gd"
    startup.write_bytes(startup.read_bytes() + b"\n# a game change\n")
    assert fingerprint_of(files_of(source, key)) == after


def test_other_inputs_alter_the_fingerprint(source, key, other_key):
    files = files_of(source, key)
    base = fingerprint_of(files)
    assert fingerprint_of(files, editor="c" * 64) != base
    assert fingerprint_of(files, template="c" * 64) != base
    assert fingerprint_of(files_of(source, other_key)) != base
    assert fingerprint_of(files_of(source, key, "linux"), "linux") != base
    icon = source / "assets/branding/rabbitlands-icon.ico"
    icon.write_bytes(icon.read_bytes() + b"\0")
    assert fingerprint_of(files_of(source, key)) != base


def test_asset_only_releases_keep_the_trust_file_and_fingerprint(source, key):
    first = files_of(source, key)
    later = files_of(source, key, commit="1" * 40, ancestors=["1" * 40, fx.COMMIT])
    assert first == later
    trust = json.loads(first["data/client_release.json"])
    assert set(trust) == set(helpers.TRUST_FIELDS) and "commit" not in trust


@pytest.mark.parametrize("platform", ["windows", "linux"])
def test_export_launcher_is_this_exporter(source, key, tmp_path, platform):
    """One helper exporter: the local/full-CI export_launcher writes exactly project_files() (the
    fixed preset included, the same bytes on every OS) and exports what the R2 workflow exports."""
    import client_release
    import package_client
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "RabbitLands-updater.pck").write_bytes(b"stale")
    calls = []

    def run_godot(godot, args, log, timeout):
        calls.append(args)
        if "--export-release" in args:
            Path(args[-1]).write_bytes(b"MZ-helper" if platform == "windows" else b"ELF-helper")
    godot = tmp_path / "godot"
    godot.write_bytes(b"editor")
    rows = client_release.export_launcher(stage, fx.identity(platform, key), godot, source,
                                          package_client.EXPORT_PRESETS, package_client.PLATFORMS[platform]["preset"],
                                          run_godot, tmp_path / "logs")
    project = tmp_path / "logs" / "updater-project"
    generated = {path.relative_to(project).as_posix(): path.read_bytes() for path in project.rglob("*")
                 if path.is_file()}
    assert generated == files_of(source, key, platform)
    preset = generated["export_presets.cfg"].decode()
    assert "binary_format/embed_pck=true" in preset and "embed_pck=false" not in preset
    assert f'name="{helpers.PRESET_NAMES[platform]}"' in preset and "[preset.1]" not in preset
    assert [args[args.index("--path") + 1] for args in calls] == [str(project)] * 2
    assert calls[1][calls[1].index("--export-release") + 1] == helpers.PRESET_NAMES[platform]
    updater, uninstall = stage / helpers.BINARIES[platform], stage / helpers.UNINSTALLERS[platform]
    assert os.path.samefile(updater, uninstall) and not (stage / "RabbitLands-updater.pck").exists()
    # the export folder keeps its logs but no second name of the helper
    work = tmp_path / "logs" / "updater-export"
    assert (work / "logs").is_dir() and not (work / "export" / helpers.BINARIES[platform]).exists()
    assert rows["updater"] == {"url": rm.helper_url(sha(updater.read_bytes()), "updater", platform),
                               "size": updater.stat().st_size, "sha256": sha(updater.read_bytes())}
    if platform == "linux" and os.name != "nt":
        assert updater.stat().st_mode & 0o111
    # a rerun into a fresh stage replaces the generated project (no stale fixture files survive)
    (project / "stale.gd").write_text("extends Node\n")
    again = tmp_path / "again"
    again.mkdir()
    client_release.export_launcher(again, fx.identity(platform, key), godot, source, package_client.EXPORT_PRESETS,
                                   package_client.PLATFORMS[platform]["preset"], run_godot, tmp_path / "logs")
    assert not (project / "stale.gd").exists()


def test_export_launcher_refuses_another_preset_and_identity(source, key, tmp_path):
    import client_release
    import package_client

    def run_godot(godot, args, log, timeout):
        pytest.fail("nothing is exported")
    stage = tmp_path / "stage"
    stage.mkdir()
    with pytest.raises(ValueError, match="preset"):
        client_release.export_launcher(stage, fx.identity("windows", key), tmp_path / "godot", source,
                                       package_client.EXPORT_PRESETS, "Linux", run_godot, tmp_path / "logs")
    with pytest.raises(helpers.HelperError) as error:
        client_release.export_launcher(stage, {**fx.identity("windows", key), "distribution": "steam"},
                                       tmp_path / "godot", source, package_client.EXPORT_PRESETS, "Windows Desktop",
                                       run_godot, tmp_path / "logs")
    assert error.value.code == "identity"


def test_a_fork_repository_keeps_its_own_trust(source, key):
    fork = files_of(source, key, repository="someone/rabbitlands-fork")
    assert json.loads(fork["data/client_release.json"])["repository"] == "someone/rabbitlands-fork"
    assert fingerprint_of(fork) != fingerprint_of(files_of(source, key))
    for bad in ("", "no-slash", "a/b/c", "a b/c", None):
        with pytest.raises(helpers.HelperError):
            files_of(source, key, repository=bad)


def test_export_into_caches_only_with_a_known_template(source, key, tmp_path):
    godot = tmp_path / "godot.exe"
    godot.write_bytes(b"editor")
    calls = []
    identity = fx.identity("windows", key)
    for index in range(2):
        stage = tmp_path / f"plain{index}"
        stage.mkdir()
        result = helpers.export_into(stage, source, identity, platform="windows", godot=godot,
                                     run_godot=_fake_export(calls), project=tmp_path / "p", work=tmp_path / "w",
                                     cache=tmp_path / "cache", template=tmp_path / "no-such-template")
        assert result.fingerprint is None and not result.reused
    assert len(calls) == 4 and not (tmp_path / "cache").exists()


def test_find_template_follows_godots_data_folders(tmp_path, monkeypatch):
    editor = tmp_path / "editor"
    editor.mkdir()
    godot = editor / "Godot_v4.7.2-stable_win64.exe"
    godot.write_bytes(b"editor")

    def place(root, platform):
        path = root / "export_templates" / helpers.TEMPLATE_VERSION / helpers.TEMPLATES[platform]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"template")
        return path
    environ = {"APPDATA": str(tmp_path / "appdata"), "XDG_DATA_HOME": str(tmp_path / "xdg")}
    assert helpers.find_template(godot, "windows", environ) is None
    user = place(tmp_path / ("appdata/Godot" if os.name == "nt" else "xdg/godot"), "linux")
    assert helpers.find_template(godot, "linux", environ) == user
    assert helpers.find_template(godot, "windows", environ) is None
    (editor / "._sc_").write_bytes(b"")
    portable = place(editor / "editor_data", "linux")
    assert helpers.find_template(godot, "linux", environ) == portable  # a self-contained editor first
    with pytest.raises(helpers.HelperError):
        helpers.find_template(godot, "macos", environ)


def test_helper_dependencies_must_be_part_of_the_helper(source, key):
    launcher = source / "src/updates/launcher.gd"
    launcher.write_bytes(launcher.read_bytes() + b'\nconst Extra = preload("res://src/runtime/cache_janitor.gd")\n')
    with pytest.raises(helpers.HelperError) as error:
        files_of(source, key)
    assert error.value.code == "helper-dependency"


def test_project_files_refuse_missing_inputs_and_other_identities(source, key):
    with pytest.raises(helpers.HelperError):
        helpers.project_files(source, fx.identity("linux", key), "windows")
    with pytest.raises(helpers.HelperError):
        files_of(source, key, distribution="steam")
    (source / "src/updates/bootstrap.gd").unlink()
    with pytest.raises(helpers.HelperError) as error:
        files_of(source, key)
    assert error.value.code == "helper-script"


# --- Reuse from the previous signed release ----------------------------------------------

class FakeHttp:
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


HELPER_BYTES = b"MZ-helper-binary" * 100


def previous_release(platform="windows", data=HELPER_BYTES, fingerprint="f" * 64, **changes):
    rows = {kind: {"url": rm.helper_url(sha(data), kind, platform), "size": len(data), "sha256": sha(data)}
            for kind in rm.HELPER_KINDS}
    return {"platform": platform, "helpers_fingerprint": fingerprint, **rows, **changes}


def test_reuse_verifies_sha256_against_the_signed_row(tmp_path):
    previous = previous_release()
    http = FakeHttp({previous["updater"]["url"]: HELPER_BYTES})
    rows = helpers.reuse(previous, "f" * 64, platform="windows", http=http, out=tmp_path / "root")
    assert rows == {kind: previous[kind] for kind in rm.HELPER_KINDS}
    updater, uninstall = tmp_path / "root/RabbitLands-updater.exe", tmp_path / "root/RabbitLands-uninstall.exe"
    assert updater.read_bytes() == HELPER_BYTES and os.path.samefile(updater, uninstall)
    assert http.calls == [("GET", previous["updater"]["url"])]
    assert sorted(path.name for path in (tmp_path / "root").iterdir()) == [uninstall.name, updater.name]


@pytest.mark.parametrize("served", [HELPER_BYTES[:-1] + b"X", HELPER_BYTES + b"!", b""])
def test_reuse_refuses_bytes_that_differ_from_the_signed_row(tmp_path, served):
    previous = previous_release()
    http = FakeHttp({previous["updater"]["url"]: served} if served else {})
    with pytest.raises((helpers.HelperError, up.UploadError)):
        helpers.reuse(previous, "f" * 64, platform="windows", http=http, out=tmp_path / "root")
    assert not (tmp_path / "root/RabbitLands-updater.exe").exists()
    assert not list((tmp_path / "root").glob(".download-*")) if (tmp_path / "root").exists() else True


def test_reuse_needs_the_same_fingerprint_and_a_legacy_pool_row(tmp_path):
    previous = previous_release()
    http = FakeHttp({previous["updater"]["url"]: HELPER_BYTES})
    assert helpers.reuse(previous, "e" * 64, platform="windows", http=http, out=tmp_path / "a") is None
    assert helpers.reuse({k: v for k, v in previous.items() if k != "helpers_fingerprint"}, "f" * 64,
                         platform="windows", http=http, out=tmp_path / "b") is None
    assert helpers.reuse(previous, "f" * 64, platform="linux", http=http, out=tmp_path / "c") is None
    assert http.calls == []
    elsewhere = previous_release(updater={**previous["updater"], "url": "https://example.com/RabbitLands-updater.exe"})
    with pytest.raises(helpers.HelperError) as error:
        helpers.reuse(elsewhere, "f" * 64, platform="windows", http=http, out=tmp_path / "d")
    assert error.value.code == "helper-url" and http.calls == []


def _fake_export(calls):
    def run_godot(godot, args, log, timeout):
        calls.append(args)
        if "--export-release" in args:
            Path(args[-1]).write_bytes(b"MZ-new-helper")
    return run_godot


def test_provide_reuses_when_equal_and_exports_otherwise(source, key, tmp_path):
    godot, template = tmp_path / "godot.exe", tmp_path / "template.exe"
    godot.write_bytes(b"editor")
    template.write_bytes(b"template")
    files = files_of(source, key)
    value = helpers.fingerprint(files, platform="windows", editor_sha256=sha(b"editor"),
                                template_sha256=sha(b"template"))
    previous = previous_release(fingerprint=value)
    http = FakeHttp({previous["updater"]["url"]: HELPER_BYTES})
    calls = []
    reused = helpers.provide(source, fx.identity("windows", key), platform="windows", godot=godot, template=template,
                             run_godot=_fake_export(calls), work=tmp_path / "w1", out=tmp_path / "r1",
                             previous=previous, http=http)
    assert reused.reused and calls == [] and reused.rows["updater"] == previous["updater"]
    exported = helpers.provide(source, fx.identity("windows", key), platform="windows", godot=godot,
                               template=template, run_godot=_fake_export(calls), work=tmp_path / "w2",
                               out=tmp_path / "r2", previous=previous_release(fingerprint="0" * 64), http=http)
    assert not exported.reused and exported.fingerprint == value
    assert [args[args.index("--path") + 2] for args in calls] == ["--import", "--export-release"]
    assert calls[1][calls[1].index("--export-release") + 1] == "Windows Desktop"
    assert exported.rows["updater"] == {"url": rm.helper_url(sha(b"MZ-new-helper"), "updater", "windows"),
                                        "size": len(b"MZ-new-helper"), "sha256": sha(b"MZ-new-helper")}
    assert exported.rows["uninstall"]["url"].endswith(f"RabbitLands-uninstall-{sha(b'MZ-new-helper')}.exe")
    project = tmp_path / "w2/helper-project"
    assert (project / "export_presets.cfg").read_bytes() == files["export_presets.cfg"]


def test_previous_release_prefers_r2_then_the_alias_and_verifies(tmp_path, key, other_key):
    payload = {"schema": 2, "platform": "windows", "repository": r2.REPOSITORY, "commit": fx.COMMIT}
    data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    signed = rm.sign(data, rm.load_signing_key(key.private, key.public))
    alias = f"https://github.com/{r2.REPOSITORY}/releases/latest/download/RabbitLands-windows.json"
    http = FakeHttp({alias: signed})
    assert helpers.previous_release(http, "windows", key.public) == payload
    assert http.calls[0] == ("GET", r2.pointer_url("windows"))
    assert helpers.previous_release(FakeHttp({alias: signed}), "windows", other_key.public) is None
    assert helpers.previous_release(FakeHttp(), "windows", key.public) is None
    assert helpers.previous_release(FakeHttp({alias: signed}), "linux", key.public) is None


def test_source_is_ascii_without_machine_paths():
    text = (TOOLS / "desktop_helpers.py").read_bytes().decode("ascii")
    for needle in ("C:/", "C:\\", "/Users/", "scratchpad", "AppData"):
        assert needle not in text
