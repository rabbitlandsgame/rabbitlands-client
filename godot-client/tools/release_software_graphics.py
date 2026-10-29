"""Select real software rendering for release-only resource cooking.

Windows uses the system D3D12 WARP adapter; Linux uses Mesa llvmpipe under
Xvfb. No graphics DLL is downloaded, copied into an application, or shipped.
Configuration is a request, never proof of capabilities: validate_observation
must accept the cooker’s actual renderer and resource-buffer readback result.
"""
from __future__ import annotations

import hashlib
import json
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
LINUX_WORLD_PACKAGES = (*LINUX_PACKAGES, "mesa-vulkan-drivers")
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


def _linux_packages(required=LINUX_PACKAGES):
    result = subprocess.run(
        ["dpkg-query", "-W", "-f=${binary:Package}\t${Version}\t${db:Status-Status}\n", *required],
        check=True, capture_output=True, text=True, timeout=30)
    packages = {}
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        require(len(parts) == 3 and parts[2] == "installed", "software graphics package is not installed")
        name, version, _ = parts
        name = name.split(":", 1)[0]
        require(name in required and name not in packages and version,
                "unexpected or duplicate software graphics package")
        packages[name] = version
    require(set(packages) == set(required), "software graphics package inventory is incomplete")
    return packages


def _identify_warp(gpu_index):
    # Keep the native Windows dependency out of Linux and fake-only callers.
    from release_windows_graphics import identify_warp
    return identify_warp(gpu_index)


