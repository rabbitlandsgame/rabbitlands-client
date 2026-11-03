#!/usr/bin/env python3
"""Compare the native content digest with Python's hashlib over a whole install.

Lists every regular file under ``--root`` (default: the installed release in
``%LOCALAPPDATA%/Programs/RabbitLands``), hashes each one through the
``RabbitLandsContentDigest`` class of a ``client_runtime`` payload in a headless
Godot run (``tests/integration/native_digest_check.gd``), hashes the same bytes
with ``hashlib.sha256``, and reports every difference. Files ending in a
``--fold-suffix`` (default ``.json``) are also compared with CRLF folded to LF,
the ``ContentDigest.FOLD_CRLF`` rule. Exit code 0 means every file matched.

Run the Godot part under the headless-Godot lock (``--launcher``) with an isolated
APPDATA/LOCALAPPDATA; the Godot process inherits this process's environment.
Nothing is written outside ``--work``.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

PROJECT = Path(__file__).resolve().parents[1]
SCRIPT = "res://tests/integration/native_digest_check.gd"
READ_BYTES = 1 << 20


def default_root() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData/Local")
    return Path(base) / "Programs/RabbitLands"


def list_files(root: Path) -> list[str]:
    """Every regular file under root (no links or junction contents), sorted, absolute, '/' separators."""
    rows = []
    for directory, folders, names in os.walk(root, followlinks=False):
        folders[:] = sorted(name for name in folders if not (Path(directory) / name).is_symlink())
        for name in names:
            path = Path(directory) / name
            if path.is_file() and not path.is_symlink():
                rows.append(path.resolve().as_posix())
    return sorted(rows)


def fold_crlf(raw: bytes) -> bytes:
    """Drop every CR directly followed by LF (a lone CR and a CR at the end stay)."""
    return raw.replace(b"\r\n", b"\n")


def python_digest(path: str, fold: bool) -> tuple[str, bool]:
    """(sha256 hex, folded) of a file; raw files stream, folded files are read whole."""
    if fold:
        raw = Path(path).read_bytes()
        normalised = fold_crlf(raw)
        return hashlib.sha256(normalised).hexdigest(), len(normalised) != len(raw)
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while block := stream.read(READ_BYTES):
            digest.update(block)
    return digest.hexdigest(), False


def compare(paths: list[str], native: dict, reference: list[str], fold_reference: dict[int, tuple[str, bool]]) -> dict:
    """Mismatches between the Godot result and hashlib, as a report."""
    mismatches = []
    digests = native.get("digests", [])
    status = native.get("status", [])
    if len(digests) != len(paths) or len(status) != len(paths):
        return {"ok": False, "error": "row count differs", "mismatches": [], "compared": 0}
    for index, path in enumerate(paths):
        if status[index] != 0 or digests[index] != reference[index]:
            mismatches.append({"path": path, "kind": "raw", "native": digests[index], "status": status[index],
                               "hashlib": reference[index]})
    fold = native.get("fold", {})
    for index, (expected, folded) in sorted(fold_reference.items()):
        row = fold.get(str(index))
        if row is None or row[1] != 0 or row[0] != expected or bool(row[2]) != folded:
            mismatches.append({"path": paths[index], "kind": "fold", "native": row, "hashlib": [expected, folded]})
    if len(fold) != len(fold_reference):
        mismatches.append({"kind": "fold-count", "native": len(fold), "hashlib": len(fold_reference)})
    return {"ok": not mismatches, "mismatches": mismatches, "compared": len(paths), "folded_compared": len(fold_reference)}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    result.add_argument("--root", type=Path, default=default_root())
    result.add_argument("--runtime-dir", type=Path, default=PROJECT / "bin/client_runtime")
    result.add_argument("--godot", type=Path, default=PROJECT / "Godot_v4.7.2-stable_win64.exe")
    result.add_argument("--work", type=Path, required=True, help="directory for the list, the result and the log")
    result.add_argument("--threads", type=int, default=4)
    result.add_argument("--workers", type=int, default=4, help="hashlib threads (at most 4)")
    result.add_argument("--fold-suffix", action="append", default=None)
    result.add_argument("--limit", type=int, default=0, help="only the first N files (0 = all)")
    result.add_argument("--timeout", type=int, default=3600)
    result.add_argument("--launcher", default="",
                        help="command prefix for the Godot run only, e.g. a headless-slot lock wrapper")
    return result


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    suffixes = [suffix.lower() for suffix in (args.fold_suffix or [".json"])]
    args.work.mkdir(parents=True, exist_ok=True)
    paths = list_files(args.root)
    if args.limit > 0:
        paths = paths[:args.limit]
    if not paths:
        print("no files under " + str(args.root), file=sys.stderr)
        return 1
    listing = args.work / "files.txt"
    listing.write_text("\n".join(paths) + "\n", encoding="utf-8")
    out = args.work / "native.json"
    log = args.work / "godot.log"
    command = shlex.split(args.launcher, posix=True) + [str(args.godot), "--headless", "--log-file", str(log), "--path", str(PROJECT), "--script", SCRIPT, "--",
               "--list=" + str(listing), "--out=" + str(out), "--runtime-dir=" + str(args.runtime_dir.resolve()),
               "--threads=" + str(args.threads)] + ["--fold-suffix=" + suffix for suffix in suffixes]
    began = time.perf_counter()
    run = subprocess.run(command, cwd=PROJECT, timeout=args.timeout, capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    godot_seconds = time.perf_counter() - began
    if not out.is_file():
        print("Godot wrote no result (exit %d)\n%s" % (run.returncode, run.stdout[-4000:]), file=sys.stderr)
        return 1
    native = json.loads(out.read_text(encoding="utf-8"))
    if "error" in native:
        print("native digest unavailable: " + json.dumps(native), file=sys.stderr)
        return 1
    fold_rows = [index for index, path in enumerate(paths) if path.lower().endswith(tuple(suffixes))]
    began = time.perf_counter()
    workers = max(1, min(4, args.workers))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        reference = list(pool.map(lambda path: python_digest(path, False)[0], paths))
        folded = list(pool.map(lambda index: python_digest(paths[index], True), fold_rows))
    python_seconds = time.perf_counter() - began
    report = compare(paths, native, reference, dict(zip(fold_rows, folded)))
    log_text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    report.update({
        "root": str(args.root), "runtime_dir": str(args.runtime_dir), "files": len(paths),
        "bytes": native.get("bytes"), "native_ms": round(native.get("native_us", 0) / 1000.0, 1),
        "godot_wall_s": round(godot_seconds, 1), "hashlib_s": round(python_seconds, 1), "threads": args.threads,
        "hashlib_workers": workers, "api_info": native.get("api_info"), "godot_exit": run.returncode,
        "script_errors": log_text.count("SCRIPT ERROR"), "engine_errors": log_text.count("ERROR:"),
    })
    (args.work / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    summary = {key: report[key] for key in ("ok", "files", "folded_compared", "bytes", "native_ms", "hashlib_s",
                                             "godot_wall_s", "threads", "godot_exit", "script_errors", "engine_errors")}
    summary["backend"] = (report.get("api_info") or {}).get("sha256_backend")
    summary["mismatches"] = len(report["mismatches"])
    print(json.dumps(summary))
    for row in report["mismatches"][:20]:
        print("MISMATCH " + json.dumps(row, ensure_ascii=False))
    return 0 if report["ok"] and run.returncode == 0 and report["script_errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
