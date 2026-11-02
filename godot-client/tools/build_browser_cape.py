"""Build the existing cape arithmetic for the browser and its export editor."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

from build_client_runtime import GODOT_CPP_REVISION, prepare_dependency, windows_environment

REPO = Path(__file__).resolve().parents[2]
EMSCRIPTEN_VERSION = "4.0.20"  # Matches the supported Godot 4.7.2 web templates.


def strip_debug_sections(data: bytes) -> bytes:
    """Remove diagnostic metadata without optimizing/re-emitting any wasm code."""
    if data[:8] != b"\0asm\x01\0\0\0":
        raise ValueError("Invalid WebAssembly header")

    def integer(at):
        value = 0
        for shift in range(0, 35, 7):
            if at >= len(data): raise ValueError("Truncated WebAssembly length")
            byte = data[at]; at += 1
            value |= (byte & 127) << shift
            if not byte & 128:
                if value > 0xffffffff: raise ValueError("Invalid WebAssembly length")
                return value, at
        raise ValueError("Invalid WebAssembly length")

    result = bytearray(data[:8]); at = 8
    while at < len(data):
        start = at; kind = data[at]; size, payload = integer(at + 1)
        end = payload + size
        if end > len(data): raise ValueError("Truncated WebAssembly section")
        remove = False
        if kind == 0:
            length, text = integer(payload)
            if text + length > end: raise ValueError("Truncated WebAssembly section name")
            name = data[text:text + length].decode("utf-8")
            remove = name.startswith(".debug") or name in {"name", "sourceMappingURL", "external_debug_info"}
        if not remove: result.extend(data[start:end])
        at = end
    return bytes(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emsdk", required=True, type=Path, help="Activated task-local Emscripten 4.0.20 SDK")
    parser.add_argument("--bindings", type=Path, default=REPO / ".local/browser-prototype/deps/godot-cpp")
    parser.add_argument("--out", type=Path, default=REPO / ".local/browser-prototype/cape-runtime")
    parser.add_argument("--jobs", type=int, choices=(1, 2), default=2)
    args = parser.parse_args()
    sdk, bindings, out = args.emsdk.resolve(), args.bindings.resolve(), args.out.resolve()
    if not all(path.is_relative_to(REPO / ".local") for path in (bindings, out)):
        parser.error("Bindings and generated output must remain in this worktree's ignored .local directory")
    if not (sdk / ".emscripten").is_file(): parser.error("Activate the SDK with --embedded first")
    cmake, ninja = shutil.which("cmake"), shutil.which("ninja")
    if not cmake or not ninja: parser.error("CMake and Ninja must be available")
    env = dict(os.environ, EMSDK=str(sdk), EM_CONFIG=str(sdk / ".emscripten"), EMSDK_PYTHON=sys.executable)
    env["PATH"] = str(sdk / "upstream/emscripten") + os.pathsep + env["PATH"]
    version = subprocess.check_output([sys.executable, str(sdk / "upstream/emscripten/emcc.py"), "--version"], env=env, text=True)
    if f" {EMSCRIPTEN_VERSION} " not in version: parser.error("Use Emscripten 4.0.20 to match the export templates")
    prepare_dependency(bindings, dict(os.environ))
    out.mkdir(parents=True, exist_ok=True)
    source = REPO / "godot-client/native/browser_cape"

    def build(name, environment, options):
        directory = out / name
        with (out / (name + ".log")).open("w", encoding="utf-8") as log:
            subprocess.run([cmake, "-S", str(source), "-B", str(directory), "-G", "Ninja",
                            "-DCMAKE_MAKE_PROGRAM=" + ninja, "-DRL_GODOT_CPP=" + str(bindings),
                            "-DGODOTCPP_TARGET=template_release", *options], env=environment,
                           stdout=log, stderr=subprocess.STDOUT, check=True)
            subprocess.run([cmake, "--build", str(directory), "--parallel", str(args.jobs)], env=environment,
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        return directory

    # These qualified O2 settings preserve the extension's indirect-call ABI.
    # Strip metadata afterwards, keeping every executable section byte-for-byte.
    web = build("web", env, ["-DCMAKE_BUILD_TYPE=RelWithDebInfo", "-DGODOTCPP_THREADS=ON",
        "-DCMAKE_TOOLCHAIN_FILE=" + str(sdk / "upstream/emscripten/cmake/Modules/Platform/Emscripten.cmake")])
    editor_env = windows_environment(dict(os.environ)) if os.name == "nt" else dict(os.environ)
    editor = build("editor", editor_env, ["-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_TRY_COMPILE_CONFIGURATION=Release",
        "-DCMAKE_MSVC_DEBUG_INFORMATION_FORMAT=Embedded", "-DCMAKE_POLICY_DEFAULT_CMP0141=NEW"])
    suffix = {"Windows": ".dll", "Linux": ".so", "Darwin": ".dylib"}[platform.system()]
    payload = out / "payload"; payload.mkdir(exist_ok=True)
    wasm = payload / "browser_cape.wasm"
    wasm.write_bytes(strip_debug_sections((web / "browser_cape.wasm").read_bytes()))
    shutil.copy2(editor / ("browser_cape" + suffix), payload)
    shutil.copy2(bindings / "LICENSE.md", payload / "godot-cpp-LICENSE.md")
    manifest = {"emscripten": EMSCRIPTEN_VERSION, "godot_cpp_revision": GODOT_CPP_REVISION,
                "policy": "rl-browser-cape-o2-startup-pool-v1", "files": {}}
    for file in payload.iterdir():
        if file.name != "build.json": manifest["files"][file.name] = hashlib.sha256(file.read_bytes()).hexdigest()
    (payload / "build.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Browser cape runtime ready: {payload}")


if __name__ == "__main__":
    main()
