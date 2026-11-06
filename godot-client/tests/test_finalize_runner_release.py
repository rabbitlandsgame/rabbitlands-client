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
            "default_features": optimization.DEFAULT_FEATURES, "default_profile": "legacy", "opt_in_profile": "human-testing",
            "receipt_sha256": "1" * 64, "native_source_digest": "2" * 64,
            "catalog_sha256": ("3" if platform == "windows" else "4") * 64,
            "coverage_sha256": "5" * 64, "entries": 6,
            "ordinary_startup_sha256": "6" * 64, "opt_in_startup_sha256": "7" * 64}


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


@pytest.mark.parametrize("problem", ["missing", "unverified", "wrong-platform", "source-mismatch", "coverage-mismatch",
                                     "enabled-default", "missing-opt-in", "old-policy"])
def test_invalid_optimization_proofs_stop_before_any_cloud_write(tmp_path, monkeypatch, problem):
    receipts, _, calls = fixture(tmp_path, monkeypatch)
    value = json.loads(receipts[1].read_text())
    if problem == "missing":
        value.pop("optimizations")
    elif problem == "unverified":
        value["optimizations"]["status"] = "pending"
    elif problem == "wrong-platform":
        value["optimizations"]["platform"] = "windows"
    elif problem in {"enabled-default", "missing-opt-in", "old-policy"}:
        field, replacement = {"enabled-default": ("default_features", optimization.FEATURES),
                              "missing-opt-in": ("opt_in_startup_sha256", ""),
                              "old-policy": ("policy", "rl-full-optimization-package-v1")}[problem]
        value["optimizations"][field] = replacement
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


def test_codec_schema_3_receipts_finalize_like_schema_2(tmp_path, monkeypatch):
    # one schema rule (shared_release_assets.packaged) for every finalizer: 2 and 3 install packages
    import shared_release_assets as shared
    assert [shared.packaged(value) for value in (1, 2, 3, 4, True, "3", None)] == [
        False, True, True, False, False, False, False]
    receipts, assets, calls = fixture(tmp_path, monkeypatch)
    for path in receipts:
        item = json.loads(path.read_text())
        stage, platform = item["stage"], item["platform"]
        extension = "exe" if platform == "windows" else "x86_64"
        assets[:] = [a for a in assets if a["name"] != f"{stage}.update.zip.001"]
        item["assets"] = [a for a in item["assets"] if not a["name"].endswith(".update.zip.001")]
        item["update_schema"] = 3
        for name in (f"{stage}.pkg.client.zip.001", f"{stage}.pkg.engine.zip.001", f"RabbitLands-{platform}.json",
                     f"{stage}-updater.{extension}", f"{stage}-uninstall.{extension}"):
            item["assets"].append({"name": name, "size": 10, "sha256": "b" * 64})
            assets.append({"id": 1000 + len(assets), "name": name, "state": "uploaded", "size": 10,
                           "digest": "sha256:" + "b" * 64})
        path.write_text(json.dumps(item))
    runner.finalize(receipts, tmp_path / "final")
    assert any(name.endswith(".pkg.client.zip.001") for name in (tmp_path / "final/SHA256SUMS").read_text().split())


# --- desktop-release-r2.yml: finalize_r2 (R2-A7) ----------------------------------------------------
#
# Real signed manifests (test key), real content sets and e2e receipts, and a fake GitHub with
# drafts, published releases and the shared pools. Nothing reaches R2 or the network.

import datetime  # noqa: E402
import shutil  # noqa: E402
import types  # noqa: E402
import urllib.request  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import desktop_r2 as r2  # noqa: E402
import desktop_release_ci as ci  # noqa: E402
import linux_download_helper  # noqa: E402
import release_manifest as rm  # noqa: E402
import shared_release_assets as shared  # noqa: E402
import upload_desktop_assets as up  # noqa: E402
import test_release_manifest as fx  # noqa: E402

