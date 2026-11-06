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
            assert state["verified"] == state.get("expected_prepublication_checks", 2), "All release inventories must be checked before publication"
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


def test_the_old_publisher_refuses_an_r2_release_receipt(tmp_path, monkeypatch):
    path, receipt, _, current, _, calls = context(tmp_path, monkeypatch)
    receipt["kind"] = "rabbitlands-desktop-r2-release"
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="verified release receipt"):
        publisher.publish(path)
    assert current["draft"] and not calls


# --- desktop-release-r2.yml: publish (not latest) and promote (R2-A7) ---------------------------------
#
# finalize_r2 runs first on the same fake GitHub (test_finalize_runner_release), so publish and
# promote read a real receipt. Pointers are signed with the test key. Promote reads the live
# pointers through a fake custom domain; nothing reaches R2 or the network.

import hashlib  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import desktop_r2 as r2  # noqa: E402
import prune_published_release as prune  # noqa: E402
import release_manifest as rm  # noqa: E402
import shared_release_assets as shared_assets  # noqa: E402
import test_finalize_runner_release as fin  # noqa: E402
from test_desktop_release_ci import FakeHttp  # noqa: E402
from test_finalize_runner_release import no_network  # noqa: E402,F401 (fixture)

key = fin.key
other_key = fin.other_key
COMMIT, DRAFT_ID, PREVIOUS_ID = fin.COMMIT, fin.DRAFT_ID, fin.PREVIOUS_ID
LIVE_HOST = "https://assets.rabbitlandsgame.com/"


def sign_pointer(manifest: bytes, key, platform, *, release_id=DRAFT_ID, rollback=False, sequence=None):
    return rm.pointer_envelope(platform=platform, sequence=sequence or fin.fx.SEQUENCE + 600, rollback=rollback,
                               release_id=release_id, run_id=9, manifest=manifest,
                               private_key=rm.load_signing_key(key.private, key.public), public_pem=key.public)


def pointer_folder(folder: Path, inputs, key, **options) -> Path:
    folder.mkdir(parents=True)
    for platform, item in inputs.signed.items():
        (folder / r2.pointer_asset_name(platform)).write_bytes(sign_pointer(item.envelope, key, platform, **options))
    return folder


@pytest.fixture
def r2_release(tmp_path, monkeypatch, key, no_network):
    """A finalized R2 draft (both platforms r2) after older releases, with this run's pointers."""
    monkeypatch.setattr(prune, "PINNED_GITHUB_HOSTED", None)  # made-up releases, so the real pin is not among them
    monkeypatch.setattr(publisher.time, "sleep", lambda _: None)
    inputs = fin.r2_inputs(tmp_path / "run", key)
    history = (("oldest", 91), ("older", 92), ("old", 93))
    github = fin.r2_world(monkeypatch, inputs, history=history)
    fin.finalize_run(inputs, key)
    ancestors = [COMMIT, fin.PREVIOUS] + [hashlib.sha256(label.encode()).hexdigest()[:40] for label, _ in history]
    monkeypatch.setattr(publisher.package, "git", lambda *args: "\n".join(ancestors) + "\n")
    monkeypatch.setattr(publisher, "commit_public_key", lambda commit: pytest.fail("tests pass the test key"))
    pointers = pointer_folder(tmp_path / "pointers", inputs, key)
    return type("Scene", (), {"inputs": inputs, "github": github, "pointers": pointers,
                              "receipt": inputs.out / "runner-release.json", "tmp": tmp_path})


def run_publish(scene, key, **changes):
    options = dict(commit=COMMIT, release_id=DRAFT_ID, receipt=scene.receipt, pointers=scene.pointers,
                   public_pem=key.public)
    options.update(changes)
    return publisher.publish_r2(**options)


