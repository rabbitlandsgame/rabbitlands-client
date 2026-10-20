"""Source streaming must preserve committed inputs without hydrating Git blobs."""
import io
import os
from pathlib import Path
import subprocess
import sys
import tarfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import runner_source
from release_storage import DiskBudget


def git_at(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True, encoding="utf-8")


@pytest.fixture
def source(tmp_path):
    origin = tmp_path / "origin"
    origin.mkdir()
    git_at(origin, "init", "-q")
    git_at(origin, "config", "core.autocrlf", "false")
    git_at(origin, "config", "uploadpack.allowFilter", "true")
    files = {"README.md": b"committed root\n", "eloria-assets/NOTICE": b"root notice\n",
             "godot-client/project.godot": b"config_version=5\n",
             "godot-client/assets/model.glb": b"binary\x00\r\n" * 1000,
             "godot-client/run.sh": b"#!/bin/sh\necho test\n",
             "eloria-assets/maps/example/world.json": b'{"map":"example"}\n',
             "eloria-assets/source/private-to-the-build.txt": b"not a runtime input\n"}
    for name, data in files.items():
        target = origin / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    git_at(origin, "add", "--", ".")
    git_at(origin, "update-index", "--chmod=+x", "godot-client/run.sh")
    git_at(origin, "-c", "user.name=Release Test", "-c", "user.email=test@example.invalid",
           "commit", "-qm", "fixture")
    sha = git_at(origin, "rev-parse", "HEAD").strip()
    data = subprocess.check_output(["git", "-C", str(origin), "archive", "--format=tar.gz",
                                    "--prefix=source/", sha])
    clone = tmp_path / "partial"
    subprocess.run(["git", "clone", "-q", "--filter=blob:none", "--no-checkout",
                    origin.as_uri(), str(clone)], check=True)
    root = tmp_path / "build"
    git_at(clone, "worktree", "add", "--detach", "--no-checkout", str(root), sha)
    return clone, root, sha, data, files


class Storage:
    def __init__(self, clone, root, **kwargs):
        self.budget = DiskBudget([clone / ".git", root], **kwargs)

    def check(self, *args):
        self.budget.check(*args)


def materialize(source, monkeypatch, data=None, **budget):
    clone, root, sha, archive, files = source
    monkeypatch.setattr(runner_source, "urlopen", lambda url, timeout: io.BytesIO(archive if data is None else data))
    runner_source.materialize(root, sha, lambda *args, cwd: git_at(cwd, *args), Storage(clone, root, **budget))


def rewrite(data, change):
    out = io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as src:
        with tarfile.open(fileobj=out, mode="w:gz") as dst:
            for item in src:
                raw = src.extractfile(item).read() if item.isfile() else None
                for member, content in change(item, raw):
                    dst.addfile(member, io.BytesIO(content) if content is not None else None)
    return out.getvalue()


def test_stream_matches_git_bytes_modes_index_and_leaves_blobs_missing(source, monkeypatch):
    clone, root, sha, data, files = source
    def local_objects():
        return git_at(clone, "cat-file", "--batch-all-objects", "--batch-check=%(objecttype) %(objectname)")
    assert "blob " not in local_objects()
    materialize(source, monkeypatch)
    assert "blob " not in local_objects()
    assert git_at(root, "rev-parse", "HEAD").strip() == sha
    assert set(git_at(root, "ls-files", "-z").split("\0")) - {""} == set(files)
    for name, data in files.items():
        if runner_source.selected(name):
            assert (root / name).read_bytes() == data
        else:
            assert not (root / name).exists()
    if os.name != "nt":
        assert (root / "godot-client/run.sh").stat().st_mode & 0o111


def test_changed_bytes_fail_git_object_verification(source, monkeypatch):
    def change(item, raw):
        if item.name.endswith("model.glb"):
            raw = b"changed" + raw[7:]
        return [(item, raw)]
    with pytest.raises(ValueError, match="differs from the committed Git blob"):
        materialize(source, monkeypatch, rewrite(source[3], change))
    assert not (source[1] / "godot-client/assets/model.glb").exists()


def test_missing_committed_inputs_fail_closed(source, monkeypatch):
    data = rewrite(source[3], lambda item, raw: [] if item.name.endswith("project.godot") else [(item, raw)])
    with pytest.raises(ValueError, match="omitted committed inputs"):
        materialize(source, monkeypatch, data)


def test_path_traversal_is_rejected_without_writing_outside_source(source, monkeypatch):
    def change(item, raw):
        if item.name.endswith("model.glb"):
            item.name = "source/../escaped.glb"
        return [(item, raw)]
    with pytest.raises(ValueError, match="unsafe path"):
        materialize(source, monkeypatch, rewrite(source[3], change))
    assert not (source[1].parent / "escaped.glb").exists()


def test_duplicate_inputs_cannot_overwrite_committed_files(source, monkeypatch):
    def change(item, raw):
        return [(item, raw), (item, raw)] if item.name.endswith("model.glb") else [(item, raw)]
    with pytest.raises(ValueError, match="duplicated source entry"):
        materialize(source, monkeypatch, rewrite(source[3], change))


def test_source_batch_reservation_preserves_margin_before_writing(source, monkeypatch):
    with pytest.raises(ValueError, match="disk budget exceeded"):
        materialize(source, monkeypatch, capacity=64 * 1024**2, reserve=2 * 1024**2)
    assert not (source[1] / "README.md").exists()
