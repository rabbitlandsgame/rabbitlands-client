"""Publication must follow both platform receipts and verified remote downloads."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import publish_runner_release as publisher
import full_optimization_package as optimization

SHA, OLD = "a" * 40, "b" * 40


def optimization_proof(platform):
    return {"policy": optimization.POLICY, "status": "verified_before_signing", "commit": SHA,
            "platform": platform, "features": optimization.FEATURES,
            "default_features": optimization.DEFAULT_FEATURES, "default_profile": "legacy", "opt_in_profile": "human-testing",
            "receipt_sha256": "1" * 64, "native_source_digest": "2" * 64,
            "catalog_sha256": ("3" if platform == "windows" else "4") * 64,
            "coverage_sha256": "5" * 64, "entries": 6,
            "ordinary_startup_sha256": "6" * 64, "opt_in_startup_sha256": "7" * 64}


def context(tmp_path, monkeypatch):
    release, shared = publisher.release, publisher.shared
    names = ["SHA256SUMS", "RabbitLands-windows.json", "RabbitLands-linux.json",
        f"RabbitLands-Windows-20261023-{SHA[:9]}-setup.exe",
        f"RabbitLands-Windows-20261023-{SHA[:9]}-windows.json",
        f"RabbitLands-Linux-20261023-{SHA[:9]}-download.sh",
        f"RabbitLands-Linux-20261023-{SHA[:9]}-linux.json"]
    def row(name):
        return {"name": name, "size": 10, "sha256": "c" * 64}
    receipt = {"schema": 1, "repository": release.REPOSITORY, "commit": SHA, "release_id": 123,
        "assets": [row(n) for n in names], "shared_release_id": 777,
        "shared_assets": [row(shared.name("c" * 64))],
        "optimizations": {platform: optimization_proof(platform) for platform in ("windows", "linux")}}
    path = tmp_path / "runner-release.json"
    path.write_text(json.dumps(receipt))
    def remote(row):
        return {"name": row["name"], "size": row["size"], "state": "uploaded", "digest": "sha256:" + row["sha256"]}
    assets = {123: [remote(r) for r in receipt["assets"]], 777: [remote(r) for r in receipt["shared_assets"]]}
    current = {"id": 123, "tag_name": "client-" + SHA, "target_commitish": SHA, "draft": True,
               "prerelease": False, "author": {"login": "github-actions[bot]"}}
    pool = {"id": 777, "tag_name": shared.TAG, "draft": False, "prerelease": True,
            "author": {"login": "github-actions[bot]"}}
    state = {"latest": {"id": 122, "tag_name": "client-" + OLD}, "cleanup_failure": False,
             "tag_commit": SHA, "latest_delay": 0, "verified": 0, "post_publish_damage": False}
    calls = []
    def gh(*args):
        calls.append(args)
        if args[:2] == ("release", "edit"):
            assert state["verified"] == 2, "Both release inventories must be checked before publication"
            assert "--draft=false" in args and "--latest" in args
            current["draft"] = False
            if state["post_publish_damage"]:
                assets[777][0]["digest"] = "sha256:" + "d" * 64
            return ""
        assert args[0] == "api"
        endpoint = args[1]
        if endpoint.endswith("/releases/123"):
            return json.dumps(current)
        if endpoint.endswith("/releases/777"):
            return json.dumps(pool)
        if endpoint.endswith("/releases/latest"):
            if not current["draft"]:
                if state["latest_delay"]:
                    state["latest_delay"] -= 1
                else:
                    state["latest"] = dict(current)
            return json.dumps(state["latest"])
        if "matching-refs" in endpoint:
            return json.dumps([{"ref": "refs/tags/client-" + SHA,
                "object": {"type": "commit", "sha": state["tag_commit"]}}])
        raise AssertionError(args)
    def inventory(id):
        state["verified"] += 1
        return assets[id]
    def cleanup(tag):
        calls.append(("cleanup", tag))
        assert not current["draft"] and state["latest"]["id"] == 123
        assert state["verified"] >= 4, "Public downloads must be verified before deleting anything"
        if state["cleanup_failure"]:
            raise ValueError("temporary GitHub failure")
        return ["client-" + OLD]
    monkeypatch.setattr(publisher.actions_release, "workflow_commit", lambda: SHA)
    monkeypatch.setattr(publisher.actions_release.runner_release, "authorize", lambda: None)
    monkeypatch.setattr(publisher.package, "git", lambda *args: SHA + "\n" + OLD)
    monkeypatch.setattr(release, "gh", gh)
    monkeypatch.setattr(release, "github_assets", inventory)
    monkeypatch.setattr(publisher.prune_published_release, "prune", cleanup)
    monkeypatch.setattr(publisher.time, "sleep", lambda _: None)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary"))
    return path, receipt, assets, current, state, calls


def test_publishes_latest_after_all_downloads_verify_then_cleans_old_releases(tmp_path, monkeypatch):
    path, _, _, current, _, calls = context(tmp_path, monkeypatch)
    assert publisher.publish(path).endswith("/client-" + SHA)
    assert not current["draft"]
    assert calls[-1] == ("cleanup", "client-" + SHA)
    assert "Published" in (tmp_path / "summary").read_text()


@pytest.mark.parametrize("problem", ["missing", "missing-linux", "unverified", "wrong-commit", "source-mismatch", "coverage-mismatch",
                                     "enabled-default", "missing-opt-in", "old-policy"])
def test_publication_requires_both_exact_optimization_proofs(tmp_path, monkeypatch, problem):
    path, receipt, _, current, _, calls = context(tmp_path, monkeypatch)
    if problem == "missing":
        receipt.pop("optimizations")
    elif problem == "missing-linux":
        receipt["optimizations"].pop("linux")
    else:
        field, value = {"unverified": ("status", "pending"), "wrong-commit": ("commit", OLD),
                        "source-mismatch": ("native_source_digest", "f" * 64),
                        "coverage-mismatch": ("coverage_sha256", "f" * 64),
                        "enabled-default": ("default_features", optimization.FEATURES),
                        "missing-opt-in": ("opt_in_startup_sha256", ""),
                        "old-policy": ("policy", "rl-full-optimization-package-v1")}[problem]
        receipt["optimizations"]["linux"][field] = value
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        publisher.publish(path)
    assert current["draft"]
    assert not calls


@pytest.mark.parametrize("problem", ["wrong-commit", "wrong-repo", "missing-linux", "duplicate", "wrong-tag",
    "wrong-target", "foreign-author", "bad-installer-digest", "missing-part", "bad-part-size", "tag-moved", "downgrade"])
def test_invalid_or_changed_build_cannot_publish_or_remove_releases(tmp_path, monkeypatch, problem):
    path, receipt, assets, current, state, calls = context(tmp_path, monkeypatch)
    if problem == "wrong-commit":
        receipt["commit"] = OLD
    elif problem == "wrong-repo":
        receipt["repository"] = "unrelated/repo"
    elif problem == "missing-linux":
        receipt["assets"] = [r for r in receipt["assets"] if not r["name"].endswith("-download.sh")]
    elif problem == "duplicate":
        receipt["assets"].append(receipt["assets"][0])
    elif problem == "wrong-tag":
        current["tag_name"] = "client-" + OLD
    elif problem == "wrong-target":
        current["target_commitish"] = OLD
    elif problem == "foreign-author":
        current["author"]["login"] = "unrelated-user"
    elif problem == "bad-installer-digest":
        assets[123][3]["digest"] = "sha256:" + "d" * 64
    elif problem == "missing-part":
        assets[777].clear()
    elif problem == "bad-part-size":
        assets[777][0]["size"] = 1
    elif problem == "tag-moved":
        state["tag_commit"] = OLD
    elif problem == "downgrade":
        monkeypatch.setattr(publisher.package, "git", lambda *args: SHA)
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        publisher.publish(path)
    assert current["draft"]
    assert not any(c[0] in ("release", "cleanup") for c in calls)


def test_latest_metadata_delay_does_not_delete_previous_release_early(tmp_path, monkeypatch):
    path, _, _, _, state, calls = context(tmp_path, monkeypatch)
    state["latest_delay"] = 2
    publisher.publish(path)
    assert state["latest_delay"] == 0 and calls[-1][0] == "cleanup"


def test_incomplete_public_verification_keeps_previous_downloads(tmp_path, monkeypatch):
    path, _, _, current, state, calls = context(tmp_path, monkeypatch)
    state["post_publish_damage"] = True
    with pytest.raises(ValueError, match="checksum"):
        publisher.publish(path)
    assert not current["draft"]
    assert not any(c[0] == "cleanup" for c in calls)


def test_failed_cleanup_can_be_retried_without_republishing_or_rebuilding(tmp_path, monkeypatch):
    path, _, _, current, state, calls = context(tmp_path, monkeypatch)
    state["cleanup_failure"] = True
    with pytest.raises(ValueError, match="is published.*cleanup failed"):
        publisher.publish(path)
    assert not current["draft"]
    state["cleanup_failure"] = False
    publisher.publish(path)
    assert sum(c[:2] == ("release", "edit") for c in calls) == 1


def test_retry_does_not_overwrite_a_different_latest_release(tmp_path, monkeypatch):
    path, _, _, current, state, calls = context(tmp_path, monkeypatch)
    current["draft"] = False
    state["latest_delay"] = 1
    with pytest.raises(ValueError, match="different release"):
        publisher.publish(path)
    assert not any(c[0] in ("release", "cleanup") for c in calls)
