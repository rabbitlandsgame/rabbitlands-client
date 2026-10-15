import hashlib
import json
import sys
import subprocess
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import client_release
import package_client


def test_packaged_history_matches_git_merge_ancestry(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        return subprocess.check_output(["git", *args], cwd=repo, text=True, stderr=subprocess.DEVNULL).strip()

    git("init", "-b", "main")
    git("config", "user.name", "Client update test")
    git("config", "user.email", "updates@example.invalid")
    (repo / "file").write_text("root")
    git("add", "."); git("commit", "-m", "root")
    root = git("rev-parse", "HEAD")
    (repo / "file").write_text("child")
    git("commit", "-am", "child")
    child = git("rev-parse", "HEAD")
    git("checkout", "-b", "side", root)
    (repo / "other").write_text("side")
    git("add", "."); git("commit", "-m", "side")
    side = git("rev-parse", "HEAD")
    before_merge = client_release.identity(repo, side, "windows", None, "o/r")
    assert child not in before_merge["ancestors"]
    git("checkout", "main")
    git("merge", "--no-ff", "-m", "merge", "side")
    merge = git("rev-parse", "HEAD")
    result = client_release.identity(repo, merge, "windows", None, "o/r")
    assert {root, child, side, merge} == set(result["ancestors"])
    assert git("merge-base", "--is-ancestor", side, merge) == ""


def test_payload_streams_large_files_as_bounded_chunks(tmp_path, monkeypatch):
    monkeypatch.setattr(client_release, "CHUNK_BYTES", 16)
    stage = tmp_path / "stage"
    (stage / "app").mkdir(parents=True)
    (stage / "eloria-assets").mkdir()
    (stage / "app/game.pck").write_bytes(bytes(range(256)))
    (stage / "eloria-assets/map.json").write_text("{}")
    (stage / "private.pem").write_text("never shipped")
    archive = tmp_path / "payload.zip"
    count, total = client_release.build_payload(stage, archive)
    assert count == 2 and total == 258
    with zipfile.ZipFile(archive) as handle:
        inventory = json.loads(handle.read("inventory.json"))
        assert all(entry["path"].startswith(("app/", "eloria-assets/")) for entry in inventory)
        chunks = [name for name in handle.namelist() if name.startswith("files/")]
        assert len(chunks) == 17
        assert all(len(handle.read(name)) <= 16 for name in chunks)
        content = b"".join(handle.read(f"files/000000/{i:06d}") for i in range(16))
        assert content == bytes(range(256))


def test_github_parts_reassemble_exactly_and_have_checksums(tmp_path):
    archive = tmp_path / "payload.zip"
    data = bytes(range(256)) * 4
    archive.write_bytes(data)
    parts = client_release.split_payload(archive, "https://github.com/o/r/releases/download/tag", part_bytes=130)
    assert len(parts) == 8
    buffers = []
    for part in parts:
        content = (tmp_path / part["url"].rsplit("/", 1)[1]).read_bytes()
        assert len(content) == part["size"] <= 130
        assert hashlib.sha256(content).hexdigest() == part["sha256"]
        buffers.append(content)
    assert b"".join(buffers) == data


def test_updating_shortcuts_use_restart_launcher_for_both_platforms(tmp_path):
    for platform in ("windows", "linux"):
        stage = tmp_path / platform
        stage.mkdir()
        (stage / ("RabbitLands-updater.exe" if platform == "windows" else "RabbitLands-updater.x86_64")).touch()
        package_client.write_launchers(stage, "play.example.org:2000", tmp_path, "test", package_client.PLATFORMS[platform])
        filename = "RabbitLands.bat" if platform == "windows" else "RabbitLands.sh"
        text = (stage / filename).read_text()
        assert "RabbitLands-updater" in text and "--server=play.example.org" in text
        assert json.loads((stage / "launcher-defaults.json").read_text())["args"] == ["--server=play.example.org", "--port=2000"]
