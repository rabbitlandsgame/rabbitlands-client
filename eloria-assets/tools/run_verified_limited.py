"""Run one pinned command through an explicitly approved bounded wrapper.

The verifier performs every structural, path, invocation, and SHA-256 check
before it creates the child.  It never uses a shell.  Timeout or interruption
terminates only the process tree rooted at the child it created.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


EXIT_PREFLIGHT = 125
EXIT_TIMEOUT = 124
EXIT_INTERRUPTED = 130
REQUIRED = {
    "argv", "pins", "cwd", "timeoutSeconds", "argvLog", "stdoutLog",
    "stderrLog", "exitLog", "timingLog", "resultLog",
}


class PreflightError(ValueError):
    pass


class WindowsJob:
    """A kill-on-close job containing only the verifier's child tree."""

    def __init__(self, process: subprocess.Popen[bytes]):
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)

        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", ctypes.c_uint32),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", ctypes.c_uint32),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", ctypes.c_uint32),
                ("SchedulingClass", ctypes.c_uint32),
            ]

        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
            )]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimits), ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        kernel.CreateJobObjectW.restype = ctypes.c_void_p
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        kernel.SetInformationJobObject.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32,
        ]
        kernel.SetInformationJobObject.restype = ctypes.c_int
        kernel.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        kernel.AssignProcessToJobObject.restype = ctypes.c_int
        kernel.TerminateJobObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel.TerminateJobObject.restype = ctypes.c_int
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle.restype = ctypes.c_int
        handle = kernel.CreateJobObjectW(None, None)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x00002000  # KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            kernel.CloseHandle(handle)
            raise ctypes.WinError(ctypes.get_last_error())
        if not kernel.AssignProcessToJobObject(handle, ctypes.c_void_p(process._handle)):
            kernel.CloseHandle(handle)
            raise ctypes.WinError(ctypes.get_last_error())
        self.kernel = kernel
        self.handle = handle

    def terminate(self) -> None:
        if self.handle and not self.kernel.TerminateJobObject(self.handle, 1):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self) -> None:
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolved_file(value: str, label: str) -> Path:
    path = Path(value).expanduser().resolve(strict=True)
    if not path.is_file():
        raise PreflightError(f"{label} is not a file: {path}")
    return path


def output_path(spec: dict[str, Any], key: str) -> Path:
    value = spec.get(key)
    if not isinstance(value, str) or not value:
        raise PreflightError(f"{key} must be a non-empty path string")
    return Path(value).expanduser().resolve()


