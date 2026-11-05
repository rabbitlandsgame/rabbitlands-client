"""Local pack and compare (tools/desktop_content.py) on fixture stages.

No R2, GitHub, network or Godot: probes and HTTPS are fakes, the tools
checkout is a throwaway Git repository with a local bare "origin", and the
release key is a throwaway RSA key (never the committed update_public.pem).
"""
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import types

import pytest

GODOT = Path(__file__).resolve().parents[1]
TOOLS = GODOT / "tools"
sys.path.insert(0, str(TOOLS))
import desktop_r2 as r2  # noqa: E402
import upload_desktop_assets as up  # noqa: E402
import desktop_content as dc  # noqa: E402

COMMITTED_PEM = (GODOT / "data/update_public.pem").read_bytes()
SEQUENCE = 1_762_300_000


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pe_bytes() -> bytes:
    return b"MZ" + b"\0" * 58 + (64).to_bytes(4, "little") + b"PE\0\0" + b"\0" * 64


# --- Keys, Git and fixtures ------------------------------------------------------

def _rsa():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return types.SimpleNamespace(
        private=key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()),
        public=key.public_key().public_bytes(serialization.Encoding.PEM,
                                             serialization.PublicFormat.SubjectPublicKeyInfo))


@pytest.fixture(scope="session")
def key():
    value = _rsa()
    assert value.public != COMMITTED_PEM
    return value


@pytest.fixture(scope="session")
def other_key():
    return _rsa()


def git(cwd, *args) -> str:
    environment = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    result = subprocess.run(["git", "-C", str(cwd), "-c", "user.name=RL Test", "-c", "user.email=test@example.invalid",
                             *args], check=True, capture_output=True, env=environment)
    return result.stdout.decode().strip()


def commit_file(repo: Path, relative: str, data: bytes, message: str) -> str:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    git(repo, "add", "--", relative)
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path, key):
    """A tools checkout: `previous` then `commit`, both pushed to a local origin."""
    remote = tmp_path / "remote" / "rabbitlandsgame" / "rabbitlands-client.git"
    remote.mkdir(parents=True)
    git(remote, "init", "-q", "--bare")
    work = tmp_path / "tools"
    work.mkdir()
    git(work, "init", "-q", "-b", "develop")
    commit_file(work, "godot-client/data/update_public.pem", key.public, "key")
    previous = commit_file(work, "godot-client/tools/asset_packages.py", b"# packaging\n", "previous release")
    commit = commit_file(work, "godot-client/data/notes.txt", b"notes\n", "release")
    git(work, "remote", "add", "origin", remote.as_posix())
    git(work, "push", "-q", "origin", "develop")
    git(work, "fetch", "-q", "origin")
    return types.SimpleNamespace(path=work, commit=commit, previous=previous, remote=remote)


def build_tree(tmp_path, repo, commit, name="build"):
    """package_client's build tree: a checkout at `commit` with an ignored import cache."""
    build = tmp_path / name
    git(tmp_path, "clone", "-q", str(repo.path), str(build))
    git(build, "checkout", "-q", "--detach", commit)
    (build / ".git" / "info" / "exclude").write_text(".godot/\n*.import\n", encoding="ascii")
    cache = build / "godot-client" / ".godot" / "imported"
    cache.mkdir(parents=True)
    (cache / "wolf.glb-0123.scn").write_bytes(b"scene")
    (cache / "ground.png-4567.ctex").write_bytes(b"texture")
    (build / "godot-client" / "icon.png.import").write_text("[remap]\n", encoding="ascii")
    return build


@pytest.fixture
def build(tmp_path, repo):
    return build_tree(tmp_path, repo, repo.commit)


CONTENT = {
    "app/RabbitLands.pck": b"GDPC" + bytes(range(256)) * 16,
    "app/assets/actors/wolf/grey/wolf.glb": b"glTF" + b"w" * 3000,
    "app/assets/actors/wolf/grey/vram/wolf.evt": b"EVT1" + b"t" * 500,
    "app/assets/audio/howl.ogg": b"OggS" + b"a" * 1000,
    "app/assets/ui/icon.png": b"\x89PNG" + b"p" * 200,
    "app/assets/ui/Big Banner.png": b"\x89PNG" + b"b" * 300,
    "eloria-assets/maps/meadow/data.json": b'{"map": "meadow"}',
    "eloria-assets/maps/meadow/vram/ground.evt": b"EVT1" + b"g" * 700,
}
CI_FILES = {
    "app/RabbitLands.exe": pe_bytes() + b"engine",
    "app/bin/client_runtime/client_runtime.dll": pe_bytes() + b"runtime",
    "app/bin/client_runtime/client_runtime.gdextension": b"[configuration]\n",
    "app/bin/client_runtime/runtime-manifest.json": b"{}",
}
ROOT_FILES = {
    "README.txt": b"Rabbit Lands\r\n",
    "RabbitLands.bat": b"@echo off\r\n",
    "RabbitLands (debug console).bat": b"@echo off\r\n",
    "launcher-defaults.json": b'{"args": []}',
    "AUDIO-CREDITS.txt": b"credits\n",
    "RabbitLands-updater.exe": pe_bytes() + b"updater",
}


def descriptor(sha_commit, platform, key, changes) -> bytes:
    value = {"schema": 1, "commit": sha_commit, "platform": platform, "ancestors": [sha_commit],
             "public_key": key.public.decode("ascii"), "repository": r2.REPOSITORY, "distribution": "github",
             "release_build": True, **changes}
    return json.dumps(value).encode()


def make_stage(root: Path, commit: str, platform: str, key, *, date="20261104", content=None, ci=None,
               extra=None, qualified=True, identity=None, **changes) -> Path:
    folder = "RabbitLands-" + platform.title()
    stage = root / f"{folder}-{date}-{commit[:9]}"
    stage.mkdir(parents=True)
    files = {**(CONTENT if content is None else content), **(CI_FILES if ci is None else ci), **(extra or {})}
    data = descriptor(commit, platform, key, {**(identity or {}), **changes})
    files["app/client-release.json"] = data
    files["app/data/client_release.json"] = data
    for relative, value in {**files, **ROOT_FILES}.items():
        path = stage / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    marker = stage / ".eloria-package"
    marker.write_text(commit + "\n", encoding="ascii")
    earlier = time.time_ns() - 60 * 10 ** 9
    os.utime(marker, ns=(earlier, earlier))
    if qualified:
        qualify(stage, commit, platform)
    return stage


def qualify(stage: Path, commit: str, platform: str, **proof) -> Path:
    logs = stage.parent / ".build" / "logs" / f"{platform}-{stage.name.split('-', 2)[2]}"
    logs.mkdir(parents=True, exist_ok=True)
    value = {"policy": "test", "status": "verified_before_signing", "commit": commit, "platform": platform, **proof}
    (logs / "optimization-proof.json").write_text(json.dumps(value), encoding="ascii")
    (logs / "smoke.log").write_text("RABBITLANDS_OPTIMIZATION_STARTUP {}\n", encoding="ascii")
    (logs / "smoke-human-testing.log").write_text("RABBITLANDS_OPTIMIZATION_STARTUP {}\n", encoding="ascii")
    return logs


