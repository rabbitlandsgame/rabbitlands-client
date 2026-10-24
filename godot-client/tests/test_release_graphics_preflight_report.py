"""Fake report gates for the early renderer probe; no engine or native calls."""
from __future__ import annotations

import copy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import release_software_graphics as graphics


@pytest.fixture
def version():
    # Engine.get_version_info() shape from the pinned release, not a version string.
    return {"major": 4, "minor": 7, "patch": 2, "status": "stable",
            "build": "official", "hash": "ed1daf0bf", "string": "4.7.2.stable.official"}


@pytest.fixture
def proof(tmp_path, version):
    tool_root = tmp_path / "tools"
    godot_dir = tool_root / "godot"
    godot_dir.mkdir(parents=True)
    godot = godot_dir / "Godot_v4.7.2-stable_win64.exe"
    godot.write_bytes(b"fake-editor-never-executed")
    project = tmp_path / "fresh-project"
    user = tmp_path / "fresh-user"
    project.mkdir()
    user.mkdir()
    (project / "project.godot").write_text("; disposable probe fixture\n", encoding="utf-8")
    config = {
        "schema": 1, "policy": graphics.POLICY, "platform": "windows",
        "tool_root": str(tool_root), "godot_dir": str(godot_dir),
        "requires_actual_observation": True, "ships_driver_files": False,
        "format_mask": 7, "env": {}, "command_prefix": [], "packages": {},
        "rendering_method": "forward_plus", "rendering_driver": "d3d12",
        "display_driver": "windows", "software_kind": "system-warp", "gpu_index": 2,
        "windows_adapter": {
            "policy": "rl-windows-warp-selection-v1", "selected_index": 2,
            "selected_adapter": {"name": "Microsoft Basic Render Driver"},
        },
    }
    # Mirrors tools/probe_release_software_graphics.gd and release_graphics_probe.gd.
    # The pinned editor exposes the RD name but does not bind its type getter.
    report = {
        "schema_version": 1, "status": "pass", "failures": [],
        "project_root": str(project), "user_directory": str(user),
        "engine_executable": str(godot), "engine_version": copy.deepcopy(version),
        "graphics": {
            "policy": graphics.OBSERVATION_POLICY, "platform": "windows",
            "requested_platform": "windows", "rendering_method": "forward_plus",
            "rendering_driver": "d3d12", "display_driver": "windows",
            "adapter_name": "Microsoft Basic Render Driver", "adapter_vendor": "Microsoft",
            "adapter_type": 4, "expected_cpu_type": 4, "software_adapter": True,
            "rendering_device_present": True,
            "rendering_device_name": "Microsoft Basic Render Driver",
            "rendering_device_type_available": False, "rendering_device_type": -1,
            "detected_format_mask": 7, "resource_buffer_probe": True,
            "resource_buffer_detail": {"ok": True, "error": "", "buffer_elements": 12,
                                       "save_reload": True, "removed": True},
        },
    }
    return {"config": config, "report": report, "project": project,
            "user_directory": user, "godot": godot}


def validate(proof):
    return graphics.validate_preflight_report(
        proof["config"], proof["report"], project=proof["project"],
        user_directory=proof["user_directory"], godot=proof["godot"])


def test_windows_complete_proof_preserves_actual_unavailable_rd_type(proof):
    original = copy.deepcopy(proof)
    receipt = validate(proof)
    assert receipt["status"] == "verified"
    assert receipt["requested"] == proof["config"]
    assert receipt["preflight"] == proof["report"]
    assert receipt["observed"]["rendering_device_type_available"] is False
    assert receipt["observed"]["rendering_device_type"] == -1
    assert receipt["ships_driver_files"] is False
    assert proof == original


def test_exposed_rd_getter_must_confirm_cpu(proof):
    proof["report"]["graphics"].update(rendering_device_type_available=True,
                                      rendering_device_type=4)
    assert validate(proof)["status"] == "verified"


def test_linux_compatibility_llvmpipe_without_rendering_device_is_valid(proof):
    config, observed = proof["config"], proof["report"]["graphics"]
    config.pop("windows_adapter")
    config.update(platform="linux", rendering_method="gl_compatibility",
                  rendering_driver="opengl3", display_driver="x11", gpu_index=None,
                  software_kind="mesa-llvmpipe", env={"LIBGL_ALWAYS_SOFTWARE": "true",
                                                       "GALLIUM_DRIVER": "llvmpipe"})
    observed.update(platform="linux", requested_platform="linux",
                    rendering_method="gl_compatibility", rendering_driver="opengl3",
                    display_driver="X11", adapter_name="llvmpipe (LLVM fixture)",
                    adapter_type=0, rendering_device_present=False,
                    rendering_device_name="", rendering_device_type_available=False,
                    rendering_device_type=-1)
    receipt = validate(proof)
    assert receipt["status"] == "verified"
    assert receipt["observed"]["adapter_type"] == 0
    assert receipt["observed"]["rendering_device_present"] is False


@pytest.mark.parametrize("report", [None, [], "pass", {},
    {"schema_version": True, "status": "pass", "failures": []},
    {"schema_version": "1", "status": "pass", "failures": []},
    {"schema_version": 2, "status": "pass", "failures": []},
    {"schema_version": 1, "status": "failed", "failures": []},
    {"schema_version": 1, "status": "pass", "failures": ["probe failed"]},
    {"schema_version": 1, "status": "pass", "failures": None},
])
def test_only_successful_supported_report_is_eligible(proof, report):
    proof["report"] = copy.deepcopy(report)
    with pytest.raises(ValueError, match="preflight did not pass"):
        validate(proof)