def write_json(path: Path, value: Any, reserved: set[Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    while True:
        descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        temporary = Path(name).resolve()
        if temporary not in reserved:
            break
        os.close(descriptor)
        temporary.unlink(missing_ok=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def safe_output_set(
    spec_path: Path, spec: Any, independently_protected: set[Path]
) -> tuple[dict[str, Path], set[Path]]:
    """Validate every write target without writing; unsafe specs get console-only errors."""
    if not isinstance(spec, dict):
        raise PreflightError("specification must be a JSON object")
    outputs = {key: output_path(spec, key) for key in REQUIRED if key.endswith("Log")}
    if len(set(outputs.values())) != len(outputs):
        raise PreflightError("log paths must be distinct")
    pin_paths: set[Path] = set()
    pins = spec.get("pins")
    if isinstance(pins, list):
        for pin in pins:
            if isinstance(pin, dict) and isinstance(pin.get("path"), str):
                pin_paths.add(Path(pin["path"]).expanduser().resolve())
    input_paths = pin_paths | independently_protected
    protected = {spec_path, *input_paths, *outputs.values()}
    if spec_path in outputs.values():
        raise PreflightError("a log path cannot replace the specification")
    collisions = set(outputs.values()) & input_paths
    if collisions:
        raise PreflightError(f"log path would replace pinned input: {sorted(map(str, collisions))}")
    return outputs, protected


def validate_spec(
    spec_path: Path, spec: Any, expected_python: Path, expected_wrapper: Path,
    outputs: dict[str, Path],
) -> tuple[list[str], Path, float, dict[str, Path], list[dict[str, str]]]:
    if not isinstance(spec, dict):
        raise PreflightError("specification must be a JSON object")
    missing = REQUIRED - set(spec)
    unknown = set(spec) - REQUIRED
    if missing or unknown:
        raise PreflightError(f"spec keys invalid; missing={sorted(missing)}, unknown={sorted(unknown)}")

    timeout = spec["timeoutSeconds"]
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise PreflightError("timeoutSeconds must be a finite positive number")
    timeout = float(timeout)
    if not math.isfinite(timeout) or timeout <= 0:
        raise PreflightError("timeoutSeconds must be a finite positive number")

    argv_value = spec["argv"]
    if not isinstance(argv_value, list) or len(argv_value) < 3 or not all(
        isinstance(item, str) and item for item in argv_value
    ):
        raise PreflightError("argv must contain at least three non-empty strings")
    argv = list(argv_value)
    actual_python = resolved_file(argv[0], "argv[0]")
    actual_wrapper = resolved_file(argv[1], "argv[1]")
    if actual_python != expected_python:
        raise PreflightError(f"argv[0] is not approved Python: {actual_python}")
    if actual_wrapper != expected_wrapper:
        raise PreflightError(f"argv[1] is not approved run_limited.py: {actual_wrapper}")
    # Resolution happens in the verifier's cwd. Execute those exact approved
    # files even when the requested command uses relative spelling and a
    # different command cwd.
    argv[0] = str(actual_python)
    argv[1] = str(actual_wrapper)

    cwd_value = spec["cwd"]
    if not isinstance(cwd_value, str) or not cwd_value:
        raise PreflightError("cwd must be a non-empty path string")
    cwd = Path(cwd_value).expanduser().resolve(strict=True)
    if not cwd.is_dir():
        raise PreflightError(f"cwd is not a directory: {cwd}")

    pins_value = spec["pins"]
    if not isinstance(pins_value, list) or not pins_value:
        raise PreflightError("pins must be a non-empty array")
    pins: list[dict[str, str]] = []
    pinned_paths: set[Path] = set()
    for index, pin in enumerate(pins_value):
        if not isinstance(pin, dict) or set(pin) != {"path", "sha256"}:
            raise PreflightError(f"pins[{index}] must contain exactly path and sha256")
        if not isinstance(pin["path"], str) or not isinstance(pin["sha256"], str):
            raise PreflightError(f"pins[{index}] values must be strings")
        expected = pin["sha256"].lower()
        if len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected):
            raise PreflightError(f"pins[{index}].sha256 is not a SHA-256 hex digest")
        path = resolved_file(pin["path"], f"pins[{index}].path")
        if path in pinned_paths:
            raise PreflightError(f"duplicate pin path: {path}")
        pinned_paths.add(path)
        pins.append({"path": str(path), "sha256": expected})
    for required_pin in (expected_python, expected_wrapper):
        if required_pin not in pinned_paths:
            raise PreflightError(f"approved invocation file is not pinned: {required_pin}")
    return argv, cwd, timeout, outputs, pins


def verify_pins(pins: list[dict[str, str]]) -> list[dict[str, str]]:
    checked = []
    for pin in pins:
        path = Path(pin["path"])
        actual = sha256(path)
        row = {**pin, "actual": actual, "matched": actual == pin["sha256"]}
        checked.append(row)
        if not row["matched"]:
            raise PreflightError(
                f"pin mismatch: {path}: expected {pin['sha256']}, got {actual}"
            )
    return checked


def stop_owned_tree(process: subprocess.Popen[bytes], job: WindowsJob | None) -> dict[str, Any]:
    if os.name == "nt":
        if job is None:
            if process.poll() is not None:
                return {"attempted": False, "reason": "gated-launcher-already-exited"}
            process.terminate()
            return {"attempted": True, "method": "gated-launcher-terminate"}
        job.terminate()
        return {"attempted": True, "method": "owned-windows-job"}
    try:
        os.killpg(process.pid, signal.SIGKILL)
        return {"attempted": True, "method": "owned-process-group-sigkill"}
    except ProcessLookupError:
        return {"attempted": False, "reason": "already-exited"}


def record_plain_logs(outputs: dict[str, Path], elapsed: float, exit_code: int) -> None:
    outputs["timingLog"].write_text(f"{elapsed:.6f}\n", encoding="ascii")
    outputs["exitLog"].write_text(f"{exit_code}\n", encoding="ascii")


def execute(spec_path: Path, expected_python: Path, expected_wrapper: Path) -> int:
    overall_start = time.monotonic()
    spec: Any = None
    outputs: dict[str, Path] = {}
    checked: list[dict[str, str]] = []
    process: subprocess.Popen[bytes] | None = None
    job: WindowsJob | None = None
    protected: set[Path] = {spec_path}
    result: dict[str, Any] = {
        "schema": 1, "spec": str(spec_path), "status": "preflight_failed",
        "childStarted": False,
    }
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        outputs, protected = safe_output_set(
            spec_path, spec, {expected_python, expected_wrapper}
        )
        argv, cwd, timeout, outputs, pins = validate_spec(
            spec_path, spec, expected_python, expected_wrapper, outputs
        )
        for path in outputs.values():
            path.parent.mkdir(parents=True, exist_ok=True)
        outputs["stdoutLog"].write_bytes(b"")
        outputs["stderrLog"].write_bytes(b"")
        checked = verify_pins(pins)
        write_json(outputs["argvLog"], {
            "schema": 1, "spec": str(spec_path), "pins": checked, "argv": argv,
            "cwd": str(cwd), "timeoutSeconds": timeout, "child": None,
        }, protected)

        child_start = time.monotonic()
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        with outputs["stdoutLog"].open("ab") as stdout, outputs["stderrLog"].open("ab") as stderr:
            launcher = [str(expected_python), "-c", (
                "import json,subprocess,sys; "
                "data=sys.stdin.buffer.read(1); "
                "raise SystemExit(125 if data!=b'x' else subprocess.call(json.loads(sys.argv[1])))"
            ), json.dumps(argv)]
            process = subprocess.Popen(
                launcher, cwd=cwd, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr, shell=False,
                creationflags=creationflags, start_new_session=(os.name != "nt"),
            )
            result.update(childStarted=True, childPid=process.pid)
            if os.name == "nt":
                job = WindowsJob(process)
            write_json(outputs["argvLog"], {
                "schema": 1, "spec": str(spec_path), "pins": checked, "argv": argv,
                "launcherArgv": launcher,
                "cwd": str(cwd), "timeoutSeconds": timeout,
                "child": {"pid": process.pid, "startedMonotonic": child_start},
            }, protected)
            assert process.stdin is not None
            process.stdin.write(b"x")
            process.stdin.close()
            try:
                child_exit = process.wait(timeout=timeout)
                result["childExitCode"] = child_exit
                if child_exit == 0:
                    status, exit_code = "success", 0
                else:
                    status, exit_code = "nonzero", child_exit
            except subprocess.TimeoutExpired:
                result["termination"] = stop_owned_tree(process, job)
                try:
                    result["childExitCode"] = process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    result["childExitCode"] = None
                status, exit_code = "timeout", EXIT_TIMEOUT
            except KeyboardInterrupt:
                result["termination"] = stop_owned_tree(process, job)
                try:
                    result["childExitCode"] = process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    result["childExitCode"] = None
                status, exit_code = "interrupted", EXIT_INTERRUPTED
        if job is not None:
            job.close()
        elapsed = time.monotonic() - overall_start
        result.update(status=status, exitCode=exit_code, elapsedSeconds=elapsed)
        record_plain_logs(outputs, elapsed, exit_code)
        write_json(outputs["resultLog"], result, protected)
        return exit_code
    except KeyboardInterrupt as error:
        if process is not None:
            try:
                result["termination"] = stop_owned_tree(process, job)
                result["childExitCode"] = process.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired) as cleanup_error:
                result["cleanupError"] = f"{type(cleanup_error).__name__}: {cleanup_error}"
        if job is not None:
            job.close()
        elapsed = time.monotonic() - overall_start
        result.update(status="interrupted", exitCode=EXIT_INTERRUPTED, elapsedSeconds=elapsed,
                      error=f"{type(error).__name__}: {error}")
        if outputs:
            record_plain_logs(outputs, elapsed, EXIT_INTERRUPTED)
            write_json(outputs["resultLog"], result, protected)
        return EXIT_INTERRUPTED
    except (OSError, ValueError, json.JSONDecodeError) as error:
        post_spawn = process is not None
        if post_spawn:
            try:
                result["termination"] = stop_owned_tree(process, job)
                result["childExitCode"] = process.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired) as cleanup_error:
                result["cleanupError"] = f"{type(cleanup_error).__name__}: {cleanup_error}"
        if job is not None:
            job.close()
        elapsed = time.monotonic() - overall_start
        result.update(
            status="runtime_failed" if post_spawn else "preflight_failed", exitCode=EXIT_PREFLIGHT,
            elapsedSeconds=elapsed, error=f"{type(error).__name__}: {error}",
            checkedPins=checked,
        )
        if outputs:
            try:
                for path in outputs.values():
                    path.parent.mkdir(parents=True, exist_ok=True)
                if not post_spawn:
                    outputs["stdoutLog"].write_bytes(b"")
                    outputs["stderrLog"].write_text(result["error"] + "\n", encoding="utf-8")
                    write_json(outputs["argvLog"], {
                        "schema": 1, "spec": str(spec_path), "child": None,
                        "preflightError": result["error"],
                    }, protected)
                else:
                    with outputs["stderrLog"].open("a", encoding="utf-8") as stream:
                        stream.write(result["error"] + "\n")
                record_plain_logs(outputs, elapsed, EXIT_PREFLIGHT)
                write_json(outputs["resultLog"], result, protected)
            except (OSError, ValueError):
                pass
        print(f"preflight error: {result['error']}", file=sys.stderr)
        return EXIT_PREFLIGHT


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("spec", type=Path)
    parser.add_argument("--expected-python", required=True, type=Path)
    parser.add_argument("--expected-run-limited", required=True, type=Path)
    args = parser.parse_args()
    try:
        spec_path = args.spec.expanduser().resolve(strict=True)
        expected_python = resolved_file(str(args.expected_python), "expected Python")
        expected_wrapper = resolved_file(str(args.expected_run_limited), "expected run_limited.py")
    except (OSError, ValueError) as error:
        print(f"preflight error: {type(error).__name__}: {error}", file=sys.stderr)
        return EXIT_PREFLIGHT
    return execute(spec_path, expected_python, expected_wrapper)


if __name__ == "__main__":
    raise SystemExit(main())
