"""Prepare optional portable WD-C5 indices in this worktree's ignored output."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess

REPO = Path(__file__).resolve().parents[2]


def prepare_job(sources: list[str], out: Path) -> dict:
    out = out.resolve()
    if not out.is_relative_to(REPO / ".local"):
        raise ValueError("Producer output must remain inside this worktree's ignored .local")
    rows = []
    for name in dict.fromkeys(sources):
        source = (REPO / name).resolve()
        if (not source.is_relative_to(REPO / "eloria-assets/maps") or source.suffix.lower() != ".glb"
                or not source.is_file() or source.is_relative_to(REPO / ".local")):
            raise ValueError("Select an existing repository map prototype GLB")
        rows.append({"path": source.relative_to(REPO).as_posix(), "absolute": source.as_posix()})
    if not rows:
        raise ValueError("Select at least one prototype with --source or --sources-json")
    return {"sources": rows, "out": out.as_posix()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", required=True, type=Path)
    parser.add_argument("--source", action="append", default=[], help="Repository-relative prototype GLB; repeatable")
    parser.add_argument("--sources-json", type=Path, help="JSON list of repository-relative prototype GLBs")
    parser.add_argument("--out", type=Path, default=REPO / ".local/browser-prototype/prototype-lods")
    args = parser.parse_args()
    sources = list(args.source)
    if args.sources_json:
        selection = json.loads(args.sources_json.read_text(encoding="utf-8"))
        if not isinstance(selection, list) or any(not isinstance(s, str) for s in selection):
            parser.error("--sources-json must contain a list of source paths")
        sources.extend(selection)
    try:
        job = prepare_job(sources, args.out)
    except ValueError as error:
        parser.error(str(error))
    out = Path(job["out"])
    out.mkdir(parents=True, exist_ok=True)
    path = out / "job.json"
    path.write_text(json.dumps(job, indent=2) + "\n", encoding="utf-8")
    env = dict(os.environ, APPDATA=str(out / "profile/roaming"), LOCALAPPDATA=str(out / "profile/local"))
    for name in ("APPDATA", "LOCALAPPDATA"):
        Path(env[name]).mkdir(parents=True, exist_ok=True)
    # A tiny CPU-only project skips gameplay autoloads, editor plugins and imports.
    project = out / "project"
    (project / "src/world").mkdir(parents=True, exist_ok=True)
    (project / "tools").mkdir(exist_ok=True)
    import shutil
    for relative in ["src/world/browser_prototype_lods.gd", "src/world/world_distance_classes.gd",
                     "tools/build_browser_prototype_lods.gd"]:
        shutil.copy2(REPO / "godot-client" / relative, project / relative)
    (project / "project.godot").write_text('config_version=5\n[application]\nconfig/name="RL prototype LOD producer"\n')
    with (out / "producer.log").open("w", encoding="utf-8") as log:
        result = subprocess.run([str(args.godot.resolve()), "--headless", "--path", str(project),
            "--script", "res://tools/build_browser_prototype_lods.gd", "--", str(path)], env=env,
            stdout=log, stderr=subprocess.STDOUT, timeout=600)
    text = (out / "producer.log").read_text(encoding="utf-8", errors="replace")
    if result.returncode or any(s in text for s in ["SCRIPT ERROR", "ERROR:", "Parse Error"]):
        raise SystemExit(f"LOD producer failed; inspect {out / 'producer.log'}")
    print(out / "index.json")


if __name__ == "__main__":
    main()
