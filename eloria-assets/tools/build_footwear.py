#!/usr/bin/env python3
"""Build the sixty-four footwear designs, fitted against every race that wears them.

The shell is solved rather than padded.  Sizing a boot to the body it was
authored on fits that body; sizing it to a guess about the others fits nobody in
particular.  So each design is built, measured against every race in its fit
group with the same connected-component parity check the tests use, and any body
vertex still outside the shell is carried back into the authoring rig's own
space and added to what the next round has to contain.  Two or three rounds is
usually enough, and a design that will not converge says so rather than shipping.

Run with ``--only <slug>`` while iterating on one design; the default builds the
whole catalogue plus its saurian variants.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import equipment_authoring as ea          # noqa: E402
import footwear_authoring as fa           # noqa: E402
import footwear_refit as fr               # noqa: E402
import garment_fit as gf                  # noqa: E402
from footwear_catalogue import DESIGNS, VISUALS  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / "godot-client"
RACES = CLIENT / "assets" / "actors" / "native" / "races"
EQUIPMENT = CLIENT / "assets" / "actors" / "native" / "equipment"
REGISTRY = CLIENT / "data" / "actors" / "equipment.json"
CATALOG = CLIENT / "data" / "actors" / "native_asset_catalog.json"

#: Which rig each fit group is authored on.  ``""`` is the reference group.
GROUP_RIG = {"": "luminous_male", "feminine_foot": "luminous_female",
             "broad_foot": "stoneborn_male", "saurian": "ssarathi_male"}


def group_members(registry: dict) -> dict:
    """Which races wear which build, one build per race.

    ``fitGroups`` maps a race to *every* group it belongs to - a Luminous woman
    is both ``feminine`` and ``bust`` - because different garment kinds claim
    different groups.  Footwear cares about the ones that claim ``boots``, and a
    race that is in none of them wears the reference piece.
    """
    groups = registry.get("fitGroups", {})
    members: dict[str, list[Path]] = {}
    for path in sorted(RACES.glob("*.glb")):
        listed = groups.get(path.stem, [])
        if isinstance(listed, str):
            listed = [listed]
        mine = [group for group in listed if group in GROUP_RIG]
        members.setdefault(mine[0] if mine else "", []).append(path)
    return members


def preimage(points: np.ndarray, author_path: Path, wearer_path: Path,
             registry: dict) -> np.ndarray:
    """Body points on a wearer, carried back into the authoring rig's space.

    Which bone carries a point is decided the way the skinning decides it: the
    ankle behind the ball of the foot, the ball ahead of it, the calf above the
    ankle.  Run through the wrong one a point comes back somewhere it never
    goes, and the shell grows to hold a place nothing is.
    """
    author = fr.skeleton(str(author_path))
    wearer = fr.skeleton(str(wearer_path))
    author_name, wearer_name = author_path.stem, wearer_path.stem
    canonical = float(registry.get("canonicalHeadRestY", 0.0)) or 1.0
    fit = wearer.head_y() / canonical
    girth = fr.girth_ratios(registry, author_name, wearer_name)
    drops = fr.ground_drops(registry, author_name, wearer_name, "boots")

    rig = ea.load_rig(wearer_path)
    carried = []
    for side in ("l", "r"):
        anatomy = fa.measure_foot(rig, side)
        axis = anatomy.toe_tip - anatomy.ankle
        axis = axis / max(float(np.linalg.norm(axis)), 1e-9)
        mine = points[np.sign(points[:, 0]) == np.sign(anatomy.ankle[0] or 1.0)]
        if not len(mine):
            continue
        along = (mine - anatomy.ankle) @ axis
        ball_at = float((anatomy.ball - anatomy.ankle) @ axis)
        above = mine[:, 1] > anatomy.ankle[1] + .025
        picks = {f"calf_{side}": above,
                 f"ball_{side}": ~above & (along >= ball_at),
                 f"foot_{side}": ~above & (along < ball_at)}
        for bone, mask in picks.items():
            if not mask.any() or bone not in author.rest or bone not in wearer.rest:
                continue
            middle = np.eye(4)
            pair = drops.get(bone)
            if pair:
                wide = fr._widening(bone, author.rest, wearer,
                                    float(girth.get(bone, 1.0)))
                middle[:3, :3] = np.eye(3) * (fit * wide)
                landed, wanted = pair[0] * (fit * wide), pair[1]
                move = wanted - landed
                middle[:3, 3] = np.linalg.inv(wearer.rest[bone][:3, :3]) @ move
            else:
                middle[:3, :3] = fr._bone_basis(bone, author.rest, wearer, fit,
                                                float(girth.get(bone, 1.0)))
            forward = wearer.rest[bone] @ middle @ np.linalg.inv(author.rest[bone])
            block = mine[mask]
            padded = np.concatenate([block, np.ones((len(block), 1))], axis=1)
            carried.append((np.linalg.inv(forward) @ padded.T).T[:, :3])
    return np.concatenate(carried) if carried else np.zeros((0, 3))


def measure(path: Path, wearers, registry: dict, author: str):
    """Fit reports for one built boot against every race that wears it."""
    reports = []
    for wearer in wearers:
        shells: list[gf.Component] = []
        for points, triangles in fr.worn_geometry(path, wearer, registry, author):
            shells.extend(gf.components(points, triangles))
        reports.append(gf.check(path, wearer, shells=shells))
    return reports


def solve(design, author_path: Path, wearers, registry: dict, out: Path,
          slug: str, rounds: int = 4, verbose: bool = True):
    """Build one design and grow it until nothing shows through."""
    primary = ea.load_rig(author_path)
    others = [ea.load_rig(path) for path in wearers if path != author_path]
    # The shaft is lofted against the whole group, the foot against this body.
    #
    # `RigSet` takes the largest reading across every race.  For the shaft that
    # is right: a calf is a calf, the Orun's is thirty per cent broader, and the
    # runtime's girth widening is one number for the whole bone rather than a
    # profile - authored to the reference alone the shaft left the broadest
    # calves showing through.  The foot is different, and is solved separately
    # against this body with a bounded allowance for the others, because there
    # the difference is an offset rather than a size and sizing for it makes a
    # boot that fits nobody.
    rig = ea.RigSet(primary, others)
    # Seeded empty.  The anchor datum now carries the foot onto each wearer
    # bodily - height, and across, and fore-and-aft - so the authored shell no
    # longer has to be cut wide enough to swallow every other body in the group
    # pre-emptively.  Anything still outside after the first round is measured
    # and added, which is a far smaller correction than sizing for all of them
    # up front: solving that way made the shell 24 cm across.
    cast: dict[str, list] = {"l": [], "r": []}
    rim = 0.0
    history = []
    for attempt in range(rounds):
        shaped = design if rim <= 0 else design.__class__(
            **{**design.__dict__,
               "shaft_thickness": design.shaft_thickness + rim})
        surface = fa.build_boot(shaped, rig, cast=cast)
        info = ea.build_equipment_piece(
            out, rig, slug, design.label, "boots", design.base, design.accent,
            finish=design.finish, surface=surface)
        reports = measure(out, wearers, registry, author_path.stem)
        exposed = sum(report.exposed for report in reports)
        history.append(exposed)
        if verbose:
            worst = max(reports, key=lambda report: report.exposed)
            print(f"    round {attempt}: {exposed:4d} exposed"
                  f" (worst {worst.rig} {worst.exposed}),"
                  f" sink {max(r.sink_mm for r in reports):.1f} mm", flush=True)
        if exposed == 0:
            return info, reports, history
        grew = False
        for report in reports:
            if not report.exposed:
                continue
            wearer = RACES / f"{report.rig}.glb"
            back = preimage(report.exposed_points, author_path, wearer, registry)
            if not len(back):
                continue
            # Anything above the ankle is the shaft's problem and the shaft is
            # one radius, not a point cloud, so it is let out instead.
            ankle = float(primary.origin("foot_l")[1])
            high = back[back[:, 1] > ankle + .025]
            low = back[back[:, 1] <= ankle + .025]
            if len(high):
                # A boot is a boot before it is a fit report. Two millimetres,
                # twice: past that the shaft stops looking like the sheet it
                # came from, and the handful of vertices still showing are worth
                # less than the silhouette.
                rim = min(rim + .002, .004)
                grew = True
            if len(low):
                for side in ("l", "r"):
                    mine = low[np.sign(low[:, 0])
                               == np.sign(primary.origin(f"foot_{side}")[0] or 1.0)]
                    if len(mine):
                        cast[side].append(mine)
                        grew = True
        if not grew:
            break
    return info, reports, history


def _one(job):
    """Build one design and both its variants.  Top level so it can be pooled."""
    design, members, registry, visual, rounds = job
    entry = {"visual": visual, "sheet": design.sheet, "cell": list(design.cell),
             "label": design.label, "shaftTopT": design.shaft_top,
             "layering": design.layering, "variants": {}}
    for group, rig_name in GROUP_RIG.items():
        wearers = members.get(group, [])
        if not wearers:
            continue
        author = RACES / f"{rig_name}.glb"
        slug = design.slug if not group else ea.variant_slug(design.slug, group)
        out = EQUIPMENT / f"{slug}.glb"
        info, reports, history = solve(design, author, wearers, registry, out,
                                       slug, rounds=rounds, verbose=False)
        entry["variants"][group or "reference"] = {
            "slug": slug, "authoredFor": rig_name,
            "triangles": info["triangles"], "bytes": info["bytes"],
            "rounds": history,
            "races": {r.rig: {"exposed": r.exposed, "covered": r.covered,
                              "sinkMm": round(r.sink_mm, 2),
                              "boundaryEdges": r.boundary_edges,
                              "volumeCm3": round(r.volume * 1e6, 1),
                              "ok": r.ok} for r in reports}}
    return design.slug, entry


def _record(results: dict) -> None:
    """Put the footwear in the asset catalogue beside everything else.

    The catalogue is what ``test_native_glb_assets`` reads to decide which
    visual ids ought to exist, so a design that is only in the registry reads as
    an id nothing declared.  ``build_native_nymara_glbs --only equipment`` resets
    the equipment sections and leaves this one alone, so the two can be rebuilt
    in either order.
    """
    if not CATALOG.is_file():
        return
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    footwear = {}
    for slug, entry in results.items():
        reference = entry["variants"].get("reference")
        if reference is None:
            continue
        footwear[slug] = {
            "id": slug, "name": entry["label"], "part": 6,
            "visual": entry["visual"], "kind": "boots",
            # The catalogue's own tests read these to decide what a piece is:
            # a garment that does not say it is skinned is checked as a prop.
            "attach": "skinned", "skinRegion": "boots",
            "authoredFor": reference["authoredFor"],
            "concept": {"sheet": entry["sheet"], "cell": entry["cell"]},
            "triangles": reference["triangles"],
            "path": f"godot-client/assets/actors/native/equipment/{slug}.glb",
            "variants": {group: variant["slug"]
                         for group, variant in entry["variants"].items()
                         if group != "reference"}}
    catalog["footwear"] = dict(sorted(footwear.items()))
    CATALOG.write_text(json.dumps(catalog, indent=1) + chr(10), encoding="utf-8")
    print(f"catalogue: {len(footwear)} footwear designs recorded")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", action="append", default=[],
                        help="build just these design slugs")
    parser.add_argument("--rounds", type=int, default=2,
                        help="fit rounds per design; the growth converges by 1")
    parser.add_argument("--jobs", type=int, default=1,
                        help="designs to build at once; they are independent")
    parser.add_argument("--report", type=Path,
                        default=ROOT / "eloria-assets" / "footwear-fit.json")
    args = parser.parse_args()

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    members = group_members(registry)
    designs = [d for d in DESIGNS if not args.only or d.slug in args.only]
    visual_of = {d.slug: v for v, d in VISUALS.items()}

    started = time.time()
    work = [(design, members, registry, visual_of[design.slug], args.rounds)
            for design in designs]
    results = {}
    if args.jobs > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            for done, (slug, entry) in enumerate(pool.map(_one, work), 1):
                results[slug] = entry
                print(f"[{done}/{len(work)}] {slug} done", flush=True)
    else:
        for done, item in enumerate(work, 1):
            slug, entry = _one(item)
            results[slug] = entry
            print(f"[{done}/{len(work)}] {slug} done", flush=True)
    args.report.write_text(json.dumps(results, indent=1), encoding="utf-8")
    _record(results)

    every = [race for entry in results.values()
             for variant in entry["variants"].values()
             for race in variant["races"].values()]
    failed = [race for race in every if not race["ok"]]
    print(f"\n{len(every) - len(failed)}/{len(every)} race fits pass"
          f"   worst sink {max(r['sinkMm'] for r in every):.1f} mm"
          f"   total exposed {sum(r['exposed'] for r in every)}"
          f"   {time.time() - started:.0f}s")
    args.report.write_text(json.dumps(results, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
