"""Cross-release upload reuse and preservation of live and pending downloads."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from contextlib import contextmanager

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import asset_packages
import build_release as release
import client_release
import runner_release as runner
import shared_release_assets as shared
from linux_download_helper import bootstrap_script
from test_asset_packages import fixture, signed


POOL = {"id": 777, "tag_name": shared.TAG, "draft": False, "prerelease": True,
        "author": {"login": "rabbitlandsgame"}}


def remote(row, index=1):
    return {"id": index, "name": row["name"], "state": "uploaded", "size": row["size"], "digest": "sha256:" + row["sha256"]}


def test_only_changed_packages_upload_across_different_release_dates_and_drafts(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "authorize", lambda: None)
    monkeypatch.setattr(shared, "ensure", lambda: POOL)
    monkeypatch.setattr(release, "gh", lambda *args: json.dumps({"draft": True, "tag_name": "client-a", "author": {"login": "rabbitlandsgame"}}))
    cloud, uploads = {}, []
    monkeypatch.setattr(release, "github_assets", lambda id: list(cloud.values()) if id == 777 else [])
    monkeypatch.setenv("GH_TOKEN", "fixture-only-token")

    @contextmanager
    def upload(request, timeout):
        name = release.urllib.parse.parse_qs(release.urllib.parse.urlparse(request.full_url).query)["name"][0]
        data = request.data.read()
        uploads.append(name)
        row = {"name": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        assert shared.NAME.fullmatch(name)[2] == row["sha256"]
        cloud[name] = remote(row, len(cloud) + 1)
        yield io.BytesIO(json.dumps(cloud[name]).encode())

    monkeypatch.setattr(release.urllib.request, "urlopen", upload)
    old_packages = None
    for index in (1, 2):
        stage = tmp_path / str(index) / f"RabbitLands-Windows-2026102{index}-{'a' if index == 1 else 'b'}"
        (stage / "app").mkdir(parents=True)
        (stage / "eloria-assets/maps/example").mkdir(parents=True)
        (stage / "app/RabbitLands.exe").write_bytes(b"same engine")
        (stage / "app/RabbitLands.pck").write_bytes(b"client revision " + str(index).encode())
        (stage / "eloria-assets/maps/example/map.json").write_bytes(b"same map")
        sink = runner.GitHubSink(index)
        packages = asset_packages.build(stage, shared.base(release.REPOSITORY), shared=True)
        for package in packages:
            for part in package["parts"]:
                path = stage.parent / part["url"].rsplit("/", 1)[1]
                sink.accept(path, {"name": path.name, "size": part["size"], "sha256": part["sha256"]})
        if index == 1:
            assert len(uploads) == 3
            old_packages = {p["id"]: p for p in packages}
        else:
            assert len(uploads) == 4 # Two unchanged packages retain their original asset IDs.
            for package in packages:
                assert (package["parts"] == old_packages[package["id"]]["parts"]) == (package["id"] != "client")
            assert sink.reused_bytes > 0 and sink.uploaded_bytes > 0


def test_parallel_upload_waits_for_existing_reservation_and_never_deletes_it(tmp_path, monkeypatch):
    path = tmp_path / shared.name("a" * 64)
    path.write_bytes(b"part")
    row = {"size": 4, "sha256": "a" * 64}
    starter = {"id": 7, "name": path.name, "state": "starter"}
    finished = remote({"name": path.name, **row}, 7)
    sequence = iter([[starter], [finished]])
    monkeypatch.setenv("GH_TOKEN", "fixture-only-token")
    monkeypatch.setattr(release, "github_assets", lambda id: next(sequence))
    monkeypatch.setattr(release.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(release, "gh", lambda *args: pytest.fail("Never delete a concurrent uploader's reservation"))
    monkeypatch.setattr(release.urllib.request, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(
        release.urllib.error.HTTPError("https://example.invalid", 422, "Already exists", {}, None)))
    assert release.upload_asset_api(777, path, row, {}, immutable=True)["id"] == 7


def test_wrong_shared_checksum_never_overwrites_a_published_blob(tmp_path, monkeypatch):
    path = tmp_path / shared.name("a" * 64)
    path.write_bytes(b"part")
    monkeypatch.setenv("GH_TOKEN", "fixture-only-token")
    monkeypatch.setattr(release, "gh", lambda *args: pytest.fail("Do not delete an unexpected shared download"))
    monkeypatch.setattr(release.urllib.request, "urlopen", lambda *args, **kwargs: pytest.fail("Do not upload over a checksum conflict"))
    with pytest.raises(ValueError, match="checksum conflict"):
        release.upload_asset_api(777, path, {"size": 4, "sha256": "a" * 64},
                                {"id": 7, "state": "uploaded", "size": 4, "digest": "sha256:" + "b" * 64}, immutable=True)
    assert path.read_bytes() == b"part"


def shared_payload(f):
    payload = json.loads(json.dumps(f["payload"]))
    for package in payload["packages"]:
        for row in package["parts"]:
            original = f["tmp_path"] / row["url"].rsplit("/", 1)[1]
            target = original.with_name(shared.name(row["sha256"]))
            shutil.copyfile(original, target)
            row["url"] = shared.base(release.REPOSITORY) + "/" + target.name
    payload["parts"] = [row for p in payload["packages"] for row in p["parts"]]
    for kind in ("updater", "uninstall"):
        row = payload[kind]
        original = f["tmp_path"] / row["url"].rsplit("/", 1)[1]
        target = original.with_name(shared.name(row["sha256"], kind, "exe"))
        shutil.copyfile(original, target)
        row["url"] = shared.base(release.REPOSITORY) + "/" + target.name
    return payload


def test_signed_shared_urls_install_and_reject_other_repositories_or_wrong_hash_names(fixture):
    f = fixture
    payload = shared_payload(f)
    assert f["run"]("bootstrap-verify", payload)[0] == 0
    assert f["run"]("update", payload)[0] == 0
    assert (f["installed"] / "app/RabbitLands.pck").read_bytes() == b"fixture pack"
    bad = json.loads(json.dumps(payload))
    bad["packages"][0]["parts"][0]["url"] = bad["packages"][0]["parts"][0]["url"].replace(release.REPOSITORY, "somebody/else")
    assert f["run"]("verify", bad)[0] == 1
    bad = json.loads(json.dumps(payload))
    bad["updater"]["url"] = shared.base(release.REPOSITORY) + "/" + shared.name("f" * 64, "updater", "exe")
    assert f["run"]("bootstrap-verify", bad)[0] == 1


def shared_finalizer_fixture(tmp_path, monkeypatch):
    from test_finalize_runner_release import fixture as original
    import finalize_runner_release as finalizer
    receipts, assets, calls = original(tmp_path, monkeypatch)
    pool_assets = []
    for path in receipts:
        item = json.loads(path.read_text())
        item["assets"] = [r for r in item["assets"] if not r["name"].endswith((".update.zip.001", ".tar.gz.001"))]
        alias = {"name": f'RabbitLands-{item["platform"]}.json', "size": 10, "sha256": "b" * 64}
        item["assets"].append(alias)
        assets.append(remote(alias, 500 + len(assets)))
        item.update(update_schema=2, shared_storage=1, shared_release_id=777, shared_packages={}, shared_helpers={}, shared_assets=[])
        for kind in ("client", "engine", "updater", "uninstall"):
            digest = hashlib.sha256((kind + item["platform"]).encode()).hexdigest()
            extension = "zip.part" if kind in ("client", "engine") else ("exe" if item["platform"] == "windows" else "x86_64")
            filename = shared.name(digest, "pkg" if kind in ("client", "engine") else kind, extension)
            row = {"name": filename, "size": 10, "sha256": digest}
            item["shared_assets"].append(row)
            pool_assets.append(remote(row, 1000 + len(pool_assets)))
            if kind in ("client", "engine"):
                item["shared_packages"][kind] = [filename]
            else:
                item["shared_helpers"][kind] = filename
        path.write_text(json.dumps(item))
    assets[:] = [a for a in assets if not a["name"].endswith((".update.zip.001", ".tar.gz.001"))]
    previous_gh = release.gh
    monkeypatch.setattr(release, "gh", lambda *args: json.dumps(POOL) if args[:2] == ("api", f"repos/{release.REPOSITORY}/releases/777") else previous_gh(*args))
    monkeypatch.setattr(release, "github_assets", lambda id: list(pool_assets if id == 777 else assets))
    return finalizer, receipts, assets, pool_assets, calls


@pytest.mark.parametrize("corrupt", [False, True])
def test_finalization_checks_shared_assets_before_touching_the_existing_build(tmp_path, monkeypatch, corrupt):
    finalizer, receipts, assets, pool_assets, calls = shared_finalizer_fixture(tmp_path, monkeypatch)
    if corrupt:
        pool_assets[-1]["digest"] = "sha256:" + "f" * 64
        with pytest.raises(ValueError, match="shared download"):
            finalizer.finalize(receipts, tmp_path / "final")
        assert not any(call[:2] == ("release", "edit") or call[:3] == ("api", "--method", "DELETE") for call in calls)
    else:
        finalizer.finalize(receipts, tmp_path / "final")
        assert len((tmp_path / "final/SHA256SUMS").read_text().splitlines()) == 14
        notes = (tmp_path / "final/RELEASE-NOTES.md").read_text()
        assert shared.base(release.REPOSITORY) in notes and ".tar.gz" not in notes
        assert "~/Games/RabbitLands/RabbitLands-updater.x86_64" in notes


def test_shared_cleanup_retains_current_files_and_defers_to_any_draft(monkeypatch):
    used, unused = shared.name("a" * 64), shared.name("b" * 64)
    assets = [{"id": 1, "name": used}, {"id": 2, "name": unused}]
    current = {"id": 22, "tag_name": "client-" + "c" * 40, "draft": False}
    draft = {"id": 33, "tag_name": "client-" + "d" * 40, "draft": True}
    calls = []
    monkeypatch.setattr(release, "github_assets", lambda id: assets)
    monkeypatch.setattr(release, "gh", lambda *args: calls.append(args))
    assert shared.collect_unused([current, POOL, draft], 22, {used: "a" * 64}) == []
    assert not calls
    assert shared.collect_unused([current, POOL], 22, {used: "a" * 64}) == [unused]
    assert calls == [("api", "--method", "DELETE", f"repos/{release.REPOSITORY}/releases/assets/2")]


def test_shared_storage_is_a_prerelease_and_is_never_latest(monkeypatch):
    calls, sequence = [], iter([None, POOL])
    monkeypatch.setattr(release, "github_release", lambda tag: next(sequence))
    monkeypatch.setattr(release, "gh", lambda *args: calls.append(args))
    assert shared.ensure("a" * 40) == POOL
    assert len(calls) == 1 and "--prerelease" in calls[0] and "--latest=false" in calls[0]
    with pytest.raises(ValueError):
        shared.validate_release({**POOL, "draft": True})


def test_linux_helper_downloads_only_the_updater_and_has_no_archive(tmp_path):
    row = {"url": shared.base(release.REPOSITORY) + "/" + shared.name("a" * 64, "updater", "x86_64"), "sha256": "a" * 64}
    script = bootstrap_script(row)
    assert "tar" not in script.split("for tool ", 1)[1].split("; do", 1)[0]
    assert row["url"] in script and "--install-update" in script and "sha256sum -c" in script
    assert ".tar.gz" not in script


def test_real_inno_installer_uses_shared_packages_for_install_and_selective_repair(fixture):
    from test_asset_packages import test_inno_single_file_setup_uses_packages_for_fresh_install_and_repair as check
    f = fixture
    f["payload"] = shared_payload(f)
    check(f)


@pytest.mark.skipif(os.name != "nt" or not shutil.which("wsl.exe"), reason="WSL Linux shell fixture")
@pytest.mark.parametrize("corrupt", [False, True])
def test_linux_bootstrap_checks_download_before_executing_and_cleans_temporary_files(tmp_path, corrupt):
    import package_client
    binary = tmp_path / "native-updater"
    binary.write_bytes(b'#!/bin/sh\nprintf "%s\\n" "$@" >"$PROBE_ARGS"\nprevious=""\nfor argument in "$@"; do\n if [ "$previous" = "--install-manifest" ]; then cat "$argument" >"$PROBE_MANIFEST"; fi\n previous=$argument\ndone\n')
    digest = client_release.digest(binary)
    row = {"url": shared.base(release.REPOSITORY) + "/" + shared.name(digest, "updater", "x86_64"), "sha256": digest}
    if corrupt:
        binary.write_bytes(b"not the trusted executable")
    script = tmp_path / "install.sh"
    envelope = {"payload": "fixture signed payload", "signature": "fixture signature"}
    script.write_bytes(bootstrap_script(row, envelope).encode())
    tools = tmp_path / "tools"
    tools.mkdir()
    curl = tools / "curl"
    curl.write_bytes(b'#!/bin/sh\nwhile [ "$#" -gt 0 ]; do\n if [ "$1" = "--output" ]; then destination=$2; break; fi\n shift\ndone\ncp -- "$SOURCE" "$destination"\n')
    temporary = tmp_path / "temporary"
    temporary.mkdir()
    args = tmp_path / "args.txt"
    manifest_copy = tmp_path / "manifest-copy.json"
    prefix = ["wsl.exe", "-d", "Ubuntu-24.04", "--exec"]
    chmod = subprocess.run([*prefix, "chmod", "700", package_client.wsl_path(curl)], capture_output=True, text=True, timeout=20)
    assert chmod.returncode == 0, chmod.stderr
    result = subprocess.run([*prefix, "env", "PATH=" + package_client.wsl_path(tools) + ":/usr/bin:/bin",
        "SOURCE=" + package_client.wsl_path(binary), "PROBE_ARGS=" + package_client.wsl_path(args),
        "PROBE_MANIFEST=" + package_client.wsl_path(manifest_copy),
        "TMPDIR=" + package_client.wsl_path(temporary), "sh", package_client.wsl_path(script),
        package_client.wsl_path(tmp_path / "Games")], capture_output=True, text=True, timeout=25)
    assert not list(temporary.iterdir()), result.stdout + result.stderr
    if corrupt:
        assert result.returncode != 0 and not args.exists()
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        values = args.read_text().splitlines()
        assert values[:5] == ["--", "--root", package_client.wsl_path(tmp_path / "Games/RabbitLands"), "--install-update", "--install-manifest"]
        assert values[5].endswith("/manifest.json") and json.loads(manifest_copy.read_text()) == envelope


def test_local_uploader_keeps_shared_files_out_of_the_versioned_draft(tmp_path, monkeypatch):
    from test_build_release import upload_fixture, mock_github
    bundle, executable = upload_fixture(tmp_path)
    blob = tmp_path / shared.name(hashlib.sha256(b"shared bytes").hexdigest())
    blob.write_bytes(b"shared bytes")
    sums = tmp_path / "SHA256SUMS"
    sums.write_text("".join(f"{client_release.digest(path)}  {path.name}\n" for path in (blob, executable)))
    data = json.loads(bundle.read_text())
    data["assets"] = release.inventory(tmp_path, [executable, blob, sums])
    bundle.write_text(json.dumps(data))
    calls = mock_github(monkeypatch)
    original = release.github_assets
    pool_assets = [remote({"name": blob.name, "size": blob.stat().st_size, "sha256": client_release.digest(blob)})]
    monkeypatch.setattr(shared, "ensure", lambda sha: POOL)
    monkeypatch.setattr(release, "github_assets", lambda id: pool_assets if id == 777 else original(id))
    monkeypatch.setattr(release.urllib.request, "urlopen", lambda *args, **kwargs: pytest.fail("Unchanged shared bytes must not upload"))
    release.upload(bundle)
    assert all(blob.name not in str(call) for call in calls)
    assert {a["name"] for a in original(123)} == {executable.name, "SHA256SUMS"}


@pytest.mark.parametrize("corrupt", [False, True])
def test_publication_cleanup_verifies_reused_files_before_deleting_any_build(tmp_path, monkeypatch, corrupt):
    from test_prune_published_release import context
    import prune_published_release as prune
    current, old, pending, calls = context(monkeypatch)
    assets = release.github_assets(current["id"])
    filename = shared.name("d" * 64)
    contents = "".join(a["digest"].removeprefix("sha256:") + "  " + a["name"] + "\n" for a in assets if a["name"] != "SHA256SUMS")
    contents += "d" * 64 + "  " + filename + "\n"
    for asset in assets:
        if asset["name"] == "SHA256SUMS":
            asset.update(size=len(contents), digest="sha256:" + hashlib.sha256(contents.encode()).hexdigest())
    pool_assets = [remote({"name": filename, "size": 10, "sha256": ("f" if corrupt else "d") * 64})]
    previous = release.gh

    def gh(*args):
        result = previous(*args)
        if args[:2] == ("release", "download"):
            (Path(args[-1]) / "SHA256SUMS").write_bytes(contents.encode("ascii"))
        return result

    monkeypatch.setattr(release, "gh", gh)
    monkeypatch.setattr(release, "github_assets", lambda id: pool_assets if id == 777 else assets)
    monkeypatch.setattr(shared, "ensure", lambda: POOL)
    if corrupt:
        with pytest.raises(ValueError, match="checksum"):
            prune.prune(current["tag_name"])
        assert not any(c[:2] == ("release", "delete") or c[:3] == ("api", "--method", "DELETE") for c in calls)
    else:
        assert prune.prune(current["tag_name"]) == [old["tag_name"]]
