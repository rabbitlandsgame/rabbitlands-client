"""Cold hosted cache bootstrap through the real budget; no engines/network."""
from pathlib import Path
from types import SimpleNamespace
import json
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import runner_release as runner
import release_storage
import release_native_runtime as native

COMMIT = "a" * 40


class ReachedPackaging(RuntimeError):
    pass


@pytest.fixture
def bootstrap(tmp_path, monkeypatch):
    repository = tmp_path / "selected-source"
    git_directory = repository / ".git"
    git_directory.mkdir(parents=True)
    tools = tmp_path / "verified-tools"
    tools.mkdir()
    godot = tools / "godot"
    godot.write_bytes(b"verified engine fixture; never executed")
    key = tmp_path / "signing-fixture.pem"
    key.write_bytes(b"non-secret fixture")
    options = SimpleNamespace(ref=COMMIT, update_signing_key=key, godot=godot,
        platform="linux", out=tmp_path / "releases", iscc=None, tool_root=[tools],
        native_cache=tmp_path / "rabbitlands-native-cache/linux", asset_cache=None,
        draft_release_id=123, server="game.example.invalid:2001")
    calls = []
    options.fixture_prewarm = []
    def git(*args, **kwargs):
        if args[:2] == ("remote", "get-url"):
            return "https://github.com/" + runner.release.REPOSITORY + ".git"
        if args[:2] == ("rev-parse", "--path-format=absolute"):
            return str(git_directory)
        if args[0] == "rev-parse":
            return COMMIT
        if args[0] == "show":
            return "fixture public key\n"
        raise AssertionError("unexpected Git operation: " + str(args))
    def version(command, *, capture):
        assert command == [str(godot), "--headless", "--version"]
        calls.append("mocked-version")
        return "4.7.2.stable.fixture"
    def public_commit(*args):
        assert args[0] == "api" and args[-1] == ".sha"
        calls.append("mocked-public-commit")
        return COMMIT
    def package(arguments, storage):
        calls.append("package")
        assert options.native_cache.parent.is_dir()
        assert options.native_cache.parent.resolve() in storage.budget.roots
        assert storage.budget.samples[0]["phase"] == "preflight"
        assert storage.budget.samples[0]["additional"] == 7_000_000_000
        assert arguments[arguments.index("--native-runtime-cache") + 1] == str(options.native_cache)
        raise ReachedPackaging("real budget preflight completed")
    def prewarm(repository_arg, commit, platform, cache_dir, work_root, check_budget, **tools):
        owner = check_budget.__self__
        expected_cache = options.out.parent / "rabbitlands-native-cache" / platform
        assert repository_arg == repository and commit == COMMIT and platform == options.platform
        assert Path(cache_dir) == expected_cache
        assert Path(work_root) == expected_cache.parent / ("bootstrap-" + platform)
        assert check_budget.__func__ is runner.RunnerStorage.check
        assert owner.source == owner.root / "source/godot-client"
        assert not owner.source.parent.exists(), "native compile must precede full asset materialization"
        assert not (owner.root / "downloads").exists()
        calls.append("prewarm")
        # Exercise the actual shared budget using its positional public API.
        check_budget("native bootstrap fixture reservation", 3 * 1024**3)
        assert owner.budget.samples[-1]["additional"] == 3 * 1024**3
        assert owner.budget.samples[-1]["bytes"] < 1024**2, "no runtime assets belong in native bootstrap"
        hit = expected_cache.exists()
        expected_cache.mkdir(parents=True, exist_ok=True)
        receipt = {"schema": 1, "selected_commit": commit, "platform": platform,
                   "cache_hit": hit, "status": "fixture-prewarmed-without-engine"}
        options.fixture_prewarm.append({"owner": owner, "cache": expected_cache,
                                        "work_root": Path(work_root), "receipt": receipt})
        return receipt
    monkeypatch.setattr(runner.package, "REPO", repository)
    monkeypatch.setattr(runner.package, "git", git)
    monkeypatch.setattr(runner.release, "run", version)
    monkeypatch.setattr(runner.release, "gh", public_commit)
    monkeypatch.setattr(runner.client_release, "identity", lambda *args: {})
    monkeypatch.setattr(runner, "GitHubSink", lambda *args: object())
    monkeypatch.setattr(runner.package, "main", package)
    # The callable is faked even before the production integration lands. No
    # branch of these runner tests may reach a compiler, Git fetch or engine.
    monkeypatch.setattr(native, "prewarm_cache", prewarm, raising=False)
    monkeypatch.setattr(release_storage.shutil, "disk_usage", lambda path: SimpleNamespace(free=100_000_000_000))
    return options, calls


