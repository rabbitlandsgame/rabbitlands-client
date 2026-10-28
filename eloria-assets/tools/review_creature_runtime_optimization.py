"""Prepare/launch the unified, read-only creature optimization reviewer.

  python eloria-assets/tools/review_creature_runtime_optimization.py \
    --catalog .local/creature-runtime-retrofit/review/catalog.json --prepare-only

Catalog schema: {complete:bool, progress:{sampled,total,baked}, entries:[{
id, display_name, source:{path,sha256,bytes}, clips:[...],
variants:[{id,label,path,sha256,bytes,metrics:{...}}], was_installed,
selected_local_draft}], review_store:".local/review-events.jsonl"}.
Paths are relative to the catalog or absolute. Journal paths MUST remain under
the catalog directory's .local. Optional entry.actor supplies the models registry
key for synthetic control entries. Approvals cover the entire exact candidate,
all clips, and never copy/install anything. Comments are separate journal events.

--smoke always copies inputs into an isolated test catalog/store; it cannot
write real approvals. --prepare-only imports an isolated project but never opens
a GPU window. The default interactive launch requires a desktop rendering slot.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "godot-client/prototypes/creature_optimization_review.gd"
GODOT = Path("C:/rabbitlands/rabbitlands-client/godot-client/Godot_v4.7.2-stable_win64.exe")


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def resolve(base, path):
    return (base / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()


def journal_path(catalog_path, catalog):
    base = Path(catalog_path).resolve().parent
    path = resolve(base, catalog.get("review_store", ".local/review-events.jsonl"))
    if not path.is_relative_to((base / ".local").resolve()) or path.suffix != ".jsonl":
        raise ValueError("Review journal must be a JSONL file under catalog directory/.local")
    return path


def native_clips(path):
    with Path(path).open("rb") as file:
        header = file.read(20)
        magic, version, _, length, kind = struct.unpack("<IIIII", header)
        if (magic, version, kind) != (0x46546C67, 2, 0x4E4F534A):
            raise ValueError("Expected self-contained GLB")
        document = json.loads(file.read(length))
    return [a["name"] for a in document.get("animations", []) if a.get("name") != "RESET"]


def load_catalog(path, verify_files=False):
    path = Path(path).resolve()
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(catalog.get("complete"), bool) or not isinstance(catalog.get("entries"), list):
        raise ValueError("Catalog requires boolean complete and entries array")
    journal_path(path, catalog)
    seen = set()
    for entry in catalog["entries"]:
        if not entry.get("id") or entry["id"] in seen:
            raise ValueError("Catalog creature IDs must be unique")
        seen.add(entry["id"])
        clips = entry.get("clips", [])
        if not clips or len(clips) != len(set(clips)):
            raise ValueError("Every creature needs its full native clip inventory")
        variant_ids = [v["id"] for v in entry.get("variants", [])]
        if len(variant_ids) != len(set(variant_ids)):
            raise ValueError("Duplicate candidate variant ID")
        for fixture in [entry["source"], *entry.get("variants", [])]:
            if len(fixture.get("sha256", "")) != 64 or int(fixture.get("bytes", -1)) < 0:
                raise ValueError("Every file requires SHA256 and byte size")
            file = resolve(path.parent, fixture["path"])
            if verify_files and (file.stat().st_size != fixture["bytes"] or digest(file) != fixture["sha256"]):
                raise ValueError("Catalog file changed: " + str(file))
        if verify_files and set(native_clips(resolve(path.parent, entry["source"]["path"]))) != set(clips):
            raise ValueError("Catalog omits or invents source clips: " + entry["id"])
    return catalog


@contextlib.contextmanager
def journal_lock(path):
    """Serialize independent reviewer processes before a single O_APPEND write."""
    lock = Path(str(path) + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+b") as file:
        if file.tell() == 0:
            file.write(b"\0")
            file.flush()
        file.seek(0)
        if os.name == "nt":
            import msvcrt
            deadline = time.monotonic() + 10
            while True:
                try:
                    msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Another reviewer is writing the journal")
                    time.sleep(.025)
            try:
                yield
            finally:
                file.seek(0)
                msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(file, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(file, fcntl.LOCK_UN)


def append_event(catalog_path, request):
    """Append one exact-version review; reject stale inputs and incomplete approvals."""
    catalog_path = Path(catalog_path).resolve()
    catalog = load_catalog(catalog_path)
    kind = request.get("type")
    if kind not in ("approve", "comment"):
        raise ValueError("Unknown review event type")
    if kind == "approve" and not catalog["complete"]:
        raise ValueError("Processing is incomplete; approval is disabled")
    entry = next((e for e in catalog["entries"] if e["id"] == request.get("actor")), None)
    if entry is None:
        raise ValueError("Creature is no longer in the catalog")
    variant = next((v for v in entry.get("variants", []) if v["id"] == request.get("variant")), None)
    if variant is None:
        raise ValueError("Candidate variant is no longer available")
    for role, fixture in (("source", entry["source"]), ("candidate", variant)):
        path = resolve(catalog_path.parent, fixture["path"])
        if request.get(role + "_sha256") != fixture["sha256"] or resolve(catalog_path.parent, request[role + "_path"]) != path:
            raise ValueError("Displayed version differs from current catalog; explicitly reload it")
        if path.stat().st_size != fixture["bytes"] or digest(path) != fixture["sha256"]:
            raise ValueError("Displayed " + role + " file changed; no review saved")
    if request.get("clip") not in entry["clips"]:
        raise ValueError("Unknown displayed clip")
    clock = float(request.get("time_seconds", 0))
    if not 0 <= clock < float("inf"):
        raise ValueError("Invalid playback time")
    text = str(request.get("text", ""))
    if kind == "comment" and not text.strip():
        raise ValueError("Comment is empty")
    if len(text.encode("utf-8")) > 1024 * 1024:
        raise ValueError("Comment exceeds 1 MiB")
    event = {"schema": 1, "event_id": str(uuid.uuid4()), "utc": dt.datetime.now(dt.timezone.utc).isoformat(),
             "test_only": bool(catalog.get("test_only", False)),
             "type": kind, "scope": "creature_candidate_all_clips" if kind == "approve" else "candidate_comment",
             "actor": entry["id"], "registry_actor": entry.get("actor", entry["id"]),
             "source_path": str(resolve(catalog_path.parent, entry["source"]["path"])),
             "source_sha256": entry["source"]["sha256"], "candidate_path": str(resolve(catalog_path.parent, variant["path"])),
             "candidate_sha256": variant["sha256"], "variant": variant["id"], "clip": request["clip"],
             "time_seconds": clock, "catalog_sha256": digest(catalog_path), "text": text if kind == "comment" else ""}
    store = journal_path(catalog_path, catalog)
    payload = (json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    with journal_lock(store):
        if digest(catalog_path) != event["catalog_sha256"]:
            raise ValueError("Catalog changed during validation; retry against the displayed version")
        if store.exists() and store.stat().st_size:
            with store.open("rb") as existing:
                existing.seek(-1, os.SEEK_END)
                if existing.read(1) != b"\n":
                    raise ValueError("Journal has an incomplete final record; preserve and reconcile it")
        descriptor = os.open(store, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            if os.write(descriptor, payload) != len(payload):
                raise OSError("Incomplete journal write; preserved for recovery")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    return event


def prepare(project, client_root, godot):
    project = Path(project).resolve()
    if ".local" not in project.parts:
        raise ValueError("Use a dedicated ignored .local project")
    marker = project / "creature-review-project.json"
    if (project / "project.godot").exists() and not marker.exists():
        raise ValueError("Refusing to change an unrelated project")
    project.mkdir(parents=True, exist_ok=True)
    for relative in ("src", "data", "addons", "assets/ui"):
        shutil.copytree(Path(client_root) / "godot-client" / relative, project / relative, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(".git", ".godot", "__pycache__"))
    (project / "prototypes").mkdir(exist_ok=True)
    shutil.copy2(SCRIPT, project / "prototypes" / SCRIPT.name)
    (project / "project.godot").write_text('config_version=5\n[application]\nconfig/name="RL creature optimization review"\n[display]\nwindow/size/viewport_width=1500\nwindow/size/viewport_height=1000\n[rendering]\nrenderer/rendering_method="forward_plus"\n', encoding="utf-8")
    save(marker, {"client_root": str(Path(client_root).resolve()), "prototype_sha256": digest(SCRIPT)})
    run_engine(godot, project, project / "import", ["--headless", "--editor", "--import"])


def run_engine(godot, project, log, args):
    env = dict(os.environ)
    for key, leaf in (("APPDATA", "roaming"), ("LOCALAPPDATA", "local")):
        env[key] = str(project / "profile" / leaf)
        Path(env[key]).mkdir(parents=True, exist_ok=True)
    with Path(str(log) + ".stdout.log").open("w", encoding="utf-8") as stdout, Path(str(log) + ".stderr.log").open("w", encoding="utf-8") as stderr:
        result = subprocess.run([str(godot), "--path", str(project), *args], env=env, stdout=stdout, stderr=stderr,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                                timeout=300 if "--headless" in args else None)
    output = Path(str(log) + ".stdout.log").read_text(encoding="utf-8") + Path(str(log) + ".stderr.log").read_text(encoding="utf-8")
    if result.returncode or any(token in output for token in ("SCRIPT ERROR:", "Parse Error:", "ERROR:", "Assertion failed")):
        raise RuntimeError("Godot reviewer failed; inspect " + str(log) + ".*.log")


def smoke_catalog(source_catalog, output):
    catalog_path = Path(source_catalog).resolve()
    catalog = load_catalog(catalog_path, verify_files=True)
    entries = [json.loads(json.dumps(e)) for e in catalog["entries"] if e.get("variants")][:2]
    if not entries:
        raise ValueError("Smoke needs at least one available candidate")
    if len(entries) == 1:
        duplicate = json.loads(json.dumps(entries[0]))
        duplicate["actor"] = duplicate.get("actor", duplicate["id"])
        duplicate["id"] += "-smoke-control"
        entries.append(duplicate)
    for entry in entries:
        for fixture in [entry["source"], *entry["variants"]]:
            fixture["path"] = str(resolve(catalog_path.parent, fixture["path"]))
        if len(entry["variants"]) == 1:
            control = json.loads(json.dumps(entry["variants"][0]))
            control["id"] += "-smoke-control"
            control["label"] = "Same-file variant control (TEST ONLY)"
            entry["variants"].append(control)
    path = output / "smoke-catalog.json"
    save(path, {"complete": True, "progress": {"sampled": 2, "total": 2, "baked": 2}, "entries": entries,
                "review_store": ".local/TEST-ONLY-review-events.jsonl", "test_only": True})
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--godot", type=Path, default=GODOT)
    parser.add_argument("--client-root", type=Path, default=ROOT)
    parser.add_argument("--project", type=Path, default=ROOT / ".local/creature-optimization-review/project")
    parser.add_argument("--output", type=Path, default=ROOT / ".local/creature-optimization-review/sessions")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--reuse-project", action="store_true")
    parser.add_argument("--append-event", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.append_event:
        try:
            print(json.dumps(append_event(args.catalog, json.loads(args.append_event.read_text(encoding="utf-8")))))
            return 0
        except (ValueError, OSError, KeyError) as error:
            print(json.dumps({"saved": False, "error": str(error)}))
            return 2
    catalog = load_catalog(args.catalog, verify_files=True)
    if ".local" not in args.output.resolve().parts:
        raise ValueError("Session output must stay in ignored .local")
    output = args.output.resolve() / (dt.datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8])
    output.mkdir(parents=True)
    catalog_path = smoke_catalog(args.catalog, output) if args.smoke else args.catalog.resolve()
    if not args.reuse_project:
        prepare(args.project.resolve(), args.client_root.resolve(), args.godot)
    elif digest(args.project / "prototypes" / SCRIPT.name) != digest(SCRIPT):
        raise ValueError("Prepared reviewer differs; prepare again")
    job = {"catalog": str(catalog_path), "output": str(output), "python": sys.executable,
           "helper": str(Path(__file__).resolve()), "prototype_sha256": digest(SCRIPT), "smoke": args.smoke}
    save(output / "job.json", job)
    print(json.dumps({"job": str(output / "job.json"), "entries": len(catalog["entries"]), "complete": catalog["complete"],
                      "review_store": str(journal_path(catalog_path, load_catalog(catalog_path))), "test_only": args.smoke}), flush=True)
    if not args.prepare_only:
        run_engine(args.godot, args.project.resolve(), output / "review", (["--headless"] if args.smoke else []) +
                   ["--script", "res://prototypes/" + SCRIPT.name, "--", str(output / "job.json")])
        if args.smoke:
            result = json.loads((output / "review-smoke.json").read_text(encoding="utf-8"))
            if not result.get("headless") or result.get("prototype_sha256") != job["prototype_sha256"]:
                raise RuntimeError("Missing or stale headless smoke receipt")
            events = [json.loads(line) for line in Path(result["journal"]).read_text(encoding="utf-8").splitlines()]
            if not events or not all(event.get("test_only") is True for event in events):
                raise RuntimeError("Smoke journal contains an event without the TEST ONLY marker")


if __name__ == "__main__":
    raise SystemExit(main())