def run_pack(stage, out, repo, *, platform="windows", build=None, **options):
    return dc.pack(stage, platform=platform, out=out, tools_repo=repo.path,
                   build_dir=build, **options)


def tree(stage: Path) -> dict:
    return {path.relative_to(stage).as_posix(): sha(path.read_bytes()) for path in stage.rglob("*") if path.is_file()}


def set_of(result) -> dict:
    return r2.parse_set_bytes(result.set_path.read_bytes())


def plan_of(result) -> dict:
    return json.loads(result.plan_path.read_text())


def package(content_set, pid_prefix) -> dict:
    matches = [row for row in content_set["packages"] if row["id"].startswith(pid_prefix)]
    assert len(matches) == 1, [row["id"] for row in content_set["packages"]]
    return matches[0]


def package_with(content_set, path) -> dict:
    matches = [row for row in content_set["packages"] if path in {entry["path"] for entry in row["files"]}]
    assert len(matches) == 1
    return matches[0]


def all_parts(content_set) -> set:
    return {part["sha256"] for row in content_set["packages"] for part in row["parts"]}


class FakeProbe:
    name = "fake"

    def __init__(self, present=(), missing=()):
        self.present, self.missing = set(present), set(missing)
        self.calls = []

    def available(self, part):
        self.calls.append(part["sha256"])
        return part["sha256"] in self.present and part["sha256"] not in self.missing


class FakeHttp:
    def __init__(self, routes=None, statuses=None):
        self.routes = dict(routes or {})
        self.statuses = dict(statuses or {})
        self.calls = []

    def request(self, method, url, *, limit, headers=None, keep_body=True):
        self.calls.append((method, url))
        if url in self.statuses:
            return up.HttpResponse(self.statuses[url], {})
        body = self.routes.get(url)
        if body is None:
            return up.HttpResponse(404, {})
        if method == "HEAD":
            return up.HttpResponse(200, {"content-length": str(len(body))})
        if len(body) > limit:
            raise up.UploadError("http-too-large", url)
        return up.HttpResponse(200, {}, body, sha(body), len(body))


def manifest_bytes(key, content_set, set_bytes, *, source="r2", sequence=SEQUENCE, packages=None, **changes):
    engine = {"id": "engine", "sha256": "e" * 64, "size": 10, "unpacked_size": 10, "file_count": 1,
              "files": [{"path": "app/RabbitLands.exe", "size": 10, "sha256": "f" * 64}],
              "parts": [{"url": r2.github_pool_url("e" * 64), "size": 10, "sha256": "e" * 64}]}
    payload = {"schema": 3, "bootstrap_schema": 1, "repository": r2.REPOSITORY, "commit": content_set["commit"],
               "platform": content_set["platform"], "version": content_set["version"],
               "ancestors": [content_set["commit"]], "launch_args": [],
               "packages": (content_set["packages"] if packages is None else packages) + [engine],
               **r2.manifest_additions(platform=content_set["platform"], sequence=sequence,
                                       helpers_fingerprint="b" * 64, root_files=[], source=source,
                                       set_sha256=sha(set_bytes)), **changes}
    return up.sign_envelope(json.dumps(payload, separators=(",", ":")).encode(), key.private)


@pytest.fixture
def released(tmp_path, repo, key):
    """The previous release: a packed Windows stage at `repo.previous` and its signed manifest."""
    stage = make_stage(tmp_path / "dist-previous", repo.previous, "windows", key, date="20261101")
    previous_build = build_tree(tmp_path, repo, repo.previous, "build-previous")
    result = run_pack(stage, tmp_path / "out-previous", repo, build=previous_build)
    content_set = set_of(result)
    data = result.set_path.read_bytes()
    manifest = tmp_path / "previous-windows.json"
    manifest.write_bytes(manifest_bytes(key, content_set, data))
    return types.SimpleNamespace(stage=stage, result=result, set=content_set, set_bytes=data, manifest=manifest)


# --- Pack: valid set and plan ---------------------------------------------------------

def test_fixture_stage_gives_a_valid_set_and_upload_plan(tmp_path, repo, key, build, capsys):
    stage = make_stage(tmp_path / "dist", repo.commit, "windows", key)
    result = run_pack(stage, tmp_path / "out", repo, build=build)
    assert result.ok and result.plan_path == tmp_path / "out" / "upload-plan.json"
    content_set = set_of(result)
    summary = r2.validate_set(content_set, public_key_sha256=sha(key.public), commit=repo.commit,
                              platform="windows", source="r2", reader_cap=r2.READER_CAP_W1A)
    assert summary == result.summary
    assert content_set["version"] == stage.name and content_set["public_key_sha256"] == sha(key.public)
    assert content_set["asset_base"] == r2.DESKTOP_ASSETS and content_set["optional_packages"] == []
    paths = {entry["path"] for row in content_set["packages"] for entry in row["files"]}
    assert paths == set(CONTENT) | {"app/client-release.json", "app/data/client_release.json"}
    assert {row["id"] for row in content_set["packages"]} >= {"client", "release-descriptor"}
    for row in content_set["packages"]:
        for part in row["parts"]:
            assert part["url"] == r2.part_url(part["sha256"])
    # The plan is exactly the uploader's contract, checked by the uploader's own loader.
    plan = up.load_plan(result.plan_path, public_key_sha256=sha(key.public))
    assert plan.set_sha256 == result.set_sha256 == sha(result.set_path.read_bytes())
    assert {row.sha256 for row in plan.rows} == all_parts(content_set)
    for row in plan.rows:
        assert row.kind == "new" and row.path.parent == tmp_path / "out" / "parts"
        assert row.path.stat().st_size == row.size and sha(row.path.read_bytes()) == row.sha256
    document = plan_of(result)
    assert all(row["local_path"].startswith("parts/RabbitLands-pkg-") for row in document["rows"])
    assert [row["key"] for row in document["rows"]] == sorted(row["key"] for row in document["rows"])
    printed = capsys.readouterr().out
    assert result.dispatch == {"windows_source": "r2", "windows_set_sha256": result.set_sha256}
    receipt = json.loads((tmp_path / "out" / "pack-receipt.json").read_text())
    assert receipt["result"] == "complete" and receipt["set_sha256"] == result.set_sha256
    assert sorted(entry["path"] for entry in receipt["ci_files"]) == sorted(CI_FILES)
    assert set(ROOT_FILES) | {".eloria-package"} <= set(receipt["root_files"])
    assert printed == ""  # pack() itself is quiet; the CLI prints


def test_ci_paths_and_root_files_are_excluded_through_a_hard_link_view(tmp_path, key, repo):
    # A case variant of a CI folder is CI-owned too (NTFS keeps the first spelling, so no other CI files here).
    ci = {"app/RabbitLands.exe": CI_FILES["app/RabbitLands.exe"], "app/bin/Client_Runtime/extra.json": b"{}"}
    stage = make_stage(tmp_path / "dist", repo.commit, "windows", key, ci=ci,
                       extra={"app/RabbitLands.EXE.txt": b"not ci"})
    view = tmp_path / "view"
    info = dc.make_view(stage, view)
    linked = {path.relative_to(view).as_posix() for path in view.rglob("*") if path.is_file()}
    expected = (set(CONTENT) | {"app/client-release.json", "app/data/client_release.json", "app/RabbitLands.EXE.txt"})
    assert linked == expected | {dc.VIEW_MARKER}
    assert info["files"] == len(expected)
    assert info["ci_files"] == sorted(ci)
    for relative in expected:
        source, link = os.stat(stage / relative), os.stat(view / relative)
        assert (link.st_dev, link.st_ino) == (source.st_dev, source.st_ino)  # a link, not a copy
        assert source.st_nlink == 2
    for name in ROOT_FILES:
        assert not (view / name).exists()
    before = tree(stage)
    assert dc.remove_view(view) and not view.exists()
    assert tree(stage) == before
    assert all(os.stat(stage / relative).st_nlink == 1 for relative in expected)


