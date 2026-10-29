"""World caches request the default renderer without altering pilot cooking."""
from pathlib import Path
import sys
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import release_software_graphics as graphics


def linux_base():
    return {"platform": "linux", "rendering_method": "gl_compatibility", "rendering_driver": "opengl3",
            "software_kind": "mesa-llvmpipe", "display_driver": "x11", "gpu_index": None,
            "command_prefix": ["xvfb-run", "-a"], "env": {"LIBGL_ALWAYS_SOFTWARE": "true"}}


def test_world_linux_selects_verified_system_vulkan_without_mutating_pilot_config():
    base = linux_base()
    driver = {"icd": "/usr/share/vulkan/icd.d/lvp_icd.json", "icd_sha256": "a" * 64,
              "library": "/usr/lib/libvulkan_lvp.so", "library_sha256": "b" * 64}
    with mock.patch.object(graphics, "prepare_graphics", return_value=base), \
            mock.patch.object(graphics, "_linux_packages", return_value={"mesa-vulkan-drivers": "fixture"}) as packages, \
            mock.patch.object(graphics, "_linux_lavapipe", return_value=driver):
        config = graphics.prepare_world_graphics("linux", Path("tools/godot"), Path("tools"), mock.Mock())
    packages.assert_called_once_with(graphics.LINUX_WORLD_PACKAGES)
    assert (config["rendering_method"], config["rendering_driver"]) == ("forward_plus", "vulkan")
    assert config["env"]["VK_DRIVER_FILES"] == driver["icd"]
    assert base["rendering_method"] == "gl_compatibility" and "VK_DRIVER_FILES" not in base["env"]
    command = graphics.cook_command(config, ["godot", "--script", "prepare.gd"])
    assert command[command.index("--rendering-driver") + 1] == "vulkan"
    assert "--headless" not in command


def test_world_windows_keeps_actual_warp_selection():
    base = {"platform": "windows", "rendering_method": "forward_plus", "rendering_driver": "d3d12"}
    with mock.patch.object(graphics, "prepare_graphics", return_value=base) as prepare, \
            mock.patch.object(graphics, "_linux_lavapipe") as linux:
        assert graphics.prepare_world_graphics("windows", Path("godot"), Path("tools"), mock.Mock(), gpu_index=2) is base
    assert prepare.call_args.kwargs["gpu_index"] == 2
    linux.assert_not_called()


def test_vulkan_world_requires_actual_cpu_adapter_and_unchanged_format_and_readback_gates():
    config = dict(linux_base(), rendering_method="forward_plus", rendering_driver="vulkan", software_kind="mesa-lavapipe")
    observed = {"policy": graphics.OBSERVATION_POLICY, "platform": "linux",
                "rendering_method": "forward_plus", "rendering_driver": "vulkan",
                "detected_format_mask": 7, "resource_buffer_probe": True, "software_adapter": True,
                "adapter_type": 4, "adapter_name": "llvmpipe (LLVM fixture)"}
    assert graphics.validate_observation(config, observed)["status"] == "verified"
    for changed in ({"adapter_type": 0}, {"adapter_name": "NVIDIA"}, {"detected_format_mask": 3},
                    {"resource_buffer_probe": False}, {"rendering_driver": "opengl3"}):
        with pytest.raises(ValueError):
            graphics.validate_observation(config, {**observed, **changed})
