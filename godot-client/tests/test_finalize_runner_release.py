"""Finalize small receipts without trusting incomplete or mismatched cloud assets."""
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_release as release
import finalize_runner_release as runner
import full_optimization_package as optimization

SHA = "a" * 40


def optimization_proof(platform):
    return {"policy": optimization.POLICY, "status": "verified_before_signing", "commit": SHA,
            "platform": platform, "features": optimization.FEATURES,
            "receipt_sha256": "1" * 64, "native_source_digest": "2" * 64,
            "catalog_sha256": ("3" if platform == "windows" else "4") * 64,
            "coverage_sha256": "5" * 64, "entries": 6}


def fixture(tmp_path, monkeypatch, *, corrupt=False):
    receipts, assets = [], []
    for platform in ("windows", "linux"):
        stage = f"RabbitLands-{platform.title()}-20261017-{SHA[:9]}"
        suffixes = [f"-{platform}.json", ".update.zip.001"]
        suffixes.extend(["-setup.exe"] if platform == "windows" else ["-download.sh", ".tar.gz.001"])
        rows = [{"name": stage + suffix, "size": 10, "sha256": "b" * 64} for suffix in suffixes]
        path = tmp_path / f"{platform}.json"
        path.write_text(json.dumps({"schema": 1, "repository": release.REPOSITORY, "commit": SHA,
            "platform": platform, "release_id": 123, "stage": stage, "assets": rows,
            "optimizations": optimization_proof(platform)}))
        receipts.append(path)
        assets.extend({"id": len(assets) + index + 1, "name": row["name"], "state": "uploaded",
                       "size": row["size"], "digest": "sha256:" + row["sha256"]} for index, row in enumerate(rows))
    if corrupt:
        assets[-1]["digest"] = "sha256:" + "c" * 64
    assets.append({"id": 99, "name": "previous-build.zip", "size": 10})
    calls = []
    draft = {"id": 123, "tag_name": "client-" + "d" * 40, "draft": True,
             "author": {"login": "rabbitlandsgame"}, "html_url": "https://example.invalid/draft"}
    def gh(*args):
        calls.append(args)
        if args[-1] == ".sha":
            return SHA
        if args[:3] == ("api", "--method", "DELETE"):
            asset_id = int(args[3].rsplit("/", 1)[1])
            assets[:] = [asset for asset in assets if asset["id"] != asset_id]
            return ""
        if "matching-refs" in args[1]:
            return "[]"
        if args[0] == "api":
            return json.dumps(draft)
        return ""
    def upload(tag, release_id, path, row, old):
        calls.append(("upload", path.name))
        assert row["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assets.append({"id": 100, "name": path.name, "state": "uploaded",
                       "size": row["size"], "digest": "sha256:" + row["sha256"]})
    monkeypatch.setattr(runner, "authorize", lambda: None)
    monkeypatch.setattr(release, "gh", gh)
    monkeypatch.setattr(release, "github_assets", lambda release_id: list(assets))
    monkeypatch.setattr(release, "github_releases", lambda: [draft])
    monkeypatch.setattr(release, "upload_asset", upload)
    return receipts, assets, calls


def test_finalizer_verifies_every_part_before_retagging_or_pruning(tmp_path, monkeypatch):
    receipts, assets, calls = fixture(tmp_path, monkeypatch)
    url = runner.finalize(receipts, tmp_path / "final")
    assert url == "https://example.invalid/draft"
    assert all(asset["name"] != "previous-build.zip" for asset in assets)
    upload = next(index for index, call in enumerate(calls) if call[0] == "upload")
    retag = next(index for index, call in enumerate(calls) if call[:2] == ("release", "edit"))
    prune = next(index for index, call in enumerate(calls) if call[:3] == ("api", "--method", "DELETE"))
    assert upload < retag < prune
    assert "--draft" in calls[retag] and not any("--draft=false" in call for call in calls)
    assert len((tmp_path / "final/SHA256SUMS").read_text().splitlines()) == 7
    verified = json.loads((tmp_path / "final/runner-release.json").read_text())
    assert verified["repository"] == release.REPOSITORY and verified["commit"] == SHA
    notes = (tmp_path / "final/RELEASE-NOTES.md").read_text()
    assert f"`RabbitLands-Windows-20261017-{SHA[:9]}-setup.exe`, from **Assets** below" in notes
    assert f"`RabbitLands-Linux-20261017-{SHA[:9]}-download.sh`, from **Assets** below" in notes
    # Draft assets use GitHub's temporary URL; the future published tag 404s.
    # The built-in Assets links remain correct after publication and retagging.
    assert f"/releases/download/client-{SHA}/" not in notes