key = fx.key
other_key = fx.other_key
COMMIT, PREVIOUS = fx.COMMIT, fx.PARENT
DRAFT_ID, PREVIOUS_ID = 123, 99
PLATFORMS = ("windows", "linux")
E2E_NAMES = ("updater-row", "install-started", "installed", "installed-files", "smoke-legacy", "startup-legacy",
             "smoke-legacy-clean", "smoke-human-testing", "startup-human-testing", "smoke-human-testing-clean",
             "recheck")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class FakeGitHub:
    """Releases, assets, pools, the latest flag and the gh verbs the release tools use."""

    def __init__(self):
        self.releases, self.latest_id, self.calls, self.next_id = {}, None, [], 10_000
        self.clock = datetime.datetime(2026, 11, 1, 12, tzinfo=datetime.timezone.utc)
        self.public_commits = set()
        self.latest_on_publish = False  # simulate GitHub ignoring --latest=false

    def tick(self) -> str:
        self.clock += datetime.timedelta(hours=1)
        return self.clock.strftime("%Y-%m-%dT%H:%M:%SZ")

    def add_release(self, release_id, tag, *, draft=False, prerelease=False, author="github-actions[bot]",
                    target=None, latest=False):
        item = {"id": release_id, "tag_name": tag, "draft": draft, "prerelease": prerelease, "immutable": False,
                "author": {"login": author}, "target_commitish": target or tag.removeprefix("client-"),
                "published_at": None if draft else self.tick(), "html_url": f"https://example.invalid/{tag}",
                "assets": {}, "data": {}}
        self.releases[release_id] = item
        if latest:
            self.latest_id = release_id
        return item

    def add_pool(self, tag):
        return self.by_tag(tag) or self.add_release(700 + len(self.releases), tag, prerelease=True, target=COMMIT)

    def add_asset(self, release_id, name, data: bytes | None = None, *, size=None, sha256=None):
        self.next_id += 1
        size = len(data) if data is not None else size
        sha256 = digest(data) if data is not None else sha256
        self.releases[release_id]["assets"][name] = {"id": self.next_id, "name": name, "state": "uploaded",
                                                     "size": size, "digest": "sha256:" + sha256}
        if data is not None:
            self.releases[release_id]["data"][name] = data

    def add_pool_row(self, row):
        if row["name"] not in self.pool_names():
            pool = self.add_pool(shared.storage_tag(row["name"]))
            self.add_asset(pool["id"], row["name"], size=row["size"], sha256=row["sha256"])

    def by_tag(self, tag):
        return next((item for item in self.releases.values() if item["tag_name"] == tag), None)

    def public(self, item) -> dict:
        return {name: value for name, value in item.items() if name not in ("assets", "data")}

    def pool_names(self) -> set:
        return {name for item in self.releases.values() if shared.STORAGE_TAG.fullmatch(item["tag_name"])
                for name in item["assets"]}

    def tags(self) -> set:
        return {item["tag_name"] for item in self.releases.values() if shared.CLIENT_TAG.fullmatch(item["tag_name"])}

    def writes(self) -> list:
        return [call for call in self.calls if call[0] in ("upload", "delete-asset")
                or call[:2] in (("release", "edit"), ("release", "delete"))]

    def edits(self) -> list:
        return [call for call in self.calls if call[:2] == ("release", "edit")]

    def gh(self, *args):
        self.calls.append(args)
        prefix = f"repos/{release.REPOSITORY}/"
        if args[:3] == ("api", "--method", "DELETE"):
            asset_id = int(args[3].rsplit("/", 1)[1])
            self.calls.append(("delete-asset", asset_id))
            for item in self.releases.values():
                item["assets"] = {n: a for n, a in item["assets"].items() if a["id"] != asset_id}
            return ""
        if args[0] == "api":
            path = args[1].removeprefix(prefix)
            if path.startswith("commits/"):
                sha = path.split("/")[1]
                return sha if sha in self.public_commits else ""
            if path == "releases/latest":
                latest = self.releases[self.latest_id]
                return str(latest["id"]) if "--jq" in args else json.dumps(self.public(latest))
            if path.startswith("releases/"):
                return json.dumps(self.public(self.releases[int(path.split("/")[1])]))
            if path.startswith("git/matching-refs/tags/"):
                item = self.by_tag(path.rsplit("/", 1)[1])
                if not item or item["draft"]:
                    return "[]"
                return json.dumps([{"ref": "refs/tags/" + item["tag_name"],
                                    "object": {"type": "commit", "sha": item["target_commitish"]}}])
            raise AssertionError(args)
        verb, tag, flags = args[1], args[2], args[3:]
        item = self.by_tag(tag)
        assert item is not None and flags[:2] == ("--repo", release.REPOSITORY), args
        if verb == "edit":
            if "--draft=false" in flags:
                item["draft"], item["published_at"] = False, self.tick()
                if self.latest_on_publish:
                    self.latest_id = item["id"]
            if "--prerelease=false" in flags:
                item["prerelease"] = False
            if "--latest" in flags:
                self.latest_id = item["id"]
            if "--target" in flags:
                item["target_commitish"] = flags[flags.index("--target") + 1]
            if "--notes-file" in flags:
                item["notes"] = Path(flags[flags.index("--notes-file") + 1]).read_text(encoding="utf-8")
            return ""
        if verb == "download":
            name = flags[flags.index("--pattern") + 1]
            (Path(flags[flags.index("--dir") + 1]) / name).write_bytes(item["data"][name])
            return ""
        if verb == "delete":
            assert flags[2:] == ("--yes",), args
            del self.releases[item["id"]]
            return ""
        raise AssertionError(args)

    def upload_asset(self, tag, release_id, path, row, old):
        data = Path(path).read_bytes()
        assert len(data) == row["size"] and digest(data) == row["sha256"]
        self.calls.append(("upload", Path(path).name))
        if not release.asset_matches(old, row):
            self.add_asset(release_id, Path(path).name, data)

    def install(self, monkeypatch):
        import prune_published_release
        import runner_release
        monkeypatch.setattr(release, "gh", self.gh)
        monkeypatch.setattr(release, "github_assets", lambda release_id: [
            dict(asset) for asset in self.releases[release_id]["assets"].values()])
        monkeypatch.setattr(release, "github_releases", lambda: [self.public(i) for i in self.releases.values()])
        monkeypatch.setattr(release, "github_release", lambda tag: (
            self.public(self.by_tag(tag)) if self.by_tag(tag) else None))
        monkeypatch.setattr(release, "upload_asset", self.upload_asset)
        for module in (runner, prune_published_release, runner_release):
            monkeypatch.setattr(module, "authorize", lambda: None)
        return self