@pytest.mark.parametrize("warm", [False, True])
@pytest.mark.parametrize("explicit", [False, True])
def test_owned_native_cache_parent_reaches_real_budget_cold_and_warm(bootstrap, warm, explicit):
    options, calls = bootstrap
    native_cache = options.native_cache
    artifact = native_cache / "existing-payload.bin"
    if warm:
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(b"verified cached payload must remain untouched")
    else:
        assert not native_cache.parent.exists()
    if not explicit:
        options.native_cache = None
    # Keep the expected resolved path available to the mocked package boundary.
    expected = native_cache
    original = runner.package.main
    def package(arguments, storage):
        assert expected.parent.is_dir()
        assert expected.parent.resolve() in storage.budget.roots
        assert storage.budget.samples[0]["phase"] == "preflight"
        assert arguments[arguments.index("--native-runtime-cache") + 1] == str(expected)
        if warm:
            assert storage.budget.samples[0]["bytes"] >= artifact.stat().st_size
        calls.append("package")
        raise ReachedPackaging("real budget preflight completed")
    runner.package.main = package
    try:
        with pytest.raises(ReachedPackaging, match="real budget preflight completed"):
            runner.build(options)
    finally:
        runner.package.main = original
    assert calls[-1] == "package"
    assert calls.index("prewarm") < calls.index("package")
    assert len(options.fixture_prewarm) == 1
    assert options.fixture_prewarm[0]["receipt"]["cache_hit"] is warm
    if warm:
        assert artifact.read_bytes() == b"verified cached payload must remain untouched"


def test_foreign_native_cache_path_is_rejected_without_creating_it(bootstrap):
    options, calls = bootstrap
    options.native_cache = options.out.parent / "foreign-cache/linux"
    assert not options.native_cache.parent.exists()
    with pytest.raises(ValueError, match="dedicated native-runtime cache"):
        runner.build(options)
    assert not options.native_cache.parent.exists()
    assert "package" not in calls
    assert "prewarm" not in calls


def test_cold_cache_creation_does_not_bypass_free_space_preflight(bootstrap, monkeypatch):
    options, calls = bootstrap
    monkeypatch.setattr(release_storage.shutil, "disk_usage", lambda path: SimpleNamespace(free=1_000_000_000))
    with pytest.raises(ValueError, match="insufficient free space"):
        runner.build(options)
    assert options.native_cache.parent.is_dir()
    assert "package" not in calls
    assert "prewarm" not in calls


@pytest.mark.parametrize("platform", ["windows", "linux"])
def test_native_prewarm_receipt_is_recorded_before_packaging_for_both_platforms(bootstrap, platform):
    options, calls = bootstrap
    options.platform = platform
    options.native_cache = options.out.parent / "rabbitlands-native-cache" / platform
    if platform == "windows":
        options.iscc = options.godot.parent / "ISCC.exe"
        options.iscc.write_bytes(b"unexecuted installer fixture")
    with pytest.raises(ReachedPackaging):
        runner.build(options)
    assert calls.index("prewarm") < calls.index("package")
    record = options.fixture_prewarm[0]
    receipt = record["owner"].root / "native-bootstrap.json"
    assert json.loads(receipt.read_text()) == record["receipt"]
    assert not record["owner"].source.parent.exists()


def test_failed_native_prewarm_blocks_asset_materialization_and_package(bootstrap, monkeypatch):
    options, calls = bootstrap
    def failed(*args, **kwargs):
        calls.append("failed-prewarm")
        raise ValueError("fixture native prewarm identity failed")
    monkeypatch.setattr(native, "prewarm_cache", failed)
    with pytest.raises(ValueError, match="prewarm identity failed"):
        runner.build(options)
    assert "package" not in calls
    root = options.out / ("runner-linux-" + COMMIT)
    assert not (root / "source").exists()
    assert not (root / "native-bootstrap.json").exists()


def test_native_prewarm_preserves_three_gib_reservation_and_two_gb_free_margin(bootstrap, monkeypatch):
    options, calls = bootstrap
    # Initial preflight succeeds, then host free space falls before compilation.
    monkeypatch.setattr(release_storage.shutil, "disk_usage", lambda path:
                        SimpleNamespace(free=4_000_000_000 if "prewarm" in calls else 100_000_000_000))
    with pytest.raises(ValueError, match="insufficient free space"):
        runner.build(options)
    assert "prewarm" in calls and "package" not in calls
    root = options.out / ("runner-linux-" + COMMIT)
    assert not (root / "source").exists()
