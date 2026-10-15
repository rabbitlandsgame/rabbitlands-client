#!/usr/bin/env python3
"""Split the generated leg pieces that came with feet into legs and boots.

Added 2026-09-06 for Eloria Client.

Legs and feet are separate slots, so a leg piece owns the body from the waist
to the ankle and nothing below it.  One of the eight generated leg sheets
disagrees: every design on ``Eight_legendary_fantasy_leg_armor_designs`` was
drawn -- and generated -- as a full harness ending in an armoured boot, so
its eight leg pieces (``Phoenix Legguards`` through ``Lion Legguards``) each
ship a pair of sabatons that a player wearing boots would be wearing twice.

**Which sheets, and how that was settled.**  A foot is the one part of a leg
piece that reaches *forward* past the shin above it, so the side silhouette
says it plainly.  Measured against the six real boot sheets as a control, the
bottom slab of a boot is about twice as deep as the column above it; of the
eight leg sheets only the legendary one reads that way, on all eight of its
designs, and the rendered silhouettes agree -- legendary shows the boot
control's L-shaped foot and the other seven end flat at the ankle.

That measurement is *not* what selects a sheet here.  Taken as a threshold it
does not separate cleanly: a flared trouser cuff on the militia sheet reaches
almost as far forward as the shallowest legendary sabaton, and trimming a cuff
because it flared would quietly restyle a design nobody complained about.  The
sheets are therefore named below after looking at them, which is the same
bargain ``import_generated_equipment.SHEETS`` makes -- what a piece *is* is
authored, and only its geometry is measured.

The ankle is still measured, per design, and reported: walking up the forward
profile from the floor, the toe's reach falls away and settles at the shin's own
minimum, between 11% and 19% of each mesh's height.  It is the evidence that a
foot is there at all.  It is no longer where the cut goes -- see below.

The cut is left open, like every other edge in this set: these are generated
shells with hundreds of boundary edges already, and the two new edges meet each
other exactly, so whichever piece is missing the other's edge is a hem.

**The feet are kept, not thrown away.**  They are the only armoured boots in
the set drawn to match one specific pair of legs, so each one is written out as
its own generated source under the boot sheet named in ``BOOTED_SHEETS``, and
picked up from there by ``import_generated_equipment`` like any other sheet.

**One cut, at ``BOOT_SHARE``, serves both.**  Everything above it is legwear and
everything below it is the boot, so no detail is on both and none is lost.  The
legs are therefore hemmed at the boot's rim rather than at the ankle, and a
player wearing no boots shows bare shin below it -- which is the trade, and the
one our user asked for, because the alternative is the sabaton's cuff riding
the leg armour and being worn twice over when the boots go on.  The legs are
seated against that hem too: see ``SHEET_SPAN`` in the importer.

Only ``<piece>.glb`` is rewritten.  ``<piece>.glb.orig`` is the raw generator
export and stays as it is -- it is what marks a source as preprocessed for
``import_generated_equipment.roster`` and what the icon renderer prefers -- and
the pre-trim ``.glb`` is kept beside it as ``.glb.booted``, which is both the
backup and where the boot is cut from once the legs no longer have one.  A
source that already has a ``.glb.booted`` is left alone, so the tool is
idempotent.

  python trim_generated_boots.py                  split, and say what moved
  python trim_generated_boots.py --dry-run        measure only
  python trim_generated_boots.py --restore        put the feet back on the legs

Then build both sheets.  The legs change geometry only, so their definitions
stay put; the boots are new items and need theirs written:

  python import_generated_equipment.py --sheet legendary_leg_armor --meshes-only
  python import_generated_equipment.py --sheet legendary_sabatons

Since the race programme's P7 cleanup (2026-10) both sheets ship as their
Human fits, so the importer no longer rebuilds them in place: refit them with
refit_human_bodies.py, install_human_equipment.py and
share_human_equipment_textures.py (a new sheet still builds as above).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

import conform_equipment as ce
import equipment_authoring as ea

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent.parent
GENERATED = PROJECT / "generate_models" / "meshy-armor-individual-glb"

#: Generated sheets whose leg pieces were drawn with the foot attached, and the
#: boot sheet each one's feet are split off into.  See the note above on why
#: this is a list and not a threshold.
BOOTED_SHEETS = {
    "Eight_legendary_fantasy_leg_armor_designs":
        "Eight_legendary_fantasy_sabatons",
}

#: Where the boot's top edge falls on the source, as a fraction of its height.
#: A source spans the waist to the sole, so its two ends are the top of the leg
#: region and the bottom of the boot region, and the boot is everything below
#: the boot region's own top edge.  Derived from the spans rather than tuned, so
#: it follows them if they ever move; 0.3025 as they stand.
#:
#: This is deliberately *not* the ankle the legs are cut at.  A boot in this set
#: has a shaft: the leg hem lands at Y 0.184 and the boot reaches 0.320, so the
#: two overlap and the trouser tucks in.  Splitting the foot off at the ankle
#: instead gives a sabaton with no shaft, and `seat` -- which scales uniformly
#: to fill the region -- then has to double it to reach 0.320, which lands a
#: foot half again too big on the body.  Measured: x2.02 cut at the ankle
#: against x1.10 cut here.
BOOT_SHARE = ((ce.SPAN["boots"][1] - ce.SPAN["boots"][0])
              / (ce.SPAN["legs"][1] - ce.SPAN["boots"][0]))

#: Rows in the height profile.  400 over a unit-tall mesh is a 2.5 mm band --
#: finer than the generator's own triangles, so the profile is limited by the
#: mesh rather than by the sampling.
ROWS = 400

#: How far up to look for the ankle, as a fraction of the piece's height.  A
#: leg piece spans roughly the waist to the sole, so a third of it is well
#: above any boot and safely below the knee.
SEARCH = 0.35

#: How much of the toe's forward reach may survive at the cut.  The profile
#: falls from the toe to a plateau at the shin; taking the first row within a
#: sixth of that fall lands on the top of the boot rather than partway up it.
SETTLED = 0.15


def forward_profile(points: np.ndarray, triangles: np.ndarray,
                    rows: int = ROWS) -> tuple[float, float, np.ndarray]:
    """How far forward the filled side view reaches, per height band.

    Rasterised from the triangles rather than the vertices: a generated shell
    is hollow and sparse, and a point cloud read straight off it reports the
    gaps between triangles as the silhouette.
    """
    height = points[:, 1]
    low, high = float(height.min()), float(height.max())
    step = (high - low) / rows
    reach = np.full(rows, -np.inf)
    for triangle in triangles:
        corner = points[triangle]
        first = max(0, int((corner[:, 1].min() - low) / step))
        last = min(rows - 1, int((corner[:, 1].max() - low) / step))
        front = corner[:, 2].max()
        band = reach[first:last + 1]
        np.maximum(band, front, out=band)
    return low, high, reach


def ankle_of(points: np.ndarray, triangles: np.ndarray) -> tuple[float, float]:
    """World Y of the ankle, and the toe's reach above the shin that found it."""
    low, high, reach = forward_profile(points, triangles)
    span = high - low
    window = reach[:int(ROWS * SEARCH)]
    live = np.isfinite(window)
    toe = float(window[live][:12].max())
    shin = float(window[live].min())
    settled = shin + SETTLED * (toe - shin)
    rows = np.flatnonzero(live & (window <= settled))
    row = int(rows[0]) if len(rows) else int(ROWS * SEARCH)
    return low + row * (span / ROWS), (toe - shin) / span