def content_set_bytes(stage, platform, packages, source):
    value = {"kind": r2.SET_KIND, "set_schema": r2.SET_SCHEMA, "source": source, "repository": r2.REPOSITORY,
             "commit": COMMIT, "platform": platform, "version": stage.name,
             "public_key_sha256": "0" * 64, "asset_base": r2.DESKTOP_ASSETS,
             "ci_paths": [*r2.CI_PATHS, *r2.CI_PREFIXES], "packages": packages, "optional_packages": [],
             "builder": {"mode": "release", "tools_commit": COMMIT, "tools_dirty": False, "release_build": True},
             "qualification": {"smoke": ["legacy", "human-testing"], "split_pck": True}}
    return r2.canonical_bytes(value)


def e2e_record(platform, version):
    steps = [{"step": name, "ok": True} for name in E2E_NAMES]
    steps[E2E_NAMES.index("startup-human-testing")]["runtime"] = {"mode": "rust", "native_available": True}
    steps += ([{"step": "setup-exe", "ok": True, "code": 0}] if platform == "windows" else
              [{"step": "download-sh-content", "ok": True}, {"step": "download-sh-run", "ok": True, "code": 0}])
    return {"kind": ci.E2E_KIND, "schema": 1, "platform": platform, "commit": COMMIT, "version": version,
            "steps": steps, "seconds": 12.5, "disk_free": 1}


def signed_platform(root, key, platform, source, *, caps=None, set_override=None):
    """A sign-job manifest of COMMIT for `platform` and its content set (desktop_release_ci.sign's shape)."""
    caps = caps or fx.CAPS_R2
    # platform-specific bytes: no content part is shared between the two platforms
    stage = fx.make_stage(root / f"stage-{platform}", platform, key,
                          content={path: data + platform.encode() for path, data in fx.CONTENT.items()})
    packages = fx.content_packages(stage, root / f"pack-{platform}", source)
    set_packages = set_override(packages) if set_override else packages
    set_bytes = content_set_bytes(stage, platform, set_packages, source)
    identity = fx.identity(platform, key)
    payload = rm.payload(identity=identity, version=stage.name, content_packages=packages,
                         ci_packages=fx.ci_packages(stage, platform, root / f"ci-{platform}"),
                         helpers=fx.helper_rows(stage, platform), launch_args=list(fx.LAUNCH_ARGS),
                         capabilities=caps, source=source, set_sha256=digest(set_bytes), sequence=fx.SEQUENCE,
                         helpers_fingerprint=fx.FINGERPRINT, root_files=fx.ROOT_FILES)
    envelope, _ = rm.sign_manifest(payload, identity, caps, rm.load_signing_key(key.private, key.public), key.public)
    return types.SimpleNamespace(platform=platform, source=source, stage=stage, set_bytes=set_bytes,
                                 envelope=envelope, payload=payload, name=f"{stage.name}-{platform}.json")


SETUP_BYTES = b"MZ fake setup " + COMMIT.encode()


def r2_inputs(root, key, sources=None, *, caps=None, set_override=None):
    """The envelopes, content-P and e2e-P artifacts of one R2 workflow run of COMMIT."""
    sources = sources or {"windows": "r2", "linux": "r2"}
    root = Path(root)
    envelopes = root / "envelopes"
    envelopes.mkdir(parents=True)
    signed, content, e2e, records = {}, {}, {}, {}
    for platform in PLATFORMS:
        item = signed_platform(root, key, platform, sources[platform], caps=caps,
                               set_override=(set_override or {}).get(platform))
        signed[platform] = item
        (envelopes / item.name).write_bytes(item.envelope)
        (envelopes / f"RabbitLands-{platform}.json").write_bytes(item.envelope)
        records[platform] = {"manifest": item.name, "sha256": digest(item.envelope), "bytes": len(item.envelope),
                             "margin": 1, "schema": item.payload["schema"], "sequence": fx.SEQUENCE,
                             "source": item.source, "set_sha256": digest(item.set_bytes)}
        content[platform] = root / f"content-{platform}"
        content[platform].mkdir()
        (content[platform] / "set.json").write_bytes(item.set_bytes)
        verified = {"kind": ci.CONTENT_KIND, "schema": 1, "platform": platform, "commit": COMMIT,
                    "source": item.source, "set_sha256": digest(item.set_bytes)}
        if item.source == "ci":
            verified.update(uploaded=True, pool={"uploaded": True})
        (content[platform] / "verified.json").write_text(json.dumps(verified))
        (content[platform] / "summary.md").write_text("summary\n")
        e2e[platform] = root / f"e2e-{platform}"
        e2e[platform].mkdir()
        (e2e[platform] / "e2e.json").write_text(json.dumps(e2e_record(platform, item.payload["version"])))
    (envelopes / "sign.json").write_text(json.dumps({"commit": COMMIT, "platforms": records}))
    # The installers-windows artifact: exactly the setup.exe the stage job uploaded to the draft.
    installers = {"windows": root / "installers-windows"}
    installers["windows"].mkdir()
    (installers["windows"] / f"{signed['windows'].payload['version']}-setup.exe").write_bytes(SETUP_BYTES)
    return types.SimpleNamespace(envelopes=envelopes, content=content, e2e=e2e, signed=signed, root=root,
                                 installers=installers, out=root / "release-verification",
                                 summary=root / "summary.md")


