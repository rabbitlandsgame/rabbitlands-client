#!/usr/bin/env python3
"""Build or verify the native-only cache for a selected desktop release commit.

No engine, export, upload or release operation is performed here. Callers may
prewarm the cache from exact native blobs before materializing game assets.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile

import build_client_runtime as builder
from client_runtime_package import ABI, EXTERNAL_SOURCE_INPUTS, LIBRARIES, NATIVE_PATH, sha256, source_digest, validate_payload

SCHEMA = 1
CACHE_POLICY = "rl-native-payload-cache-v1"
BUILD_RESERVE_BYTES = 3 * 1024**3
MAX_PAYLOAD_BYTES = 256 * 1024**2
MAX_PREWARM_SOURCE_BYTES = 64 * 1024**2
SOURCE_SUFFIXES = {".rs", ".h", ".cpp", ".toml", ".lock", ".in", ".json"}
BUILD_TOOLS = tuple(Path("godot-client/tools") / name for name in (
    "build_client_runtime.py", "release_native_runtime.py", "client_runtime_package.py"))


def require(value, message):
    if not value:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def native_input(path):
    return path.name == "CMakeLists.txt" or path.suffix in SOURCE_SUFFIXES


def git_source_identity(repository, commit):
    """Read only tree/blob IDs; key planning must not hydrate the selected assets."""
    repository = Path(repository).resolve()
    require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "full selected commit required")
    roots = [NATIVE_PATH, *EXTERNAL_SOURCE_INPUTS, *BUILD_TOOLS]
    tree = builder.output(["git", "-C", repository, "ls-tree", "-r", "-z", commit, "--", *roots])
    expected = {}
    for row in tree.split("\0"):
        if not row:
            continue
        metadata, relative = row.split("\t", 1)
        mode, kind, blob = metadata.split()
        path = Path(relative)
        if path.is_relative_to(NATIVE_PATH):
            tail = path.relative_to(NATIVE_PATH)
            if any(part in {"target", "build", ".deps", ".git"} for part in tail.parts[:-1]) or not native_input(path):
                continue
        require(mode in {"100644", "100755"} and kind == "blob" and re.fullmatch(r"[0-9a-f]{40}", blob),
                "native build input is not a regular committed blob: " + relative)
        expected[relative] = blob
    require(expected and all(path.as_posix() in expected for path in (*EXTERNAL_SOURCE_INPUTS, *BUILD_TOOLS)),
            "selected commit lacks native helper or external arithmetic inputs")
    record = {"selected_commit": commit, "input_count": len(expected),
              "build_tools": {path.as_posix(): expected[path.as_posix()] for path in BUILD_TOOLS},
              "input_blob_digest": hashlib.sha256(canonical(expected)).hexdigest()}
    return record, expected


def source_identity(repository, commit):
    repository = Path(repository).resolve()
    require(builder.output(["git", "-C", repository, "rev-parse", "HEAD"]) == commit,
            "materialized worktree HEAD differs from selected commit")
    record, expected = git_source_identity(repository, commit)
    root = repository / NATIVE_PATH
    actual = set()
    for directory, folders, files in os.walk(root):
        folders[:] = [name for name in folders if name not in {"target", "build", ".deps", ".git"}]
        for name in folders:
            require(not (Path(directory) / name).is_symlink(), "linked native source directory is unsupported")
        for name in files:
            path = Path(directory) / name
            if native_input(path):
                actual.add(path.relative_to(repository).as_posix())
    actual.update(path.as_posix() for path in (*EXTERNAL_SOURCE_INPUTS, *BUILD_TOOLS))
    require(actual == set(expected), "native build input set differs from selected commit")
    for relative, expected_blob in expected.items():
        path = repository / relative
        require(path.is_file() and not path.is_symlink(), "missing or linked native input: " + relative)
        size = path.stat().st_size
        digest = hashlib.sha1(f"blob {size}\0".encode("ascii"))
        with path.open("rb") as stream:
            while block := stream.read(1024**2):
                digest.update(block)
        require(digest.hexdigest() == expected_blob, "native input differs from selected Git blob: " + relative)
    record["source_digest"] = source_digest(repository)
    return record


def cache_identity(source, platform, toolchain):
    # Whole game commits may share native bytes. Preserve the original build's
    # commit separately; a cache hit re-proves every input against today's commit.
    return {"schema": SCHEMA, "policy": CACHE_POLICY, "platform": platform, "architecture": "x86_64",
            "abi": ABI, "engine": [4, 7], "rust": builder.RUST_VERSION,
            "godot_cpp": builder.GODOT_CPP_REVISION,
            "source": {key: value for key, value in source.items() if key not in {"selected_commit", "source_digest"}},
            "toolchain": toolchain}


def cache_key(identity):
    return CACHE_POLICY + "-" + identity["platform"] + "-" + hashlib.sha256(canonical(identity)).hexdigest()


def tool_context(platform, cargo="cargo", cmake="cmake", ninja="ninja", toolchain=builder.RUST_VERSION):
    require(platform in {"windows", "linux"}, "desktop release helper supports Windows and Linux only")
    require(builder.host_platform() == platform, "native cache preparation must run on its target OS/architecture")
    env = builder.build_environment(platform)
    actual = builder.toolchain_identity(platform, cargo, toolchain, cmake, ninja, env)
    version = re.search(r"cmake version (\d+)\.(\d+)", actual["cmake"])
    require(version and tuple(map(int, version.groups())) >= (3, 20), "CMake 3.20 or newer required")
    return env, actual


def release_cache_key(repository, commit, platform, **tools):
    source, _ = git_source_identity(repository, commit)
    _, actual = tool_context(platform, **tools)
    identity = cache_identity(source, platform, actual)
    return {"key": cache_key(identity), "identity": identity, "source": source,
            "requires_materialized_verification": True}


def verify_binary(path, platform):
    with path.open("rb") as stream:
        header = stream.read(64)
        if platform == "windows":
            require(len(header) == 64 and header[:2] == b"MZ", "native payload is not a PE binary")
            offset = struct.unpack_from("<I", header, 60)[0]
            require(64 <= offset <= 1024**2, "invalid native PE header offset")
            stream.seek(offset)
            pe = stream.read(26)
            require(len(pe) == 26 and pe[:4] == b"PE\0\0" and struct.unpack_from("<H", pe, 4)[0] == 0x8664
                    and struct.unpack_from("<H", pe, 24)[0] == 0x20B, "native payload is not an x86_64 PE32+ library")
        else:
            require(len(header) == 64 and header[:6] == b"\x7fELF\x02\x01"
                    and struct.unpack_from("<HH", header, 16) == (3, 62),
                    "native payload is not an x86_64 little-endian ELF shared library")


def verify_release_payload(directory, repository, platform, identity):
    directory = Path(directory)
    expected = {LIBRARIES[platform], "client_runtime.gdextension", "runtime-manifest.json", ".gdignore"}
    require(directory.is_dir() and not directory.is_symlink(), "missing or linked native payload directory")
    require({path.name for path in directory.iterdir()} == expected, "native payload inventory differs")
    total = 0
    for name in expected:
        path = directory / name
        require(path.is_file() and not path.is_symlink(), "linked or non-file native payload: " + name)
        total += path.stat().st_size
    require(0 < total <= MAX_PAYLOAD_BYTES, "native payload exceeds bounded cache size")
    manifest = validate_payload(directory, repository, platform)
    require(manifest.get("schema") == 1 and manifest.get("rustc") == identity["toolchain"]["rustc"]
            and manifest.get("cargo") == identity["toolchain"]["cargo"]
            and manifest.get("godot_cpp_revision") == builder.GODOT_CPP_REVISION
            and manifest.get("build") == identity["toolchain"], "native payload compiler or dependency provenance differs")
    require((directory / ".gdignore").read_bytes() == b"", "native payload scan guard differs")
    require((directory / "client_runtime.gdextension").read_bytes() ==
            (Path(repository) / NATIVE_PATH / "client_runtime.gdextension.in").read_bytes(),
            "native descriptor differs from the selected source template")
    verify_binary(directory / LIBRARIES[platform], platform)
    return {"bytes": total, "manifest": manifest,
            "files": {name: sha256(directory / name) for name in sorted(expected)}}


def validate_cache(entry, repository, platform, identity):
    require(entry.is_dir() and not entry.is_symlink(), "native cache entry is missing or linked")
    require({path.name for path in entry.iterdir()} == {"cache-record.json", "payload"}, "native cache inventory differs")
    record_path = entry / "cache-record.json"
    require(record_path.is_file() and not record_path.is_symlink() and record_path.stat().st_size < 1024**2,
            "native cache record is missing, linked or oversized")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    require(record.get("schema") == SCHEMA and record.get("identity") == identity,
            "native cache identity differs; refusing corrupt or stale cache")
    validated = verify_release_payload(entry / "payload", repository, platform, identity)
    require(record.get("files") == validated["files"], "native cache bytes differ from their build receipt")
    require(re.fullmatch(r"[0-9a-f]{40}", record.get("built_for_commit", "")) is not None,
            "native cache lacks its original selected build commit")
    return record, validated


def remove_owned_work(directory, parent):
    directory, parent = Path(directory).resolve(), Path(parent).resolve()
    require(directory.parent == parent and directory.name.startswith("rl-native-"), "refusing unowned native cleanup path")
    marker = directory / ".rl-native-work.json"
    require(marker.is_file() and json.loads(marker.read_text()).get("path") == str(directory),
            "native cleanup ownership marker is missing")
    def writable_retry(function, path, error):
        path = Path(path)
        require(path.resolve().is_relative_to(directory), "read-only cleanup escaped owned native work")
        if not isinstance(error, PermissionError):
            raise error
        path.chmod(path.stat().st_mode | stat.S_IWUSR)
        function(path)
    # Git pack files can be read-only on Windows. Retry only the exact owned
    # entry; never reset permissions on a caller's cache/source directory.
    shutil.rmtree(directory, onexc=writable_retry)


def workspace_bytes(directory):
    total = 0
    for root, folders, files in os.walk(directory):
        for name in folders:
            require(not (Path(root) / name).is_symlink(), "native workspace contains a linked directory")
        for name in files:
            path = Path(root) / name
            require(not path.is_symlink(), "native workspace contains a linked file")
            total += path.stat().st_size
    return total


def unlinked_path(path):
    """Reject linked existing ancestors before resolving an owned scratch path."""
    path = Path(os.path.abspath(path))
    for candidate in (*reversed(path.parents), path):
        require(not candidate.is_symlink() and not getattr(candidate, "is_junction", lambda: False)(),
                "linked native prewarm path is unsupported: " + str(candidate))
    return path.resolve()


def prewarm_cache(repository, commit, platform, cache_dir, work_root, check_budget, **tools):
    """Build/validate the normal cache from a disposable native-only Git worktree.

    Raw committed blobs avoid checkout filters and autocrlf. The later ordinary
    prepare_runtime call revalidates the same cache against the full checkout.
    check_budget accepts its reservation as a positional second argument, as
    release_storage.DiskBudget.check does; prepare_runtime keeps its existing API.
    """
    repository, cache_dir, work_root = map(unlinked_path, (repository, cache_dir, work_root))
    for left, right in ((repository, cache_dir), (repository, work_root), (cache_dir, work_root)):
        require(not left.is_relative_to(right) and not right.is_relative_to(left),
                "native prewarm source, cache and work roots must be disjoint")
    require(not work_root.exists() or work_root.is_dir(), "native prewarm work root is not a directory")
    _, expected = git_source_identity(repository, commit)
    def budget(label, upcoming_bytes=0):
        return check_budget(label, upcoming_bytes)
    budget("before native-only prewarm worktree", MAX_PREWARM_SOURCE_BYTES)
    work_root.mkdir(parents=True, exist_ok=True)
    envelope = Path(tempfile.mkdtemp(prefix="rl-native-prewarm-", dir=work_root)).resolve()
    source, compiler, output = (envelope / name for name in ("source", "compiler", "output"))
    marker = envelope / ".rl-native-work.json"
    ownership = {"path": str(envelope), "kind": "native-cache-prewarm", "commit": commit,
                 "source": str(source), "repository": str(repository)}
    marker.write_text(json.dumps(ownership), encoding="utf-8")
    source_bytes = 0
    receipt = None
    try:
        # --no-checkout never hydrates the selected game assets. read-tree sets
        # the real worktree index without writing any tracked worktree files.
        builder.output(["git", "-C", repository, "worktree", "add", "--detach", "--no-checkout", source, commit])
        builder.output(["git", "-C", source, "read-tree", commit])
        require(builder.output(["git", "-C", source, "rev-parse", "HEAD"]) == commit,
                "native prewarm HEAD differs from selected commit")
        for relative, oid in expected.items():
            relative_path = Path(relative)
            require(not relative_path.is_absolute() and ".." not in relative_path.parts,
                    "unsafe native prewarm input path")
            path = source / relative_path
            require(path.resolve().is_relative_to(source) and not path.exists(),
                    "native prewarm input already exists or escaped scratch")
            size = int(builder.output(["git", "-C", repository, "cat-file", "-s", oid]))
            source_bytes += size
            require(0 <= size <= MAX_PREWARM_SOURCE_BYTES and source_bytes <= MAX_PREWARM_SOURCE_BYTES,
                    "native prewarm inputs exceed bounded source reservation")
            budget("native-only prewarm blob " + relative)
            data = subprocess.run(["git", "-C", str(repository), "cat-file", "blob", oid],
                                  check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60).stdout
            require(len(data) == size and hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest() == oid,
                    "native prewarm raw Git blob differs: " + relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            unlinked_path(path.parent)
            with path.open("xb") as stream:
                stream.write(data)
        verified_source = source_identity(source, commit)
        budget("native-only prewarm sources verified")
        receipt = prepare_runtime(source, commit, platform, cache_dir, output, compiler, budget, **tools)
        require(receipt["source"] == verified_source, "native prewarm source proof changed")
        # The temporary payload is only a second verification copy. Its path is
        # deliberately absent from the returned, persistent cache receipt.
        receipt.pop("payload", None)
        receipt["prewarm"] = {"policy": "exact-native-git-blobs-before-assets-v1",
                              "input_count": len(expected), "materialized_source_bytes": source_bytes,
                              "planned_source_bytes": MAX_PREWARM_SOURCE_BYTES,
                              "game_assets_materialized": False}
    finally:
        require(envelope.parent == work_root and not envelope.is_symlink()
                and marker.is_file() and not marker.is_symlink()
                and json.loads(marker.read_text()) == ownership,
                "native prewarm cleanup ownership changed")
        if source.exists():
            require(not source.is_symlink() and (source / ".git").is_file()
                    and not (source / ".git").is_symlink(), "native prewarm worktree ownership is missing")
            require(Path(builder.output(["git", "-C", source, "rev-parse", "--show-toplevel"])).resolve() == source
                    and builder.output(["git", "-C", source, "rev-parse", "HEAD"]) == commit,
                    "native prewarm worktree identity changed before cleanup")
            common = lambda root: Path(builder.output(["git", "-C", root, "rev-parse", "--path-format=absolute", "--git-common-dir"])).resolve()
            require(common(source) == common(repository), "native prewarm worktree belongs to another repository")
            builder.output(["git", "-C", repository, "worktree", "remove", "--force", source])
            require(not source.exists(), "native prewarm worktree removal did not complete")
        remove_owned_work(envelope, work_root)
    budget("native-only prewarm scratch cleaned")
    receipt["prewarm"]["scratch_cleaned"] = True
    return receipt


def prepare_runtime(repository, commit, platform, cache_dir, out, work_root, check_budget, *,
                    cargo="cargo", cmake="cmake", ninja="ninja", toolchain=builder.RUST_VERSION, jobs=2):
    require(1 <= jobs <= 8, "native compiler jobs must be between 1 and 8")
    repository, cache_dir, out, work_root = map(lambda path: Path(path).resolve(),
                                               (repository, cache_dir, out, work_root))
    require(not out.exists(), "native output must be a fresh directory")
    for path in (cache_dir, work_root):
        require(not repository.is_relative_to(path) and path != repository, "native work/cache cannot contain source checkout")
    for left, right in ((out, cache_dir), (out, work_root), (cache_dir, work_root)):
        require(not left.is_relative_to(right) and not right.is_relative_to(left),
                "native output, cache and disposable work roots must be disjoint")
    source = source_identity(repository, commit)
    env, actual = tool_context(platform, cargo=cargo, cmake=cmake, ninja=ninja, toolchain=toolchain)
    identity = cache_identity(source, platform, actual)
    key = cache_key(identity)
    cache_dir.mkdir(parents=True, exist_ok=True)
    entry = cache_dir / key
    hit = entry.exists()
    workspace = None
    metrics = {"planned_workspace_bytes": BUILD_RESERVE_BYTES, "observed_peak_workspace_bytes": None,
               "sample_count": 0, "poll_seconds": 5, "measured_before_cleanup": False,
               "status": "not_created", "scope": "sampled native workspace disk bytes; caller accounts other roots"}
    def observe_work(label):
        current = workspace_bytes(workspace)
        metrics["sample_count"] += 1
        metrics["observed_peak_workspace_bytes"] = max(metrics["observed_peak_workspace_bytes"] or 0, current)
        metrics["status"] = "measured"
        check_budget(label)
        require(current <= BUILD_RESERVE_BYTES, "native workspace exceeded its 3 GiB reservation: " + label)
    try:
        if not hit:
            check_budget("before native build", upcoming_bytes=BUILD_RESERVE_BYTES)
            work_root.mkdir(parents=True, exist_ok=True)
            workspace = Path(tempfile.mkdtemp(prefix="rl-native-", dir=work_root)).resolve()
            (workspace / ".rl-native-work.json").write_text(json.dumps({"path": str(workspace)}), encoding="utf-8")
            payload = workspace / "cache/payload"
            args = builder.parser().parse_args([])
            args.repository, args.out, args.jobs = repository, payload, jobs
            args.build_root, args.dependency_dir = workspace / "build", workspace / "godot-cpp"
            args.cargo, args.cmake, args.ninja, args.toolchain = cargo, cmake, ninja, toolchain
            check_budget("native inputs verified")
            builder.build_payload(args, platform, env, actual, checkpoint=observe_work)
            verified = verify_release_payload(payload, repository, platform, identity)
            require(source_identity(repository, commit) == source, "selected native inputs changed during build")
            record = {"schema": SCHEMA, "identity": identity, "built_for_commit": commit, "files": verified["files"]}
            (workspace / "cache/cache-record.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
            check_budget("before native cache copy", upcoming_bytes=verified["bytes"])
            # Cache publication is exclusive: a parallel or pre-existing entry
            # cannot be silently overwritten by a new build.
            entry.mkdir(exist_ok=False)
            shutil.copytree(workspace / "cache", entry, dirs_exist_ok=True)
        record, verified = validate_cache(entry, repository, platform, identity)
        check_budget("before native payload materialization", upcoming_bytes=verified["bytes"])
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(entry / "payload", out)
        copied = verify_release_payload(out, repository, platform, identity)
        require(copied["files"] == verified["files"], "native output copy changed payload bytes")
        require(source_identity(repository, commit) == source, "selected native inputs changed before staging")
        receipt = {"schema": SCHEMA, "policy": CACHE_POLICY, "platform": platform, "payload": str(out),
                   "selected_commit": commit, "source": source, "cache_key": key, "cache_hit": hit,
                   "built_for_commit": record["built_for_commit"], "verification": copied}
    finally:
        if workspace is not None:
            try:
                metrics["measured_before_cleanup"] = True
                observe_work("native peak before scratch cleanup")
            finally:
                remove_owned_work(workspace, work_root)
    check_budget("native build scratch cleaned")
    receipt["scratch_cleaned"] = True
    receipt["workspace_budget"] = metrics
    return receipt


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("action", choices=("key", "prepare"))
    result.add_argument("--repository", type=Path, required=True)
    result.add_argument("--commit", required=True)
    result.add_argument("--platform", choices=("windows", "linux"), required=True)
    result.add_argument("--cargo", default="cargo")
    result.add_argument("--cmake", default="cmake")
    result.add_argument("--ninja", default="ninja")
    result.add_argument("--toolchain", default=builder.RUST_VERSION)
    result.add_argument("--cache-dir", type=Path)
    result.add_argument("--out", type=Path)
    result.add_argument("--work-root", type=Path)
    result.add_argument("--receipt", type=Path)
    result.add_argument("--jobs", type=int, default=2)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    tools = {name: getattr(args, name) for name in ("cargo", "cmake", "ninja", "toolchain")}
    if args.action == "key":
        receipt = release_cache_key(args.repository, args.commit, args.platform, **tools)
    else:
        require(all((args.cache_dir, args.out, args.work_root)), "prepare requires cache-dir, out and work-root")
        def disk_check(label, upcoming_bytes=0):
            parent = args.work_root.resolve()
            while not parent.exists():
                parent = parent.parent
            require(shutil.disk_usage(parent).free >= upcoming_bytes + 512 * 1024**2,
                    "native disk reserve exhausted: " + label)
        receipt = prepare_runtime(args.repository, args.commit, args.platform, args.cache_dir, args.out,
                                  args.work_root, disk_check, jobs=args.jobs, **tools)
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