def test_view_refuses_links_and_another_volume(tmp_path, key, repo, monkeypatch):
    stage = make_stage(tmp_path / "dist", repo.commit, "windows", key)
    import release_storage

    def cross_device(source, target):
        raise OSError(18, "Invalid cross-device link")
    monkeypatch.setattr(release_storage, "link_file", cross_device)
    with pytest.raises(dc.ContentError) as caught:
        dc.make_view(stage, tmp_path / "view")
    assert caught.value.code == "view-link"


def directory_link(link: Path, target: Path) -> None:
    """A junction on Windows (no privilege needed), a symlink elsewhere."""
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def test_removing_a_view_never_follows_a_link(tmp_path, capsys):
    # A stale marked view that now holds a junction into other files: os.walk
    # descends into junctions, so a blind unlink pass would delete them.
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "precious.txt").write_bytes(b"keep")
    parts = tmp_path / "parts"
    view = parts / ".v0123abcd"
    (view / "app").mkdir(parents=True)
    (view / dc.VIEW_MARKER).write_bytes(b"")
    (view / "app" / "file.bin").write_bytes(b"x")
    directory_link(view / "app" / "linked", victim)
    assert dc._is_link(view / "app" / "linked")
    assert dc.remove_view(view) is False
    assert (victim / "precious.txt").read_bytes() == b"keep"
    assert dc.clean_stale(parts) == 1 and "could not remove the old view" in capsys.readouterr().err
    assert (victim / "precious.txt").read_bytes() == b"keep" and (view / "app" / "file.bin").is_file()
    # A view that is itself a link is never entered either.
    linked_view = parts / ".v89abcdef"
    directory_link(linked_view, view)
    assert dc.remove_view(linked_view) is False and (view / dc.VIEW_MARKER).is_file()
    for link in (linked_view, view / "app" / "linked"):  # remove the links themselves, never their targets
        if os.name == "nt":
            os.rmdir(link)
        else:
            os.unlink(link)
    assert (victim / "precious.txt").is_file() and dc.remove_view(view) and not view.exists()


def test_a_view_file_that_vanishes_during_the_pack_is_refused(tmp_path, repo, key, build, monkeypatch):
    import asset_packages
    original = asset_packages.build

    def build_after_a_removal(view, *args, **kwargs):
        (view / "app/assets/ui/icon.png").unlink()  # e.g. another run's clean-up of this view
        return original(view, *args, **kwargs)
    monkeypatch.setattr(asset_packages, "build", build_after_a_removal)
    stage = make_stage(tmp_path / "dist", repo.commit, "windows", key)
    with pytest.raises(dc.ContentError) as caught:
        run_pack(stage, tmp_path / "out", repo, build=build)
    assert caught.value.code == "view-changed"
    out = tmp_path / "out"
    assert not (out / "set.json").exists() and not (out / "upload-plan.json").exists()
    assert (stage / "app/assets/ui/icon.png").is_file()  # only the view's link was removed


def test_pack_leaves_the_stage_unchanged_and_removes_its_view(tmp_path, repo, key, build):
    stage = make_stage(tmp_path / "dist", repo.commit, "windows", key)
    before = tree(stage)
    run_pack(stage, tmp_path / "out", repo, build=build)
    assert tree(stage) == before
    assert not [entry for entry in (tmp_path / "out" / "parts").iterdir() if entry.name.startswith(".v")]
    assert all(os.stat(path).st_nlink == 1 for path in stage.rglob("*") if path.is_file())


def test_rerun_is_byte_identical(tmp_path, repo, key, build):
    stage = make_stage(tmp_path / "dist", repo.commit, "windows", key)
    first = run_pack(stage, tmp_path / "out", repo, build=build)
    set_bytes, plan_bytes = first.set_path.read_bytes(), first.plan_path.read_bytes()
    stamp = first.set_path.stat().st_mtime_ns
    # An interrupted earlier run left a temporary part and a marked view behind.
    parts = tmp_path / "out" / "parts"
    (parts / ".v0123abcd.pkg.audio-01.zip.001").write_bytes(b"partial")
    (parts / ".v89abcdef").mkdir()
    (parts / ".v89abcdef" / dc.VIEW_MARKER).write_bytes(b"")
    second = run_pack(stage, tmp_path / "out", repo, build=build)
    assert second.set_path.read_bytes() == set_bytes and second.plan_path.read_bytes() == plan_bytes
    assert second.set_sha256 == first.set_sha256 and first.set_path.stat().st_mtime_ns == stamp
    assert sorted(entry.name for entry in parts.iterdir() if entry.name.startswith(".")) == []
    # A second output folder from the same inputs is byte-identical too.
    third = run_pack(stage, tmp_path / "out-again", repo, build=build)
    assert third.set_path.read_bytes() == set_bytes and third.plan_path.read_bytes() == plan_bytes


def test_url_rewrite_is_idempotent_and_ci_keeps_pool_urls(tmp_path, repo, key, build):
    stage = make_stage(tmp_path / "dist", repo.commit, "windows", key)
    result = run_pack(stage, tmp_path / "out", repo, build=build)
    packages = set_of(result)["packages"]
    assert r2.rewrite_part_urls(packages) == packages
    assert r2.rewrite_part_urls(r2.rewrite_part_urls(packages)) == packages
    ci = run_pack(stage, tmp_path / "out-ci", repo, build=build, source="ci")
    ci_set = set_of(ci)
    assert ci.plan_path is None and not (tmp_path / "out-ci" / "upload-plan.json").exists()
    assert ci.dispatch == {} and ci_set["source"] == "ci" and ci_set["asset_base"] == r2.GITHUB_DOWNLOADS
    for row in ci_set["packages"]:
        for part in row["parts"]:
            assert part["url"] == r2.github_pool_url(part["sha256"])
            assert (tmp_path / "out-ci" / "parts" / f"RabbitLands-pkg-{part['sha256']}.zip.part").is_file()
    r2.validate_set(ci_set, public_key_sha256=sha(key.public), source="ci", reader_cap=r2.READER_CAP_W1A)
    # Same files, same bytes: the ci rows differ from the r2 rows only by URL (every fixture
    # package is one part, below both part sizes).
    assert r2.rewrite_part_urls(ci_set["packages"]) == packages
    with pytest.raises(dc.ContentError):
        run_pack(stage, tmp_path / "out-ci", repo, build=build, source="ci", previous="none", probe=FakeProbe())


# --- Reuse --------------------------------------------------------------------------------

