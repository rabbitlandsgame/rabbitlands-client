"""Build one desktop target with bounded storage, staging parts in an existing draft.

This does not enable Actions, provision a signing secret, or publish a release.
Use a metadata-complete, blob-filtered checkout containing only godot-client/tools.
The two platforms run in separate jobs; finalize their small receipts together.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import shutil
import sys

import build_release as release
import client_release
import shared_release_assets as shared
import package_client as package
from release_storage import DiskBudget
from release_asset_cache import AssetCache, input_key


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
        self.pool = None
        self.shared_previous = {}
        self.uploaded_bytes = self.reused_bytes = 0

    def shared_inventory(self):
        if self.pool is None:
            self.pool = shared.ensure()
            self.shared_previous = {a["name"]: a for a in release.github_assets(self.pool["id"])}
        return self.shared_previous

    def reuse(self, rows: list[dict]) -> bool:
        previous = self.shared_inventory()
        for row in rows:
            old = previous.get(row["name"], {})
            if not release.asset_matches(old, row):
                if old.get("state") == "uploaded":
                    raise ValueError("A completed shared download conflicts with its signed checksum.")
                return False
        self.reused_bytes += sum(row["size"] for row in rows)
        return True

    def accept(self, path: Path, row: dict) -> None:
        if path.stat().st_size != row["size"] or client_release.digest(path) != row["sha256"]:
            raise ValueError("A runner download changed before upload.")
        pooled = shared.is_name(path.name)
        if pooled and shared.NAME.fullmatch(path.name)[2] != row["sha256"]:
            raise ValueError("Shared download name and checksum disagree.")
        if pooled and self.pool is None:
            self.shared_inventory()
        previous = self.shared_previous if pooled else self.previous
        old = previous.get(path.name, {})
        reused = release.asset_matches(old, row)
        actual = release.upload_asset_api(self.pool["id"] if pooled else self.release_id, path, row, old,
                                          **({"immutable": True} if pooled else {}))
        if not release.asset_matches(actual, row):
            raise ValueError(f"GitHub did not verify {path.name}; retaining the local part.")
        previous[path.name] = actual
        if reused:
            self.reused_bytes += row["size"]
            package.log(f"Reusing verified download {path.name}")
        else:
            self.uploaded_bytes += row["size"]


class RunnerStorage:
    def __init__(self, root: Path, budget: DiskBudget, sink, asset_cache=None):
        self.root, self.budget, self.sink = root.resolve(), budget, sink
        self.rows = {}
        self.shared_rows = {}
        self.linux_archive = None
        self.source = None
        self.actor_plans = {}
        self.asset_cache = asset_cache
        self.previous_packages = {}

    def reuse_package(self, previous):
        parts = previous.get("parts", [])
        if not parts or not all(shared.matches(p, release.REPOSITORY) for p in parts):
            return False
        rows = [{"name": p["url"].rsplit("/", 1)[1], "size": p["size"], "sha256": p["sha256"]}
                for p in parts]
        missing = []
        for row in rows:
            if row["name"] in self.shared_rows:
                if self.shared_rows[row["name"]] != row:
                    raise ValueError("Conflicting cached package part.")
            else:
                missing.append(row)
        if not self.sink.reuse(missing):
            return False
        self.shared_rows.update({r["name"]: r for r in rows})
        if self.asset_cache:
            self.asset_cache.reused_packages += 1
        release.write_json(self.root / "spooled-assets.json", {"assets": list(self.rows.values()),
                           "shared_assets": list(self.shared_rows.values())})
        package.log(f"Reusing prepared package {previous['id']} ({len(parts)} verified parts)")
        return True

    def check(self, phase, additional=0):
        self.budget.check(phase, additional)
        release.write_json(self.root / "disk-usage.json", self.budget.report())
        package.log(f"runner disk: {phase}: peak {self.budget.peak / 1e9:.2f} GB; "
                    f"{self.budget.reserve / 1e9:.1f} GB reserved")

    def accept_part(self, path, part):
        if path.is_symlink() or not path.resolve().is_relative_to(self.root):
            raise ValueError("Runner asset is outside its disposable output directory.")
        row = {"name": path.name, "size": part["size"], "sha256": part["sha256"]}
        rows = self.shared_rows if shared.matches(part, release.REPOSITORY) else self.rows
        if path.name in rows:
            if rows[path.name] == row and rows is self.shared_rows:
                return
            raise ValueError("Duplicate runner asset name.")
        self.sink.accept(path, row)
        rows[path.name] = row
        release.write_json(self.root / "spooled-assets.json", {"assets": list(self.rows.values()), "shared_assets": list(self.shared_rows.values())})

    def part_matches(self, name, part):
        return (self.rows.get(name) or self.shared_rows.get(name)) == {"name": name, "size": part["size"], "sha256": part["sha256"]}

    def clear_cache(self, path):
        path = path.resolve()
        if self.asset_cache and path == self.asset_cache.vram:
            self.check("graphics cache retained")
            return
        allowed = {self.root / "source/godot-client/.godot", self.root / "vram-cache"}
        if path not in allowed or not path.is_relative_to(self.root):
            raise ValueError("Refusing to remove a cache outside this fresh runner build.")
        self.check("before cache cleanup")
        if self.asset_cache and path == self.root / "source/godot-client/.godot":
            self.asset_cache.retain_imports(path.parent)
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
    cache = None
    native_cache = getattr(options, "native_cache", None) or options.out.resolve().parent / "rabbitlands-native-cache" / options.platform
    native_cache = native_cache.resolve()
    if native_cache != options.out.resolve().parent / "rabbitlands-native-cache" / options.platform:
        raise ValueError("Use the job's dedicated native-runtime cache outside both repositories.")
    # Actions cache misses leave no directory. DiskBudget needs an existing
    # volume root before the native builder creates its cache and scratch.
    native_cache.parent.mkdir(parents=True, exist_ok=True)
    if getattr(options, "asset_cache", None):
        cache_root = options.out.resolve().parent / "rabbitlands-asset-cache" / options.platform
        if options.asset_cache.resolve() != cache_root or any(cache_root.is_relative_to(repo) for repo in (
                package.REPO, package.REPO.parent / "rabbitlands-server")):
            raise ValueError("Use the job's disposable rabbitlands-asset-cache directory outside the repositories.")
        cache = AssetCache(cache_root, input_key(package.git, sha, options.platform))
    git_dir = Path(package.git("rev-parse", "--path-format=absolute", "--git-common-dir").strip())
    budget = DiskBudget([package.REPO, git_dir, root, options.godot.resolve(),
                         *([options.iscc.resolve().parent] if options.iscc else []), *options.tool_root,
                         native_cache.parent,  # Payload cache plus its short-lived compiler scratch.
                         *([cache.root] if cache else [])])
    budget.check("preflight", 7_000_000_000)  # Runtime worktree + import/export scratch, before any uploads.
    storage = RunnerStorage(root, budget, GitHubSink(options.draft_release_id), cache)
    source = root / "source"
    storage.source = source / "godot-client"
    output = root / "downloads"
    args = ["--platform", options.platform, "--ref", sha, "--release-build", "--shared-release-assets", "--no-zip", "--no-fetch", "--godot", str(options.godot),
            "--build-dir", str(source), "--out", str(output), "--vram-cache", str(cache.vram if cache else root / "vram-cache"),
            "--update-signing-key", str(key), "--update-public-key", str(storage.source / "data/update_public.pem"),
            "--server", options.server, "--full-optimizations", "--native-runtime-cache",
            str(native_cache)]
    if options.platform == "windows":
        if options.iscc is None:
            raise ValueError("The Windows runner needs Inno Setup 6 (--iscc).")
        args.extend(["--installer", "--online-installer", "--no-zip", "--iscc", str(options.iscc)])
    # prepare_build_tree materializes the selected commit before checking its public key.
    # package.main checks key existence first, so materialize that tiny file from Git.
    key_bytes = package.git("show", f"{sha}:godot-client/data/update_public.pem").encode("ascii")
    runner_public = root / "update_public.pem"
    runner_public.write_bytes(key_bytes)
    if cache:
        storage.previous_packages = cache.packages(key_bytes, options.platform, release.REPOSITORY)
        package.log(f"Asset cache: {'verified hit' if cache.hit else 'cold build'}; "
                    f"{len(storage.previous_packages)} prior packages")
    args[args.index("--update-public-key") + 1] = str(runner_public)
    if package.main(args, storage):
        raise ValueError("Runner packaging failed; verified remote parts can be reused on the next attempt.")
    stage = next(path for path in output.iterdir() if path.is_dir() and (path / package.MARKER).is_file())
    identity = json.loads((stage / "app/client-release.json").read_text())
    if identity["commit"] != sha or identity["platform"] != options.platform:
        raise ValueError("Runner identity differs from the selected commit.")
    manifest = output / f"{stage.name}-{options.platform}.json"
    envelope = json.loads(manifest.read_text())
    payload = json.loads(base64.b64decode(envelope["payload"], validate=True))
    if cache:
        cache.built_packages = len(payload["packages"]) - cache.reused_packages
        cache.finish(manifest.read_bytes())
    small = [manifest, output / f"RabbitLands-{options.platform}.json"]
    if options.platform == "windows":
        small.append(output / f"{stage.name}-setup.exe")
    else:
        helper = output / f"{stage.name}-download.sh"
        from linux_download_helper import bootstrap_script
        helper.write_text(bootstrap_script(payload["updater"], envelope), encoding="utf-8", newline="\n")
        small.append(helper)
    for path in small:
        storage.accept_part(path, {"size": path.stat().st_size, "sha256": client_release.digest(path)})
        path.unlink()
    storage.check("complete")
    receipt = root / f"{options.platform}-runner.json"
    release.write_json(receipt, {"schema": 1, "repository": release.REPOSITORY, "commit": sha,
        "platform": options.platform, "release_id": options.draft_release_id, "stage": stage.name,
        "update_schema": 2, "shared_storage": 1, "shared_release_id": storage.sink.pool["id"],
        "shared_assets": list(storage.shared_rows.values()),
        "shared_packages": {p["id"]: [i["url"].rsplit("/", 1)[1] for i in p["parts"]] for p in payload["packages"]},
        "shared_helpers": {kind: payload[kind]["url"].rsplit("/", 1)[1] for kind in ("updater", "uninstall")},
        "transfer": {"uploaded_bytes": storage.sink.uploaded_bytes, "reused_bytes": storage.sink.reused_bytes},
        "asset_cache": cache.report() if cache else {"hit": False, "enabled": False},
        "optimizations": storage.optimization_proof,
        "assets": list(storage.rows.values()), "disk": budget.report()})
    # Keep the tiny receipt/logs. Only this invocation's fresh worktree and stage are removed.
    storage.cleanup(stage, sha)
    storage.check("workspace released")
    if cache:
        # Cache upload creates a compressed archive only after the large source
        # and stage have gone. Charge worst-case archive scratch to the budget.
        from release_storage import unique_bytes
        storage.check("before cache save", unique_bytes([cache.root]) + 64 * 1024**2)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary and cache:
        with Path(summary).open("a", encoding="utf-8") as output_summary:
            output_summary.write(f"\n{options.platform}: {cache.reused_packages} packages reused without rebuilding; "
                f"{cache.built_packages} rebuilt. Uploaded {storage.sink.uploaded_bytes:,} bytes; "
                f"reused {storage.sink.reused_bytes:,} bytes. Asset cache: {'hit' if cache.hit else 'cold'}.\n")
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
    parser.add_argument("--asset-cache", type=Path)
    parser.add_argument("--native-cache", type=Path)
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
