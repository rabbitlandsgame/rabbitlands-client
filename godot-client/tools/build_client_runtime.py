#!/usr/bin/env python3
"""Build the pinned Rust core and official Godot adapter into ignored storage."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from client_runtime_package import ABI, LIBRARIES, sha256, source_digest

CLIENT = Path(__file__).resolve().parents[1]
REPOSITORY = CLIENT.parent
SOURCE = CLIENT / "native/client_runtime"
RUST_VERSION = "1.99.1"


def run(command, env=None, cwd=SOURCE):
    subprocess.run([str(value) for value in command], cwd=cwd, env=env, check=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cargo", default=shutil.which("cargo") or str(Path.home() / ".cargo/bin/cargo.exe"))
    parser.add_argument("--cmake", default=shutil.which("cmake") or "cmake")
    parser.add_argument("--toolchain", default="stable", help="installed alias; actual rustc version must equal the pin")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--out", type=Path, default=CLIENT / "bin/client_runtime")
    args = parser.parse_args(argv)
    if not 1 <= args.jobs <= 8:
        parser.error("--jobs must be between 1 and 8")
    target = {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}.get(platform.system())
    if target is None or platform.machine().lower() not in {"amd64", "x86_64"}:
        parser.error("native host not qualified; ordinary client keeps the legacy path")
    env = dict(os.environ, CARGO_BUILD_JOBS=str(args.jobs))
    version = subprocess.check_output([args.cargo, "+" + args.toolchain, "--version"], text=True, env=env)
    rustc = str(Path(args.cargo).with_name("rustc.exe" if os.name == "nt" else "rustc"))
    actual = subprocess.check_output([rustc, "+" + args.toolchain, "--version"], text=True, env=env).strip()
    if not actual.startswith("rustc " + RUST_VERSION + " "):
        parser.error("pinned Rust " + RUST_VERSION + " required; observed " + actual)
    run([args.cargo, "+" + args.toolchain, "test", "--locked", "--offline"], env, SOURCE / "core")
    run([args.cargo, "+" + args.toolchain, "build", "--release", "--locked", "--offline"], env, SOURCE / "core")
    rust_library = SOURCE / "core/target/release" / ("rabbitlands_client_core.lib" if target == "windows" else "librabbitlands_client_core.a")
    build = SOURCE / "build" / (target + "-release")
    command = [args.cmake, "-S", SOURCE, "-B", build, "-DGODOTCPP_TARGET=template_release",
               "-DRL_RUST_LIBRARY=" + str(rust_library), "-DRL_BUILD_JOBS=" + str(args.jobs)]
    if target == "windows":
        command += ["-G", "Visual Studio 17 2022", "-A", "x64"]
    else:
        command += ["-DCMAKE_BUILD_TYPE=Release"]
    run(command, env)
    run([args.cmake, "--build", build, "--config", "Release", "--parallel", args.jobs], env)
    library = build / ("Release" if target == "windows" else "") / LIBRARIES[target]
    args.out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(library, args.out / LIBRARIES[target])
    shutil.copy2(SOURCE / "client_runtime.gdextension.in", args.out / "client_runtime.gdextension")
    (args.out / ".gdignore").write_text("", encoding="utf-8")
    manifest = {"schema": 1, "abi": ABI, "engine_major": 4, "engine_minor": 7, "platform": target,
                "architecture": "x86_64", "library": LIBRARIES[target], "rustc": actual, "cargo": version.strip(),
                "godot_cpp_revision": "507ed9d840c01a3c5b2a39af8bb4000bfac30bf5",
                "source_digest": source_digest(REPOSITORY), "library_sha256": sha256(args.out / LIBRARIES[target]),
                "descriptor_sha256": sha256(args.out / "client_runtime.gdextension")}
    (args.out / "runtime-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("Native runtime built: " + str(args.out))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