def prepare_graphics(platform, godot_dir, tool_root, check_budget, *,
                     external_driver_dir=None, gpu_index=None, xvfb_run=None):
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
    require(gpu_index is None or (type(gpu_index) is int and gpu_index >= 0),
            "software adapter index must be automatic or a nonnegative integer")
    check_budget("before software graphics configuration")
    common = {"schema": 1, "policy": POLICY, "platform": platform,
              "tool_root": str(tool_root), "godot_dir": str(godot_dir),
              "requires_actual_observation": True, "ships_driver_files": False,
              "format_mask": FORMAT_MASK}
    if platform == "windows":
        adapter = _identify_warp(gpu_index)
        selected = adapter.get("selected_index")
        require(adapter.get("policy") == "rl-windows-warp-selection-v1"
                and type(selected) is int and selected >= 0
                and (gpu_index is None or selected == gpu_index),
                "actual Windows WARP selection differs from its requested index")
        config = dict(common, env={}, command_prefix=[],
                      rendering_method="forward_plus", rendering_driver="d3d12",
                      display_driver="windows", gpu_index=selected, windows_adapter=adapter,
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


def _linux_lavapipe():
    """Use only the distro-installed CPU Vulkan driver, never a downloaded DLL."""
    result = subprocess.run(["dpkg-query", "-L", "mesa-vulkan-drivers"],
                            check=True, capture_output=True, text=True, timeout=30)
    files = [Path(line) for line in result.stdout.splitlines() if line.startswith("/")]
    manifests = [path for path in files if path.parent == Path("/usr/share/vulkan/icd.d")
                 and path.name.startswith("lvp_icd") and path.suffix == ".json"]
    libraries = [path for path in files if path.name == "libvulkan_lvp.so"]
    require(len(manifests) == 1 and len(libraries) == 1,
            "one distro-installed lavapipe Vulkan ICD and library are required")
    manifest, library = manifests[0], libraries[0]
    require(manifest.is_file() and library.is_file() and not manifest.is_symlink(),
            "installed lavapipe driver files are unavailable")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    declared = data.get("ICD", {}).get("library_path")
    require(isinstance(declared, str) and Path(declared).name == library.name,
            "lavapipe ICD does not name the installed CPU Vulkan library")
    if "/" in declared:
        named = Path(declared) if Path(declared).is_absolute() else manifest.parent / declared
        require(named.resolve() == library.resolve(), "lavapipe ICD names another driver library")
    return {"icd": str(manifest), "icd_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "library": str(library.resolve()), "library_sha256": hashlib.sha256(library.read_bytes()).hexdigest()}


def prepare_world_graphics(platform, godot_dir, tool_root, check_budget, *, gpu_index=None):
    """Request the game's default Forward+ renderer for the lean world cache.

    Keep the older optimization pilot's Compatibility cook unchanged. Actual
    CPU-device, format and buffer roundtrip observations remain mandatory.
    """
    config = prepare_graphics(platform, godot_dir, tool_root, check_budget, gpu_index=gpu_index)
    if platform == "linux":
        packages = _linux_packages(LINUX_WORLD_PACKAGES)
        driver = _linux_lavapipe()
        config = dict(config, packages=packages, rendering_method="forward_plus",
                      rendering_driver="vulkan", software_kind="mesa-lavapipe", lavapipe=driver,
                      env={**config["env"], "VK_DRIVER_FILES": driver["icd"]})
    check_budget("world Forward+ software graphics configuration ready")
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
        if "windows_adapter" in config:
            selection = config["windows_adapter"]
            require(selection.get("selected_index") == config["gpu_index"]
                    and name.strip().casefold() == str(selection.get("selected_adapter", {}).get("name", "")).strip().casefold(),
                    "actual Windows adapter differs from the independently selected WARP identity")
    elif config.get("software_kind") == "mesa-lavapipe":
        require(adapter_type == CPU_DEVICE_TYPE and
                any(label in name.lower() for label in ("llvmpipe", "lavapipe")),
                "selected Linux Vulkan adapter is not CPU lavapipe")
    else:
        # Godot's GL adapter-type API returns OTHER even for llvmpipe.
        require("llvmpipe" in name.lower(), "selected Linux adapter is not llvmpipe")
    return {"schema": 1, "policy": POLICY, "status": "verified", "requested": config,
            "observed": dict(observation), "ships_driver_files": False}


def validate_preflight_report(config, report, *, project, user_directory, godot):
    """Bind early renderer proof to this exact fresh project, profile and editor.

    Configuration and the adapter inventory do not substitute for an actual
    CPU renderer, texture capabilities or native buffer save/reload.
    """
    require(isinstance(report, dict) and type(report.get("schema_version")) is int
            and report["schema_version"] == 1 and report.get("status") == "pass"
            and report.get("failures") == [], "early graphics preflight did not pass")
    for key, expected in (("project_root", project), ("user_directory", user_directory),
                          ("engine_executable", godot)):
        value = report.get(key)
        require(isinstance(value, str) and Path(value).is_absolute(),
                "early graphics " + key + " is missing or not absolute")
        actual_path, expected_path = str(Path(value).resolve()), str(Path(expected).resolve())
        if config["platform"] == "windows":
            actual_path, expected_path = actual_path.casefold(), expected_path.casefold()
        require(actual_path == expected_path, "early graphics " + key + " differs from this invocation")
    version = report.get("engine_version")
    require(isinstance(version, dict) and all(type(version.get(key)) is int and version[key] == value
            for key, value in (("major", 4), ("minor", 7), ("patch", 2)))
            and version.get("status") == "stable", "early graphics editor version differs from the pinned release")
    observed = report.get("graphics")
    receipt = validate_observation(config, observed)
    require(observed.get("requested_platform") == config["platform"]
            and str(observed.get("display_driver", "")).casefold() == config["display_driver"].casefold(),
            "early graphics native platform/display differs")
    buffer = observed.get("resource_buffer_detail")
    require(isinstance(buffer, dict) and buffer.get("ok") is True and buffer.get("error") == ""
            and type(buffer.get("buffer_elements")) is int and buffer["buffer_elements"] == 12
            and buffer.get("save_reload") is True and buffer.get("removed") is True,
            "early graphics actual resource-buffer proof is incomplete")
    if config["platform"] == "windows" or config.get("software_kind") == "mesa-lavapipe":
        if config["platform"] == "windows":
            require("windows_adapter" in config, "early graphics independent WARP selection is missing")
        require(type(observed.get("expected_cpu_type")) is int and observed["expected_cpu_type"] == CPU_DEVICE_TYPE
                and observed.get("rendering_device_present") is True
                and observed.get("rendering_device_name") == observed.get("adapter_name"),
                "early graphics selected RenderingDevice does not confirm the actual CPU adapter")
        # The pinned editor does not bind RenderingDevice.get_device_type to
        # scripts. Keep that absence explicit; RenderingServer's supported
        # bound getter above must still report the real CPU type.
        available = observed.get("rendering_device_type_available")
        require(type(available) is bool and type(observed.get("rendering_device_type")) is int
                and observed["rendering_device_type"] == (CPU_DEVICE_TYPE if available else -1),
                "early graphics RenderingDevice type observation is inconsistent")
    return dict(receipt, preflight=dict(report))
