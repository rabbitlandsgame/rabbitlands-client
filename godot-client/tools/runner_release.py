"""Build one desktop target with bounded storage, staging parts in an existing draft.

This does not enable Actions, provision a signing secret, or publish a release.
Use a metadata-complete, blob-filtered checkout containing only godot-client/tools.
The two platforms run in separate jobs; finalize their small receipts together.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys

import build_release as release
import client_release
import package_client as package
from linux_download_helper import download_script
from release_storage import DiskBudget


def authorize() -> None:
    # An installation token has no human /user identity. Accept it only in
    # this repository's own Actions context. GET /repos does not expose the
    # human user's .permissions.push field for this token. The workflow grants
    # contents: write; GitHub enforces it on each draft/upload API operation.
    if os.environ.get("GITHUB_ACTIONS") == "true":
        if os.environ.get("GITHUB_REPOSITORY") != release.REPOSITORY:
            raise ValueError("This runner is not executing in the Rabbit Lands client repository.")
        if release.gh("api", f"repos/{release.REPOSITORY}", "--jq", ".full_name") != release.REPOSITORY:
            raise ValueError("The workflow token cannot access the Rabbit Lands client repository.")
        return
    if release.gh("api", "user", "--jq", ".login") != release.ACCOUNT:
        raise ValueError("Use the Rabbit Lands account to stage release downloads.")
    if release.gh("api", f"repos/{release.REPOSITORY}", "--jq", ".permissions.push") != "true":
        raise ValueError("The workflow token needs contents: write on the client repository.")


class GitHubSink:
    """Only acknowledge a part after GitHub records its exact SHA-256 and size."""
    def __init__(self, release_id: int):
        authorize()
        self.release_id = release_id
        draft = json.loads(release.gh("api", f"repos/{release.REPOSITORY}/releases/{release_id}"))
        if not draft["draft"] or draft["author"]["login"] not in (release.ACCOUNT, "github-actions[bot]"):
            raise ValueError("Runner uploads require the project's existing draft release.")
        self.tag = draft["tag_name"]
        self.previous = {asset["name"]: asset for asset in release.github_assets(release_id)}

    def accept(self, path: Path, row: dict) -> None:
        if path.stat().st_size != row["size"] or client_release.digest(path) != row["sha256"]:
            raise ValueError("A runner download changed before upload.")
        actual = release.upload_asset_api(self.release_id, path, row, self.previous.get(path.name, {}))
        if not release.asset_matches(actual, row):
            raise ValueError(f"GitHub did not verify {path.name}; retaining the local part.")
        self.previous[path.name] = actual


class RunnerStorage:
    def __init__(self, root: Path, budget: DiskBudget, sink):
        self.root, self.budget, self.sink = root.resolve(), budget, sink
        self.rows = {}
        self.linux_archive = None
        self.source = None
        self.actor_plans = {}

    def check(self, phase, additional=0):
        self.budget.check(phase, additional)
        release.write_json(self.root / "disk-usage.json", self.budget.report())
        package.log(f"runner disk: {phase}: peak {self.budget.peak / 1e9:.2f} GB; "
                    f"{self.budget.reserve / 1e9:.1f} GB reserved")

    def accept_part(self, path, part):
        if path.is_symlink() or not path.resolve().is_relative_to(self.root):
            raise ValueError("Runner asset is outside its disposable output directory.")
        row = {"name": path.name, "size": part["size"], "sha256": part["sha256"]}
        if path.name in self.rows:
            raise ValueError("Duplicate runner asset name.")
        self.sink.accept(path, row)
        self.rows[path.name] = row
        release.write_json(self.root / "spooled-assets.json", {"assets": list(self.rows.values())})

    def part_matches(self, name, part):
        return self.rows.get(name) == {"name": name, "size": part["size"], "sha256": part["sha256"]}

    def clear_cache(self, path):
        path = path.resolve()
        allowed = {self.root / "source/godot-client/.godot", self.root / "vram-cache"}
        if path not in allowed or not path.is_relative_to(self.root):
            raise ValueError("Refusing to remove a cache outside this fresh runner build.")
        self.check("before cache cleanup")
        if path.exists():
            shutil.rmtree(path)

    def retire_editor_sources(self, project):
        if project.resolve() != self.root / "source/godot-client" or project.parent.resolve() not in self.actor_plans:
            raise ValueError("Editor sources can be retired only after this runner's reference proof.")
        self.check("editor reference proof complete")
        for folder in package.EDITOR_ONLY_PCK_DIRS:
            path = (project / folder).resolve()
            if not path.is_relative_to(project.resolve()) or path == project.resolve():
                raise ValueError("Editor source cleanup escaped the disposable project.")
            if path.exists():
                shutil.rmtree(path)
            path.mkdir()
            (path / ".gdignore").write_text("", encoding="utf-8")

    def cleanup(self, stage, sha):
        source = self.root / "source"
        if (source.resolve() != source or stage.resolve().parent != self.root / "downloads"
                or (stage / package.MARKER).read_text().strip() != sha
                or json.loads((self.root / ".runner-release.json").read_text()) != {
                    "repository": release.REPOSITORY, "commit": sha}):
            raise ValueError("Runner cleanup targets do not belong to this build.")
        package.git("-c", "core.longpaths=true", "worktree", "remove", "--force", str(source))
        shutil.rmtree(stage)
        for logs in (self.root / "downloads/.build/logs").glob("*"):
            if not logs.resolve().is_relative_to(self.root):
                raise ValueError("Runner logs escaped the owned output directory.")
            for name in ("updater-project", "installer-project"):
                project = logs / name
                if project.exists():
                    if not project.resolve().is_relative_to(self.root):
                        raise ValueError("Helper project escaped the owned output directory.")
                    shutil.rmtree(project)
            for helper in logs.glob("RabbitLands-install-*.exe"):
                helper.unlink()


def build(options) -> Path:
    sha = package.git("rev-parse", "--verify", "--end-of-options", options.ref + "^{commit}").strip()
    key = options.update_signing_key.resolve()
    origin = package.git("remote", "get-url", "origin").strip()
    if origin.rstrip("/").removesuffix(".git") not in (
            f"git@github.com:{release.REPOSITORY}", f"https://github.com/{release.REPOSITORY}"):
        raise ValueError("Use only the final Rabbit Lands client repository.")
    if not key.is_file() or any(key.is_relative_to(repo) for repo in (package.REPO, package.REPO.parent / "rabbitlands-server")):
        raise ValueError("The existing private signing key must be outside both repositories.")
    if not release.run([str(options.godot), "--headless", "--version"], capture=True).startswith("4.7.2.stable"):
        raise ValueError("Runner builds require Godot 4.7.2-stable and its matching export template.")
    # Require complete commit ancestry, without fetching historical blobs.
    # A sparse tools-only checkout need not materialize the public key yet.
    client_release.identity(package.REPO, sha, options.platform, None, release.REPOSITORY)
    if release.gh("api", f"repos/{release.REPOSITORY}/commits/{sha}", "--jq", ".sha") != sha:
        raise ValueError("The selected commit is not in the public client repository.")
    root = options.out.resolve() / f"runner-{options.platform}-{sha}"
    if any(root.is_relative_to(repo) for repo in (package.REPO, package.REPO.parent / "rabbitlands-server")):
        raise ValueError("Runner outputs must be outside both repositories.")
    root.mkdir(parents=True, exist_ok=False)
    release.write_json(root / ".runner-release.json", {"repository": release.REPOSITORY, "commit": sha})
    git_dir = Path(package.git("rev-parse", "--path-format=absolute", "--git-common-dir").strip())
    budget = DiskBudget([package.REPO, git_dir, root, options.godot.resolve(),
                         *([options.iscc.resolve().parent] if options.iscc else []), *options.tool_root])
    budget.check("preflight", 7_000_000_000)  # Runtime worktree + import/export scratch, before any uploads.
    storage = RunnerStorage(root, budget, GitHubSink(options.draft_release_id))
    source = root / "source"
    storage.source = source / "godot-client"
    output = root / "downloads"
    args = ["--platform", options.platform, "--ref", sha, "--no-fetch", "--godot", str(options.godot),
            "--build-dir", str(source), "--out", str(output), "--vram-cache", str(root / "vram-cache"),
            "--update-signing-key", str(key), "--update-public-key", str(storage.source / "data/update_public.pem"),
            "--server", options.server]
    if options.platform == "windows":
        if options.iscc is None:
            raise ValueError("The Windows runner needs Inno Setup 6 (--iscc).")
        args.extend(["--installer", "--online-installer", "--no-zip", "--iscc", str(options.iscc)])
    # prepare_build_tree materializes the selected commit before checking its public key.
    # package.main checks key existence first, so materialize that tiny file from Git.
    key_bytes = package.git("show", f"{sha}:godot-client/data/update_public.pem").encode("ascii")
    runner_public = root / "update_public.pem"
    runner_public.write_bytes(key_bytes)
    args[args.index("--update-public-key") + 1] = str(runner_public)
    if package.main(args, storage):
        raise ValueError("Runner packaging failed; verified remote parts can be reused on the next attempt.")
    stage = next(path for path in output.iterdir() if path.is_dir() and (path / package.MARKER).is_file())
    identity = json.loads((stage / "app/client-release.json").read_text())
    if identity["commit"] != sha or identity["platform"] != options.platform:
        raise ValueError("Runner identity differs from the selected commit.")
    manifest = output / f"{stage.name}-{options.platform}.json"
    small = [manifest, output / f"RabbitLands-{options.platform}.json"]
    if options.platform == "windows":
        small.append(output / f"{stage.name}-setup.exe")
    else:
        archive = storage.linux_archive
        helper = output / f"{stage.name}-download.sh"
        base = f"https://github.com/{release.REPOSITORY}/releases/download/client-{sha}"
        parts = [{"path": part["url"].rsplit("/", 1)[1], "sha256": part["sha256"]} for part in archive["parts"]]
        helper.write_text(download_script(stage.name, sha, base, archive["sha256"], parts), encoding="utf-8", newline="\n")
        small.append(helper)
    for path in small:
        storage.accept_part(path, {"size": path.stat().st_size, "sha256": client_release.digest(path)})
        path.unlink()
    storage.check("complete")
    receipt = root / f"{options.platform}-runner.json"
    release.write_json(receipt, {"schema": 1, "repository": release.REPOSITORY, "commit": sha,
        "platform": options.platform, "release_id": options.draft_release_id, "stage": stage.name,
        "update_schema": 2, "assets": list(storage.rows.values()), "disk": budget.report()})
    # Keep the tiny receipt/logs. Only this invocation's fresh worktree and stage are removed.
    storage.cleanup(stage, sha)
    storage.check("workspace released")
    data = json.loads(receipt.read_text())
    data["disk"] = budget.report()
    release.write_json(receipt, data)
    print(f"Runner receipt ready: {receipt}")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=("windows", "linux"), required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--godot", type=Path, required=True)
    parser.add_argument("--iscc", type=Path)
    parser.add_argument("--update-signing-key", type=Path, required=True)
    parser.add_argument("--draft-release-id", type=int, required=True)
    parser.add_argument("--tool-root", type=Path, action="append", required=True,
                        help="downloaded Godot/templates/tool directories charged to runner storage; repeatable")
    parser.add_argument("--server", default="game.rabbitlandsgame.com:2001")
    try:
        build(parser.parse_args())
    except (OSError, ValueError, package.PackageError) as error:
        print(f"Runner release failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
