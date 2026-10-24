"""Exercise storage bounds, archive compatibility, and failure-safe part disposal."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import zipfile
import subprocess

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import client_release
import package_client as package
import release_storage as storage
from runner_release import RunnerStorage, GitHubSink


def collector(root, buffers, limit):
    def accept(path, row):
        current = list(root.glob("archive*.*[0-9]"))
        assert current == [path]
        data = path.read_bytes()
        assert len(data) == row["size"] <= limit
        assert hashlib.sha256(data).hexdigest() == row["sha256"]
        buffers.append(data)
    return accept


def test_streamed_zip_reassembles_and_retains_only_one_part(tmp_path):
    stage = tmp_path / "game"
    (stage / "app").mkdir(parents=True)
    (stage / "eloria-assets").mkdir()
    contents = os.urandom(100_000)
    (stage / "app/game.pck").write_bytes(contents)
    (stage / "eloria-assets/map.json").write_text("{}")
    buffers = []
    path = tmp_path / "archive.update.zip"
    with storage.PartWriter(path, "https://example.invalid/releases", 4096,
                            collector(tmp_path, buffers, 4096)) as writer:
        count, unpacked = client_release.build_payload(stage, writer)
    data = b"".join(buffers)
    assert count == 2 and unpacked == len(contents) + 2
    assert writer.size == len(data) and writer.sha256 == hashlib.sha256(data).hexdigest()
    assert not path.exists() and not list(tmp_path.glob("archive.update.zip.*"))
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.testzip() is None
        assert archive.read("files/000000/000000") == contents
        assert archive.getinfo("files/000000/000000").flag_bits & 8  # ZIP data descriptor
        assert len(json.loads(archive.read("inventory.json"))) == 2


def test_unacknowledged_part_survives_and_no_further_parts_are_created(tmp_path):
    def reject(path, row):
        raise RuntimeError("Remote checksum did not match")
    writer = storage.PartWriter(tmp_path / "archive", "", 4, reject)
    with pytest.raises(RuntimeError, match="checksum"):
        with writer:
            writer.write(b"abcdefgh")
    assert (tmp_path / "archive.001").read_bytes() == b"abcd"
    assert not (tmp_path / "archive.002").exists()
    assert writer.parts == []


def test_failed_compressor_does_not_acknowledge_its_partial_archive(tmp_path):
    calls = []
    with pytest.raises(RuntimeError):
        with storage.PartWriter(tmp_path / "archive", "", 100, lambda *args: calls.append(args)) as writer:
            writer.write(b"incomplete")
            raise RuntimeError("compression failed")
    assert calls == [] and (tmp_path / "archive.001").exists()


def test_tar_stream_keeps_modes_and_contains_real_files_for_hard_links(tmp_path, monkeypatch):
    stage = tmp_path / "game"
    (stage / "app").mkdir(parents=True)
    (stage / package.MARKER).write_text("a" * 40)
    (stage / "RabbitLands.sh").write_text("#!/bin/sh\n")
    binary = stage / "app/RabbitLands.x86_64"
    binary.write_bytes(os.urandom(10_000))
    storage.link_file(binary, stage / "app/identical.data")
    monkeypatch.setattr(client_release, "PART_BYTES", 2048)
    buffers = []
    def accept(path, row):
        buffers.append(path.read_bytes())
        assert len(list(tmp_path.glob("*.tar.gz.*"))) == 1
    result = package.make_tarball_parts(stage, package.PLATFORMS["linux"], "", accept, None)
    data = b"".join(buffers)
    assert result["size"] == len(data) and result["sha256"] == hashlib.sha256(data).hexdigest()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        assert not any(member.islnk() or member.issym() for member in archive.getmembers())
        assert not any(member.name.endswith(package.MARKER) for member in archive.getmembers())
        assert archive.getmember("game/RabbitLands.sh").mode == 0o755
        assert archive.getmember("game/app/RabbitLands.x86_64").mode == 0o755
        assert archive.getmember("game/app/identical.data").mode == 0o644
        assert archive.extractfile("game/app/identical.data").read() == binary.read_bytes()
    assert not list(tmp_path.glob("*.tar.gz*"))


def test_budget_counts_linked_assets_once_and_preserves_margin(tmp_path, monkeypatch):
    source, stage = tmp_path / "source", tmp_path / "stage"
    source.mkdir(); stage.mkdir()
    (source / "asset").write_bytes(bytes(128))
    storage.link_file(source / "asset", stage / "asset")
    assert storage.unique_bytes([source, stage, source, source / "asset"]) == 128
    budget = storage.DiskBudget([source, stage], capacity=256, reserve=64)
    budget.check("staged", additional=64)
    assert budget.peak == 128 and budget.planned_peak == 192
    with pytest.raises(ValueError, match="margin"):
        budget.check("too large", additional=65)
    monkeypatch.setattr(storage.shutil, "disk_usage", lambda path: type("Usage", (), {"free": 63})())
    with pytest.raises(ValueError, match="reserve"):
        budget.free_check()


def test_live_resource_rename_rescans_directory_and_counts_final_file(tmp_path, monkeypatch):
    staging, final = tmp_path / "writing-000952.res", tmp_path / "digest.res"
    staging.write_bytes(bytes(256))
    original = Path.lstat
    moved = []

    def rename_before_stat(path, *args, **kwargs):
        if path == staging and not moved:
            staging.rename(final)
            moved.append(True)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", rename_before_stat)
    assert storage.unique_bytes([tmp_path]) == 256
    assert moved and final.is_file() and not staging.exists()


@pytest.mark.parametrize("replace", [False, True])
def test_directory_retry_accounts_observed_same_name_growth_or_replacement(tmp_path, monkeypatch, replace):
    stable = tmp_path / "a-stable.res"
    stable.write_bytes(bytes(64))
    staging, final = tmp_path / "writing-000952.res", tmp_path / "digest.res"
    staging.write_bytes(bytes(128))
    original_stat, original_walk = Path.lstat, storage.os.walk
    moved = []

    def sorted_walk(*args, **kwargs):
        for directory, folders, files in original_walk(*args, **kwargs):
            yield directory, folders, sorted(files)

    def publish_and_grow(path, *args, **kwargs):
        if path == staging and not moved:
            staging.rename(final)
            if replace:
                replacement = tmp_path / "replacement.res"
                replacement.write_bytes(bytes(1024))
                replacement.replace(stable)
            else:
                stable.write_bytes(bytes(1024))
            moved.append(True)
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(storage.os, "walk", sorted_walk)
    monkeypatch.setattr(Path, "lstat", publish_and_grow)
    budget = storage.DiskBudget([tmp_path], capacity=1000, reserve=64)
    with pytest.raises(ValueError, match="margin"):
        budget.check("live growth must remain accounted")
    assert budget.peak == 1152 + (64 if replace else 0)
    assert storage.unique_bytes([tmp_path]) == 1152  # Fresh idle inventory.


def test_rename_retry_discovers_new_nested_directory_and_deduplicates_links(tmp_path, monkeypatch):
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested/keep.res").write_bytes(bytes(64))
    staging, final = tmp_path / "writing-000952.res", tmp_path / "digest.res"
    staging.write_bytes(bytes(128))
    original = Path.lstat
    moved = []

    def publish_with_new_directory(path, *args, **kwargs):
        if path == staging and not moved:
            staging.rename(final)
            nested = tmp_path / "new-nested"
            nested.mkdir()
            os.link(final, nested / "alias.res")
            (nested / "new.res").write_bytes(bytes(256))
            moved.append(True)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", publish_with_new_directory)
    assert storage.unique_bytes([tmp_path]) == 448
    assert moved


def test_inventory_retry_preserves_inode_dedup_and_keeps_budget_enforcement(tmp_path, monkeypatch):
    staging, final, alias = tmp_path / "writing-000952.res", tmp_path / "digest.res", tmp_path / "a-alias.res"
    staging.write_bytes(bytes(256))
    os.link(staging, alias)
    original_stat, original_walk = Path.lstat, storage.os.walk
    moved, scans = [], []

    def sorted_walk(*args, **kwargs):
        scans.append(True)
        for directory, folders, files in original_walk(*args, **kwargs):
            yield directory, folders, sorted(files)

    def rename_before_stat(path, *args, **kwargs):
        if path == staging and not moved:
            staging.rename(final)
            moved.append(True)
        return original_stat(path, *args, **kwargs)

    budget = storage.DiskBudget([tmp_path], capacity=384, reserve=64)
    monkeypatch.setattr(storage.os, "walk", sorted_walk)
    monkeypatch.setattr(Path, "lstat", rename_before_stat)
    budget.check("live rename", additional=64)
    assert len(scans) == 1  # Retry the affected directory, not all accounted roots.
    assert budget.peak == 256 and budget.planned_peak == 320
    with pytest.raises(ValueError, match="margin"):
        budget.check("still enforced", additional=65)
    monkeypatch.setattr(storage.shutil, "disk_usage", lambda path: type("Usage", (), {"free": 63})())
    with pytest.raises(ValueError, match="reserve"):
        budget.check("physical reserve still enforced")


def test_removed_duplicate_staging_resource_is_absent_after_retry(tmp_path, monkeypatch):
    staging = tmp_path / "writing-000952.res"
    staging.write_bytes(bytes(256))
    (tmp_path / "digest.res").write_bytes(bytes(256))
    original = Path.lstat
    removed = []

    def remove_before_stat(path, *args, **kwargs):
        if path == staging and not removed:
            staging.unlink()
            removed.append(True)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", remove_before_stat)
    assert storage.unique_bytes([tmp_path]) == 256
    assert removed


def test_inventory_churn_is_bounded_and_permissions_still_fail(tmp_path, monkeypatch):
    staging = tmp_path / "writing-000952.res"
    staging.write_bytes(bytes(256))
    original = Path.lstat
    for exception in (FileNotFoundError, PermissionError, OSError):
        calls = []

        def fail_stat(path, *args, **kwargs):
            if path == staging:
                calls.append(True)
                raise exception("fixture storage change")
            return original(path, *args, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(Path, "lstat", fail_stat)
            if exception is FileNotFoundError:
                with pytest.raises(ValueError, match="cannot verify disk budget"):
                    storage.unique_bytes([tmp_path])
                assert len(calls) == storage.INVENTORY_ATTEMPTS
            else:
                with pytest.raises(exception, match="fixture storage change"):
                    storage.unique_bytes([tmp_path])
                assert len(calls) == 1


def test_missing_required_inventory_root_is_never_a_transient_entry(tmp_path):
    with pytest.raises(FileNotFoundError):
        storage.unique_bytes([tmp_path / "missing-required-root"])


def test_several_transient_entry_races_can_settle_within_bounded_inventory_attempts(tmp_path, monkeypatch):
    staging = tmp_path / "writing-000952.res"
    staging.write_bytes(bytes(256))
    original = Path.lstat
    calls = []

    def initially_changing(path, *args, **kwargs):
        if path == staging:
            calls.append(True)
            if len(calls) < storage.INVENTORY_ATTEMPTS:
                raise FileNotFoundError("fixture concurrent resource publication")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", initially_changing)
    assert storage.unique_bytes([tmp_path]) == 256
    assert len(calls) == storage.INVENTORY_ATTEMPTS


@pytest.mark.parametrize("error", [PermissionError(13, "fixture inaccessible directory"),
                                 OSError(5, "fixture directory IO failure")])
def test_unreadable_directory_enumeration_is_never_silently_omitted(tmp_path, monkeypatch, error):
    blocked = tmp_path / "unreadable"
    blocked.mkdir()
    (blocked / "asset.res").write_bytes(bytes(256))
    original = storage.os.scandir

    def fail_enumeration(path):
        if Path(path) == blocked:
            raise error
        return original(path)

    monkeypatch.setattr(storage.os, "scandir", fail_enumeration)
    with pytest.raises(type(error), match="fixture"):
        storage.unique_bytes([tmp_path])


def test_required_inventory_root_disappearing_during_walk_still_fails(tmp_path, monkeypatch):
    root = tmp_path / "required-root"
    root.mkdir()
    original = storage.os.walk
    scans = []

    def remove_root_during_walk(*args, **kwargs):
        scans.append(True)
        for entry in original(*args, **kwargs):
            root.rmdir()
            yield entry

    monkeypatch.setattr(storage.os, "walk", remove_root_during_walk)
    with pytest.raises(FileNotFoundError):
        storage.unique_bytes([root])
    assert len(scans) == 1


def test_inventory_still_rejects_a_link_after_transient_rename(tmp_path, monkeypatch):
    staging, final = tmp_path / "writing-000952.res", tmp_path / "digest.res"
    staging.write_bytes(bytes(256))
    original = Path.lstat
    moved = []

    def rename_then_observe_link(path, *args, **kwargs):
        if path == staging and not moved:
            staging.rename(final)
            moved.append(True)
        if path == final:
            # Exercise the link policy without requiring Windows symlink privileges.
            return type("LinkStat", (), {"st_mode": 0o120777})()
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", rename_then_observe_link)
    with pytest.raises(ValueError, match="link escapes"):
        storage.unique_bytes([tmp_path])
    assert moved


def test_hard_link_failure_has_no_silent_copy_fallback(tmp_path, monkeypatch):
    source = tmp_path / "original"
    source.write_bytes(b"asset")
    monkeypatch.setattr(storage.os, "link", lambda *args: (_ for _ in ()).throw(OSError("another filesystem")))
    with pytest.raises(OSError):
        storage.link_file(source, tmp_path / "copy")
    assert not (tmp_path / "copy").exists()


def test_cleanup_cannot_touch_an_unowned_cache(tmp_path):
    outside = tmp_path / "user-cache"
    outside.mkdir()
    (outside / "keep").write_text("user data")
    root = tmp_path / "owned"
    root.mkdir()
    runner = RunnerStorage(root, storage.DiskBudget([root]), None)
    with pytest.raises(ValueError, match="Refusing"):
        runner.clear_cache(outside)
    assert (outside / "keep").read_text() == "user data"


def test_editor_sources_are_removed_only_after_reference_proof(tmp_path, monkeypatch):
    root = tmp_path / "owned"
    project = root / "source/godot-client"
    authoring = project / "world_authoring"
    authoring.mkdir(parents=True)
    (authoring / "editor-model.glb").write_bytes(b"editor-only geometry")
    runner = RunnerStorage(root, storage.DiskBudget([root]), None)
    with pytest.raises(ValueError, match="reference proof"):
        runner.retire_editor_sources(project)
    assert (authoring / "editor-model.glb").exists()
    calls = []
    proof = {"loose": {"kept-because-editor-names-it.png"}}
    monkeypatch.setattr(package, "_actor_shipping", lambda path: calls.append(path) or proof)
    monkeypatch.setattr(package, "STORAGE", runner)
    assert package.actor_shipping(project.parent) is proof
    runner.retire_editor_sources(project)
    assert not (authoring / "editor-model.glb").exists() and (authoring / ".gdignore").exists()
    assert package.actor_shipping(project.parent) is proof
    assert calls == [project.parent]


def test_sink_requires_github_recorded_digest_before_disposal(tmp_path, monkeypatch):
    import runner_release
    import build_release
    monkeypatch.setattr(runner_release, "authorize", lambda: None)
    draft = {"draft": True, "author": {"login": "rabbitlandsgame"}, "tag_name": "current"}
    monkeypatch.setattr(build_release, "gh", lambda *args: json.dumps(draft))
    monkeypatch.setattr(build_release, "github_assets", lambda release_id: [])
    monkeypatch.setattr(build_release, "upload_asset_api", lambda *args: {})
    path = tmp_path / "part"
    path.write_bytes(b"part")
    row = {"name": "part", "size": 4, "sha256": client_release.digest(path)}
    sink = GitHubSink(1)
    with pytest.raises(ValueError, match="retaining"):
        sink.accept(path, row)
    assert path.read_bytes() == b"part"


def test_direct_upload_streams_once_and_checks_github_digest(tmp_path, monkeypatch):
    import build_release
    import io
    from contextlib import contextmanager
    path = tmp_path / "package.zip.001"
    path.write_bytes(b"package bytes" * 1024)
    row = {"size": path.stat().st_size, "sha256": client_release.digest(path)}
    calls = []
    monkeypatch.setenv("GH_TOKEN", "test-only-token")
    monkeypatch.setattr(build_release, "github_assets", lambda _: pytest.fail("No per-upload release listing is needed."))

    @contextmanager
    def upload(request, timeout):
        calls.append(request.full_url)
        assert request.full_url == "https://uploads.github.com/repos/rabbitlandsgame/rabbitlands-client/releases/123/assets?name=package.zip.001"
        assert int(request.get_header("Content-length")) == row["size"]
        assert hasattr(request.data, "read") and request.data.read() == path.read_bytes()
        yield io.BytesIO(json.dumps({"id": 42, "name": path.name, "state": "uploaded",
                                    "size": row["size"], "digest": "sha256:" + row["sha256"]}).encode())

    monkeypatch.setattr(build_release.urllib.request, "urlopen", upload)
    assert build_release.upload_asset_api(123, path, row, {})["id"] == 42
    assert len(calls) == 1 and path.is_file()


def test_direct_upload_recovers_acknowledgement_lost_after_github_stored_bytes(tmp_path, monkeypatch):
    import build_release
    path = tmp_path / "package.zip.001"
    path.write_bytes(b"package")
    row = {"size": path.stat().st_size, "sha256": client_release.digest(path)}
    actual = {"id": 42, "name": path.name, "state": "uploaded", "size": row["size"], "digest": "sha256:" + row["sha256"]}
    monkeypatch.setenv("GH_TOKEN", "test-only-token")
    monkeypatch.setattr(build_release.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(build_release.urllib.error.URLError("connection lost")))
    monkeypatch.setattr(build_release, "github_assets", lambda _: [actual])
    assert build_release.upload_asset_api(123, path, row, {}) == actual
    assert path.is_file()


def test_disposable_worktree_cleanup_handles_long_windows_paths(tmp_path, monkeypatch):
    repo, root = tmp_path / "repo", tmp_path / "owned"
    root.mkdir()
    worktree = root / "source"
    repo.mkdir()
    def git(*args):
        return subprocess.check_output(["git", "-c", "core.longpaths=true", *args], cwd=repo, stderr=subprocess.STDOUT)
    git("init", "-b", "master")
    git("config", "user.name", "Runner storage test")
    git("config", "user.email", "storage@example.invalid")
    asset = repo / ("x" * 100) / ("y" * 100) / "asset.txt"
    asset.parent.mkdir(parents=True)
    asset.write_text("long-path fixture")
    git("add", ".")
    git("commit", "-m", "fixture")
    git("worktree", "add", "--detach", str(worktree), "HEAD")
    assert (worktree / asset.relative_to(repo)).read_text() == "long-path fixture"
    sha = git("rev-parse", "HEAD").decode().strip()
    (root / ".runner-release.json").write_text(json.dumps({"repository": "rabbitlandsgame/rabbitlands-client", "commit": sha}))
    stage = root / "downloads/game"
    stage.mkdir(parents=True)
    (stage / package.MARKER).write_text(sha)
    logs = root / "downloads/.build/logs/test"
    (logs / "installer-project").mkdir(parents=True)
    (logs / "updater-project").mkdir()
    (logs / "RabbitLands-install-fixture.exe").write_bytes(b"generated helper")
    (logs / "smoke.log").write_text("startup passed")
    real_git = package.git
    monkeypatch.setattr(package, "git", lambda *args, **kwargs: real_git(*args, cwd=repo, **kwargs))
    RunnerStorage(root, storage.DiskBudget([root, repo]), None).cleanup(stage, sha)
    assert not worktree.exists()
    assert not stage.exists()
    assert (logs / "smoke.log").exists()
    assert not (logs / "installer-project").exists() and not list(logs.glob("*.exe"))
