"""Retention schema 2: whole releases stay for rollback, and a replacement never interrupts public installers."""
import ast
import hashlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import prune_published_release as prune
import shared_release_assets as shared

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
COMMITTED_PIN = prune.PINNED_GITHUB_HOSTED


@pytest.fixture(autouse=True)
def no_pinned_release(monkeypatch):
    """These fixtures name made-up releases, so the real pin would not be among them; tests of the pin set their own."""
    monkeypatch.setattr(prune, "PINNED_GITHUB_HOSTED", None)


def context(monkeypatch, *, latest=True, corrupt=False):
    """The current latest release, its two retained predecessors, one older release and a draft."""
    monkeypatch.setattr(prune, "PINNED_GITHUB_HOSTED", None)
    current = {"id": 20, "tag_name": "client-" + "a" * 40, "draft": False,
               "author": {"login": "rabbitlandsgame"}, "published_at": "2026-10-17T12:00:00Z"}
    previous = [{"id": 12, "tag_name": "client-" + "1" * 40, "draft": False, "published_at": "2026-10-16T12:00:00Z"},
                {"id": 11, "tag_name": "client-" + "2" * 40, "draft": False, "published_at": "2026-10-15T12:00:00Z"}]
    old = {"id": 10, "tag_name": "client-" + "b" * 40, "draft": False, "published_at": "2026-10-14T12:00:00Z"}
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
    monkeypatch.setattr(prune.release, "github_releases", lambda: [current, *previous, old, pending])
    monkeypatch.setattr(prune.release, "github_assets", lambda id: assets)
    return current, old, pending, calls


def test_only_verified_latest_publication_retires_releases_outside_the_retained_set(monkeypatch):
    current, old, pending, calls = context(monkeypatch)
    assert prune.prune(current["tag_name"]) == [old["tag_name"]]
    deletions = [call for call in calls if call[:2] == ("release", "delete")]
    assert [call[2] for call in deletions] == [old["tag_name"]]
    assert all(pending["tag_name"] not in call for call in calls)
    # the two previous releases are rollback targets: their inventories were read, they were not deleted
    assert sum(call[:2] == ("release", "download") for call in calls) == 3


@pytest.mark.parametrize("problem", ["draft", "not-latest", "corrupt"])
def test_unverified_publication_never_removes_any_release(monkeypatch, problem):
    current, _, _, calls = context(monkeypatch, latest=problem != "not-latest", corrupt=problem == "corrupt")
    if problem == "draft":
        current["draft"] = True
    with pytest.raises(ValueError):
        prune.prune(current["tag_name"])
    assert not any(call[:2] == ("release", "delete") for call in calls)


# --- the retained set ---------------------------------------------------------------------------------

def release(release_id, hour, *, draft=False, tag=None):
    item = {"id": release_id, "tag_name": tag or "client-" + f"{release_id:x}".rjust(40, "0"), "draft": draft}
    if not draft:
        item["published_at"] = f"2026-11-01T{hour:02d}:00:00Z" if hour is not None else "not a time"
    return item


def ids(items) -> set:
    return {item["id"] for item in items}


def test_retention_schema_2_constants_gate_the_r2_workflow():
    import actions_release
    assert type(prune.RETENTION_SCHEMA) is int and prune.RETENTION_SCHEMA == 2 and prune.KEEP_PREVIOUS == 2
    assert shared.CLIENT_TAG.fullmatch(COMMITTED_PIN)
    assert actions_release.retention_guard() == 2


def test_retention_keeps_latest_every_newer_release_and_the_two_published_before_it():
    releases = [release(i, i) for i in range(1, 8)]
    pool = {"id": 60, "tag_name": shared.TAG, "draft": False, "prerelease": True}
    releases += [release(50, None, draft=True), release(9, None), pool]
    latest = releases[4]  # published at 05:00, e.g. a rollback target marked latest again
    retained, retired = prune.retention(releases, latest)
    # 6 and 7 are newer (published not latest, or rolled back from); 9's time is unreadable: kept
    assert ids(retained) == {5, 6, 7, 4, 3, 9} and ids(retired) == {2, 1}
    assert ids(prune.retention(releases, latest, keep_previous=0)[1]) == {1, 2, 3, 4}
    # drafts and the shared pools are never in either list
    assert not ({50, 60} & (ids(retained) | ids(retired)))