def test_reuse_from_the_previous_signed_manifests_content_set(tmp_path, repo, key, build, released):
    changed = {**CONTENT, "app/assets/audio/howl.ogg": b"OggS" + b"A" * 1200}
    stage = make_stage(tmp_path / "dist", repo.commit, "windows", key, content=changed)
    probe = FakeProbe(present=all_parts(released.set))
    result = run_pack(stage, tmp_path / "out", repo, build=build, previous=str(released.manifest),
                      previous_set_file=released.result.set_path, probe=probe)
    content_set = set_of(result)
    previous = {row["id"]: row for row in released.set["packages"]}
    rows = {row["id"]: row for row in content_set["packages"]}
    reused = {pid for pid in rows if rows[pid] == previous.get(pid)}
    assert reused == set(rows) - {"release-descriptor", package(content_set, "audio")["id"]}
    plan = plan_of(result)
    kinds = {row["sha256"]: row["kind"] for row in plan["rows"]}
    for pid in reused:
        assert all(kinds[part["sha256"]] == "reused" for part in rows[pid]["parts"])
        for part in rows[pid]["parts"]:
            assert not (tmp_path / "out" / "parts" / f"RabbitLands-pkg-{part['sha256']}.zip.part").exists()
    for pid in set(rows) - reused:
        assert all(kinds[part["sha256"]] == "new" for part in rows[pid]["parts"])
    assert result.counts["reused"] == len(reused) and result.counts["new"] == len(rows) - len(reused)
    assert set(probe.calls) == all_parts(released.set)  # every candidate part was HEADed, nothing else
    up.load_plan(result.plan_path, public_key_sha256=sha(key.public))
    receipt = json.loads((tmp_path / "out" / "pack-receipt.json").read_text())
    assert receipt["previous"]["rows"] == "content-set" and receipt["previous"]["commit"] == repo.previous


def test_a_missing_part_means_rebuild_and_identical_bytes(tmp_path, repo, key, build, released):
    stage = make_stage(tmp_path / "dist", repo.commit, "windows", key)
    actors = package_with(released.set, "app/assets/actors/wolf/grey/wolf.glb")
    missing = {part["sha256"] for part in actors["parts"]}
    result = run_pack(stage, tmp_path / "out", repo, build=build, previous=str(released.manifest),
                      previous_set_file=released.result.set_path,
                      probe=FakeProbe(present=all_parts(released.set), missing=missing))
    rows = {row["id"]: row for row in set_of(result)["packages"]}
    assert rows[actors["id"]] == actors  # rebuilt, and deterministic: the same package bytes
    kinds = {row["sha256"]: row for row in plan_of(result)["rows"]}
    for digest in missing:
        assert kinds[digest]["kind"] == "new" and kinds[digest]["local_path"].endswith(f"{digest}.zip.part")


def test_previous_from_the_live_pointer_chain(tmp_path, repo, key, build, released):
    manifest = released.manifest.read_bytes()
    pointer = r2.pointer_payload(platform="windows", sequence=SEQUENCE + 100, rollback=False, release_id=7,
                                 run_id=8, commit=repo.previous, version=released.set["version"],
                                 manifest_sequence=SEQUENCE, manifest_sha256=sha(manifest),
                                 manifest_size=len(manifest))
    http = FakeHttp({r2.pointer_url("windows"): up.sign_envelope(r2.pointer_bytes(pointer), key.private),
                     r2.manifest_url("windows", sha(manifest)): manifest,
                     r2.set_url("windows", sha(released.set_bytes)): released.set_bytes})
    stage = make_stage(tmp_path / "dist", repo.commit, "windows", key)
    result = run_pack(stage, tmp_path / "out", repo, build=build, previous="live", http=http,
                      probe=FakeProbe(present=all_parts(released.set)))
    assert result.counts["reused"] == len(released.set["packages"]) - 1  # all but the release descriptor
    expected = [r2.pointer_url("windows"), r2.manifest_url("windows", sha(manifest)),
                r2.set_url("windows", sha(released.set_bytes))]
    assert [url for _, url in http.calls] == expected  # .json only: never edge-cached, no part GET
    receipt = json.loads((tmp_path / "out" / "pack-receipt.json").read_text())
    assert receipt["previous"]["source"] == "live" and receipt["previous"]["pointer_sequence"] == SEQUENCE + 100
    with pytest.raises(dc.ContentError) as caught:
        run_pack(stage, tmp_path / "out-2", repo, build=build, previous="live", http=FakeHttp(),
                 probe=FakeProbe())
    assert caught.value.code == "live-pointer-missing"


def test_previous_refusals(tmp_path, repo, key, other_key, build, released):
    stage = make_stage(tmp_path / "dist", repo.commit, "windows", key)
    probe = FakeProbe(present=all_parts(released.set))

    def refused(manifest_data, set_data=None, **options):
        manifest = tmp_path / f"manifest-{len(list(tmp_path.glob('manifest-*')))}.json"
        manifest.write_bytes(manifest_data)
        set_file = None
        if set_data is not None:
            set_file = manifest.with_suffix(".set")
            set_file.write_bytes(set_data)
        with pytest.raises(r2.DesktopR2Error) as caught:
            run_pack(stage, tmp_path / "out", repo, build=build, previous=str(manifest), previous_set_file=set_file,
                     probe=probe, **options)
        return caught.value.code

    signed_by_other = manifest_bytes(other_key, released.set, released.set_bytes)
    assert refused(signed_by_other, released.set_bytes) == "signature"
    tampered = json.loads(released.set_bytes)
    tampered["packages"][0]["size"] += 0  # same rows, re-serialised pretty: not canonical
    assert refused(released.manifest.read_bytes(), json.dumps(tampered, indent=1).encode()) == "previous-set-sha256"
    rows = json.loads(json.dumps(released.set["packages"]))
    rows[0]["files"][0]["sha256"] = "0" * 64
    assert refused(manifest_bytes(key, released.set, released.set_bytes, packages=rows),
                   released.set_bytes) == "previous-set-mismatch"
    linux = dict(released.set, platform="linux", version=released.set["version"].replace("Windows", "Linux"))
    assert refused(manifest_bytes(key, linux, released.set_bytes), released.set_bytes) == "previous-manifest"
    assert refused(manifest_bytes(key, released.set, released.set_bytes, schema=2), released.set_bytes) \
        == "previous-manifest"
    # A ci release keeps its set as an artifact: its signed rows are used, without a set.
    ci = manifest_bytes(key, released.set, released.set_bytes, source="ci")
    manifest = tmp_path / "ci-manifest.json"
    manifest.write_bytes(ci)
    result = run_pack(stage, tmp_path / "out-ci", repo, build=build, previous=str(manifest), probe=probe)
    assert result.counts["reused"] == len(released.set["packages"]) - 1
    broken = json.loads(json.dumps(released.set["packages"]))
    broken[0]["parts"] = [{"url": "x", "size": 0, "sha256": "a" * 64}]
    broken_manifest = manifest_bytes(key, released.set, released.set_bytes, source="ci", packages=broken)
    assert refused(broken_manifest) == "previous-rows"
    # Reuse needs a probe; a set file needs a previous release.
    with pytest.raises(dc.ContentError):
        run_pack(stage, tmp_path / "out-x", repo, build=build, previous=str(released.manifest))
    with pytest.raises(dc.ContentError):
        run_pack(stage, tmp_path / "out-x", repo, build=build, previous_set_file=released.result.set_path,
                 probe=probe)


