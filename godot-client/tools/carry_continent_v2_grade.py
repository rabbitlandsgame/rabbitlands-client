#!/usr/bin/env python3
"""Carry each map's ground-colour grade onto its re-cut crop.

The scenes read base-colors-graded.rgba8, a grade over the frozen crop (colour-grade.json binds the two). When a
partition change re-cuts a crop (a new window, new ground), the grade must follow it. The tool that made the grades
is not in the repository, so this carries them instead:
  * a vertex whose frozen crop colour is unchanged (same continent position, same bytes) keeps its graded bytes;
  * every other vertex gets the map's grade as a per-channel log ratio graded/frozen, harmonically inpainted from the
    carried vertices, so feathers, accents and canopy smoothing continue smoothly across new or re-cut ground.
Previous crops are read from Git (--from COMMIT); a successor map reads its predecessor's files (marker-renames-a3).
colour-grade.json keeps its targets and gains a "carried" record; parentFrozenCrop and graded are rebound.

  python godot-client/tools/carry_continent_v2_grade.py --from COMMIT [--check]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
from scipy import ndimage

import continent_v2_territories as T

CHECKOUT = T.CHECKOUT
REGIONS = CHECKOUT / "godot-client/world_authoring/regions"
RENAMES = CHECKOUT / "eloria-assets/maps/continent-v2/_continent_v2/marker-renames-a3.json"


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def git_show(ref: str, path: Path) -> bytes:
    return subprocess.run(["git", "show", f"{ref}:{path.relative_to(CHECKOUT).as_posix()}"], cwd=CHECKOUT,
                          capture_output=True, check=True).stdout


def window(provenance: dict):
    crop = provenance["crop"]
    first = np.asarray(crop["parentGrid"]["continentFirstVertex"], float) + T.CELL * np.array([crop["col0"], crop["row0"]])
    return first, crop["cols"], crop["rows"]


def push_pull(values: np.ndarray, weight: np.ndarray) -> np.ndarray:
    """Smooth fill of the unweighted cells from the weighted ones (pyramid push-pull); weighted cells keep their
    values where their weight is 1."""
    if min(values.shape) <= 2 or weight.sum() == 0:
        mean = (values * weight).sum() / max(weight.sum(), 1e-9)
        return np.where(weight > 0, values * weight + mean * (1 - weight), mean)
    h, w = values.shape
    ph, pw = h + h % 2, w + w % 2
    v = np.pad(values * weight, ((0, ph - h), (0, pw - w)))
    k = np.pad(weight, ((0, ph - h), (0, pw - w)))
    sv = v.reshape(ph // 2, 2, pw // 2, 2).sum((1, 3))
    sk = k.reshape(ph // 2, 2, pw // 2, 2).sum((1, 3))
    coarse = push_pull(sv / np.maximum(sk, 1e-9), np.minimum(sk, 1.0))
    up = ndimage.zoom(coarse, 2, order=1)[:h, :w]
    return values * weight + up * (1 - weight)


def harmonic(values: np.ndarray, known: np.ndarray) -> np.ndarray:
    return np.where(known, values, push_pull(np.where(known, values, 0.0), known.astype(np.float64)))


def carry(region: Path, previous: Path, ref: str):
    grade = json.loads((region / "colour-grade.json").read_text(encoding="utf-8"))
    frozen_new = (region / "base-colors.rgba8").read_bytes()
    if grade["parentFrozenCrop"]["sha256"] == sha(frozen_new):
        return None
    prov_new = json.loads((region / "terrain-provenance.json").read_text(encoding="utf-8"))
    prov_old = json.loads(git_show(ref, previous / "terrain-provenance.json"))
    frozen_old = git_show(ref, previous / "base-colors.rgba8")
    graded_old = git_show(ref, previous / grade["graded"]["path"])
    old_grade = json.loads(git_show(ref, previous / "colour-grade.json"))
    if sha(frozen_old) != old_grade["parentFrozenCrop"]["sha256"] or sha(graded_old) != old_grade["graded"]["sha256"]:
        raise ValueError(f"{region.name}: the previous grade is not bound to its previous crop")
    f0, w0, h0 = window(prov_old)
    f1, w1, h1 = window(prov_new)
    old_c = np.frombuffer(frozen_old, np.uint8).reshape(h0, w0, 4)
    old_g = np.frombuffer(graded_old, np.uint8).reshape(h0, w0, 4)
    new_c = np.frombuffer(frozen_new, np.uint8).reshape(h1, w1, 4)
    # new vertex (r, c) -> old (r - dr, c - dc)
    dc, dr = ((f1 - f0) / T.CELL).astype(int)
    rr, cc = np.mgrid[0:h1, 0:w1]
    orr, occ = rr + dr, cc + dc
    inside = (orr >= 0) & (orr < h0) & (occ >= 0) & (occ < w0)
    same = np.zeros((h1, w1), bool)
    same[inside] = (old_c[orr[inside], occ[inside]] == new_c[inside]).all(-1)
    graded = new_c.copy()
    graded[same] = old_g[orr[same], occ[same]]
    if (~same).any():
        ratio = np.log((graded[..., :3].astype(np.float64) + 1.0) / (new_c[..., :3].astype(np.float64) + 1.0))
        for k in range(3):
            filled = harmonic(np.where(same, ratio[..., k], 0.0), same)
            value = (new_c[..., k].astype(np.float64) + 1.0) * np.exp(filled) - 1.0
            graded[..., k] = np.where(same, graded[..., k], np.clip(np.round(value), 0, 255).astype(np.uint8))
    blob = graded.tobytes()
    grade["parentFrozenCrop"]["sha256"] = sha(frozen_new)
    grade["graded"]["sha256"] = sha(blob)
    grade["graded"]["changedVertices"] = int((graded != new_c).any(-1).sum())
    grade["carried"] = {"tool": "godot-client/tools/carry_continent_v2_grade.py", "fromCommit": ref,
                        "fromRegion": previous.relative_to(CHECKOUT).as_posix(),
                        "keptVertices": int(same.sum()), "carriedVertices": int((~same).sum()),
                        "method": "unchanged frozen bytes keep their graded bytes; the rest take a harmonically "
                                  "inpainted per-channel log ratio graded/frozen"}
    return blob, (json.dumps(grade, indent=1, ensure_ascii=False) + "\n").encode("utf-8"), grade["carried"]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from", dest="ref", required=True, help="commit holding the previous crops and grades")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    renamed = json.loads(RENAMES.read_text(encoding="utf-8"))["maps"] if RENAMES.exists() else {}
    successor_of = {new: old for old, new in renamed.items()}
    report, stale = {}, []
    for t in T.load_territories():
        region = REGIONS / t.id
        if not (region / "colour-grade.json").exists():
            continue
        previous = REGIONS / successor_of.get(t.id, t.id)
        result = carry(region, previous, args.ref)
        if result is None:
            continue
        blob, grade, record = result
        report[t.id] = record
        target = region / json.loads(grade)["graded"]["path"]
        if args.check:
            if not target.exists() or target.read_bytes() != blob or (region / "colour-grade.json").read_bytes() != grade:
                stale.append(t.id)
        else:
            target.write_bytes(blob)
            (region / "colour-grade.json").write_bytes(grade)
    print(json.dumps({"maps": report, "stale": stale}, indent=1))
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
