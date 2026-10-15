#!/usr/bin/env python3
"""Rebuild the checked-in Four Gates GLB package from its compact blockout seed."""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


TOOLS = Path(__file__).resolve().parent
ASSETS = TOOLS.parent
PACKAGE = ASSETS / "maps" / "four-gates-city"
SOURCE = PACKAGE / "source"
STEPS = (
    "enhance_four_gates.py",
    "landmark_four_gates.py",
    "populate_four_gates.py",
    "author_four_gates_landmarks.py",
    "terrain_water_four_gates.py",
    "polish_four_gates_visuals.py",
    "detail_four_gates.py",
    "compact_four_gates_lod2.py",
)


def main():
    with tempfile.TemporaryDirectory(prefix="four-gates-rebuild-") as temp:
        root = Path(temp)
        work = root / "four-gates-city-package"
        shutil.copytree(PACKAGE, work)
        shutil.copy2(SOURCE / "four-gates-city-blockout.glb", work / "four-gates-city.glb")
        shutil.copy2(SOURCE / "four-gates-city-blockout.json", work / "four-gates-city.json")
        for step in STEPS:
            subprocess.run([sys.executable, str(TOOLS / step)], cwd=root, check=True)
        for name in ("four-gates-city.glb", "four-gates-city.json", "four-gates-city-lod2.glb", "four-gates-city-lod2.json"):
            shutil.copy2(work / name, PACKAGE / name)
        for texture in (work / "textures").glob("*.png"):
            shutil.copy2(texture, PACKAGE / "textures" / texture.name)
    subprocess.run([sys.executable, str(TOOLS / "validate_four_gates_package.py")], check=True)


if __name__ == "__main__":
    main()