def test_cross_platform_reuse_set(tmp_path, repo, key, build, released):
    windows = run_pack(make_stage(tmp_path / "dist", repo.commit, "windows", key), tmp_path / "out-windows", repo,
                       build=build)
    windows_set = set_of(windows)
    linux_stage = make_stage(tmp_path / "dist-linux", repo.commit, "linux", key,
                             ci={"app/RabbitLands.x86_64": b"\x7fELF" + b"\0" * 60})
    probe = FakeProbe(present=all_parts(windows_set))
    result = run_pack(linux_stage, tmp_path / "out-linux", repo, platform="linux", build=build,
                      reuse_set=windows.set_path, probe=probe)
    linux_set = set_of(result)
    assert linux_set["platform"] == "linux" and linux_set["version"] == linux_stage.name
    shared = {row["id"]: row for row in windows_set["packages"]}
    rows = {row["id"]: row for row in linux_set["packages"]}
    assert {pid for pid in rows if rows[pid] == shared.get(pid)} == set(rows) - {"release-descriptor"}
    assert result.counts["reused"] == len(rows) - 1
    assert linux_set["builder"]["local_engine_sha256"] == sha(b"\x7fELF" + b"\0" * 60)
    # The other platform's set must be of the same commit.
    with pytest.raises(r2.DesktopR2Error) as caught:
        run_pack(linux_stage, tmp_path / "out-linux", repo, platform="linux", build=build,
                 reuse_set=released.result.set_path, probe=probe)
    assert caught.value.code == "commit"
    pretty = tmp_path / "pretty.json"
    pretty.write_text(json.dumps(windows_set, indent=1))
    with pytest.raises(r2.DesktopR2Error) as caught:
        run_pack(linux_stage, tmp_path / "out-linux", repo, platform="linux", build=build, reuse_set=pretty,
                 probe=probe)
    assert caught.value.code == "set-not-canonical"


def test_disagreeing_candidates_pick_the_one_equal_to_the_local_files(tmp_path, repo, key, build):
    # Previous Linux release (old audio) and this commit's Windows set (new audio) both offer "audio".
    old_build = build_tree(tmp_path, repo, repo.previous, "build-previous")
    old_stage = make_stage(tmp_path / "dist-old", repo.previous, "linux", key, date="20261101")
    old = run_pack(old_stage, tmp_path / "out-old", repo, platform="linux", build=old_build)
    old_set = set_of(old)
    manifest = tmp_path / "old-linux.json"
    manifest.write_bytes(manifest_bytes(key, old_set, old.set_path.read_bytes()))
    new_audio = {**CONTENT, "app/assets/audio/howl.ogg": b"OggS" + b"N" * 900}
    windows = run_pack(make_stage(tmp_path / "dist-win", repo.commit, "windows", key, content=new_audio),
                       tmp_path / "out-win", repo, build=build)
    windows_set = set_of(windows)
    stage = make_stage(tmp_path / "dist-linux", repo.commit, "linux", key, content=new_audio)
    probe = FakeProbe(present=all_parts(windows_set) | all_parts(old_set))
    result = run_pack(stage, tmp_path / "out-linux", repo, platform="linux", build=build,
                      previous=str(manifest), previous_set_file=old.set_path, reuse_set=windows.set_path,
                      probe=probe)
    rows = {row["id"]: row for row in set_of(result)["packages"]}
    audio = package(windows_set, "audio")
    assert package(old_set, "audio")["id"] == audio["id"] and package(old_set, "audio") != audio
    assert rows[audio["id"]] == audio
    kinds = {row["sha256"]: row["kind"] for row in plan_of(result)["rows"]}
    assert all(kinds[part["sha256"]] == "reused" for part in audio["parts"])


def test_probes(tmp_path):
    part = {"url": r2.part_url("a" * 64), "size": 5, "sha256": "a" * 64}
    headers = r2.object_headers(r2.part_key("a" * 64), "a" * 64)

    class Bucket:
        selftest = False

        def __init__(self, head):
            self.value, self.keys = head, []

        def head(self, key):
            self.keys.append(key)
            if isinstance(self.value, Exception):
                raise self.value
            return self.value
    good = {"ContentLength": 5, "Metadata": {"sha256": "a" * 64}, **headers}
    bucket = Bucket(good)
    assert dc.S3Probe(bucket).available(part) and bucket.keys == [r2.part_key("a" * 64)]
    assert not dc.S3Probe(Bucket(None)).available(part)
    assert not dc.S3Probe(Bucket({**good, "ContentLength": 6})).available(part)
    with pytest.raises(up.SdkError):
        dc.S3Probe(Bucket(up.SdkError("HeadObject", "AccessDenied", 403))).available(part)
    http = FakeHttp({part["url"]: b"12345"})
    assert dc.PublicProbe(http).available(part) and http.calls == [("HEAD", part["url"])]
    ci_row = {**part, "url": r2.github_pool_url("a" * 64)}
    assert not dc.PublicProbe(http).available(ci_row) and len(http.calls) == 1  # only derived R2 rows are HEADed
    assert not dc.PublicProbe(FakeHttp()).available(part)
    assert not dc.PublicProbe(FakeHttp({part["url"]: b"1234"})).available(part)
    with pytest.raises(dc.ContentError) as caught:
        dc.PublicProbe(FakeHttp(statuses={part["url"]: 403})).available(part)
    assert caught.value.code == "probe-public"


def test_the_s3_probe_client_can_only_head(tmp_path, monkeypatch):
    guard = dc.HeadOnlyGuard(bucket=r2.BUCKET)
    key = r2.part_key("a" * 64)
    assert guard.inspect("HeadObject", {"Bucket": r2.BUCKET, "Key": key}) == {"operation": "HeadObject", "key": key}
    writes = {"Bucket": r2.BUCKET, "Key": key, "Body": b"x", "ContentLength": 1, "IfNoneMatch": "*"}
    for name, params in (("PutObject", writes), ("GetObject", {"Bucket": r2.BUCKET, "Key": key}),
                         ("ListObjectsV2", {"Bucket": r2.BUCKET, "Prefix": "desktop/v1/parts/"}),
                         ("DeleteObject", {"Bucket": r2.BUCKET, "Key": key})):
        with pytest.raises(up.GuardError) as caught:
            guard.inspect(name, params)
        assert caught.value.code == "sdk-operation"
    with pytest.raises(up.GuardError) as caught:  # the uploader's key guard still applies
        guard.inspect("HeadObject", {"Bucket": r2.BUCKET, "Key": "browser/assets/x.bin"})
    assert caught.value.code == "sdk-key"
    # --probe s3 builds its client with this guard (no SDK or credential needed here).
    seen = {}
    monkeypatch.setattr(up, "load_config", lambda path: types.SimpleNamespace(bucket=r2.BUCKET))
    monkeypatch.setattr(up, "create_client", lambda config, sdk_guard: seen.setdefault("guard", sdk_guard))
    args = dc.build_parser().parse_args(["pack", "--stage", "s", "--platform", "windows", "--out", "o",
                                         "--previous", "live", "--probe", "s3", "--credentials", "c.json"])
    probe = dc._probe_from_arguments(args, None)
    assert isinstance(probe, dc.S3Probe) and type(seen["guard"]) is dc.HeadOnlyGuard


# --- Provenance -------------------------------------------------------------------------------

