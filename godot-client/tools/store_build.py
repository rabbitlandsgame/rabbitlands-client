"""Build native Steam depots or a manually replaced macOS test bundle.

No Steam credentials, App ID or GitHub signing secret is needed to build.
Artifacts are streamed to bounded parts; SteamPipe upload is a separate step.
"""
from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile

import client_release
import package_client as package
from release_storage import DiskBudget, PartWriter
from runner_release import RunnerStorage
import setup_runner_tools


def tar_member(info):
    if PurePosixPath(info.name).name == package.MARKER:
        return None
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    name = PurePosixPath(info.name).name
    executable = name == "RabbitLands.x86_64" or (name.startswith("RabbitLands") and name.endswith(".sh"))
    info.mode = 0o755 if info.isdir() or info.mode & 0o111 or executable else 0o644
    return info


def pack(stage: Path, out: Path, budget=None) -> dict:
    out.mkdir(parents=True, exist_ok=False)
    with PartWriter(out / "depot.tar.gz", "artifact:", client_release.PART_BYTES, budget=budget) as writer:
        with tarfile.open(fileobj=writer, mode="w|gz", compresslevel=1, dereference=False) as archive:
            archive.add(stage, arcname=".", filter=tar_member)
    return {"parts": [{"name": p["url"].rsplit("/", 1)[-1], "size": p["size"], "sha256": p["sha256"]}
                      for p in writer.parts], "size": writer.size, "sha256": writer.sha256}


def native_platform():
    return "windows" if os.name == "nt" else "macos" if sys.platform == "darwin" else "linux"


def build(options):
    if options.platform != native_platform():
        raise ValueError("Use a native runner for each platform.")
    if options.distribution == "standalone" and options.platform != "macos":
        raise ValueError("Windows/Linux standalone distribution uses the existing GitHub installer workflow.")
    sha = package.git("rev-parse", "--verify", "--end-of-options", options.ref + "^{commit}").strip()
    root = options.out.resolve()
    if root.is_relative_to(package.REPO) or root.is_relative_to(package.REPO.parent / "rabbitlands-server"):
        raise ValueError("Build outputs must be outside both repositories.")
    root.mkdir(parents=True, exist_ok=False)
    (root / "BUILD.json").write_text(json.dumps({"commit": sha, "distribution": options.distribution}))
    git_dir = Path(package.git("rev-parse", "--path-format=absolute", "--git-common-dir").strip())
    world_cache = root.parent / "rabbitlands-native-cache/world-preparation-cache"
    if options.platform != "macos":
        world_cache.mkdir(parents=True, exist_ok=True)
    budget = DiskBudget([package.REPO, git_dir, root,
                         *([world_cache] if options.platform != "macos" else [])],
                        allow_internal_symlinks=options.platform == "macos")
    storage = RunnerStorage(root, budget, None)
    storage.check("preflight", 7_000_000_000)
    config = setup_runner_tools.install(options.platform, root / "tools", installers=False)
    os.environ.update(config["env"])
    version = subprocess.check_output([str(config["godot"]), "--headless", "--version"], text=True).strip()
    if not version.startswith("4.7.2.stable"):
        raise ValueError("Store builds require the pinned Godot 4.7.2-stable toolchain.")
    if options.platform == "macos":
        subprocess.run(["lipo", str(config["godot"]), "-verify_arch", "x86_64", "arm64"], check=True)
    public = root / "update_public.pem"
    public.write_text(package.git("show", f"{sha}:godot-client/data/update_public.pem"), encoding="ascii")
    source = root / "source"
    storage.source = source / "godot-client"
    args = ["--platform", options.platform, "--distribution", options.distribution,
            "--ref", sha, "--no-fetch", "--godot", str(config["godot"]), "--build-dir", str(source),
            "--out", str(root / "downloads"), "--vram-cache", str(root / "vram-cache"),
            "--update-public-key", str(public), "--no-zip"]
    if options.platform != "macos":
        args += ["--prepared-world", "--world-preparation-cache", str(world_cache)]
    if package.main(args, storage):
        raise ValueError("Store build failed; see retained startup and disk diagnostics.")
    stage = next(path for path in (root / "downloads").iterdir()
                 if path.is_dir() and (path / package.MARKER).is_file())
    # No additional full-size tar/ZIP or artifact copy. Retire the owned source
    # tree before streaming, and charge retained parts to the same disk budget.
    package.git("-c", "core.longpaths=true", "worktree", "remove", "--force", str(source))
    storage.check("before artifact streaming")
    packed = pack(stage, root / "artifact", budget)
    storage.check("artifact complete")
    receipt = {"schema": 1, "commit": sha, "platform": options.platform,
               "distribution": options.distribution, "archive": packed,
               "macos_signing": "ad-hoc-test-only" if options.platform == "macos" else None}
    (root / "artifact/depot.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if (stage / package.MARKER).read_text().strip() != sha or stage.resolve().parent != root / "downloads":
        raise ValueError("Refusing to clean an unowned stage.")
    unpacked = sum(path.stat().st_size for path in stage.rglob("*") if path.is_file() and not path.is_symlink())
    shutil.rmtree(stage)
    if options.platform == "macos":
        # Restore only after releasing the original stage: prove that the
        # actual transport preserves signing, modes and resource paths without
        # retaining two complete app bundles on a small runner.
        storage.check("before Mac archive restore", unpacked)
        restored = root / "verified-bundle"
        extract(root / "artifact", restored)
        bundle = package.macos_package.bundle(restored)
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(bundle)], check=True)
        logs = next((root / "downloads/.build/logs").glob("macos-*"))
        package.macos_package.smoke_binary(bundle / "Contents/MacOS/RabbitLands", restored,
            logs / "smoke-restored.log", package.run_godot, package.SMOKE_FAILURES)
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(bundle)], check=True)
        storage.check("Mac archive verified")
        shutil.rmtree(restored)
    storage.check("workspace released")
    if options.platform != "macos":
        from release_storage import unique_bytes
        storage.check("before world cache save", unique_bytes([world_cache]) + 64 * 1024**2)
    return receipt


