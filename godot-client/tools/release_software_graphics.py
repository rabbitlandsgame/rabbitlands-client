"""Select real software rendering for release-only resource cooking.

Windows uses the system D3D12 WARP adapter; Linux uses Mesa llvmpipe under
Xvfb. No graphics DLL is downloaded, copied into an application, or shipped.
Configuration is a request, never proof of capabilities: validate_observation
must accept the cooker’s actual renderer and resource-buffer readback result.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

POLICY = "rl-release-software-graphics-v1"
OBSERVATION_POLICY = "actual-renderer-supported-format-subset-v1"
CPU_DEVICE_TYPE = 4
FORMAT_MASK = 7
LINUX_PACKAGES = ("libgl1-mesa-dri", "libglx-mesa0", "xvfb", "xauth")
# These can conceal missing features or change the selected driver. Never use
# version/extension overrides to manufacture a cook capability token.
CONTROLLED_ENV = frozenset((
    "LIBGL_ALWAYS_SOFTWARE", "GALLIUM_DRIVER", "MESA_LOADER_DRIVER_OVERRIDE",
    "MESA_GL_VERSION_OVERRIDE", "MESA_GLES_VERSION_OVERRIDE",
    "MESA_GLSL_VERSION_OVERRIDE", "MESA_EXTENSION_OVERRIDE", "GALLIUM_OVERRIDE_CPU_CAPS",
    "VK_DRIVER_FILES", "VK_ICD_FILENAMES", "GODOT_RENDERING_DRIVER",
))


def require(value, message):
    if not value:
        raise ValueError(message)


def host_platform():
    return {"win32": "windows", "linux": "linux"}.get(sys.platform, "unsupported")


def _linux_packages():
    result = subprocess.run(
        ["dpkg-query", "-W", "-f=${binary:Package}\t${Version}\t${db:Status-Status}\n", *LINUX_PACKAGES],
        check=True, capture_output=True, text=True, timeout=30)
    packages = {}
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        require(len(parts) == 3 and parts[2] == "installed", "software graphics package is not installed")
        name, version, _ = parts
        name = name.split(":", 1)[0]
        require(name in LINUX_PACKAGES and name not in packages and version,
                "unexpected or duplicate software graphics package")
        packages[name] = version
    require(set(packages) == set(LINUX_PACKAGES), "software graphics package inventory is incomplete")
    return packages


def prepare_graphics(platform, godot_dir, tool_root, check_budget, *,
                     external_driver_dir=None, gpu_index=0, xvfb_run=None):
    """Return process-only configuration; does not launch Godot or install tools.

    Linux's signed distro packages must already be installed by the workflow.
    Their actual versions are recorded rather than claiming a fixed Mesa build.
    The caller accounts system package installation/free-space before invoking
    this helper. Built-in Windows WARP belongs to the hosted OS image.
    """
    require(platform in ("windows", "linux") and host_platform() == platform,
            "software cooking must run on its native supported operating system")
    godot_dir, tool_root = Path(godot_dir).resolve(), Path(tool_root).resolve()
    require(godot_dir.is_dir() and tool_root.is_dir() and godot_dir.is_relative_to(tool_root),
            "Godot tools must be inside the accounted tool root")
    require(external_driver_dir is None, "unqualified external graphics driver sideload is unsupported")
    require(type(gpu_index) is int and gpu_index >= 0, "software adapter index must be a nonnegative integer")
    check_budget("before software graphics configuration")
    common = {"schema": 1, "policy": POLICY, "platform": platform,
              "tool_root": str(tool_root), "godot_dir": str(godot_dir),
              "requires_actual_observation": True, "ships_driver_files": False,
              "format_mask": FORMAT_MASK}
    if platform == "windows":
        config = dict(common, env={}, command_prefix=[],
                      rendering_method="forward_plus", rendering_driver="d3d12",
                      display_driver="windows", gpu_index=gpu_index,
                      software_kind="system-warp", packages={})
    else:
        paths = {name: (str(xvfb_run) if name == "xvfb-run" and xvfb_run is not None
                        else shutil.which(name)) for name in ("xvfb-run", "Xvfb", "xauth")}
        require(all(value and Path(value).is_file() for value in paths.values()),
                "Linux software cooking requires installed xvfb-run, Xvfb and xauth")
        config = dict(common, env={"LIBGL_ALWAYS_SOFTWARE": "true", "GALLIUM_DRIVER": "llvmpipe"},
                      command_prefix=[paths["xvfb-run"], "-a", "-s", "-screen 0 1280x720x24 -nolisten tcp"],
                      rendering_method="gl_compatibility", rendering_driver="opengl3",
                      display_driver="x11", gpu_index=None,
                      software_kind="mesa-llvmpipe", packages=_linux_packages())
    check_budget("software graphics configuration ready")
    return config


def child_environment(config, base=None):
    """Return an isolated environment without modifying the parent process."""
    result = dict(os.environ if base is None else base)
    for name in CONTROLLED_ENV:
        result.pop(name, None)
    result.update(config["env"])
    return result


def cook_command(config, argv):
    """Add real renderer flags before script arguments; reject conflicting flags."""
    require(isinstance(argv, (tuple, list)) and argv and all(isinstance(item, (str, Path)) for item in argv),
            "a nonempty Godot argument list is required")
    command = [str(item) for item in argv]
    delimiter = command.index("--") if "--" in command else len(command)
    engine, script = command[:delimiter], command[delimiter:]
    require(not any(item == "--headless" or item.startswith("--headless=") for item in engine),
            "resource cooking requires a real renderer, not --headless")
    wanted = {"--rendering-method": config["rendering_method"],
              "--rendering-driver": config["rendering_driver"],
              "--display-driver": config["display_driver"],
              # Build checks need real graphics resources, but no audio device.
              "--audio-driver": "Dummy"}
    if config["gpu_index"] is not None:
        wanted["--gpu-index"] = str(config["gpu_index"])
    existing = {}
    index = 1
    while index < len(engine):
        item = engine[index]
        key, equal, value = item.partition("=")
        if key in wanted or key == "--gpu-index":
            if not equal:
                require(index + 1 < len(engine), "missing graphics argument value")
                index += 1
                value = engine[index]
            require(key not in existing, "duplicate graphics argument: " + key)
            require(key in wanted and value == wanted[key], "conflicting software graphics argument: " + key)
            existing[key] = value
        index += 1
    for key, value in wanted.items():
        if key not in existing:
            engine.extend((key, value))
    return [*config["command_prefix"], *engine, *script]


def validate_observation(config, observation):
    """Fail closed on actual renderer/capability/readback evidence from Godot."""
    require(isinstance(observation, dict), "actual cook graphics observation is missing")
    require(observation.get("policy") == OBSERVATION_POLICY,
            "actual cook graphics observation policy is unsupported")
    for key in ("platform", "rendering_method", "rendering_driver"):
        require(observation.get(key) == config[key], "actual cook " + key + " differs from requested software graphics")
    require(type(observation.get("detected_format_mask")) is int
            and observation["detected_format_mask"] == FORMAT_MASK,
            "actual software renderer does not support the required texture format mask 7")
    require(observation.get("resource_buffer_probe") is True,
            "software renderer did not pass actual resource-buffer save/reload")
    require(observation.get("software_adapter") is True, "actual cook adapter is not identified as software")
    name = observation.get("adapter_name")
    adapter_type = observation.get("adapter_type")
    require(isinstance(name, str) and name.strip() and type(adapter_type) is int,
            "actual adapter name/type observation is missing")
    if config["platform"] == "windows":
        require(adapter_type == CPU_DEVICE_TYPE and
                ("warp" in name.lower() or "microsoft basic render driver" in name.lower()),
                "selected Windows adapter is not the expected CPU WARP renderer")
    else:
        # Godot's GL adapter-type API returns OTHER even for llvmpipe.
        require("llvmpipe" in name.lower(), "selected Linux adapter is not llvmpipe")
    return {"schema": 1, "policy": POLICY, "status": "verified", "requested": config,
            "observed": dict(observation), "ships_driver_files": False}
