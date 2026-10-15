#!/usr/bin/env python3
"""Fail when assets lack provenance, or when Eternal Lands content reappears.

This used to guard one thing: that no file in `eloria-assets/` carried the name
of an official Eternal Lands map. The repository has since dropped the C client
it forked, the Eternal Lands format data pack that client loaded, and the ELM
maps the server read, so the guard now covers the whole tree and the file
formats as well as the names. Nothing here is a licensing opinion - it is a
tripwire, so that content which was deliberately removed cannot come back by
being copied in, generated, or vendored without someone noticing.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

# Official Eternal Lands map names. `startmap.elm` is on this list and was, for
# a while, the key Four Gates was served under; see godot-client/data/maps.
PROHIBITED_NAMES = {
    "startmap.elm", "map2.elm", "map3.elm", "map4f.elm", "map5nf.elm",
    "map6nf.elm", "map7.elm", "map8.elm", "map9f.elm", "map11.elm",
    "map12.elm", "map13.elm", "map14f.elm", "map15f.elm",
}

# Eternal Lands engine formats. The Godot client reads none of them: maps are
# GLB plus a JSON manifest, walk grids are EWCG, actors are GLB, and textures
# are PNG, JPEG or WebP.
#
#   .elm            map
#   .e3d            3D object
#   .caf .cmf .csf .crf .xaf .xmf .xsf .xrf    Cal3D animation/mesh/skeleton
#   .dds .bmp       the pack's texture formats
PROHIBITED_SUFFIXES = {
    ".elm", ".e3d", ".caf", ".cmf", ".csf", ".crf",
    ".xaf", ".xmf", ".xsf", ".xrf", ".dds", ".bmp",
}

SKIP_DIRECTORIES = {".git", ".github", "__pycache__", "build", "dist",
                    ".godot", ".import", "node_modules"}


def walk(root: Path):
    """Every file the repository contains.

    Tracked files, not whatever is lying in the working directory. This is a
    statement about what the project ships, and a developer's checkout is full
    of things that are not that - an unpacked dependency tarball, a stale
    worktree, an old build. Failing on those is a false alarm, and a compliance
    check that cries wolf is one nobody reads.
    """
    listed = subprocess.run(["git", "-C", str(root), "ls-files", "-z"],
                            capture_output=True, text=True, check=False)
    if listed.returncode == 0:
        for name in listed.stdout.split("\0"):
            if not name:
                continue
            path = root / name
            if path.is_file():
                yield path
        return
    # Not a git checkout - an exported tarball, say. Fall back to the tree.
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if SKIP_DIRECTORIES & set(path.relative_to(root).parts):
            continue
        yield path


def main() -> int:
    assets = Path(__file__).resolve().parents[1]
    repo = assets.parent

    failures: list[str] = []

    provenance_path = assets / "provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    if not provenance.get("assets"):
        failures.append("asset provenance is empty")

    named = sorted(str(p.relative_to(repo)) for p in walk(repo)
                   if p.name.casefold() in PROHIBITED_NAMES)
    if named:
        failures.append("official Eternal Lands asset names:\n  "
                        + "\n  ".join(named))

    formats = sorted(str(p.relative_to(repo)) for p in walk(repo)
                     if p.suffix.casefold() in PROHIBITED_SUFFIXES)
    if formats:
        failures.append("Eternal Lands engine file formats:\n  "
                        + "\n  ".join(formats))

    if failures:
        print("\n\n".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