@pytest.mark.parametrize("field", ["project_root", "user_directory", "engine_executable"])
@pytest.mark.parametrize("problem", ["missing", "relative", "different", "wrong-type"])
def test_report_paths_bind_exact_fresh_invocation(proof, field, problem):
    report = proof["report"]
    if problem == "missing":
        report.pop(field)
    elif problem == "relative":
        report[field] = "relative/probe"
    elif problem == "different":
        report[field] = str(Path(report[field]).with_name("another-owned-path"))
    else:
        report[field] = True
    with pytest.raises(ValueError, match=field):
        validate(proof)


def test_windows_path_binding_is_case_insensitive(proof):
    for field in ("project_root", "user_directory", "engine_executable"):
        proof["report"][field] = proof["report"][field].upper()
    assert validate(proof)["status"] == "verified"


@pytest.mark.parametrize("change", [None, {}, {"major": 3}, {"minor": 6}, {"patch": 1},
    {"major": True}, {"minor": "7"}, {"patch": 2.0}, {"status": "dev"},
])
def test_only_pinned_stable_engine_version_is_accepted(proof, change):
    if change is None or change == {}:
        proof["report"]["engine_version"] = change
    else:
        proof["report"]["engine_version"].update(change)
    with pytest.raises(ValueError, match="editor version"):
        validate(proof)


@pytest.mark.parametrize("change", [
    {"policy": "unqualified"}, {"platform": "linux"}, {"requested_platform": "linux"},
    {"rendering_method": "gl_compatibility"}, {"rendering_driver": "vulkan"},
    {"display_driver": "headless"}, {"display_driver": "dummy"}, {"display_driver": ""},
    {"detected_format_mask": 0}, {"detected_format_mask": 3}, {"detected_format_mask": True},
    {"detected_format_mask": 7.0}, {"resource_buffer_probe": False},
    {"resource_buffer_probe": 1}, {"software_adapter": False}, {"software_adapter": 1},
    {"adapter_type": 2}, {"adapter_type": True}, {"adapter_type": 4.0},
    {"adapter_name": "NVIDIA fixture"}, {"adapter_name": ""},
    {"adapter_name": "Microsoft Basic Render Driver", "adapter_type": 1},
])
def test_configuration_does_not_substitute_for_actual_software_capabilities(proof, change):
    proof["report"]["graphics"].update(change)
    with pytest.raises(ValueError):
        validate(proof)


@pytest.mark.parametrize("problem", ["missing", "not-object", "not-ok", "numeric-ok", "error",
    "wrong-count", "numeric-count", "float-count", "no-reload", "numeric-reload",
    "not-removed", "numeric-removed"])
def test_actual_buffer_save_reload_and_cleanup_are_required(proof, problem):
    observed = proof["report"]["graphics"]
    if problem == "missing":
        observed.pop("resource_buffer_detail")
    elif problem == "not-object":
        observed["resource_buffer_detail"] = []
    else:
        field, value = {
            "not-ok": ("ok", False), "numeric-ok": ("ok", 1),
            "error": ("error", "native_reload_failed"), "wrong-count": ("buffer_elements", 0),
            "numeric-count": ("buffer_elements", True), "float-count": ("buffer_elements", 12.0),
            "no-reload": ("save_reload", False), "numeric-reload": ("save_reload", 1),
            "not-removed": ("removed", False), "numeric-removed": ("removed", 1),
        }[problem]
        observed["resource_buffer_detail"][field] = value
    with pytest.raises(ValueError, match="resource-buffer proof"):
        validate(proof)


@pytest.mark.parametrize("field,value", [
    ("expected_cpu_type", None), ("expected_cpu_type", True), ("expected_cpu_type", 2),
    ("rendering_device_present", None), ("rendering_device_present", False),
    ("rendering_device_present", 1), ("rendering_device_name", ""),
    ("rendering_device_name", "another adapter"),
])
def test_windows_rd_presence_and_name_confirm_rs_cpu_observation(proof, field, value):
    observed = proof["report"]["graphics"]
    if value is None:
        observed.pop(field)
    else:
        observed[field] = value
    with pytest.raises(ValueError, match="RenderingDevice"):
        validate(proof)


@pytest.mark.parametrize("available,device_type", [
    (None, -1), (1, 4), ("false", -1), (False, None), (False, True),
    (False, "-1"), (False, 0), (False, 4), (True, None), (True, True),
    (True, -1), (True, 0), (True, 4.0),
])
def test_rd_type_absence_is_explicit_and_available_getter_must_be_cpu(proof, available, device_type):
    observed = proof["report"]["graphics"]
    for field, value in (("rendering_device_type_available", available),
                         ("rendering_device_type", device_type)):
        if value is None:
            observed.pop(field)
        else:
            observed[field] = value
    with pytest.raises(ValueError, match="type observation"):
        validate(proof)


@pytest.mark.parametrize("problem", ["missing", "different-index", "missing-name", "different-name"])
def test_windows_native_selection_receipt_must_bind_observed_adapter(proof, problem):
    config = proof["config"]
    if problem == "missing":
        config.pop("windows_adapter")
    elif problem == "different-index":
        config["windows_adapter"]["selected_index"] = config["gpu_index"] + 1
    elif problem == "missing-name":
        config["windows_adapter"]["selected_adapter"].pop("name")
    else:
        config["windows_adapter"]["selected_adapter"]["name"] = "other WARP adapter"
    with pytest.raises(ValueError, match="WARP|selected WARP identity"):
        validate(proof)


def test_independent_adapter_name_comparison_allows_only_case_and_outer_whitespace(proof):
    proof["config"]["windows_adapter"]["selected_adapter"]["name"] = " microsoft BASIC render DRIVER "
    assert validate(proof)["status"] == "verified"