def pool_rows_of(payload) -> list:
    """GitHub pool rows (CI packages, ci-source content parts, helpers) of a signed payload."""
    rows = []
    for package in payload["packages"]:
        for part in package["parts"]:
            if part["url"].startswith(r2.GITHUB_DOWNLOADS):
                rows.append({"name": part["url"].rsplit("/", 1)[1], "size": part["size"], "sha256": part["sha256"]})
    for kind in rm.HELPER_KINDS:
        row = payload[kind]
        rows.append({"name": row["url"].rsplit("/", 1)[1], "size": row["size"], "sha256": row["sha256"]})
    return rows


def r2_part_rows(payload) -> list:
    return [part for package in payload["packages"] for part in package["parts"]
            if part["url"].startswith(r2.DESKTOP_ASSETS)]


def helper_rows_for(label: str) -> list:
    return [{"name": shared.name(digest((kind + platform + label).encode()), kind,
                                 "exe" if platform == "windows" else "x86_64"),
             "size": 10, "sha256": digest((kind + platform + label).encode())}
            for platform in PLATFORMS for kind in ("updater", "uninstall")]


def pkg_row(label: str) -> dict:
    value = digest(label.encode())
    return {"name": shared.name(value), "size": 10, "sha256": value}


def published_release(github, release_id, commit, *, pool_rows=(), latest=False, r2_release=False):
    """A published client release with a verifiable SHA256SUMS (and pointers for an R2-era release)."""
    item = github.add_release(release_id, f"client-{commit}", latest=latest)
    files = {f"RabbitLands-Windows-20261101-{commit[:9]}-{suffix}": suffix.encode() + commit.encode()
             for suffix in ("setup.exe", "windows.json")}
    files.update({f"RabbitLands-Linux-20261101-{commit[:9]}-{suffix}": suffix.encode() + commit.encode()
                  for suffix in ("download.sh", "linux.json")})
    files.update({f"RabbitLands-{p}.json": p.encode() + commit.encode() for p in PLATFORMS})
    if r2_release:
        part = digest(b"r2 part " + commit.encode())
        files[shared.R2_SUMS] = f"{part}  desktop/v1/parts/{part}.bin\n".encode()
    for name, data in files.items():
        github.add_asset(release_id, name, data)
    for row in pool_rows:
        github.add_pool_row(row)
    sums = "".join(f"{digest(data)}  {name}\n" for name, data in files.items())
    sums += "".join(f"{row['sha256']}  {row['name']}\n" for row in pool_rows)
    github.add_asset(release_id, "SHA256SUMS", "".join(sorted(sums.splitlines(keepends=True))).encode("ascii"))
    if r2_release:
        for platform in PLATFORMS:
            github.add_asset(release_id, r2.pointer_asset_name(platform), b'{"pointer":"' + platform.encode() + b'"}')
    return item


def r2_world(monkeypatch, inputs, *, history=(), stale=True):
    """The fake GitHub as the stage job leaves it: older published releases (`history`, oldest
    first, as (label, release id)), the previous latest, this commit's draft with its manifests
    and installers, and every pool row uploaded."""
    github = FakeGitHub().install(monkeypatch)
    github.public_commits.add(COMMIT)
    github.add_pool(shared.TAG)
    for label, release_id in history:
        published_release(github, release_id, digest(label.encode())[:40],
                          pool_rows=[pkg_row(label), pkg_row("shared"), *helper_rows_for(label)])
    published_release(github, PREVIOUS_ID, PREVIOUS, latest=True,
                      pool_rows=[pkg_row("previous"), pkg_row("shared"), *helper_rows_for("previous")])
    github.add_release(DRAFT_ID, f"client-{COMMIT}", draft=True, target=COMMIT)
    for platform, item in inputs.signed.items():
        github.add_asset(DRAFT_ID, item.name, item.envelope)
        github.add_asset(DRAFT_ID, f"RabbitLands-{platform}.json", item.envelope)
        if platform == "windows":
            github.add_asset(DRAFT_ID, f"{item.payload['version']}-setup.exe", SETUP_BYTES)
        else:
            script = linux_download_helper.bootstrap_script(item.payload["updater"], json.loads(item.envelope))
            github.add_asset(DRAFT_ID, f"{item.payload['version']}-download.sh", script.encode("utf-8"))
        for row in pool_rows_of(item.payload):
            github.add_pool_row(row)
    if stale:
        github.add_asset(DRAFT_ID, "previous-build.zip", b"stale")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(inputs.summary))
    return github


def finalize_run(inputs, key, **changes):
    options = dict(commit=COMMIT, release_id=DRAFT_ID, envelopes=inputs.envelopes, content=inputs.content,
                   e2e=inputs.e2e, installers=inputs.installers, out=inputs.out, public_pem=key.public)
    options.update(changes)
    return runner.finalize_r2(**options)


@pytest.fixture
def no_network(monkeypatch):
    """Finalize, publish and the prune never open a connection; promote gets an explicit fake."""
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("no network call is allowed"))
    monkeypatch.setattr(up, "Http", lambda *a, **k: pytest.fail("no HTTP client is created here"))


@pytest.fixture
def scene(tmp_path, monkeypatch, key, no_network):
    inputs = r2_inputs(tmp_path / "run", key)
    return inputs, r2_world(monkeypatch, inputs)


