"""Create an ignored project configuration overlay for worker-pool diagnostics.

Source/data/import directories link to this task's checkout. Only project.godot
and override.cfg are private copies; the original configuration is never edited.
No engine is launched and no recursive cleanup is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "godot-client"
RUNTIME_DIRS = ["src","tests","data","assets","addons","native","schemas","scripts","world_authoring","prototypes","tools"]


def configured_override(original: bytes | None, threads: int) -> bytes | None:
    if threads == 0:
        return original
    if threads not in (4,8):
        raise ValueError("Only the declared 4/8-thread diagnostics are supported")
    text = original.decode("utf-8") if original is not None else ""
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines(keepends=True)
    section = ""
    threading_end = None
    found = []
    for index,line in enumerate(lines):
        heading = re.match(r"^\s*\[([^]]+)\]\s*$",line.lstrip("\ufeff").strip())
        if heading:
            if section == "threading": threading_end = index
            section = heading.group(1)
        if section == "threading" and re.match(r'^\s*"?worker_pool/max_threads"?\s*=',line):
            found.append(index)
    if len(found) > 1:
        raise ValueError("Ambiguous worker_pool/max_threads entries")
    assignment = f"worker_pool/max_threads={threads}"+newline
    if found:
        lines[found[0]] = assignment
    elif section == "threading" or threading_end is not None:
        insertion = len(lines) if threading_end is None else threading_end
        if insertion > 0 and not lines[insertion-1].endswith(("\r","\n")):
            lines[insertion-1] += newline
        lines.insert(insertion,assignment)
    else:
        if text and not text.endswith(("\r","\n")): lines.append(newline)
        lines.extend([newline+"[threading]"+newline,assignment])
    return "".join(lines).encode("utf-8")


def sha(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def junction(destination: Path, source: Path) -> None:
    source = source.resolve()
    if not source.is_relative_to(ROOT.resolve()):
        raise ValueError("Overlay link target must be task-owned")
    if destination.exists():
        if not destination.is_dir() or destination.resolve() != source:
            raise ValueError("Existing overlay link differs: "+str(destination))
        return
    env = dict(os.environ,RL_OVERLAY_DEST=str(destination),RL_OVERLAY_SOURCE=str(source))
    result = subprocess.run(["powershell.exe","-NoProfile","-NonInteractive","-Command",
        "New-Item -ItemType Junction -Path $env:RL_OVERLAY_DEST -Target $env:RL_OVERLAY_SOURCE | Out-Null"],
        env=env,capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode or destination.resolve() != source:
        raise RuntimeError("Cannot create task overlay junction: "+result.stderr)


def prepare(folder: Path, threads: int) -> dict:
    folder = folder.resolve()
    if not folder.is_relative_to((ROOT/".local").resolve()):
        raise ValueError("Overlay must be in this task's ignored .local directory")
    folder.mkdir(parents=True,exist_ok=True)
    manifest_path = folder/"overlay.json"
    override_source = SOURCE/"override.cfg"
    original = override_source.read_bytes() if override_source.exists() else None
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text())
        if existing["source_project"] != str(SOURCE.resolve()) or existing["original_override_sha256"] != sha(original):
            raise ValueError("Overlay ownership/original override changed")
    project = folder/"godot-client"
    project.mkdir(exist_ok=True)
    if project.resolve() != project:
        raise ValueError("Configuration project must be a real task directory")
    backup = folder/"original-override.cfg"
    if original is not None:
        if backup.exists() and backup.read_bytes() != original:
            raise ValueError("Original override recovery copy differs")
        backup.write_bytes(original)
    for name in RUNTIME_DIRS:
        if (SOURCE/name).is_dir(): junction(project/name,SOURCE/name)
    imports = project/".godot"
    imports.mkdir(exist_ok=True)
    if imports.resolve() != imports:
        raise ValueError("Overlay import metadata must be a real task directory")
    if (SOURCE/".godot/imported").is_dir(): junction(imports/"imported",SOURCE/".godot/imported")
    for name in ["global_script_class_cache.cfg","uid_cache.bin","extension_list.cfg",".gdignore"]:
        if (SOURCE/".godot"/name).is_file(): (imports/name).write_bytes((SOURCE/".godot"/name).read_bytes())
    assets = folder/"eloria-assets"
    assets.mkdir(exist_ok=True)
    if assets.resolve() != assets: raise ValueError("Overlay asset root must be a real task directory")
    for name in ["maps","fonts"]:
        if (ROOT/"eloria-assets"/name).is_dir(): junction(assets/name,ROOT/"eloria-assets"/name)
    project_data = (SOURCE/"project.godot").read_bytes()
    if (project/"project.godot").exists() and (project/"project.godot").samefile(SOURCE/"project.godot"):
        raise ValueError("Overlay project configuration must not alias its source")
    (project/"project.godot").write_bytes(project_data)
    configured = configured_override(original,threads)
    target = project/"override.cfg"
    if target.is_symlink() or not target.resolve().is_relative_to(project):
        raise ValueError("Overlay override path escapes its project")
    if target.exists() and override_source.exists() and target.samefile(override_source):
        raise ValueError("Overlay override must not alias its source")
    if configured is None:
        if target.exists(): target.unlink() # Only this owned, single config file.
    else:
        target.write_bytes(configured)
    if (override_source.read_bytes() if override_source.exists() else None) != original:
        raise ValueError("Original override changed during preparation")
    result = {"source_project":str(SOURCE.resolve()),"project":str(project),"worker_threads":threads,
        "original_override_exists":original is not None,"original_override_sha256":sha(original),
        "overlay_override_sha256":sha(configured),"project_sha256":sha(project_data),
        "original_untouched":True,"shared_source_data_import_directories":True,
        "scope":"Private configuration overlay only; source/import directories are task-shared, UID/class metadata copied. Shader/driver cache state is uncontrolled. OS/GPU settings and primary checkout are untouched."}
    manifest_path.write_text(json.dumps(result,indent=2),encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--worker-threads",type=int,choices=[0,4,8],default=0,help="0 preserves the exact existing override, including absence")
    args = parser.parse_args()
    print(json.dumps(prepare(args.output,args.worker_threads),indent=2))
    return 0


if __name__ == "__main__": raise SystemExit(main())