def test_provenance_block_is_present(tmp_path, repo, key, build):
    godot = tmp_path / "Godot.exe"
    godot.write_bytes(b"editor")
    stage = make_stage(tmp_path / "dist", repo.commit, "windows", key)
    result = run_pack(stage, tmp_path / "out", repo, build=build, godot=godot)
    builder = set_of(result)["builder"]
    assert builder["mode"] == "release" and builder["tools_commit"] == git(repo.path, "rev-parse", "HEAD")
    assert builder["tools_dirty"] is False and builder["tools_on_origin"] is True
    assert len(builder["import_cache_digest"]) == 64 and builder["import_cache_files"] == 3
    assert builder["godot_editor_sha256"] == sha(b"editor") and builder["release_build"] is True
    assert builder["package_format"] == "deflate1"
    assert builder["local_engine_sha256"] == sha(CI_FILES["app/RabbitLands.exe"])
    assert builder["local_native_library_sha256"] == sha(CI_FILES["app/bin/client_runtime/client_runtime.dll"])
    qualification = set_of(result)["qualification"]
    assert qualification["smoke"] == ["legacy", "human-testing"] and qualification["split_pck"] is False
    assert len(qualification["optimization_proof_sha256"]) == 64
    # The digest follows the import cache (paths, sizes, mtimes), and so does the set.
    cache = build / "godot-client" / ".godot" / "imported" / "wolf.glb-0123.scn"
    later = cache.stat().st_mtime_ns + 5 * 10 ** 9
    os.utime(cache, ns=(later, later))
    again = run_pack(stage, tmp_path / "out", repo, build=build, godot=godot)
    assert set_of(again)["builder"]["import_cache_digest"] != builder["import_cache_digest"]
    assert again.set_sha256 != result.set_sha256
    assert up.load_plan(again.plan_path, public_key_sha256=sha(key.public)).set_sha256 == again.set_sha256


def test_split_pck_is_recorded(tmp_path, repo, key, build):
    stage = make_stage(tmp_path / "dist", repo.commit, "windows", key,
                       extra={"app/packs/world-a.pck": b"GDPC" + b"x" * 400})
    assert set_of(run_pack(stage, tmp_path / "out", repo, build=build))["qualification"]["split_pck"] is True


def test_a_dirty_or_non_origin_tools_tree_is_refused(tmp_path, repo, key, build):
    stage = make_stage(tmp_path / "dist", repo.commit, "windows", key)

    def code():
        with pytest.raises(dc.ContentError) as caught:
            run_pack(stage, tmp_path / "out", repo, build=build)
        return caught.value.code
    notes = repo.path / "godot-client/data/notes.txt"
    notes.write_bytes(b"edited\n")
    assert code() == "tools-dirty"
    git(repo.path, "checkout", "-q", "--", "godot-client/data/notes.txt")
    (repo.path / "untracked.py").write_bytes(b"")
    assert code() == "tools-dirty"
    (repo.path / "untracked.py").unlink()
    # A local commit that origin does not have.
    commit_file(repo.path, "godot-client/data/local.txt", b"local\n", "unpublished")
    assert code() == "tools-not-on-origin"
    git(repo.path, "push", "-q", "origin", "develop")
    git(repo.path, "fetch", "-q", "origin")
    run_pack(stage, tmp_path / "out", repo, build=build)
    # An origin that is not the client repository.
    git(repo.path, "remote", "set-url", "origin", (tmp_path / "remote" / "someone-else.git").as_posix())
    assert code() == "tools-not-on-origin"
    git(repo.path, "remote", "set-url", "origin", repo.remote.as_posix())
    # Packaging modules that differ from the packaged commit's.
    commit_file(repo.path, "godot-client/tools/asset_packages.py", b"# changed ids\n", "packaging change")
    git(repo.path, "push", "-q", "origin", "develop")
    git(repo.path, "fetch", "-q", "origin")
    assert code() == "tools-packaging-drift"
    # A tools commit that does not contain the packaged commit.
    git(repo.path, "checkout", "-q", "--detach", repo.previous)
    assert code() == "tools-lack-commit"
    git(repo.path, "checkout", "-q", "develop")
    # A commit the tools checkout does not have at all.
    unknown = "1234567" + "0" * 33
    lost = make_stage(tmp_path / "dist-lost", unknown, "windows", key)
    with pytest.raises(dc.ContentError) as caught:
        run_pack(lost, tmp_path / "out-lost", repo, build=build)
    assert caught.value.code == "tools-missing-commit"


def test_dev_mode_admits_a_dirty_tree_records_it_and_writes_no_plan(tmp_path, repo, key, build):
    stage = make_stage(tmp_path / "dist", repo.commit, "windows", key, release_build=False, qualified=False)
    first = run_pack(stage, tmp_path / "out", repo, build=build, dev=True)
    assert first.plan_path is None
    (repo.path / "godot-client/data/notes.txt").write_bytes(b"edited\n")
    result = run_pack(stage, tmp_path / "out", repo, dev=True)
    content_set = set_of(result)
    assert result.plan_path is None and not (tmp_path / "out" / "upload-plan.json").exists()
    builder = content_set["builder"]
    assert builder["mode"] == "dev" and builder["tools_dirty"] is True and builder["release_build"] is False
    assert builder["import_cache_digest"] is None
    assert content_set["qualification"] == {"optimization_proof_sha256": None, "smoke": [], "split_pck": False}
    receipt = json.loads((tmp_path / "out" / "pack-receipt.json").read_text())
    assert {"tools-dirty", "stage-not-release-build", "qualification-proof"} <= set(receipt["dev_problems"])
    # A release-mode plan never outlives its set: a later dev run removes it.
    git(repo.path, "checkout", "-q", "--", "godot-client/data/notes.txt")
    release = make_stage(tmp_path / "dist-release", repo.commit, "windows", key)
    run_pack(release, tmp_path / "out-release", repo, build=build)
    assert (tmp_path / "out-release" / "upload-plan.json").is_file()
    (repo.path / "untracked.txt").write_bytes(b"")
    run_pack(release, tmp_path / "out-release", repo, build=build, dev=True)
    assert not (tmp_path / "out-release" / "upload-plan.json").exists()


def test_import_cache_rules(tmp_path, repo, key, build):
    stage = make_stage(tmp_path / "dist", repo.commit, "windows", key)
    with pytest.raises(dc.ContentError) as caught:
        run_pack(stage, tmp_path / "out", repo)
    assert caught.value.code == "import-cache-required"
    other = build_tree(tmp_path, repo, repo.previous, "build-other")
    with pytest.raises(dc.ContentError) as caught:
        run_pack(stage, tmp_path / "out", repo, build=other)
    assert caught.value.code == "build-dir-commit"


# --- Stage identity and qualification -------------------------------------------------------------

@pytest.mark.parametrize("change, code", [
    ({"commit": "0" * 40}, "stage-identity"),
    ({"repository": "someone/else"}, "stage-identity"),
    ({"distribution": "steam"}, "stage-distribution"),
    ({"release_build": False}, "stage-not-release-build"),
    ({"public_key": "-----BEGIN PUBLIC KEY-----\nAAAA\n-----END PUBLIC KEY-----\n"}, "stage-public-key"),
    ({"schema": 2}, "stage-descriptor"),
    ({"schema": True}, "stage-descriptor"),
])
def test_stage_identity_refusals(tmp_path, repo, key, build, change, code):
    stage = make_stage(tmp_path / "dist", repo.commit, "windows", key, identity=change)
    with pytest.raises(dc.ContentError) as caught:
        run_pack(stage, tmp_path / "out", repo, build=build)
    assert caught.value.code == code
    assert not (tmp_path / "out").exists()  # refused before any output


