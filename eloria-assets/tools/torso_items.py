#!/usr/bin/env python3
"""The item side of the sixty-four torso designs.

Added 2026-09-03 for Eloria Client.  ``torso_designs`` says what each design
looks like and what part-5 visual draws it; this says which item wears that
visual, and where its inventory icon lives.

The two halves of a wearable are owned by different repositories here, unlike
the generated armour and weapon sets whose importers write both.  The server's
``dev-server/tools/sync_torso_items.py`` owns the item definitions - it is what
writes them into ``config/eloria/items.txt`` - and this owns the pixels their
``image_id`` resolves to.  The two numbers below are therefore stated twice, in
that tool and here, and ``build_item_icon_atlases`` cross-checks them against
the profile so a set rebuilt on one side alone cannot go unnoticed.
"""
from __future__ import annotations

from pathlib import Path

import torso_designs

HERE = Path(__file__).resolve().parent
CLIENT = HERE.parent.parent / "godot-client"
PROJECT = HERE.parent.parent.parent

#: Where the built garments are; their stems are the roster's slugs and the
#: names the rendered icons carry.
MESHES = CLIENT / "assets/actors/native/equipment"

#: The icons, rendered from those meshes.  ``make_icons.py`` renders whatever
#: ``.glb`` files a directory holds, and MESHES holds far more than these -
#: every other equipment set, and a ``<slug>__bust`` fit variant of each of
#: these - so the sixty-four are staged into a directory of their own first.
#: ``--stage`` below does that; ``--out`` must be an absolute path, or Blender
#: writes the renders relative to its own working directory and the run ends
#: with "renders are missing":
#:
#:   python torso_items.py --stage /tmp/torso_glb
#:   python ../../../generate_models/equipment_icons/make_icons.py \
#:       --from /tmp/torso_glb --out <abs>/generate_models/equipment_icons/out-torso \
#:       --no-sheets
#:   python build_item_icon_atlases.py
ICONS = PROJECT / "generate_models" / "equipment_icons" / "out-torso" / "icons"

#: The served profile's ledger.  The generated armour set is items 1274-1529
#: with icons 118-373, the weapons 1530-1629 with 374-473 and the potion shelf
#: 1650-1681 with 474-505; the torso designs are the fourth and last run of
#: both.  Kept in step with dev-server/tools/sync_torso_items.py.
FIRST_ITEM_ID = 1682
FIRST_IMAGE_ID = 506


class Piece:
    __slots__ = ("source", "slug", "name", "kind", "part", "visual",
                 "finish", "item_id", "image_id")

    def __init__(self, source, slug, name, kind, visual, finish,
                 item_id, image_id):
        self.source, self.slug, self.name = source, slug, name
        self.kind, self.part, self.visual = kind, 5, visual
        self.finish, self.item_id, self.image_id = finish, item_id, image_id


def roster() -> list[Piece]:
    """Every torso design, in the fixed order that owns its ids."""
    return [
        Piece(MESHES / f"{slug}.glb", slug, label, kind,
              torso_designs.FIRST_VISUAL + index, finish,
              FIRST_ITEM_ID + index, FIRST_IMAGE_ID + index)
        for index, (slug, label, kind, finish, _base, _accent, _style)
        in enumerate(torso_designs.DESIGNS)
    ]


def stage(target: Path) -> int:
    """Copy just these sixty-four meshes into `target`, for the renderer."""
    import shutil

    target.mkdir(parents=True, exist_ok=True)
    for piece in roster():
        shutil.copy2(piece.source, target / piece.source.name)
    return len(roster())


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", type=Path,
                    help="copy the sixty-four meshes here for make_icons.py")
    arguments = ap.parse_args()

    pieces = roster()
    print(f"{len(pieces)} torso items {pieces[0].item_id}-{pieces[-1].item_id},"
          f" icons {pieces[0].image_id}-{pieces[-1].image_id}")
    if arguments.stage:
        print(f"staged {stage(arguments.stage)} meshes to {arguments.stage}")