def live_domain(scene, *, pointers=None, manifests=True) -> FakeHttp:
    """The custom domain after the local R2 publish: both pointers live, both manifest copies present."""
    http = FakeHttp()
    for platform, item in scene.inputs.signed.items():
        data = (pointers or {}).get(platform, (scene.pointers / r2.pointer_asset_name(platform)).read_bytes())
        if data is not None:
            http.objects[r2.pointer_url(platform)] = data
        if manifests:
            http.objects[r2.manifest_url(platform, fin.digest(item.envelope))] = item.envelope
    return http


def run_promote(scene, key, http, **changes):
    options = dict(commit=COMMIT, release_id=DRAFT_ID, receipt=scene.receipt, public_pem=key.public, http=http)
    options.update(changes)
    return publisher.promote_r2(**options)


def test_publish_r2_publishes_not_latest_with_its_pointers_and_never_prunes(r2_release, key, monkeypatch):
    scene, github = r2_release, r2_release.github
    monkeypatch.setattr(prune, "prune", lambda tag: pytest.fail("publish never prunes"))
    tags_before, start = github.tags(), len(github.calls)
    url = run_publish(scene, key)
    item = github.releases[DRAFT_ID]
    assert url.endswith(f"/client-{COMMIT}") and not item["draft"] and not item["prerelease"]
    assert github.latest_id == PREVIOUS_ID  # /releases/latest, what released games read, is unchanged
    for platform in fin.PLATFORMS:
        name = r2.pointer_asset_name(platform)
        assert item["data"][name] == (scene.pointers / name).read_bytes()
    (edit,) = github.edits()[1:]  # the first edit is finalize's retag
    assert "--draft=false" in edit and "--latest=false" in edit and "--latest" not in edit
    assert github.tags() == tags_before and not any(call[0] == "delete-asset" for call in github.calls[start:])
    assert "not latest" in scene.inputs.summary.read_text()


def test_publish_r2_rerun_replaces_only_its_own_pointers(r2_release, key):
    scene, github = r2_release, r2_release.github
    run_publish(scene, key)
    fresh = pointer_folder(scene.tmp / "pointers-2", scene.inputs, key, sequence=fin.fx.SEQUENCE + 900)
    run_publish(scene, key, pointers=fresh)
    item = github.releases[DRAFT_ID]
    assert github.latest_id == PREVIOUS_ID and not item["draft"]
    assert all(item["data"][r2.pointer_asset_name(p)] == (fresh / r2.pointer_asset_name(p)).read_bytes()
               for p in fin.PLATFORMS)
    assert sum("--draft=false" in call for call in github.edits()) == 1


@pytest.mark.parametrize("problem", ["rollback", "other-release", "other-key", "extra-file", "missing", "swapped",
                                     "other-manifest", "receipt-kind", "receipt-release", "not-ancestor"])
def test_publish_r2_refuses_before_any_release_write(r2_release, key, other_key, monkeypatch, problem):
    scene, github = r2_release, r2_release.github
    writes = len(github.writes())
    options, folder = {}, scene.pointers
    windows = folder / r2.pointer_asset_name("windows")
    if problem == "rollback":
        folder = pointer_folder(scene.tmp / "p2", scene.inputs, key, rollback=True)
    elif problem == "other-release":
        folder = pointer_folder(scene.tmp / "p2", scene.inputs, key, release_id=DRAFT_ID + 1)
    elif problem == "other-key":
        good = rm.verify(windows.read_bytes(), key.public, limit=r2.MAX_POINTER_BYTES)[1]
        windows.write_bytes(rm.sign(r2.pointer_bytes(good, platform="windows"),
                                    rm.load_signing_key(other_key.private, other_key.public)))
    elif problem == "extra-file":
        (folder / "RabbitLands-windows.json").write_bytes(b"{}")
    elif problem == "missing":
        windows.unlink()
    elif problem == "swapped":
        linux = folder / r2.pointer_asset_name("linux")
        data = windows.read_bytes()
        windows.write_bytes(linux.read_bytes())
        linux.write_bytes(data)
    elif problem == "other-manifest":
        # a valid forward pointer of this release, but to a manifest finalize did not verify
        other = fin.signed_platform(scene.tmp / "other", key, "windows", "r2", set_override=fin._remove_last_package)
        assert other.envelope != scene.inputs.signed["windows"].envelope
        windows.write_bytes(sign_pointer(other.envelope, key, "windows"))
    elif problem in ("receipt-kind", "receipt-release"):
        value = json.loads(scene.receipt.read_text())
        value.update({"receipt-kind": {"kind": "rabbitlands-desktop-runner"},
                      "receipt-release": {"release_id": DRAFT_ID + 1}}[problem])
        scene.receipt.write_text(json.dumps(value))
    elif problem == "not-ancestor":
        monkeypatch.setattr(publisher.package, "git", lambda *args: COMMIT + "\n")
    options["pointers"] = folder
    with pytest.raises(ValueError):
        run_publish(scene, key, **options)
    assert len(github.writes()) == writes and github.releases[DRAFT_ID]["draft"]
    assert github.latest_id == PREVIOUS_ID