def test_stage_name_marker_and_copy_refusals(tmp_path, repo, key, build):
    stage = make_stage(tmp_path / "dist", repo.commit, "windows", key)
    with pytest.raises(dc.ContentError) as caught:
        run_pack(stage, tmp_path / "out", repo, platform="linux", build=build)
    assert caught.value.code == "stage-name"
    (stage / "app/data/client_release.json").write_bytes(b"{}")
    with pytest.raises(dc.ContentError) as caught:
        run_pack(stage, tmp_path / "out", repo, build=build)
    assert caught.value.code == "stage-descriptor"
    renamed = stage.with_name(stage.name.replace(repo.commit[:9], repo.previous[:9]))
    stage.rename(renamed)
    with pytest.raises(dc.ContentError) as caught:
        run_pack(renamed, tmp_path / "out", repo, build=build)
    assert caught.value.code == "stage-name"
    (renamed / ".eloria-package").write_text("not a commit\n")
    with pytest.raises(dc.ContentError) as caught:
        run_pack(renamed, tmp_path / "out", repo, build=build)
    assert caught.value.code == "stage-marker"


def test_qualification_refusals(tmp_path, repo, key, build):
    stage = make_stage(tmp_path / "dist", repo.commit, "windows", key, qualified=False)

    def code():
        with pytest.raises(dc.ContentError) as caught:
            run_pack(stage, tmp_path / "out", repo, build=build)
        return caught.value.code
    assert code() == "qualification-proof"
    logs = qualify(stage, repo.previous, "windows")
    assert code() == "qualification-proof-identity"
    qualify(stage, repo.commit, "windows", status="failed")
    assert code() == "qualification-proof-identity"
    qualify(stage, repo.commit, "windows")
    (logs / "smoke-human-testing.log").unlink()
    assert code() == "qualification-smoke"
    qualify(stage, repo.commit, "windows")
    # A later (failed) rebuild of the stage rewrote the marker after the proof.
    marker = stage / ".eloria-package"
    later = (logs / "optimization-proof.json").stat().st_mtime_ns + 10 ** 9
    os.utime(marker, ns=(later, later))
    assert code() == "qualification-proof-stale"
    moved = tmp_path / "moved-logs"
    qualify(stage, repo.commit, "windows")
    os.utime(marker, ns=(later - 120 * 10 ** 9, later - 120 * 10 ** 9))
    os.rename(logs, moved)
    assert code() == "qualification-proof"
    assert run_pack(stage, tmp_path / "out", repo, build=build, logs=moved).ok


# --- Hygiene, privacy and output locations ------------------------------------------------------

@pytest.mark.parametrize("extra, code", [
    ({"app/assets/ui/evil.png": b"\x7fELF" + b"\0" * 60}, "native-magic"),
    ({"app/assets/ui/macho.bin": bytes.fromhex("cffaedfe") + b"\0" * 60}, "native-magic"),
    ({"app/assets/ui/helper.dll": b"data"}, "native-extension"),
    ({"app/override.cfg": b"[application]\n"}, "engine-file"),
    ({"app/assets/ui/extra.gdextension": b"[configuration]\n"}, "gdextension"),
    ({"app/assets/ui/caf\u00e9.png": b"png"}, "path-ascii"),
])
def test_executable_code_and_path_hygiene(tmp_path, repo, key, build, extra, code):
    stage = make_stage(tmp_path / "dist", repo.commit, "windows", key, extra=extra)
    with pytest.raises(r2.SetError) as caught:
        run_pack(stage, tmp_path / "out", repo, build=build)
    assert caught.value.code == code
    out = tmp_path / "out"
    assert not (out / "set.json").exists() and not (out / "upload-plan.json").exists()
    assert not [entry for entry in (out / "parts").iterdir() if entry.name.startswith(".v")]
    assert json.loads((out / "pack-receipt.json").read_text())["result"] == "failed"


def test_set_has_no_absolute_paths_or_user_names(tmp_path, repo, key, build):
    stage = make_stage(tmp_path / "dist", repo.commit, "windows", key)
    result = run_pack(stage, tmp_path / "out", repo, build=build)
    text = result.set_path.read_bytes().decode("ascii")
    folded = text.casefold()
    for value in (str(tmp_path), tmp_path.as_posix(), str(Path.home()), Path.home().as_posix(), str(TOOLS),
                  TOOLS.as_posix(), "\\", "c:/", "/users/", "/home/", "appdata", "pytest"):
        assert value.casefold() not in folded, value
    user = getpass.getuser()
    assert len(user) < 3 or user.casefold() not in folded
    assert not re.search(r"[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:", text)  # no timestamps
    assert re.findall(r"20[0-9]{6}", text) == ["20261104"]  # the only date is the stage version's
    plan = result.plan_path.read_text()
    assert str(tmp_path) not in plan and tmp_path.as_posix() not in plan


def test_privacy_check_refuses_a_local_path(tmp_path):
    with pytest.raises(dc.ContentError) as caught:
        dc._privacy_check(json.dumps({"note": f"{tmp_path.as_posix()}/x"}).encode(), (tmp_path,))
    assert caught.value.code == "set-local-path"


def test_output_location_rules(tmp_path, repo, key, build):
    stage = make_stage(tmp_path / "dist", repo.commit, "windows", key)
    worktree = tmp_path / "checkout"
    worktree.mkdir()
    git(worktree, "init", "-q")
    with pytest.raises(r2.DesktopR2Error) as caught:
        run_pack(stage, worktree / "out", repo, build=build)
    assert caught.value.code == "out-location"
    (worktree / ".gitignore").write_text("ignored/\n")
    assert run_pack(stage, worktree / "ignored" / "out", repo, build=build).ok
    with pytest.raises(dc.ContentError) as caught:
        run_pack(stage, stage / "app" / "out", repo, build=build)
    assert caught.value.code == "out-location"
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "other.txt").write_text("x")
    with pytest.raises(dc.ContentError) as caught:
        run_pack(stage, busy, repo, build=build)
    assert caught.value.code == "out-not-empty"
    run_pack(stage, tmp_path / "out-ci", repo, build=build, source="ci")
    with pytest.raises(dc.ContentError) as caught:
        run_pack(stage, tmp_path / "out-ci", repo, build=build)
    assert caught.value.code == "out-other"
    linux = make_stage(tmp_path / "dist-linux", repo.commit, "linux", key)
    run_pack(linux, tmp_path / "out-linux", repo, platform="linux", build=build)
    with pytest.raises(dc.ContentError) as caught:
        run_pack(stage, tmp_path / "out-linux", repo, build=build)
    assert caught.value.code == "out-other"


# --- Compare --------------------------------------------------------------------------------------