def test_the_pinned_last_github_hosted_release_is_always_retained():
    releases = [release(i, i) for i in range(1, 7)]
    retained, retired = prune.retention(releases, releases[-1], pinned=releases[0]["tag_name"])
    assert ids(retained) == {6, 5, 4, 1} and ids(retired) == {2, 3}
    for pinned in ("client-" + "e" * 40, "client-assets", "client-ABC"):
        with pytest.raises(ValueError):
            prune.retention(releases, releases[-1], pinned=pinned)
    with pytest.raises(ValueError):
        prune.retention(releases[:-1], releases[-1])  # latest not among the published releases
    with pytest.raises(ValueError):
        prune.retention(releases + [dict(releases[0])], releases[-1])  # one release listed twice
    with pytest.raises(ValueError):
        prune.retention(releases, {**releases[-1], "published_at": None})


# --- whole releases and their pool downloads (fake GitHub) --------------------------------------------

def label_commit(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()[:40]


def world(monkeypatch, fin, layout):
    """Published releases in publication order: (label, release id, pool labels, R2-era?)."""
    github = fin.FakeGitHub().install(monkeypatch)
    github.add_pool(shared.TAG)
    for label, release_id, pools, r2_era in layout:
        fin.published_release(github, release_id, label_commit(label), r2_release=r2_era,
                              pool_rows=[*(fin.pkg_row(name) for name in pools), *fin.helper_rows_for(label)])
    github.latest_id = layout[-1][1]
    return github


def mark_latest(github, label):
    github.gh("release", "edit", "client-" + label_commit(label), "--repo", prune.release.REPOSITORY, "--latest")


@pytest.fixture
def fin(monkeypatch):
    import test_finalize_runner_release as module
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("prune makes no network call"))
    return module


def test_an_r2_release_then_an_older_retained_release_marked_latest_keeps_both_with_all_pool_assets(
        monkeypatch, fin):
    # G: pre-R2 (GitHub-hosted content), T: helper-train release (ci content), R1: first R2 content release
    github = world(monkeypatch, fin, [("g", 40, ["g-content", "g-engine"], False),
                                      ("t", 41, ["t-content", "t-engine"], False),
                                      ("r1", 42, ["r1-engine", "r1-native"], True)])
    pools, tags = github.pool_names(), github.tags()
    r1 = github.by_tag("client-" + label_commit("r1"))
    r1_files = dict(r1["assets"])
    mark_latest(github, "t")  # rollback: gh release edit client-<T> --latest ("edited": fires no cleanup)
    assert prune.prune("client-" + label_commit("t")) == []
    assert github.tags() == tags and github.pool_names() == pools
    assert not any(call[0] == "delete-asset" or call[:2] == ("release", "delete") for call in github.calls)
    for label in ("g", "t", "r1"):  # every release's helpers stay, for a rollback handoff in either direction
        assert {row["name"] for row in fin.helper_rows_for(label)} <= github.pool_names()
    assert r1["assets"] == r1_files  # its pointers and R2-SHA256SUMS included
    # rolling forward again needs nothing that was removed
    mark_latest(github, "r1")
    assert prune.prune("client-" + label_commit("r1")) == [] and github.pool_names() == pools


def test_after_a_rollback_only_releases_outside_the_retained_set_lose_their_own_files(monkeypatch, fin):
    github = world(monkeypatch, fin, [("x", 30, ["x-only", "shared"], False), ("y", 31, ["y-only", "shared"], False),
                                      ("g", 32, ["g-only", "shared"], False), ("t", 33, ["t-only"], False),
                                      ("r1", 34, ["r1-engine"], True)])
    github.add_pool_row(fin.pkg_row("orphan"))
    mark_latest(github, "t")
    assert prune.prune("client-" + label_commit("t")) == ["client-" + label_commit("x")]
    removed = {fin.pkg_row("x-only")["name"], fin.pkg_row("orphan")["name"],
               *(row["name"] for row in fin.helper_rows_for("x"))}
    assert removed.isdisjoint(github.pool_names())
    for label in ("y", "g", "t", "r1"):
        assert {row["name"] for row in fin.helper_rows_for(label)} <= github.pool_names()
    assert {fin.pkg_row(name)["name"] for name in ("shared", "y-only", "g-only", "t-only", "r1-engine")} \
        <= github.pool_names()


def test_pre_r2_parts_of_the_pinned_github_hosted_release_are_retained(monkeypatch, fin):
    layout = [("p", 50, ["p-content", "p-engine"], False), ("q", 51, ["q-content"], False),
              ("a", 52, ["a-engine"], True), ("b", 53, ["b-engine"], True), ("c", 54, ["c-engine"], True)]
    github = world(monkeypatch, fin, layout)
    monkeypatch.setattr(prune, "PINNED_GITHUB_HOSTED", "client-" + label_commit("p"))
    assert prune.prune("client-" + label_commit("c")) == ["client-" + label_commit("q")]
    names = github.pool_names()
    assert {fin.pkg_row("p-content")["name"], fin.pkg_row("p-engine")["name"]} <= names
    assert {row["name"] for row in fin.helper_rows_for("p")} <= names
    assert fin.pkg_row("q-content")["name"] not in names


