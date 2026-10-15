#!/usr/bin/env python3
"""Resolve a creature slug to the concept figure it was authored from.

The concept art ships two ways.  The original delivery is fourteen 4x3 sheets,
which ``concept_sheet_index.py`` has to segment before anything can be compared
against them.  The later delivery is the same fourteen sheets already cut into
one PNG per figure, on transparency, named ``<sheet>__NN__<subject>.png`` where
``NN`` is the one-based cell index in reading order.

Cut figures are strictly better evidence than segmented ones -- they are the
artist's own bounds rather than a guess -- so this prefers them and falls back
to segmenting a whole sheet only when the cut set is not available.

Point ``ELORIA_CONCEPT_FIGURES`` at the directory holding the per-sheet
subdirectories, or ``ELORIA_CONCEPT_DIR`` at the whole sheets.

    python3 eloria-assets/tools/concept_figures.py --list
    python3 eloria-assets/tools/concept_figures.py amberwood_treant
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import creature_roster as RO

# The roster keys creatures by an opaque sheet stem.  The cut-figure delivery
# names the same sheets descriptively.  Verified subject-by-subject: every cell
# index lines up with the roster's (row, col) under ``index = row * 4 + col``.
SHEET_DIRS = {
    "47a41963": "amethyst_barrens_crystal_creatures_sheet",
    "4dc46727": "amethyst_barrens_crystal_creatures_sheet",
    "f1bb1663": "cross-region_fantasy_enemies_bosses_sheet",
    "93197c59": "cross-region_natural_wildlife_sheet",
    "1e840e1e": "cross-region_natural_wildlife_sheet",
    "bc78bfcc": "crownwater_crystal_aquatic_creatures_sheet",
    "4cf4bb0e": "crownwater_magical_aquatic_creatures_sheet",
    "5b11c39c": "crownwater_manymouth_aquatic_creatures_sheet",
    "2dd667c5": "grey_moors_spirits_creatures_sheet",
    "53a67c51": "manymouth_crownwater_aquatic_monsters_sheet",
    "4bbc1f8e": "manymouth_delta_swamp_creatures_sheet",
    "66616a1d": "verdant_ssarathi_jungle_creatures_sheet",
    "15c7630b": "whitehorn_glacier_creatures_sheet",
    "a5ba7c19": "amberwood_forest_spirits_creatures_sheet_b",
    "c09f0eed": "amberwood_forest_spirits_creatures_sheet",
    "4250fde7": "amberwood_grey_moors_creatures_transparent_sheet_b",
}

# The pre-roster native creatures were authored from cells the roster leaves
# unassigned.  Keyed the same way so they compare against art too.
LEGACY_CELLS = {
    "horse": ("93197c59", 0, 0),
    "red_fox": ("93197c59", 0, 2),
    "giant_tortoise": ("93197c59", 1, 3),
    "miretoad": ("4bbc1f8e", 0, 2),
    "giant_komodo": ("4bbc1f8e", 0, 3),
    "giant_crocodile": ("4bbc1f8e", 1, 0),
    "mountain_goat": ("15c7630b", 0, 0),
    "snow_hare": ("15c7630b", 0, 1),
    "frost_maw": ("15c7630b", 0, 2),
    "ice_bear": ("15c7630b", 0, 3),
    "frost_tiger": ("15c7630b", 1, 2),
    "mossback_boar": ("c09f0eed", 0, 1),
    "elk": ("c09f0eed", 0, 0),
    "emberfox": ("c09f0eed", 0, 2),
}


def _root() -> Path | None:
    raw = os.environ.get("ELORIA_CONCEPT_FIGURES")
    if not raw:
        return None
    root = Path(raw)
    if not root.is_dir():
        return None

    def holds_sheets(base: Path) -> bool:
        """A sheet directory is a subdirectory of cut figures, not a stray file."""
        return any(child.is_dir() and len(list(child.glob("*__*.png"))) >= 8
                   for child in base.iterdir())

    # Tolerate the delivery being nested inside a directory of its own name.
    if not holds_sheets(root):
        for candidate in (root / root.name, *(c for c in root.iterdir() if c.is_dir())):
            if candidate.is_dir() and holds_sheets(candidate):
                return candidate
    return root


def cell_for(slug: str):
    """(sheet stem, row, col) for a slug, or None if it is not keyed to art."""
    for entry in RO.ROSTER:
        if entry[0] == slug:
            return entry[7], entry[8], entry[9]
    return LEGACY_CELLS.get(slug)


def figure_path(slug: str) -> Path | None:
    """The cut concept figure for a slug, if the cut delivery is available."""
    root = _root()
    cell = cell_for(slug)
    if root is None or cell is None:
        return None
    stem, row, col = cell
    if stem not in SHEET_DIRS:
        # An unknown stem is a creature with no concept figure -- authored
        # rather than measured.  Falling through to ``root / ""`` searched the
        # delivery root and matched whatever stray file shared the cell index,
        # which silently keyed a creature to a completely unrelated subject.
        return None
    directory = root / SHEET_DIRS[stem]
    if not directory.is_dir():
        return None
    matches = sorted(directory.glob(f"*__{row * 4 + col + 1:02d}__*.png"))
    return matches[0] if matches else None


def subject_of(path: Path) -> str:
    """The artist's own name for a figure, from its filename."""
    return path.stem.split("__")[-1].replace("-", " ")


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] == "--list":
        slugs = [e[0] for e in RO.ROSTER] + sorted(LEGACY_CELLS)
        missing = 0
        for slug in slugs:
            path = figure_path(slug)
            if path is None:
                missing += 1
                print(f"{slug:26s}  --")
            else:
                print(f"{slug:26s}  {subject_of(path)}")
        print(f"\n{len(slugs) - missing}/{len(slugs)} slugs resolved to a cut figure")
        return
    for slug in args:
        path = figure_path(slug)
        print(path if path else f"{slug}: no figure")


if __name__ == "__main__":
    main()
