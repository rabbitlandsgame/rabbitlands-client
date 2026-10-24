"""Retire verified, disposable runner inputs after their last consumer."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil

import build_release as release
from client_release import digest

SDK_MARKER = ".rl-release-native-toolchain.json"


def checked_path(root):
    root = Path(root).absolute()
    for path in (root, *root.parents):
        if path.is_symlink() or path.is_junction():
            raise ValueError("Runner retirement path contains a link: " + str(path))
    return root.resolve()


def regular_tree(root):
    """Reject links before resolving or recursively removing an owned tree."""
    root = checked_path(root)
    for directory, folders, files in os.walk(root, followlinks=False):
        for name in [*folders, *files]:
            path = Path(directory) / name
            if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(root):
                raise ValueError("Runner retirement input contains a link: " + str(path))
            if name in files and not path.is_file():
                raise ValueError("Runner retirement requires regular files")
    return root.resolve()


def sdk_owner(root, runner_temp, commit, platform):
    root, runner_temp = regular_tree(root), checked_path(runner_temp)
    if (root != runner_temp / "rabbitlands-native-toolchain" or not root.is_dir()
            or not re.fullmatch(r"[0-9a-f]{40}", commit) or platform not in {"windows", "linux"}
            or os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("GITHUB_REPOSITORY") != release.REPOSITORY
            or Path(os.environ.get("RUNNER_TEMP", "")).resolve() != runner_temp
            or Path(os.environ.get("RUSTUP_HOME", "")).resolve() != root / "rustup"
            or Path(os.environ.get("CARGO_HOME", "")).resolve() != root / "cargo"):
        raise ValueError("Native SDK retirement requires this job's dedicated toolchain and homes")
    return {"schema": 1, "repository": release.REPOSITORY, "commit": commit, "platform": platform,
            "run_id": os.environ["GITHUB_RUN_ID"], "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"]}


def claim_native_sdk(root, runner_temp, commit, platform):
    owner = sdk_owner(root, runner_temp, commit, platform)
    root = Path(root).resolve()
    if {p.name for p in root.iterdir()} - {"rustup", "cargo", SDK_MARKER}:
        raise ValueError("Native toolchain contains inputs not owned by the pinned Rust installation")
    marker = root / SDK_MARKER
    if marker.exists():
        if json.loads(marker.read_text()) != owner:
            raise ValueError("Native SDK ownership belongs to another run")
    else:
        with marker.open("x", encoding="utf-8") as stream:
            json.dump(owner, stream, sort_keys=True)
    return owner


def retire_native_sdk(root, runner_temp, commit, platform, bootstrap, check_budget, receipt_path):
    owner = sdk_owner(root, runner_temp, commit, platform)
    root = Path(root).resolve()
    if (json.loads((root / SDK_MARKER).read_text()) != owner
            or bootstrap.get("selected_commit") != commit or bootstrap.get("platform") != platform
            or bootstrap.get("scratch_cleaned") is not True
            or bootstrap.get("prewarm", {}).get("scratch_cleaned") is not True
            or bootstrap.get("prewarm", {}).get("game_assets_materialized") is not False
            or bootstrap.get("prewarm", {}).get("policy") != "exact-native-git-blobs-before-assets-v1"):
        raise ValueError("Native SDK retirement requires a completed exact-source native bootstrap")
    if {p.name for p in root.iterdir()} - {"rustup", "cargo", SDK_MARKER}:
        raise ValueError("Native SDK ownership changed before retirement")
    rows = {p.relative_to(root).as_posix(): {"size": p.stat().st_size, "sha256": digest(p)}
            for p in sorted(root.rglob("*")) if p.is_file() and p != root / SDK_MARKER}
    receipt = {**owner, "status": "verified_before_retirement", "files": rows,
               "retired_bytes": sum(row["size"] for row in rows.values())}
    receipt_path = checked_path(receipt_path)
    if receipt_path.exists() or receipt_path.resolve().is_relative_to(root):
        raise ValueError("Native SDK retirement receipt must be fresh and outside the SDK")
    release.write_json(receipt_path, receipt)
    check_budget("native SDK verified before retirement")
    # Keep the accounted volume root and ownership marker. Only the two homes
    # installed by this Actions job are removed; system Rust/MSVC stays intact.
    for name in ("rustup", "cargo"):
        path = root / name
        regular_tree(path)
        if path.exists():
            shutil.rmtree(path)
    receipt["status"] = "retired_after_verified_native_bootstrap"
    release.write_json(receipt_path, receipt)
    check_budget("native SDK retired before runtime source materialization")
    return receipt


def retire_unstaged_maps(source, stage, expected, protected, check_budget, receipt_path):
    """Remove committed map inputs absent from both shipment and cook closure."""
    source, stage = regular_tree(source), regular_tree(stage)
    maps = source / "eloria-assets/maps"
    if (source == stage or source.is_relative_to(stage) or stage.is_relative_to(source)
            or not source.is_dir() or not stage.is_dir() or not maps.is_dir()):
        raise ValueError("Map retirement requires disjoint source and stage trees")
    candidates = {}
    for path in sorted(maps.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source).as_posix()
        if relative not in expected:
            raise ValueError("Uncommitted map retirement input: " + relative)
        if (stage / relative).is_file() or relative in protected:
            continue
        size = path.stat().st_size
        blob = hashlib.sha1(f"blob {size}\0".encode("ascii"))
        with path.open("rb") as stream:
            while chunk := stream.read(1024**2):
                blob.update(chunk)
        if blob.hexdigest() != expected[relative]:
            raise ValueError("Map retirement bytes differ from selected Git input: " + relative)
        candidates[relative] = {"size": size, "git_blob": blob.hexdigest(), "sha256": digest(path)}
    # Validate the complete protected closure before removing any candidate.
    for relative, protected_digest in protected.items():
        path = source / relative
        if not path.resolve().is_relative_to(source) or not path.is_file() or digest(path) != protected_digest:
            raise ValueError("Prepared input changed before map retirement: " + relative)
    receipt_path = checked_path(receipt_path)
    if receipt_path.exists() or receipt_path.resolve().is_relative_to(maps):
        raise ValueError("Map retirement receipt must be fresh and outside the retired map inputs")
    receipt = {"schema": 1, "policy": "unstaged-committed-maps-outside-prepared-closure-v1",
               "status": "verified_before_retirement", "files": candidates,
               "retired_bytes": sum(row["size"] for row in candidates.values()), "protected_inputs": protected}
    release.write_json(receipt_path, receipt)
    check_budget("unstaged map source inputs verified")
    for relative, row in candidates.items():
        path = source / relative
        if (stage / relative).exists() or digest(path) != row["sha256"]:
            raise ValueError("Map retirement input changed during retirement: " + relative)
        path.unlink()
    receipt["status"] = "retired_after_shipping_and_prepared_closure_proof"
    release.write_json(receipt_path, receipt)
    check_budget("unstaged map sources retired before graphics and prepared cooking")
    return receipt
