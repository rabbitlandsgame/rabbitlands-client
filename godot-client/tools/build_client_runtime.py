#!/usr/bin/env python3
"""Build the pinned Rust core and official Godot adapter into ignored storage."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys

from client_runtime_package import ABI, LIBRARIES, sha256, source_digest

CLIENT = Path(__file__).resolve().parents[1]
REPOSITORY = CLIENT.parent
RUST_VERSION = "1.99.1"
GODOT_CPP_REVISION = "507ed9d840c01a3c5b2a39af8bb4000bfac30bf5"
BUILD_POLICY = "rl-native-release-ninja-v1"
HOST_TARGETS = {"windows": "x86_64-pc-windows-msvc", "linux": "x86_64-unknown-linux-gnu", "macos": "x86_64-apple-darwin"}


def stop_owned_child(child, system=None):
    """Stop this invocation's child tree, never an executable-name/global match."""
    if child.poll() is not None:
        return
    if (system or os.name) == "nt":
        # Keep Popen's process handle open, so this PID cannot be reused while
        # the exact owned tree is terminated by the Windows process-tree API.
        try:
            subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        try:
            os.killpg(child.pid, signal.SIGTERM)
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if child.poll() is None:
        child.kill()
    child.wait(timeout=15)


def run(command, env=None, cwd=None, checkpoint=None, label="native subprocess"):
    command = [str(value) for value in command]
    if checkpoint is None:
        subprocess.run(command, cwd=cwd, env=env, check=True)
        return
    checkpoint(label + " before start")
    child = subprocess.Popen(command, cwd=cwd, env=env,
                             start_new_session=os.name != "nt",
                             creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
    try:
        while True:
            try:
                code = child.wait(timeout=5)
                break
            except subprocess.TimeoutExpired:
                checkpoint(label + " running")
        checkpoint(label + " completed")
        if code:
            raise subprocess.CalledProcessError(code, command)
    except BaseException:
        stop_owned_child(child)
        raise


def output(command, env=None, cwd=None):
    return subprocess.check_output([str(value) for value in command], cwd=cwd, env=env,
                                   text=True, encoding="utf-8", errors="replace").strip()


def host_platform():
    target = {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}.get(platform.system())
    if target is None or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise ValueError("native builds require an x86_64 Windows, Linux or Intel macOS host")
    return target


def windows_environment(environment):
    """Ask the installed Visual Studio for x64 tools; never assume its year."""
    env = {name.upper(): value for name, value in environment.items()}
    vswhere = shutil.which("vswhere", path=env.get("PATH"))
    if not vswhere:
        vswhere = str(Path(env.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) /
                      "Microsoft Visual Studio/Installer/vswhere.exe")
    installation = output([vswhere, "-latest", "-products", "*", "-requires",
                           "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                           "-property", "installationPath"], env)
    script = Path(installation) / "Common7/Tools/VsDevCmd.bat"
    if not installation or not script.is_file() or any(c in str(script) for c in '\r\n"'):
        raise ValueError("Visual Studio x64 C++ tools were not found by vswhere")
    command = 'call "' + str(script) + '" -no_logo -arch=x64 -host_arch=x64 >nul && set'
    text = output([env.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", command], env)
    for line in text.splitlines():
        name, separator, value = line.partition("=")
        if separator and name:
            for existing in list(env):
                if existing.lower() == name.lower():
                    env.pop(existing)
            env[name.upper()] = value
    if env.get("VSCMD_ARG_TGT_ARCH", "").lower() != "x64":
        raise ValueError("Visual Studio did not initialize an x64 target environment")
    return env


def build_environment(target, environment=None):
    env = dict(os.environ if environment is None else environment)
    # Inherited overrides can change ABI/flags without changing source inputs.
    for name in list(env):
        upper = name.upper()
        if upper.startswith(("RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "CARGO_TARGET_", "CARGO_BUILD_", "CARGO_PROFILE_", "CMAKE_")) or upper in {
                "RUSTC", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "CC", "CXX", "CFLAGS", "CXXFLAGS",
                "LDFLAGS", "CL", "_CL_", "LINK", "_LINK_", "CARGO_INCREMENTAL", "RUSTC_BOOTSTRAP"}:
            env.pop(name)
    return windows_environment(env) if target == "windows" else env


def toolchain_identity(target, cargo, toolchain, cmake, ninja, env):
    cargo_path = shutil.which(str(cargo), path=env.get("PATH")) or str(cargo)
    rustc = str(Path(cargo_path).with_name("rustc.exe" if target == "windows" else "rustc"))
    rust_info = output([rustc, "+" + toolchain, "-vV"], env)
    first = rust_info.splitlines()[0]
    if not first.startswith("rustc " + RUST_VERSION + " "):
        raise ValueError("pinned Rust " + RUST_VERSION + " required; observed " + first)
    host = next((line.removeprefix("host: ") for line in rust_info.splitlines() if line.startswith("host: ")), "")
    if host != HOST_TARGETS[target]:
        raise ValueError("Rust host target must be " + HOST_TARGETS[target] + "; observed " + host)
    compiler = shutil.which("cl.exe" if target == "windows" else ("clang++" if target == "macos" else "g++"), path=env.get("PATH"))
    if not compiler:
        raise ValueError("required MSVC x64 or GNU C++ compiler is unavailable")
    if target == "windows":
        probe = subprocess.run([compiler], env=env, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", check=False)
        banner = (probe.stdout + probe.stderr).strip()
        if "x64" not in banner:
            raise ValueError("C++ compiler did not report an x64 MSVC target")
    else:
        banner = output([compiler, "--version"], env)
        compiler_target = output([compiler, "-dumpmachine"], env)
        if target == "macos":
            if not compiler_target.startswith("x86_64-apple-darwin"):
                raise ValueError("C++ compiler must target Intel macOS; observed " + compiler_target)
        elif compiler_target not in {"x86_64-linux-gnu", "x86_64-pc-linux-gnu", "x86_64-unknown-linux-gnu"}:
            raise ValueError("C++ compiler must target x86_64 GNU/Linux; observed " + compiler_target)
    return {"policy": BUILD_POLICY, "rustc": first, "rust_host": host,
            "cargo": output([cargo_path, "+" + toolchain, "--version"], env),
            "cmake": output([cmake, "--version"], env).splitlines()[0],
            "ninja": output([ninja, "--version"], env),
            "compiler": banner.splitlines()[0], "compiler_path": compiler, "generator": "Ninja"}


def verify_dependency(directory, env):
    revision = output(["git", "-C", directory, "rev-parse", "HEAD"], env)
    modified = output(["git", "-C", directory, "status", "--porcelain", "--untracked-files=all"], env)
    if revision != GODOT_CPP_REVISION or modified:
        raise ValueError("godot-cpp checkout must match the clean pinned revision before compilation")
    return revision


def prepare_dependency(directory, env, checkpoint=None):
    if directory.exists():
        return verify_dependency(directory, env)
    directory.parent.mkdir(parents=True, exist_ok=True)
    run(["git", "init", directory], env, checkpoint=checkpoint, label="native dependency init")
    run(["git", "-C", directory, "remote", "add", "origin", "https://github.com/godotengine/godot-cpp.git"], env, checkpoint=checkpoint, label="native dependency origin")
    run(["git", "-C", directory, "fetch", "--depth", "1", "origin", GODOT_CPP_REVISION], env, checkpoint=checkpoint, label="native dependency fetch")
    run(["git", "-C", directory, "checkout", "--detach", "FETCH_HEAD"], env, checkpoint=checkpoint, label="native dependency checkout")
    return verify_dependency(directory, env)


def build_payload(args, target, env, identity, checkpoint=None):
    repository = args.repository.resolve()
    source = repository / "godot-client/native/client_runtime"
    original_digest = source_digest(repository)
    work = args.build_root.resolve() if args.build_root else source / "build" / (target + "-release")
    dependency = args.dependency_dir.resolve() if args.dependency_dir else source / ".deps/godot-cpp"
    env = dict(env, CARGO_BUILD_JOBS=str(args.jobs), CARGO_TARGET_DIR=str(work / "cargo"))
    prepare_dependency(dependency, env, checkpoint=checkpoint)
    run([args.cargo, "+" + args.toolchain, "test", "--locked", "--offline"], env, source / "core", checkpoint=checkpoint, label="native Rust tests")
    run([args.cargo, "+" + args.toolchain, "build", "--release", "--locked", "--offline"], env, source / "core", checkpoint=checkpoint, label="native Rust release")
    rust_library = work / "cargo/release" / (
        "rabbitlands_client_core.lib" if target == "windows" else "librabbitlands_client_core.a")
    build = work / "cpp"
    command = [args.cmake, "-S", source, "-B", build, "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
               "-DCMAKE_MAKE_PROGRAM=" + str(args.ninja),
               "-DCMAKE_CXX_COMPILER=" + identity["compiler_path"],
               "-DGODOTCPP_TARGET=template_release", "-DGODOT_CPP_REVISION=" + GODOT_CPP_REVISION,
               "-DFETCHCONTENT_SOURCE_DIR_GODOT_CPP=" + str(dependency),
               "-DFETCHCONTENT_UPDATES_DISCONNECTED_GODOT_CPP=ON",
               "-DRL_RUST_LIBRARY=" + str(rust_library), "-DRL_BUILD_JOBS=" + str(args.jobs)]
    run(command, env, checkpoint=checkpoint, label="native CMake configure")
    verify_dependency(dependency, env)
    run([args.cmake, "--build", build, "--config", "Release", "--parallel", args.jobs], env, checkpoint=checkpoint, label="native C++ release")
    verify_dependency(dependency, env)
    if source_digest(repository) != original_digest:
        raise ValueError("native source inputs changed while the payload was being built")
    args.out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(build / LIBRARIES[target], args.out / LIBRARIES[target])
    shutil.copy2(source / "client_runtime.gdextension.in", args.out / "client_runtime.gdextension")
    (args.out / ".gdignore").write_text("", encoding="utf-8")
    manifest = {"schema": 1, "abi": ABI, "engine_major": 4, "engine_minor": 7, "platform": target,
                "architecture": "x86_64", "library": LIBRARIES[target], "rustc": identity["rustc"],
                "cargo": identity["cargo"], "godot_cpp_revision": GODOT_CPP_REVISION,
                "build": identity, "source_digest": original_digest,
                "library_sha256": sha256(args.out / LIBRARIES[target]),
                "descriptor_sha256": sha256(args.out / "client_runtime.gdextension")}
    (args.out / "runtime-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--repository", type=Path, default=REPOSITORY)
    result.add_argument("--cargo", default=shutil.which("cargo") or "cargo")
    result.add_argument("--cmake", default=shutil.which("cmake") or "cmake")
    result.add_argument("--ninja", default=shutil.which("ninja") or "ninja")
    result.add_argument("--toolchain", default=RUST_VERSION,
                        help="installed rustup name; rustc version and target are checked against the pins")
    result.add_argument("--platform", choices=tuple(HOST_TARGETS))
    result.add_argument("--jobs", type=int, default=2)
    result.add_argument("--build-root", type=Path)
    result.add_argument("--dependency-dir", type=Path)
    result.add_argument("--out", type=Path, default=CLIENT / "bin/client_runtime")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    if not 1 <= args.jobs <= 8:
        raise ValueError("--jobs must be between 1 and 8")
    target = host_platform()
    if args.platform and args.platform != target:
        raise ValueError("cross-compilation is not supported by this release helper")
    env = build_environment(target)
    identity = toolchain_identity(target, args.cargo, args.toolchain, args.cmake, args.ninja, env)
    build_payload(args, target, env, identity)
    print("Native runtime built: " + str(args.out))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