def test_r2_finalize_checks_github_rows_by_inventory_and_r2_rows_against_the_content_sets(scene, key):
    inputs, github = scene
    assert finalize_run(inputs, key) == f"https://example.invalid/client-{COMMIT}"
    sums = shared.checksum_inventory((inputs.out / "SHA256SUMS").read_text(encoding="ascii"))
    r2_sums = shared.r2_checksum_inventory((inputs.out / shared.R2_SUMS).read_text(encoding="ascii"))
    for platform, item in inputs.signed.items():
        hosted = r2_part_rows(item.payload)
        assert hosted, platform
        for part in hosted:
            # an R2 row: listed in R2-SHA256SUMS, never in SHA256SUMS, never looked up in (or put into) a pool
            assert r2_sums[r2.part_key(part["sha256"])] == part["sha256"]
            assert shared.name(part["sha256"]) not in sums and shared.name(part["sha256"]) not in github.pool_names()
        for row in pool_rows_of(item.payload):
            assert sums[row["name"]] == row["sha256"]
        assert r2_sums[r2.set_key(platform, digest(item.set_bytes))] == digest(item.set_bytes)
        assert r2_sums[r2.manifest_key(platform, digest(item.envelope))] == digest(item.envelope)
        assert sums[item.name] == sums[f"RabbitLands-{platform}.json"] == digest(item.envelope)
    parts = {part["sha256"] for item in inputs.signed.values() for part in r2_part_rows(item.payload)}
    assert len(r2_sums) == len(parts) + 4  # every R2 part once, plus both sets and both manifest copies
    assert shared.R2_SUMS in sums and "SHA256SUMS" not in sums
    draft = github.releases[DRAFT_ID]
    assert set(draft["assets"]) == {name for name in sums if not shared.is_name(name)} | {"SHA256SUMS"}
    assert draft["draft"] and github.latest_id == PREVIOUS_ID
    order = [call[0] if call[0] in ("upload", "delete-asset") else call[1] for call in github.writes()]
    assert order == ["upload", "upload", "edit", "delete-asset"]  # R2-SHA256SUMS, SHA256SUMS, retag, stale file
    assert [call[1] for call in github.calls if call[0] == "upload"] == [shared.R2_SUMS, "SHA256SUMS"]
    edit = github.edits()[0]
    assert "--draft" in edit and "--draft=false" not in edit and "--latest" not in edit
    receipt = json.loads((inputs.out / "runner-release.json").read_text())
    assert receipt["kind"] == runner.R2_RECEIPT_KIND and receipt["release_id"] == DRAFT_ID
    assert {p: v["source"] for p, v in receipt["platforms"].items()} == {"windows": "r2", "linux": "r2"}
    assert receipt["e2e"]["windows"]["setup_exe"] == "passed" and receipt["r2_objects"] == len(r2_sums)
    assert receipt["pointers"] == {p: r2.pointer_asset_name(p) for p in PLATFORMS}
    assert runner.load_r2_receipt(inputs.out / "runner-release.json", commit=COMMIT, release_id=DRAFT_ID)
    policy = json.loads((inputs.out / "client_updates.json").read_text())
    base = f"https://github.com/{release.REPOSITORY}/releases/download/client-{COMMIT}/"
    assert policy["required_commit"] == COMMIT
    assert policy["manifests"] == {p: base + inputs.signed[p].name for p in PLATFORMS}  # old clients read GitHub
    notes = draft["notes"]
    assert r2.DESKTOP_ASSETS in notes and "R2-SHA256SUMS" in notes and base not in notes
    assert f"`{inputs.signed['windows'].stage.name}-setup.exe`" in notes
    assert f"`{inputs.signed['linux'].stage.name}-download.sh`" in notes
    assert "R2 objects" in inputs.summary.read_text()
    # What a returning player reads. Setup converts an old Windows folder; the Linux
    # helper and the standalone updaters refuse one (bootstrap.gd root_error).
    assert ("Close Rabbit Lands, then run this setup; it converts your existing folder. If setup\n"
            "is interrupted or a shortcut says to use the original installer, run this setup again.") in notes
    assert "reuse their matching packages" not in notes
    assert "Run that game's old\nuninstaller first, or pass another parent folder" in notes
    assert "expect a full\ndownload" in notes
    standalone = notes[notes.index("## Standalone helpers"):]
    assert "cannot convert a folder installed before November 2026" in standalone


@pytest.mark.parametrize("sources", [{"windows": "r2", "linux": "ci"}, {"windows": "ci", "linux": "r2"},
                                     {"windows": "ci", "linux": "ci"}])
