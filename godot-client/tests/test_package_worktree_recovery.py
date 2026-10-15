"""Real Git regressions for orphaned persistent package worktrees."""
import subprocess
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import package_client as package


def make_repo(path):
    path.mkdir()
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=path, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    git("init", "-b", "develop")
    git("config", "user.name", "Package recovery test")
    git("config", "user.email", "recovery@example.invalid")
    (path / "tracked.txt").write_text("current commit")
    (path / ".gitignore").write_text(".godot/\n*.import\n")
    git("add", ".")
    git("commit", "-m", "fixture")
    return git, git("rev-parse", "HEAD")


def test_orphaned_cache_is_registered_to_the_current_repository(tmp_path, monkeypatch):
    repo = tmp_path / "source"
    git, sha = make_repo(repo)
    monkeypatch.setattr(package, "REPO", repo)
    real_git = package.git
    monkeypatch.setattr(package, "git", lambda *args, cwd=repo, **kw: real_git(*args, cwd=cwd, **kw))
    build = tmp_path / "cached-build"
    build.mkdir()
    (build / ".git").write_text(f"gitdir: {tmp_path / 'old-source/.git/worktrees/client-src'}\n")
    if os.name == "nt":
        import ctypes
        assert ctypes.windll.kernel32.SetFileAttributesW(str(build / ".git"), 2)
    (build / "tracked.txt").write_text("previous build")
    (build / ".godot").mkdir()
    (build / ".godot/import-cache.bin").write_bytes(b"expensive import")
    (build / "texture.png.import").write_text("cached import settings")
    package.recover_build_worktree(build, sha)
    assert Path(real_git("rev-parse", "--show-toplevel", cwd=build).strip()).resolve() == build.resolve()
    assert Path(real_git("rev-parse", "--git-common-dir", cwd=build).strip()).resolve() == (repo / ".git").resolve()
    assert (build / "tracked.txt").read_text() == "previous build"
    real_git("checkout", "--detach", "--force", sha, cwd=build)
    real_git("clean", "-ffd", "-q", cwd=build)
    assert (build / "tracked.txt").read_text() == "current commit"
    assert (build / ".godot/import-cache.bin").read_bytes() == b"expensive import"
    assert (build / "texture.png.import").read_text() == "cached import settings"
    assert not list(tmp_path.glob("client-src-registration-*"))
    assert str(build).replace("\\", "/") in git("worktree", "list", "--porcelain")


def test_failed_registration_restores_the_original_git_link(tmp_path, monkeypatch):
    repo = tmp_path / "source"
    _, sha = make_repo(repo)
    monkeypatch.setattr(package, "REPO", repo)
    build = tmp_path / "cached-build"
    build.mkdir()
    original = b"gitdir: missing-repository/worktrees/client-src\n"
    (build / ".git").write_bytes(original)
    (build / "keep.txt").write_text("keep")
    def fail(*_args, **_kwargs):
        raise package.PackageError("registration failed")
    monkeypatch.setattr(package, "git", fail)
    with pytest.raises(package.PackageError, match="registration failed"):
        package.recover_build_worktree(build, sha)
    assert (build / ".git").read_bytes() == original
    assert (build / "keep.txt").read_text() == "keep"


def test_the_source_checkout_cannot_be_used_as_a_build(tmp_path, monkeypatch):
    monkeypatch.setattr(package, "REPO", tmp_path)
    with pytest.raises(package.PackageError, match="source checkout"):
        package.prepare_build_tree(tmp_path, "a" * 40)