def test_compare_reports_installed_file_drift_against_a_signed_manifest(tmp_path, repo, key, other_key, build):
    stage = make_stage(tmp_path / "dist", repo.commit, "windows", key)
    result = run_pack(stage, tmp_path / "out", repo, build=build)
    content_set = set_of(result)
    reference = manifest_bytes(key, content_set, result.set_path.read_bytes())
    report = dc.compare(stage, platform="windows", reference=reference, kind="manifest", public_pem=key.public)
    files = report["files"]
    assert files["same"] == len(CONTENT) + 2 and not files["changed"] and not files["local_only"]
    assert not files["reference_only"]  # CI paths (engine, runtime) are ignored on both sides
    assert report["packages"]["unchanged"] == len(content_set["packages"])
    assert report["packages"]["download_unpacked_bytes"] == 0 and report["local"]["commit"] == repo.commit
    assert report["reference"]["sha256"] == sha(reference) and report["reference"]["commit"] == repo.commit
    (stage / "app/assets/audio/howl.ogg").write_bytes(b"OggS" + b"Z" * 1000)
    (stage / "app/assets/ui/new.png").write_bytes(b"\x89PNG new")
    (stage / "eloria-assets/maps/meadow/data.json").unlink()
    (stage / "app/RabbitLands.exe").write_bytes(b"MZ another engine")
    report = dc.compare(stage, platform="windows", reference=reference, kind="manifest", public_pem=key.public)
    files = report["files"]
    assert [row["path"] for row in files["changed"]] == ["app/assets/audio/howl.ogg"]
    changed = files["changed"][0]
    assert changed["reference_sha256"] == sha(CONTENT["app/assets/audio/howl.ogg"])
    assert changed["sha256"] == sha(b"OggS" + b"Z" * 1000)
    assert [row["path"] for row in files["local_only"]] == ["app/assets/ui/new.png"]
    assert [row["path"] for row in files["reference_only"]] == ["eloria-assets/maps/meadow/data.json"]
    packages = report["packages"]
    changed_ids = {row["id"] for row in packages["changed"]} | {row["id"] for row in packages["new"]}
    assert package(content_set, "audio")["id"] in changed_ids
    assert packages["unchanged"] < len(content_set["packages"]) and packages["download_unpacked_bytes"] > 0
    with pytest.raises(up.UploadError) as caught:
        dc.compare(stage, platform="windows", reference=reference, kind="manifest", public_pem=other_key.public)
    assert caught.value.code == "signature"
    with pytest.raises(dc.ContentError):
        dc.compare(stage, platform="linux", reference=reference, kind="manifest", public_pem=key.public)


def test_compare_against_a_set(tmp_path, repo, key, build):
    stage = make_stage(tmp_path / "dist", repo.commit, "windows", key)
    result = run_pack(stage, tmp_path / "out", repo, build=build)
    report = dc.compare(stage, platform="windows", reference=result.set_path.read_bytes(), kind="set")
    assert report["reference"]["kind"] == "set" and report["files"]["same"] == len(CONTENT) + 2
    assert report["packages"]["unchanged"] == len(set_of(result)["packages"])


# --- Command line -----------------------------------------------------------------------------------

def test_cli_pack_and_compare(tmp_path, repo, key, build, monkeypatch, capsys):
    monkeypatch.setattr(dc, "TOOLS_REPO", repo.path)
    public = tmp_path / "trust" / "update_public.pem"
    public.parent.mkdir()
    public.write_bytes(key.public)
    monkeypatch.setattr(up, "PUBLIC_KEY_PATH", public)
    stage = make_stage(tmp_path / "dist", repo.commit, "windows", key)
    out = tmp_path / "out"
    assert dc.main(["pack", "--stage", str(stage), "--platform", "windows", "--out", str(out), "--previous", "none",
                    "--build-dir", str(build)]) == 0
    printed = capsys.readouterr().out
    content_set_sha = sha((out / "set.json").read_bytes())
    assert f"windows_source=r2 windows_set_sha256={content_set_sha}" in printed
    assert "upload_desktop_assets.py content --plan" in printed
    manifest = tmp_path / "reference.json"
    manifest.write_bytes(manifest_bytes(key, r2.parse_set_bytes((out / "set.json").read_bytes()),
                                        (out / "set.json").read_bytes()))
    report = tmp_path / "reports" / "compare.json"
    assert dc.main(["compare", "--stage", str(stage), "--platform", "windows", "--manifest", str(manifest),
                    "--report", str(report)]) == 0
    assert json.loads(report.read_text())["kind"] == dc.COMPARE_KIND
    assert "0 changed" in capsys.readouterr().out
    # Refusals exit 2 and print to stderr.
    assert dc.main(["pack", "--stage", str(stage), "--platform", "windows", "--out", str(out),
                    "--previous", "none"]) == 2
    assert "import-cache-required" in capsys.readouterr().err
    for extra in (["--previous", "live"], ["--previous", "none", "--credentials", str(public)],
                  ["--previous", "none", "--probe", "s3"]):
        assert dc.main(["pack", "--stage", str(stage), "--platform", "windows", "--out", str(out),
                        "--build-dir", str(build), *extra]) == 2
    with pytest.raises(SystemExit):
        dc.main(["pack", "--stage", str(stage), "--platform", "windows", "--out", str(out), "--previous", "none",
                 "--workers", "5"])


def test_tool_source_holds_no_machine_paths_and_no_writes_to_r2():
    source = (TOOLS / "desktop_content.py").read_text(encoding="utf-8")
    for fragment in ("C:/", "C:\\", "/Users/", "AppData", "scratchpad", "worktrees/", ".local/browser-prototype"):
        assert fragment not in source, fragment
    for name in ("put_object", "put_immutable", "put_pointer", "upload_content", "delete_object", "run_content",
                 "release_local_parts", "copy_object", ".put(", "Bucket.put"):
        assert name not in source, name
    # The only bucket call is the uploader's reuse check (S3 HEAD through its guarded client).
    assert source.count("up.verify_reused(") == 1 and "bucket.head" not in source.replace("self.bucket", "")
    assert source.isascii()


def test_r2_parts_use_the_r2_part_size_and_ci_parts_keep_theirs(tmp_path, repo, key, build, monkeypatch):
    """R2 content is cut into client_release.R2_PART_BYTES parts (64 MiB, design Q10);
    GitHub-hosted (ci) content keeps client_release.PART_BYTES. Same package bytes."""
    import client_release
    noise = b"".join(hashlib.sha256(str(i).encode()).digest() for i in range(1000))  # 32,000 bytes, incompressible
    stage = make_stage(tmp_path / "dist", repo.commit, "windows", key,
                       content={**CONTENT, "app/RabbitLands.pck": b"GDPC" + noise})
    monkeypatch.setattr(client_release, "R2_PART_BYTES", 4096)
    hosted = set_of(run_pack(stage, tmp_path / "out", repo, build=build))
    ci = set_of(run_pack(stage, tmp_path / "out-ci", repo, build=build, source="ci"))
    pack = next(row for row in hosted["packages"] if row["id"] == "client")
    assert len(pack["parts"]) > 1 and max(part["size"] for part in pack["parts"]) == 4096
    assert all(part["url"] == r2.part_url(part["sha256"]) for part in pack["parts"])
    ci_pack = next(row for row in ci["packages"] if row["id"] == "client")
    assert len(ci_pack["parts"]) == 1 and ci_pack["sha256"] == pack["sha256"]