def test_r2_finalize_takes_mixed_r2_and_ci_sources(tmp_path, monkeypatch, key, no_network, sources):
    inputs = r2_inputs(tmp_path / "run", key, sources)
    github = r2_world(monkeypatch, inputs)
    finalize_run(inputs, key)
    sums = shared.checksum_inventory((inputs.out / "SHA256SUMS").read_text(encoding="ascii"))
    r2_sums = shared.r2_checksum_inventory((inputs.out / shared.R2_SUMS).read_text(encoding="ascii"))
    for platform, item in inputs.signed.items():
        content_parts = [part for package in item.payload["packages"] if package["id"] not in r2.CI_PACKAGE_IDS
                         for part in package["parts"]]
        set_key = r2.set_key(platform, digest(item.set_bytes))
        if sources[platform] == "r2":
            assert all(r2.part_key(part["sha256"]) in r2_sums for part in content_parts) and set_key in r2_sums
        else:
            # GitHub-hosted content: inventory-checked in the pools, absent from R2-SHA256SUMS
            assert all(sums[part["url"].rsplit("/", 1)[1]] == part["sha256"] for part in content_parts)
            assert not any(r2.part_key(part["sha256"]) in r2_sums for part in content_parts) and set_key not in r2_sums
        assert r2.manifest_key(platform, digest(item.envelope)) in r2_sums  # the pointer's manifest copy
    notes = github.releases[DRAFT_ID]["notes"]
    assert (r2.DESKTOP_ASSETS in notes) == ("r2" in sources.values())
    # schema 3 always has R2 manifest copies, so the notes name R2-SHA256SUMS even for ci/ci
    assert shared.R2_SUMS in notes and shared.R2_SUMS in github.releases[DRAFT_ID]["assets"]


def test_r2_finalize_of_schema_2_ci_sources_has_no_r2_objects(tmp_path, monkeypatch, key, no_network):
    # a commit whose reader predates schema 3 ships GitHub-hosted content only (no pointer, no R2 copy)
    inputs = r2_inputs(tmp_path / "run", key, {"windows": "ci", "linux": "ci"}, caps=fx.CAPS2)
    github = r2_world(monkeypatch, inputs)
    finalize_run(inputs, key)
    assert not (inputs.out / shared.R2_SUMS).exists() and shared.R2_SUMS not in github.releases[DRAFT_ID]["assets"]
    assert shared.R2_SUMS not in github.releases[DRAFT_ID]["notes"]
    receipt = json.loads((inputs.out / "runner-release.json").read_text())
    assert receipt["r2_objects"] == 0 and {v["schema"] for v in receipt["platforms"].values()} == {2}


def _remove_last_package(packages):
    return packages[:-1]


def tamper_content(inputs, problem):
    windows = inputs.content["windows"]
    if problem == "other-set":
        (windows / "set.json").write_bytes(inputs.signed["linux"].set_bytes)
    elif problem == "edited-set":
        # still canonical, the same header and packages: only the dispatched SHA-256 tells them apart
        value = json.loads(inputs.signed["windows"].set_bytes)
        value["qualification"]["split_pck"] = False
        (windows / "set.json").write_bytes(r2.canonical_bytes(value))
    elif problem == "verified-source":
        value = json.loads((windows / "verified.json").read_text())
        (windows / "verified.json").write_text(json.dumps({**value, "source": "ci"}))
    elif problem == "verified-missing":
        (windows / "verified.json").unlink()
    elif problem == "verified-kind":
        value = json.loads((windows / "verified.json").read_text())
        (windows / "verified.json").write_text(json.dumps({**value, "kind": ci.E2E_KIND}))


@pytest.mark.parametrize("problem", ["other-set", "edited-set", "verified-source", "verified-missing",
                                     "verified-kind"])
def test_r2_rows_need_the_dispatched_content_artifact(scene, key, problem):
    inputs, github = scene
    tamper_content(inputs, problem)
    with pytest.raises(ValueError):
        finalize_run(inputs, key)
    assert github.calls == [] and not inputs.out.exists()


def test_a_manifest_whose_content_rows_are_not_exactly_the_sets_is_refused(tmp_path, monkeypatch, key, no_network):
    inputs = r2_inputs(tmp_path / "run", key, set_override={"windows": _remove_last_package})
    github = r2_world(monkeypatch, inputs)
    with pytest.raises(ValueError, match="exactly the dispatched set"):
        finalize_run(inputs, key)
    assert github.calls == []


def test_a_ci_content_artifact_must_be_a_finished_upload(tmp_path, monkeypatch, key, no_network):
    inputs = r2_inputs(tmp_path / "run", key, {"windows": "r2", "linux": "ci"})
    github = r2_world(monkeypatch, inputs)
    path = inputs.content["linux"] / "verified.json"
    path.write_text(json.dumps({**json.loads(path.read_text()), "uploaded": False}))
    with pytest.raises(ValueError, match="finished content check"):
        finalize_run(inputs, key)
    assert github.calls == []


def test_manifest_rows_are_r2_parts_of_r2_sets_or_partitioned_pool_parts(scene, key):
    inputs, _ = scene
    windows = json.loads(json.dumps(inputs.signed["windows"].payload))
    pool, hosted = runner.manifest_rows(windows)
    assert pool and hosted and all(key.startswith("desktop/v1/parts/") for key in hosted)
    for change in ("ci-package-on-r2", "content-on-pool", "legacy-pool", "foreign-host", "helper-on-pool-shard"):
        value = json.loads(json.dumps(windows))
        content = next(p for p in value["packages"] if p["id"] not in r2.CI_PACKAGE_IDS)
        engine = next(p for p in value["packages"] if p["id"] == "engine")
        if change == "ci-package-on-r2":
            engine["parts"][0]["url"] = r2.part_url(engine["parts"][0]["sha256"])
        elif change == "content-on-pool":
            content["parts"][0]["url"] = r2.github_pool_url(content["parts"][0]["sha256"])
        elif change == "legacy-pool":
            engine["parts"][0]["url"] = r2.github_pool_url(engine["parts"][0]["sha256"], partitioned=False)
        elif change == "foreign-host":
            engine["parts"][0]["url"] = "https://example.invalid/" + shared.name(engine["parts"][0]["sha256"])
        else:
            name = value["updater"]["url"].rsplit("/", 1)[1]
            value["updater"]["url"] = f"{r2.GITHUB_DOWNLOADS}client-assets-1/{name}"
        with pytest.raises(ValueError):
            runner.manifest_rows(value)
    linux = json.loads(json.dumps(inputs.signed["linux"].payload))
    linux["content"]["source"] = "ci"  # an R2 part is never accepted in a ci set
    with pytest.raises(ValueError):
        runner.manifest_rows(linux)


