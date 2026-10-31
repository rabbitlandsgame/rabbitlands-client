"""Capacity and destination integrity for checksum-partitioned downloads."""
import hashlib
import json
from pathlib import Path
import sys
import re

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_release as release
import shared_release_assets as shared
from test_asset_packages import fixture
from test_shared_release_assets import shared_payload, shared_finalizer_fixture


def fixture_cloud(monkeypatch, count=1200):
    ids = {shared.TAG: 1}
    rows, cloud = {}, {1: []}
    for index in range(count):
        digest = hashlib.sha256(str(index).encode()).hexdigest()
        filename = shared.name(digest)
        tag = shared.storage_tag(filename)
        pool_id = ids.setdefault(tag, len(ids) + 1)
        row = {"name": filename, "size": 12, "sha256": digest}
        rows[filename] = row
        cloud.setdefault(pool_id, []).append({**row, "state": "uploaded", "digest": "sha256:" + digest})
    tags = {value: tag for tag, value in ids.items()}
    monkeypatch.setattr(release, "github_assets", lambda pool_id: cloud[pool_id])
    monkeypatch.setattr(release, "gh", lambda *args: json.dumps({
        "id": int(args[-1].rsplit("/", 1)[-1]),
        "tag_name": tags[int(args[-1].rsplit("/", 1)[-1])],
        "draft": False, "prerelease": True, "author": {"login": release.ACCOUNT}}))
    return rows, ids, cloud


def test_more_than_one_thousand_packages_verify_across_bounded_destinations(monkeypatch):
    rows, ids, cloud = fixture_cloud(monkeypatch)
    assert len(rows) == 1200 and len(ids) == 17
    assert max(map(len, cloud.values())) < 1000
    assert set(shared.verify_storage(rows, ids)) == set(rows)


def test_matching_legacy_copy_cannot_mask_a_missing_shard_download(monkeypatch):
    rows, ids, cloud = fixture_cloud(monkeypatch, 1)
    tag = shared.storage_tag(next(iter(rows)))
    cloud[ids[shared.TAG]] = cloud[ids[tag]]
    cloud[ids[tag]] = []
    with pytest.raises(ValueError, match="destination checksum"):
        shared.verify_storage(rows, ids)


def test_corrupt_part_keeps_verification_fatal(monkeypatch):
    rows, ids, cloud = fixture_cloud(monkeypatch, 1)
    cloud[ids[shared.storage_tag(next(iter(rows)))]][0]["digest"] = "sha256:" + "f" * 64
    with pytest.raises(ValueError, match="checksum"):
        shared.verify_storage(rows, ids)


@pytest.mark.parametrize("change", ["missing", "duplicate_id", "bad_tag", "wrong_identity"])
def test_untrusted_receipt_cannot_redirect_a_storage_destination(monkeypatch, change):
    rows, ids, cloud = fixture_cloud(monkeypatch, 1)
    tag = shared.storage_tag(next(iter(rows)))
    if change == "missing":
        del ids[tag]
    elif change == "duplicate_id":
        ids[tag] = ids[shared.TAG]
    elif change == "bad_tag":
        ids["client-assets-evil"] = 777
    else:
        ids[tag], ids[shared.TAG] = ids[shared.TAG], ids[tag]
    with pytest.raises(ValueError):
        shared.verify_storage(rows, ids)


def test_bootstrap_helpers_keep_legacy_download_urls_and_foreign_shards_fail():
    for kind in ("updater", "uninstall"):
        filename = shared.name("a" * 64, kind, "exe")
        assert shared.storage_tag(filename) == shared.TAG
        assert shared.download_url(release.REPOSITORY, filename) == shared.base(release.REPOSITORY) + "/" + filename
    filename = shared.name("a" * 64)
    row = {"sha256": "a" * 64, "url": shared.download_url(release.REPOSITORY, filename)}
    assert shared.matches(row, release.REPOSITORY)
    assert not shared.matches({**row, "url": row["url"].replace("client-assets-a", "client-assets-b")}, release.REPOSITORY)
    assert not shared.matches(row, "someone/else")
    assert shared.matches({**row, "url": shared.base(release.REPOSITORY) + "/" + filename}, release.REPOSITORY)


def test_installed_legacy_bootstrap_accepts_new_helpers_before_sharded_packages(fixture):
    f = fixture
    payload = shared_payload(f)
    for package in payload["packages"]:
        for part in package["parts"]:
            part["url"] = shared.download_url(release.REPOSITORY, part["url"].rsplit("/", 1)[1])
    payload["parts"] = [part for package in payload["packages"] for part in package["parts"]]
    script = f["tmp_path"] / "project/src/updates/release.gd"
    current = script.read_text()
    legacy = re.sub(r'(?ms)^static func shared_download\(.*?(?=^static func verify_envelope)',
        'static func shared_download(row: Dictionary, repository: String, kind := "pkg", extension := "zip.part") -> bool:\n'
        '\treturn valid_hash(row.get("sha256")) and row.get("url") == "https://github.com/%s/releases/download/client-assets/RabbitLands-%s-%s.%s" % [repository, kind, row.sha256, extension]\n\n', current)
    assert legacy != current
    try:
        script.write_text(legacy)
        assert f["run"]("bootstrap-verify", payload)[0] == 0
        assert f["run"]("verify", payload)[0] == 1
    finally:
        script.write_text(current)
    assert f["run"]("update", payload)[0] == 0
    assert (f["installed"] / "app/RabbitLands.pck").read_bytes() == b"fixture pack"