def clip(points, normals, uvs, triangles, cut, *, above: bool):
    """One side of world Y `cut`, with the straddling triangles cut in two.

    Left open at the cut.  Capping it would be the odd thing to do here: these
    shells carry hundreds of boundary edges already, and both new edges land
    inside the other garment -- the leg's hem inside the boot, the boot's rim
    under the leg -- where nothing can see them.
    """
    keep = points[:, 1] >= cut if above else points[:, 1] <= cut
    out_points = list(points)
    out_normals = list(normals)
    out_uvs = list(uvs)
    made: dict[tuple[int, int], int] = {}

    def cross(inside: int, outside: int) -> int:
        """The vertex where the edge meets the cut, made once per edge."""
        key = (inside, outside) if inside < outside else (outside, inside)
        if key in made:
            return made[key]
        here, there = points[inside], points[outside]
        share = (cut - here[1]) / (there[1] - here[1])
        point = here + (there - here) * share
        point[1] = cut
        normal = normals[inside] + (normals[outside] - normals[inside]) * share
        length = float(np.linalg.norm(normal))
        out_points.append(point)
        out_normals.append(normal / length if length > 1e-9 else normals[inside])
        out_uvs.append(uvs[inside] + (uvs[outside] - uvs[inside]) * share)
        made[key] = len(out_points) - 1
        return made[key]

    kept: list[tuple[int, int, int]] = []
    for triangle in triangles:
        inside = [corner for corner in triangle if keep[corner]]
        if len(inside) == 3:
            kept.append(tuple(int(c) for c in triangle))
        elif len(inside) == 2:
            # Clipping one corner off leaves a quad; both halves keep the
            # triangle's winding by starting from the same new edge.
            at = next(n for n in range(3) if not keep[triangle[n]])
            gone, near, far = (int(triangle[at]), int(triangle[(at + 1) % 3]),
                               int(triangle[(at + 2) % 3]))
            first, second = cross(near, gone), cross(far, gone)
            kept.append((first, near, far))
            kept.append((first, far, second))
        elif len(inside) == 1:
            at = next(n for n in range(3) if keep[triangle[n]])
            stays, after, before = (int(triangle[at]), int(triangle[(at + 1) % 3]),
                                    int(triangle[(at + 2) % 3]))
            kept.append((stays, cross(stays, after), cross(stays, before)))

    if not kept:
        raise ValueError("the cut removed the whole mesh")
    faces = np.asarray(kept, dtype=np.int64)
    used = np.unique(faces)
    remap = np.full(len(out_points), -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    return (np.asarray(out_points)[used], np.asarray(out_normals)[used],
            np.asarray(out_uvs)[used], remap[faces])


def write_piece(target: Path, stem: str, kept, png) -> None:
    glb = ea.EquipmentGLB(generator="Eloria trim_generated_boots")
    material = ce.textured_material(glb, stem, png)
    glb.mesh(stem, [glb.primitive(kept[0], kept[1], kept[2], kept[3],
                                  material)])
    glb.write(target)


def whole_of(source: Path) -> Path:
    """The mesh with its foot still on: the backup once the legs are cut."""
    booted = source.with_name(source.name + ".booted")
    return booted if booted.exists() else source


def trim(source: Path, *, dry_run: bool) -> str:
    backup = source.with_name(source.name + ".booted")
    if backup.exists():
        return "%-14s already trimmed" % source.stem.split("__")[-1]

    piece, png = ce.read_source(source)
    points, normals, uvs = piece.positions, piece.normals, piece.uvs
    triangles = piece.indices.reshape(-1, 3)
    low, high = float(points[:, 1].min()), float(points[:, 1].max())
    # The SAME line the boot is cut at, not the ankle.  Cutting the legs at the
    # ankle and the boot at the boot line leaves the band between them on both
    # pieces, and that band is the sabaton's own cuff -- so the leg armour kept
    # a set of boot plates around its hem, and a player wearing the boots wore
    # them twice over.  One line divides the design once: everything above it
    # is legwear, everything below is the boot, and the detail that comes off
    # one is exactly the detail that goes onto the other.
    cut = low + BOOT_SHARE * (high - low)
    _, reach = ankle_of(points, triangles)

    kept = clip(points, normals, uvs, triangles, cut, above=True)
    told = ("%-14s cut at %5.1f%% of height, toe reached %.3f past the shin, "
            "%d -> %d triangles"
            % (source.stem.split("__")[-1], 100 * BOOT_SHARE,
               reach, len(triangles), len(kept[3])))
    if dry_run:
        return told

    source.replace(backup)
    write_piece(source, source.stem, kept, png)
    return told


def split_boots(source: Path, boot_stem: str, *, dry_run: bool) -> str:
    """Write the foot end of a booted leg piece out as its own boot source.

    The feet are the reason this sheet had to be trimmed at all, and they are
    the only armoured boots in the set drawn to match a specific pair of legs,
    so they are kept and made wearable rather than thrown away.

    Emitted as a `.glb` with a `.glb.orig` beside it, because
    ``import_generated_equipment.roster`` reads that sibling as the mark of a
    preprocessed source and skips anything without one.  The two are identical
    here: there is no separate raw export for a mesh that was derived rather
    than generated, and nothing downstream wants a different one.
    """
    name = source.name.replace(source.name.split("__")[0], boot_stem, 1)
    target = source.with_name(name)
    label = source.stem.split("__")[-1]
    if target.exists():
        return "%-14s boots already split off" % label

    piece, png = ce.read_source(whole_of(source))
    points, normals, uvs = piece.positions, piece.normals, piece.uvs
    triangles = piece.indices.reshape(-1, 3)
    low, high = float(points[:, 1].min()), float(points[:, 1].max())
    cut = low + BOOT_SHARE * (high - low)

    kept = clip(points, normals, uvs, triangles, cut, above=False)
    told = ("%-14s boot is the bottom %.1f%%, %d triangles -> %s"
            % (label, 100 * BOOT_SHARE, len(kept[3]), target.name))
    if dry_run:
        return told

    write_piece(target, target.stem, kept, png)
    write_piece(target.with_name(target.name + ".orig"), target.stem, kept, png)
    return told


def restore(source: Path, boot_stem: str) -> str:
    """Put the foot back on the legs, and take the split-off boots away."""
    label = source.stem.split("__")[-1]
    name = source.name.replace(source.name.split("__")[0], boot_stem, 1)
    for boot in (source.with_name(name),
                 source.with_name(name + ".orig")):
        if boot.exists():
            boot.unlink()
    backup = source.with_name(source.name + ".booted")
    if not backup.exists():
        return "%-14s no backup to restore" % label
    backup.replace(source)
    return "%-14s restored" % label


def main() -> int:
    parser = argparse.ArgumentParser(
        description="split generated leg pieces built with feet into a leg "
                    "piece and a boot piece")
    parser.add_argument("--generated", type=Path, default=GENERATED,
                        help="directory of generated meshes")
    parser.add_argument("--sheet", default=None,
                        help="only this sheet stem, of the ones listed above")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--restore", action="store_true",
                        help="put back the pre-trim meshes and drop the boots")
    args = parser.parse_args()

    if not args.generated.is_dir():
        print("no generated meshes at %s" % args.generated)
        return 2
    sheets = {stem: boots for stem, boots in BOOTED_SHEETS.items()
              if not args.sheet or stem == args.sheet}
    if not sheets:
        print("not a sheet with boots built in: %s" % args.sheet)
        return 2

    for sheet, boot_stem in sheets.items():
        sources = sorted(args.generated.glob(sheet + "__*.glb"))
        print("%s -- %d piece(s)" % (sheet, len(sources)))
        for source in sources:
            if args.restore:
                print("  " + restore(source, boot_stem))
                continue
            print("  " + trim(source, dry_run=args.dry_run))
            print("  " + split_boots(source, boot_stem,
                                     dry_run=args.dry_run))
    if args.dry_run:
        print("\nnothing written (--dry-run)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