@pytest.mark.parametrize("problem", ["failed-step", "missing-step", "duplicate-step", "legacy-native", "commit",
                                     "version", "kind", "setup-other-skip", "missing-receipt"])
def test_r2_finalize_needs_every_e2e_proof(scene, key, problem):
    inputs, github = scene
    path = inputs.e2e["linux" if problem != "setup-other-skip" else "windows"] / "e2e.json"
    record = json.loads(path.read_text())
    steps = record["steps"]
    if problem == "failed-step":
        steps[3]["ok"] = False
    elif problem == "missing-step":
        record["steps"] = [s for s in steps if s["step"] != "recheck"]
    elif problem == "duplicate-step":
        steps.append(dict(steps[0]))
    elif problem == "legacy-native":
        steps[E2E_NAMES.index("startup-human-testing")]["runtime"] = {"mode": "legacy", "native_available": False}
    elif problem == "commit":
        record["commit"] = PREVIOUS
    elif problem == "version":
        record["version"] = inputs.signed["windows"].payload["version"]
    elif problem == "kind":
        record["kind"] = ci.CONTENT_KIND
    elif problem == "setup-other-skip":
        steps[-1] = {"step": "setup-exe", "ok": None, "skipped": "timeout"}
    path.write_text(json.dumps(record))
    if problem == "missing-receipt":
        path.unlink()
    with pytest.raises(ValueError):
        finalize_run(inputs, key)
    assert github.calls == []


def test_a_setup_exe_skipped_for_disk_needs_the_local_pre_promote_check(scene, key):
    inputs, _ = scene
    path = inputs.e2e["windows"] / "e2e.json"
    record = json.loads(path.read_text())
    record["steps"][-1] = {"step": "setup-exe", "ok": None, "skipped": "disk", "free": 1, "need": 2}
    path.write_text(json.dumps(record))
    finalize_run(inputs, key)
    receipt = json.loads((inputs.out / "runner-release.json").read_text())
    assert receipt["e2e"]["windows"]["setup_exe"] == "skipped-disk"
    assert "local pre-promote setup check" in inputs.summary.read_text()


def test_the_e2e_steps_finalize_requires_are_the_ones_the_e2e_job_records(scene, key, tmp_path):
    from test_desktop_release_ci import FakeDisplay, FakeRuns
    inputs, _ = scene
    item = inputs.signed["linux"]
    exec_dir = tmp_path / "exec-linux"
    (exec_dir / "root").mkdir(parents=True)
    shutil.copyfile(item.stage / fx.HELPER["linux"], exec_dir / "root" / fx.HELPER["linux"])
    envelope = inputs.envelopes / item.name
    script = tmp_path / "download.sh"
    script.write_bytes(linux_download_helper.bootstrap_script(item.payload["updater"],
                                                              json.loads(item.envelope)).encode("utf-8"))
    runs = FakeRuns(item.payload, item.stage, exec_dir / "root" / fx.HELPER["linux"])
    e2e = ci.E2E(platform="linux", envelope=envelope, exec_dir=exec_dir, work=tmp_path / "e2e", public_pem=key.public,
                 run=runs, user=None, alive=lambda: False, sleep=lambda seconds: None, display_server=FakeDisplay())
    receipt = e2e.run_all(installer=script)
    (inputs.e2e["linux"] / "e2e.json").write_text(json.dumps(receipt))
    assert runner.check_e2e(inputs.e2e["linux"], item.payload)["steps"] == len(receipt["steps"])


@pytest.mark.parametrize("problem", ["sign-commit", "alias", "other-key", "sign-source", "name"])
def test_r2_finalize_takes_only_this_runs_signed_manifests(scene, key, other_key, problem):
    inputs, github = scene
    sign = json.loads((inputs.envelopes / "sign.json").read_text())
    options = {}
    if problem == "sign-commit":
        sign["commit"] = PREVIOUS
    elif problem == "alias":
        (inputs.envelopes / "RabbitLands-linux.json").write_bytes(inputs.signed["windows"].envelope)
    elif problem == "other-key":
        options["public_pem"] = other_key.public
    elif problem == "sign-source":
        sign["platforms"]["windows"]["source"] = "ci"
    else:
        sign["platforms"]["windows"]["manifest"] = inputs.signed["linux"].name
    (inputs.envelopes / "sign.json").write_text(json.dumps(sign))
    with pytest.raises(ValueError):
        finalize_run(inputs, key, **options)
    assert github.calls == []