def test_bad_cloud_digest_preserves_previous_files_and_tag(tmp_path, monkeypatch):
    receipts, assets, calls = fixture(tmp_path, monkeypatch, corrupt=True)
    with pytest.raises(ValueError, match="checksum"):
        runner.finalize(receipts, tmp_path / "final")
    assert any(asset["name"] == "previous-build.zip" for asset in assets)
    assert not any(call[:2] == ("release", "edit") or call[:3] == ("api", "--method", "DELETE") for call in calls)


def test_finalizing_a_draft_keeps_the_working_published_release(tmp_path, monkeypatch):
    receipts, assets, calls = fixture(tmp_path, monkeypatch)
    old = {"id": 99, "tag_name": "client-" + "f" * 40, "draft": False}
    monkeypatch.setattr(release, "github_releases", lambda: [old])
    runner.finalize(receipts, tmp_path / "final")
    assert not any(call[:2] == ("release", "delete") for call in calls)


def test_different_platform_commits_cannot_be_finalized(tmp_path, monkeypatch):
    receipts, assets, calls = fixture(tmp_path, monkeypatch)
    data = json.loads(receipts[1].read_text())
    data["commit"] = "e" * 40
    receipts[1].write_text(json.dumps(data))
    with pytest.raises(ValueError, match="same release"):
        runner.finalize(receipts, tmp_path / "final")
    assert calls == []


@pytest.mark.parametrize("problem", ["missing", "unverified", "wrong-platform", "source-mismatch", "coverage-mismatch"])
def test_invalid_optimization_proofs_stop_before_any_cloud_write(tmp_path, monkeypatch, problem):
    receipts, _, calls = fixture(tmp_path, monkeypatch)
    value = json.loads(receipts[1].read_text())
    if problem == "missing":
        value.pop("optimizations")
    elif problem == "unverified":
        value["optimizations"]["status"] = "pending"
    elif problem == "wrong-platform":
        value["optimizations"]["platform"] = "windows"
    else:
        field = "native_source_digest" if problem == "source-mismatch" else "coverage_sha256"
        value["optimizations"][field] = "f" * 64
    receipts[1].write_text(json.dumps(value))
    with pytest.raises(ValueError):
        runner.finalize(receipts, tmp_path / "final")
    assert calls == []


@pytest.mark.parametrize("missing_helper", [False, True])
def test_package_release_requires_both_bootstraps_and_latest_aliases(tmp_path, monkeypatch, missing_helper):
    receipts, assets, calls = fixture(tmp_path, monkeypatch)
    for path in receipts:
        item = json.loads(path.read_text())
        stage, platform = item["stage"], item["platform"]
        extension = "exe" if platform == "windows" else "x86_64"
        assets[:] = [a for a in assets if a["name"] != f"{stage}.update.zip.001"]
        item["assets"] = [a for a in item["assets"] if not a["name"].endswith(".update.zip.001")]
        item["update_schema"] = 2
        names = [f"{stage}.pkg.client.zip.001", f"{stage}.pkg.engine.zip.001", f"RabbitLands-{platform}.json",
                 f"{stage}-updater.{extension}", f"{stage}-uninstall.{extension}"]
        if missing_helper and platform == "windows":
            names.remove(f"{stage}-uninstall.exe")
        for name in names:
            item["assets"].append({"name": name, "size": 10, "sha256": "b" * 64})
            assets.append({"id": 1000 + len(assets), "name": name, "state": "uploaded", "size": 10, "digest": "sha256:" + "b" * 64})
        path.write_text(json.dumps(item))
    if missing_helper:
        with pytest.raises(ValueError, match="missing required"):
            runner.finalize(receipts, tmp_path / "final")
        assert calls == []
    else:
        runner.finalize(receipts, tmp_path / "final")
        assert all(a["name"] != "previous-build.zip" for a in assets)