def test_publish_r2_refuses_a_promoted_release_and_reports_a_latest_flip(r2_release, key):
    scene, github = r2_release, r2_release.github
    github.latest_on_publish = True  # GitHub made it latest despite --latest=false
    with pytest.raises(ValueError, match="GitHub latest changed"):
        run_publish(scene, key)
    with pytest.raises(ValueError, match="already GitHub latest"):
        run_publish(scene, key)


def test_publish_r2_refuses_a_changed_inventory_before_uploading_its_pointers(r2_release, key):
    scene, github = r2_release, r2_release.github
    github.add_asset(DRAFT_ID, "unexpected.zip", b"late upload")
    writes = len(github.writes())
    with pytest.raises(ValueError, match="inventory"):
        run_publish(scene, key)
    assert github.releases[DRAFT_ID]["draft"] and len(github.writes()) == writes


def test_promote_flips_latest_only_after_both_live_pointers_match_then_prunes_with_retention(r2_release, key):
    scene, github = r2_release, r2_release.github
    run_publish(scene, key)
    http = live_domain(scene)
    pools_before = github.pool_names()
    url = run_promote(scene, key, http)
    assert url.endswith(f"/client-{COMMIT}") and github.latest_id == DRAFT_ID
    # only anonymous GETs of the two live pointers and the two manifest copies, on the custom domain
    assert sorted(http.calls) == sorted(
        [("GET", r2.pointer_url(p)) for p in fin.PLATFORMS]
        + [("GET", r2.manifest_url(p, fin.digest(item.envelope))) for p, item in scene.inputs.signed.items()])
    assert all(url.startswith(LIVE_HOST + "desktop/v1/") for _, url in http.calls)
    # retained: the new latest, the two before it (99 and 93); 91 and 92 retired with only their own files
    assert github.tags() == {f"client-{COMMIT}", f"client-{fin.PREVIOUS}",
                             "client-" + hashlib.sha256(b"old").hexdigest()[:40]}
    removed = pools_before - github.pool_names()
    assert removed == {fin.pkg_row(label)["name"] for label in ("oldest", "older")} | {
        row["name"] for label in ("oldest", "older") for row in fin.helper_rows_for(label)}
    for item in scene.inputs.signed.values():
        assert all(row["name"] in github.pool_names() for row in fin.pool_rows_of(item.payload))  # helpers too
    assert {row["name"] for row in fin.helper_rows_for("old")} <= github.pool_names()
    assert fin.pkg_row("shared")["name"] in github.pool_names()
    summary = scene.inputs.summary.read_text()
    assert "Promoted" in summary and "Retired 2 release(s)" in summary


@pytest.mark.parametrize("problem", ["pointer-404", "pointer-stale", "pointer-older-release", "manifest-missing",
                                     "manifest-other", "draft", "not-ancestor", "asset-tampered",
                                     "asset-digest"])