@pytest.mark.parametrize("problem", ["pool-part", "helper", "download-sh", "setup-missing", "setup-bytes",
                                     "manifest-digest", "other-draft", "private-commit", "draft-tag", "published",
                                     "foreign-author"])
def test_r2_finalize_verifies_every_github_row_before_any_write(scene, key, problem):
    inputs, github = scene
    draft = github.releases[DRAFT_ID]
    windows = inputs.signed["windows"]
    if problem == "pool-part":
        engine = next(p for p in windows.payload["packages"] if p["id"] == "engine")["parts"][0]
        pool = github.by_tag(shared.storage_tag(shared.name(engine["sha256"])))
        del pool["assets"][shared.name(engine["sha256"])]
    elif problem == "helper":
        name = windows.payload["uninstall"]["url"].rsplit("/", 1)[1]
        github.by_tag(shared.TAG)["assets"][name]["digest"] = "sha256:" + "f" * 64
    elif problem == "download-sh":
        github.add_asset(DRAFT_ID, f"{inputs.signed['linux'].payload['version']}-download.sh", b"#!/bin/sh\nother\n")
    elif problem == "setup-missing":
        del draft["assets"][f"{windows.payload['version']}-setup.exe"]
    elif problem == "setup-bytes":
        # A setup.exe on the draft that is not the installers artifact's (Q18), even if GitHub's digest is its own.
        github.add_asset(DRAFT_ID, f"{windows.payload['version']}-setup.exe", b"MZ another setup")
    elif problem == "manifest-digest":
        draft["assets"][windows.name]["digest"] = "sha256:" + "f" * 64
    elif problem == "other-draft":
        github.add_release(555, "client-" + "e" * 40, draft=True)
    elif problem == "private-commit":
        github.public_commits.clear()
    elif problem == "draft-tag":
        draft["tag_name"] = "client-" + PREVIOUS
    elif problem == "published":
        draft["draft"] = False
    else:
        draft["author"] = {"login": "somebody-else"}
    with pytest.raises(ValueError):
        finalize_run(inputs, key)
    assert github.writes() == [] and github.latest_id == PREVIOUS_ID


def test_r2_finalize_needs_a_fresh_output_folder_and_both_platforms(scene, key):
    inputs, github = scene
    inputs.out.mkdir()
    with pytest.raises(ValueError, match="must not exist"):
        finalize_run(inputs, key)
    with pytest.raises(ValueError):
        finalize_run(inputs, key, out=inputs.root / "other", content={"windows": inputs.content["windows"]})
    with pytest.raises(ValueError):
        finalize_run(inputs, key, out=inputs.root / "other", release_id=0)
    assert github.calls == []


@pytest.mark.parametrize("problem", ["absent", "no-windows", "empty", "extra-file", "other-name"])
def test_r2_finalize_needs_exactly_the_windows_installers_artifact(scene, key, problem):
    inputs, github = scene
    folder = inputs.installers["windows"]
    setup = next(folder.iterdir())
    installers = dict(inputs.installers)
    if problem == "absent":
        installers = None
    elif problem == "no-windows":
        installers = {"linux": folder}
    elif problem == "empty":
        setup.unlink()
    elif problem == "extra-file":
        (folder / "notes.txt").write_text("extra")
    else:
        setup.rename(folder / "RabbitLands-setup.exe")
    with pytest.raises(ValueError, match="installers artifact"):
        finalize_run(inputs, key, installers=installers)
    assert github.calls == [] and not inputs.out.exists()


def test_r2_finalize_binds_setup_exe_to_the_installers_artifact(scene, key):
    inputs, github = scene
    finalize_run(inputs, key)
    name = f"{inputs.signed['windows'].payload['version']}-setup.exe"
    sums = shared.checksum_inventory((inputs.out / "SHA256SUMS").read_text(encoding="ascii"))
    assert sums[name] == digest(SETUP_BYTES)


def test_r2_receipt_loader_refuses_tampering(scene, key):
    inputs, _ = scene
    finalize_run(inputs, key)
    path = inputs.out / "runner-release.json"
    good = json.loads(path.read_text())
    assert runner.load_r2_receipt(path, commit=COMMIT, release_id=DRAFT_ID)["assets"]["SHA256SUMS"]
    for change in ("kind", "commit", "release", "pointer", "pool", "manifest", "installer", "schema", "legacy-key"):
        value = json.loads(json.dumps(good))
        if change == "kind":
            value["kind"] = "rabbitlands-desktop-runner"
        elif change == "commit":
            value["commit"] = PREVIOUS
        elif change == "release":
            value["release_id"] = DRAFT_ID + 1
        elif change == "pointer":
            value["assets"].append({"name": r2.pointer_asset_name("windows"), "size": 5, "sha256": "1" * 64})
        elif change == "pool":
            value["shared_assets"][0]["sha256"] = "1" * 64
        elif change == "manifest":
            value["platforms"]["windows"]["manifest_sha256"] = "1" * 64
        elif change == "installer":
            value["platforms"]["linux"]["installer"] = "RabbitLands-linux.json"
        elif change == "schema":
            value["platforms"]["linux"]["schema"] = 1
        else:
            value["shared_release_ids"] = {"client-assets-0": 5}
        path.write_text(json.dumps(value))
        with pytest.raises(ValueError):
            runner.load_r2_receipt(path, commit=COMMIT, release_id=DRAFT_ID)