class Parts(io.RawIOBase):
    def __init__(self, paths):
        self.paths = iter(paths)
        self.handle = None

    def readable(self):
        return True

    def readinto(self, buffer):
        while True:
            if self.handle is None:
                path = next(self.paths, None)
                if path is None:
                    return 0
                self.handle = path.open("rb")
            count = self.handle.readinto(buffer)
            if count:
                return count
            self.handle.close()
            self.handle = None

    def close(self):
        if self.handle:
            self.handle.close()
        super().close()


def extract(artifact: Path, out: Path):
    import hashlib
    receipt = json.loads((artifact / "depot.json").read_text())
    if receipt.get("schema") != 1 or receipt.get("distribution") not in {"steam", "standalone"}:
        raise ValueError("Unsupported depot artifact.")
    paths, total, digest = [], 0, hashlib.sha256()
    for index, part in enumerate(receipt["archive"]["parts"], 1):
        if part["name"] != f"depot.tar.gz.{index:03d}":
            raise ValueError("Invalid or unordered artifact part.")
        path = artifact / part["name"]
        if path.is_symlink() or path.stat().st_size != part["size"] or client_release.digest(path) != part["sha256"]:
            raise ValueError("Depot part size or SHA-256 differs from its receipt.")
        with path.open("rb") as handle:
            while chunk := handle.read(1024**2):
                digest.update(chunk)
                total += len(chunk)
        paths.append(path)
    if total != receipt["archive"]["size"] or digest.hexdigest() != receipt["archive"]["sha256"]:
        raise ValueError("Depot archive SHA-256 differs from its receipt.")
    out.mkdir(parents=True, exist_ok=False)
    # Python's data filter prevents absolute/traversal paths, escaping links,
    # device nodes and writes outside this new destination. No concatenated copy.
    with Parts(paths) as raw, io.BufferedReader(raw) as stream, tarfile.open(fileobj=stream, mode="r|gz") as archive:
        for member in archive:
            archive.extract(member, out, filter="data")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    compile = commands.add_parser("build")
    compile.add_argument("--platform", choices=("windows", "linux", "macos"), required=True)
    compile.add_argument("--distribution", choices=("steam", "standalone"), default="steam")
    compile.add_argument("--ref", default="HEAD")
    compile.add_argument("--out", type=Path, required=True)
    unpack = commands.add_parser("extract")
    unpack.add_argument("--artifact", type=Path, required=True)
    unpack.add_argument("--out", type=Path, required=True)
    options = parser.parse_args()
    try:
        receipt = build(options) if options.command == "build" else extract(options.artifact, options.out)
        print(json.dumps({key: receipt[key] for key in ("commit", "platform", "distribution")}, indent=2))
    except (OSError, ValueError, package.PackageError) as error:
        parser.exit(1, f"Store build failed: {error}\n")


if __name__ == "__main__":
    main()