@pytest.mark.parametrize("misplaced", [False, True])
def test_partitioned_finalization_checks_each_destination_before_draft_mutation(tmp_path, monkeypatch, misplaced):
    finalizer, receipts, assets, pooled, calls = shared_finalizer_fixture(tmp_path, monkeypatch)
    ids, cloud = {shared.TAG: 777}, {777: []}
    for asset in pooled:
        tag = shared.storage_tag(asset["name"])
        pool_id = ids.setdefault(tag, 777 + len(ids))
        cloud.setdefault(pool_id, []).append(asset)
    for path in receipts:
        item = json.loads(path.read_text())
        item["shared_release_ids"] = ids
        path.write_text(json.dumps(item))
    previous = release.gh
    tags = {value: tag for tag, value in ids.items()}
    def gh(*args):
        if args[:1] == ("api",) and args[-1].startswith(f"repos/{release.REPOSITORY}/releases/"):
            suffix = args[-1].rsplit("/", 1)[1]
            if suffix.isdigit() and int(suffix) in tags:
                return json.dumps({"id": int(suffix), "tag_name": tags[int(suffix)], "draft": False,
                                   "prerelease": True, "author": {"login": release.ACCOUNT}})
        return previous(*args)
    monkeypatch.setattr(release, "gh", gh)
    monkeypatch.setattr(release, "github_assets", lambda pool_id: cloud[pool_id] if pool_id in cloud else assets)
    if misplaced:
        shard = next(key for key in cloud if key != 777)
        cloud[777].append(cloud[shard].pop())
        with pytest.raises(ValueError, match="destination checksum"):
            finalizer.finalize(receipts, tmp_path / "final")
        assert not any(call[:2] == ("release", "edit") for call in calls)
    else:
        finalizer.finalize(receipts, tmp_path / "final")
        result = json.loads((tmp_path / "final/runner-release.json").read_text())
        assert result["shared_release_ids"] == ids


def test_full_legacy_store_does_not_block_package_shards_or_delete_live_assets(tmp_path, monkeypatch):
    pools = {shared.TAG: {"id": 1, "tag_name": shared.TAG}, shared.TAG + "-a": {"id": 2, "tag_name": shared.TAG + "-a"}}
    legacy = [{"name": str(index)} for index in range(1000)]
    monkeypatch.setattr(shared, "ensure", lambda sha, tag=shared.TAG: pools[tag])
    monkeypatch.setattr(release, "github_assets", lambda pool_id: legacy if pool_id == 1 else [])
    monkeypatch.setattr(release, "gh", lambda *args: pytest.fail("Never remove an unverified live asset"))
    uploads = []
    def upload(pool_id, path, row, old, **kwargs):
        uploads.append(pool_id)
        return {**row, "state": "uploaded", "digest": "sha256:" + row["sha256"]}
    monkeypatch.setattr(release, "upload_asset_api", upload)
    store = shared.Storage("b" * 40)
    path = tmp_path / shared.name("a" * 64)
    store.upload(path, {"name": path.name, "size": 4, "sha256": "a" * 64})
    assert uploads == [2] and len(legacy) == 1000
    path = tmp_path / shared.name("a" * 64, "updater", "exe")
    with pytest.raises(ValueError, match="full.*preserve published"):
        store.upload(path, {"name": path.name, "size": 4, "sha256": "a" * 64})
    assert uploads == [2] and len(legacy) == 1000


@pytest.mark.parametrize("misplaced", [False, True])
def test_partitioned_publication_checks_destinations_before_becoming_latest(tmp_path, monkeypatch, misplaced):
    from test_publish_runner_release import context
    import publish_runner_release as publisher
    path, receipt, assets, current, state, calls = context(tmp_path, monkeypatch)
    tag = shared.storage_tag(receipt["shared_assets"][0]["name"])
    receipt["shared_release_ids"] = {shared.TAG: 777, tag: 778}
    assets[778], assets[777] = assets[777], []
    state["expected_prepublication_checks"] = 3
    if misplaced:
        assets[777] = assets[778]
        assets[778] = []
    path.write_text(json.dumps(receipt))
    previous = release.gh
    def gh(*args):
        if args == ("api", f"repos/{release.REPOSITORY}/releases/778"):
            return json.dumps({"id": 778, "tag_name": tag, "draft": False, "prerelease": True,
                               "author": {"login": release.ACCOUNT}})
        return previous(*args)
    monkeypatch.setattr(release, "gh", gh)
    if misplaced:
        with pytest.raises(ValueError, match="destination checksum"):
            publisher.publish(path)
        assert current["draft"] and not any(call[0] == "cleanup" for call in calls)
    else:
        publisher.publish(path)
        assert not current["draft"] and calls[-1][0] == "cleanup"


@pytest.mark.parametrize("platform", ["windows", "linux"])
def test_signed_platform_outputs_support_partitioned_storage(fixture, platform):
    from test_asset_packages import test_publication_signs_package_inventory_and_collects_all_installer_assets
    test_publication_signs_package_inventory_and_collects_all_installer_assets(fixture, "partitioned", platform)
    manifest = fixture["tmp_path"] / f"RabbitLands-{platform.title()}-20261024-bbbbbbbbb-{platform}.json"
    import base64
    payload = json.loads(base64.b64decode(json.loads(manifest.read_text())["payload"]))
    for part in payload["parts"]:
        assert part["url"] == shared.download_url(release.REPOSITORY, part["url"].rsplit("/", 1)[1])
    for kind in ("updater", "uninstall"):
        assert payload[kind]["url"].startswith(shared.base(release.REPOSITORY) + "/")