def test_without_the_pin_the_oldest_github_hosted_release_is_retired(monkeypatch, fin):
    github = world(monkeypatch, fin, [("p", 50, ["p-content"], False), ("q", 51, ["q-content"], False),
                                      ("a", 52, ["a-engine"], True), ("b", 53, ["b-engine"], True),
                                      ("c", 54, ["c-engine"], True)])
    assert sorted(prune.prune("client-" + label_commit("c"))) == sorted(
        "client-" + label_commit(label) for label in ("p", "q"))
    assert fin.pkg_row("p-content")["name"] not in github.pool_names()


@pytest.mark.parametrize("problem", ["pinned-missing", "retained-sums-corrupt", "retained-sums-missing",
                                     "unexpected-asset", "pointer-incomplete"])
def test_prune_deletes_nothing_unless_every_retained_inventory_verifies(monkeypatch, fin, problem):
    github = world(monkeypatch, fin, [("x", 60, ["x-only"], False), ("a", 61, ["a-engine"], False),
                                      ("b", 62, ["b-engine"], True), ("c", 63, ["c-engine"], True)])
    b, c = github.by_tag("client-" + label_commit("b")), github.by_tag("client-" + label_commit("c"))
    if problem == "pinned-missing":
        monkeypatch.setattr(prune, "PINNED_GITHUB_HOSTED", "client-" + "e" * 40)
    elif problem == "retained-sums-corrupt":
        b["assets"]["SHA256SUMS"]["digest"] = "sha256:" + "f" * 64
    elif problem == "retained-sums-missing":
        del b["assets"]["SHA256SUMS"]
    elif problem == "unexpected-asset":
        github.add_asset(c["id"], "unlisted.zip", b"not in SHA256SUMS")
    else:
        next(asset for name, asset in c["assets"].items() if shared.is_pointer_name(name))["state"] = "starter"
    pools, tags = github.pool_names(), github.tags()
    with pytest.raises(ValueError):
        prune.prune("client-" + label_commit("c"))
    assert github.pool_names() == pools and github.tags() == tags


def test_a_pending_draft_keeps_every_pool_download(monkeypatch, fin):
    github = world(monkeypatch, fin, [("x", 70, ["x-only"], False), ("a", 71, ["a-engine"], False),
                                      ("b", 72, ["b-engine"], True), ("c", 73, ["c-engine"], True)])
    github.add_release(74, "client-" + label_commit("next"), draft=True)
    pools = github.pool_names()
    assert prune.prune("client-" + label_commit("c")) == ["client-" + label_commit("x")]
    assert github.pool_names() == pools  # the draft may be uploading; collect_unused waits for the next prune


def test_prune_and_shared_storage_never_reach_r2_or_the_network():
    for module in (prune, shared):
        source = Path(module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import)
                    for alias in node.names}
        imported |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        assert not imported & {"boto3", "botocore", "s3transfer", "urllib", "http", "socket", "requests",
                               "upload_desktop_assets", "desktop_r2"}, module.__name__
        assert "assets.rabbitlandsgame.com" not in source and "release.gh(" in source or module is shared


# --- the old release-event cleanup workflow ------------------------------------------------------------

def test_the_release_event_cleanup_workflow_is_a_no_op():
    yaml = pytest.importorskip("yaml")
    text = (WORKFLOWS / "published-client-cleanup.yml").read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)
    triggers = workflow.get("on", workflow.get(True))
    assert set(triggers) == {"workflow_dispatch"}  # no release event: publication starts nothing
    assert workflow["permissions"] == {} and workflow["concurrency"] == {
        "group": "rabbitlands-desktop-release", "cancel-in-progress": False}
    (job,) = workflow["jobs"].values()
    assert job["permissions"] == {} and 0 < job["timeout-minutes"] <= 10
    (step,) = job["steps"]
    assert set(step) == {"name", "run"} and step["run"].startswith("echo ")
    for needle in ("python", "prune_published_release", "gh ", "GH_TOKEN", "github.token", "secrets.", "uses:",
                   "checkout", "release:"):
        assert needle not in step["run"] and needle not in text.split("jobs:", 1)[1], needle
    assert text.isascii() and "\r" not in text