def test_promote_refuses_unless_both_live_pointers_are_byte_equal_to_the_release_assets(
        r2_release, key, monkeypatch, problem):
    scene, github = r2_release, r2_release.github
    monkeypatch.setattr(prune, "prune", lambda tag: pytest.fail("nothing is pruned"))
    windows = scene.inputs.signed["windows"]
    if problem != "draft":
        run_publish(scene, key)
    else:
        # the publish job uploaded its pointers but stopped before publishing: still a draft
        for platform in fin.PLATFORMS:
            name = r2.pointer_asset_name(platform)
            github.add_asset(DRAFT_ID, name, (scene.pointers / name).read_bytes())
    pointers, manifests = {}, True
    if problem == "pointer-404":
        pointers = {"linux": None}
    elif problem == "pointer-stale":
        # validly signed for this release and manifest, but not the bytes the release carries
        pointers = {"windows": sign_pointer(windows.envelope, key, "windows", sequence=fin.fx.SEQUENCE + 700)}
    elif problem == "pointer-older-release":
        pointers = {"windows": b'{"payload":"e30=","signature":"AA=="}'}
    elif problem == "manifest-missing":
        manifests = False
    elif problem == "not-ancestor":
        monkeypatch.setattr(publisher.package, "git", lambda *args: COMMIT + "\n")
    elif problem == "asset-tampered":
        # validly signed and live, but for another release: byte equality alone is not enough
        other = sign_pointer(windows.envelope, key, "windows", release_id=DRAFT_ID + 5)
        github.add_asset(DRAFT_ID, r2.pointer_asset_name("windows"), other)
        pointers = {"windows": other}
    http = live_domain(scene, pointers=pointers, manifests=manifests)
    if problem == "manifest-other":
        # the same length, other bytes: only the hash tells them apart
        other = windows.envelope[:-2] + (b"A" if windows.envelope[-2:-1] != b"A" else b"B") + windows.envelope[-1:]
        http.objects[r2.manifest_url("windows", fin.digest(windows.envelope))] = other
    elif problem == "asset-digest":
        # the release listing no longer matches the bytes a download returns
        github.releases[DRAFT_ID]["assets"][r2.pointer_asset_name("windows")]["digest"] = "sha256:" + "f" * 64
    tags, edits = github.tags(), len(github.edits())
    with pytest.raises(ValueError):
        run_promote(scene, key, http)
    assert github.latest_id == PREVIOUS_ID and github.tags() == tags and len(github.edits()) == edits


def test_promote_rerun_after_latest_only_prunes_again(r2_release, key, monkeypatch):
    scene, github = r2_release, r2_release.github
    run_publish(scene, key)
    http = live_domain(scene)
    failures = iter([ValueError("temporary GitHub failure")])

    def flaky(tag):
        error = next(failures, None)
        if error:
            raise error
        return []
    monkeypatch.setattr(prune, "prune", flaky)
    with pytest.raises(ValueError, match="is GitHub latest.*Rerun this promote job"):
        run_promote(scene, key, http)
    assert github.latest_id == DRAFT_ID
    run_promote(scene, key, http)
    assert sum("--latest" in call for call in github.edits()) == 1


def test_promote_and_publish_hold_no_r2_credential_and_write_nothing_to_r2():
    import ast
    for module in (publisher, fin.runner, prune, shared_assets):
        source = Path(module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import)
                    for alias in node.names}
        imported |= {node.module.split(".")[0] for node in ast.walk(tree)
                     if isinstance(node, ast.ImportFrom) and node.module}
        assert not imported & {"boto3", "botocore", "s3transfer"}, module.__name__
        for needle in ("create_client", "Bucket(", "put_object", "delete_object", "load_config", "credentials",
                       "IfNoneMatch", "PutObject"):
            assert needle not in source, (module.__name__, needle)
    # promote reads the live custom domain only through the anonymous client, by GET
    source = Path(publisher.__file__).read_text(encoding="utf-8")
    assert source.count('http.request("GET"') == 1 and "up.Http()" in source
