import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest


HERE = Path(__file__).resolve().parent
RUNNER = HERE / "run_verified_limited.py"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make_tools(tmp_path):
    wrapper = tmp_path / "run_limited.py"
    wrapper.write_text(
        "import subprocess,sys\nraise SystemExit(subprocess.call(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    return wrapper


def make_spec(tmp_path, wrapper, target, *, timeout=5, target_args=()):
    logs = {name: str(tmp_path / f"{name}.log") for name in (
        "argvLog", "stdoutLog", "stderrLog", "exitLog", "timingLog", "resultLog"
    )}
    spec = {
        "argv": [sys.executable, str(wrapper), sys.executable, str(target), *target_args],
        "pins": [
            {"path": sys.executable, "sha256": digest(sys.executable)},
            {"path": str(wrapper), "sha256": digest(wrapper)},
            {"path": str(target), "sha256": digest(target)},
        ],
        "cwd": str(tmp_path), "timeoutSeconds": timeout, **logs,
    }
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    return path, spec


def invoke(spec_path, wrapper, *, verifier_cwd=None):
    return subprocess.run(
        [sys.executable, str(RUNNER), str(spec_path),
         "--expected-python", sys.executable,
         "--expected-run-limited", str(wrapper)],
        cwd=verifier_cwd, capture_output=True, text=True, check=False,
    )


def result(spec):
    return json.loads(Path(spec["resultLog"]).read_text(encoding="utf-8"))


def test_bad_pin_rejects_before_launch(tmp_path):
    wrapper = make_tools(tmp_path)
    sentinel = tmp_path / "launched"
    target = tmp_path / "target.py"
    target.write_text(f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('yes')\n", encoding="utf-8")
    spec_path, spec = make_spec(tmp_path, wrapper, target)
    spec["pins"][-1]["sha256"] = "0" * 64
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    completed = invoke(spec_path, wrapper)
    assert completed.returncode == 125
    assert not sentinel.exists()
    assert result(spec)["status"] == "preflight_failed"
    assert result(spec)["childStarted"] is False


def test_wrong_wrapper_position_rejects_before_launch(tmp_path):
    wrapper = make_tools(tmp_path)
    impostor = tmp_path / "other.py"
    impostor.write_text("raise SystemExit(0)\n", encoding="utf-8")
    target = tmp_path / "target.py"
    target.write_text("raise SystemExit(0)\n", encoding="utf-8")
    spec_path, spec = make_spec(tmp_path, wrapper, target)
    spec["argv"][1] = str(impostor)
    spec["pins"].append({"path": str(impostor), "sha256": digest(impostor)})
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    completed = invoke(spec_path, wrapper)
    assert completed.returncode == 125
    assert result(spec)["status"] == "preflight_failed"
    assert result(spec)["childStarted"] is False


def test_relative_wrapper_executes_canonical_approved_path(tmp_path):
    verifier_cwd = tmp_path / "verify"
    command_cwd = tmp_path / "command"
    approved_dir = verifier_cwd / "approved"
    impostor_dir = command_cwd / "approved"
    approved_dir.mkdir(parents=True)
    impostor_dir.mkdir(parents=True)
    wrapper = make_tools(approved_dir)
    sentinel = tmp_path / "impostor-launched"
    impostor = impostor_dir / "run_limited.py"
    impostor.write_text(
        f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('bad')\nraise SystemExit(9)\n",
        encoding="utf-8",
    )
    target = command_cwd / "target.py"
    target.write_text("print('approved-wrapper')\n", encoding="utf-8")
    spec_path, spec = make_spec(tmp_path, wrapper, target)
    spec["cwd"] = str(command_cwd)
    spec["argv"][1] = str(Path("approved") / "run_limited.py")
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    completed = invoke(spec_path, wrapper, verifier_cwd=verifier_cwd)
    assert completed.returncode == 0
    assert not sentinel.exists()
    record = result(spec)
    assert record["status"] == "success"
    argv_record = json.loads(Path(spec["argvLog"]).read_text())
    assert argv_record["argv"][1] == str(wrapper.resolve())


@pytest.mark.parametrize("timeout", [0, float("inf")])
def test_invalid_timeout_rejects_before_launch(tmp_path, timeout):
    wrapper = make_tools(tmp_path)
    sentinel = tmp_path / "launched"
    target = tmp_path / "target.py"
    target.write_text(f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('yes')\n", encoding="utf-8")
    spec_path, spec = make_spec(tmp_path, wrapper, target, timeout=timeout)
    completed = invoke(spec_path, wrapper)
    assert completed.returncode == 125
    assert not sentinel.exists()
    assert result(spec)["status"] == "preflight_failed"


def test_spec_output_collision_preserves_spec(tmp_path):
    wrapper = make_tools(tmp_path)
    target = tmp_path / "target.py"
    target.write_text("raise SystemExit(0)\n", encoding="utf-8")
    spec_path, spec = make_spec(tmp_path, wrapper, target)
    spec["resultLog"] = str(spec_path)
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    before = spec_path.read_bytes()
    completed = invoke(spec_path, wrapper)
    assert completed.returncode == 125
    assert spec_path.read_bytes() == before


def test_pinned_input_output_collision_preserves_input(tmp_path):
    wrapper = make_tools(tmp_path)
    target = tmp_path / "target.py"
    target.write_text("raise SystemExit(0)\n", encoding="utf-8")
    spec_path, spec = make_spec(tmp_path, wrapper, target)
    spec["stderrLog"] = str(target)
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    before = target.read_bytes()
    completed = invoke(spec_path, wrapper)
    assert completed.returncode == 125
    assert target.read_bytes() == before


def test_unpinned_approved_wrapper_output_collision_preserves_wrapper(tmp_path):
    wrapper = make_tools(tmp_path)
    target = tmp_path / "target.py"
    target.write_text("raise SystemExit(0)\n", encoding="utf-8")
    spec_path, spec = make_spec(tmp_path, wrapper, target)
    spec["pins"] = [pin for pin in spec["pins"] if Path(pin["path"]).resolve() != wrapper.resolve()]
    spec["stdoutLog"] = str(wrapper)
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    before = wrapper.read_bytes()
    completed = invoke(spec_path, wrapper)
    assert completed.returncode == 125
    assert wrapper.read_bytes() == before


@pytest.mark.parametrize(("code", "status"), [(0, "success"), (7, "nonzero")])
def test_records_real_exit(tmp_path, code, status):
    wrapper = make_tools(tmp_path)
    target = tmp_path / "target.py"
    target.write_text(f"print('hello', flush=True)\nraise SystemExit({code})\n", encoding="utf-8")
    spec_path, spec = make_spec(tmp_path, wrapper, target)
    completed = invoke(spec_path, wrapper)
    assert completed.returncode == code
    record = result(spec)
    assert record["status"] == status
    assert record["childExitCode"] == code
    assert record["childStarted"] is True
    assert Path(spec["stdoutLog"]).read_text().strip().endswith("hello")
    assert Path(spec["exitLog"]).read_text().strip() == str(code)


def pid_running(pid):
    if os.name == "nt":
        import ctypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        kernel.GetExitCodeProcess.restype = ctypes.c_int
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle.restype = ctypes.c_int
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = ctypes.c_uint32()
        assert kernel.GetExitCodeProcess(handle, ctypes.byref(code))
        assert kernel.CloseHandle(handle)
        return code.value == 259
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def test_timeout_stops_child_and_grandchild(tmp_path):
    wrapper = make_tools(tmp_path)
    grandchild = tmp_path / "grandchild.py"
    grandchild.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
    pid_file = tmp_path / "grandchild.pid"
    target = tmp_path / "target.py"
    target.write_text(
        "import pathlib,subprocess,sys,time\n"
        f"p=subprocess.Popen([sys.executable,{str(grandchild)!r}])\n"
        f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid))\n"
        "time.sleep(60)\n", encoding="utf-8",
    )
    spec_path, spec = make_spec(tmp_path, wrapper, target, timeout=.5)
    completed = invoke(spec_path, wrapper)
    assert completed.returncode == 124
    assert completed.stdout == ""
    assert completed.stderr == ""
    record = result(spec)
    assert record["status"] == "timeout"
    assert record["termination"]["attempted"] is True
    assert record["elapsedSeconds"] < 3
    child_pid = record["childPid"]
    grandchild_pid = int(pid_file.read_text())
    for _ in range(30):
        if not pid_running(grandchild_pid):
            break
        time.sleep(.1)
    assert not pid_running(grandchild_pid)
    assert not pid_running(child_pid)


@pytest.mark.skipif(os.name != "nt", reason="Windows Job setup failure path")
@pytest.mark.parametrize(("failure", "status", "exit_code"), [
    (OSError, "runtime_failed", 125),
    (KeyboardInterrupt, "interrupted", 130),
])
def test_job_setup_failure_saves_result_and_stops_gated_launcher(
    tmp_path, monkeypatch, failure, status, exit_code
):
    module_spec = importlib.util.spec_from_file_location("verified_runner_under_test", RUNNER)
    module = importlib.util.module_from_spec(module_spec)
    assert module_spec.loader is not None
    module_spec.loader.exec_module(module)
    wrapper = make_tools(tmp_path)
    target = tmp_path / "target.py"
    sentinel = tmp_path / "launched"
    target.write_text(f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('bad')\n", encoding="utf-8")
    spec_path, spec = make_spec(tmp_path, wrapper, target)

    class InjectedFailure:
        def __init__(self, process):
            raise failure("injected Job setup failure")

    monkeypatch.setattr(module, "WindowsJob", InjectedFailure)
    actual_exit = module.execute(spec_path.resolve(), Path(sys.executable).resolve(), wrapper.resolve())
    assert actual_exit == exit_code
    record = result(spec)
    assert record["status"] == status
    assert record["termination"]["method"] == "gated-launcher-terminate"
    assert not sentinel.exists()
    for _ in range(30):
        if not pid_running(record["childPid"]):
            break
        time.sleep(.1)
    assert not pid_running(record["childPid"])
