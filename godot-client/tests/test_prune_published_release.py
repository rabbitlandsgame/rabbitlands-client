"""A replacement draft must not interrupt the working public installers."""
import hashlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import prune_published_release as prune


def context(monkeypatch, *, latest=True, corrupt=False):
    current = {"id": 20, "tag_name": "client-" + "a" * 40, "draft": False,
               "author": {"login": "rabbitlandsgame"}, "published_at": "2026-10-17T12:00:00Z"}
    old = {"id": 10, "tag_name": "client-" + "b" * 40, "draft": False, "published_at": "2026-10-16T12:00:00Z"}
    pending = {"id": 30, "tag_name": "client-" + "c" * 40, "draft": True}
    names = ["build-setup.exe", "build-download.sh", "build-windows.json", "build-linux.json", "build.update.zip.001"]
    sums = "".join("b" * 64 + "  " + name + "\n" for name in names).encode("ascii")
    assets = [{"name": name, "state": "uploaded", "digest": "sha256:" + "b" * 64, "size": 10} for name in names]
    assets.append({"name": "SHA256SUMS", "state": "uploaded", "size": len(sums), "digest": "sha256:" + hashlib.sha256(sums).hexdigest()})
    if corrupt:
        assets[0]["digest"] = "sha256:" + "f" * 64
    calls = []
    def gh(*args):
        calls.append(args)
        if args[-1] == ".id":
            return "20" if latest else "99"
        if args[:2] == ("release", "download"):
            (Path(args[-1]) / "SHA256SUMS").write_bytes(sums)
        return ""
    monkeypatch.setattr(prune, "authorize", lambda: None)
    monkeypatch.setattr(prune.release, "gh", gh)
    monkeypatch.setattr(prune.release, "github_release", lambda tag: current)
    monkeypatch.setattr(prune.release, "github_releases", lambda: [current, old, pending])
    monkeypatch.setattr(prune.release, "github_assets", lambda id: assets)
    return current, old, pending, calls


def test_only_verified_latest_publication_retires_older_downloads(monkeypatch):
    current, old, pending, calls = context(monkeypatch)
    assert prune.prune(current["tag_name"]) == [old["tag_name"]]
    deletion = next(call for call in calls if call[:2] == ("release", "delete"))
    assert deletion[2] == old["tag_name"] and all(pending["tag_name"] not in call for call in calls)


@pytest.mark.parametrize("problem", ["draft", "not-latest", "corrupt"])
def test_unverified_publication_never_removes_any_release(monkeypatch, problem):
    current, _, _, calls = context(monkeypatch, latest=problem != "not-latest", corrupt=problem == "corrupt")
    if problem == "draft":
        current["draft"] = True
    with pytest.raises(ValueError):
        prune.prune(current["tag_name"])
    assert not any(call[:2] == ("release", "delete") for call in calls)
