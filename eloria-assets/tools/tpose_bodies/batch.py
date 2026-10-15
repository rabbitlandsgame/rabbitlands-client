"""Build the verified roster only after the current Luminous pilot is accepted."""

from pathlib import Path
import argparse, json
import numpy as np
from audit import WORKTREE, g, digest
from build import fit
from surfaces import run as split_surfaces, calibration
from verify import verify


def hair_fit(model, gender):
    d, b = g.read(model)
    world = g.globals_of(d)
    head = next(i for i, n in enumerate(d["nodes"]) if n.get("name") == "Head")
    p = d["meshes"][0]["primitives"][0]
    v = g.accessor(d, b, p["attributes"]["POSITION"])
    local = (v - world[head][:3, 3]) @ world[head][:3, :3]
    core = local[
        (abs(local[:, 0]) < 0.085) & (local[:, 1] > 0.08) & (local[:, 1] < 0.24)
    ]
    top = float(np.percentile(core[abs(core[:, 0]) < 0.045, 1], 99))
    cap = core[(core[:, 1] > top - 0.09) & (core[:, 1] <= top)]
    lo, hi = np.percentile(cap, [1, 99], axis=0)
    hd, hb = g.read(
        WORKTREE / f"godot-client/assets/actors/native/hair/buzzed_{gender}.glb"
    )
    hv = g.accessor(hd, hb, hd["meshes"][0]["primitives"][0]["attributes"]["POSITION"])
    hlo, hhi = hv.min(0), hv.max(0)
    scale = np.array(
        [
            (hi[0] - lo[0] + 0.008) / (hhi[0] - hlo[0]),
            (top + 0.006) / hhi[1],
            (hi[2] - lo[2] + 0.010) / (hhi[2] - hlo[2]),
        ]
    )
    offset = np.array([(hi[0] + lo[0]) / 2, 0, (hi[2] + lo[2]) / 2]) - np.array(
        [(hhi[0] + hlo[0]) * scale[0] / 2, 0, (hhi[2] + hlo[2]) * scale[2] / 2]
    )
    return {"scale": scale.tolist(), "offset": offset.tolist()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--skip-verify", action="store_true")
    a = ap.parse_args()
    base = WORKTREE / "tpose-body-build"
    pilot = base / "out/luminous_female.glb"
    review = json.loads(
        (base / "reports/luminous_female_visual_review.json").read_text()
    )
    if not review.get("accepted") or review.get("model_sha256") != digest(pilot):
        raise ValueError("Current pilot must be reviewed before batching")
    catalog = json.loads(
        (WORKTREE / "godot-client/data/actors/native_asset_catalog.json").read_text()
    )
    roster = list(catalog["races"])
    inventory = json.loads((base / "reports/inventory.json").read_text())
    if set(roster) != set(inventory["roster"]):
        raise ValueError("Roster changed since inventory")
    library = base / "out/Universal_Animation_Library.glb"
    template = base / "in/luminous_female.glb"
    for slug in roster:
        if a.only and slug not in a.only:
            continue
        if slug == "luminous_female":
            continue
        source_slug = slug.replace("luminous_", "luminous_human_").replace(
            "votary_", "whitehorn_votary_"
        )
        unsplit = base / f"out/{slug}_unsplit.glb"
        out = base / f"out/{slug}.glb"
        fit(base / f"in/{source_slug}_tpose_rigged.glb", library, template, unsplit)
        report = split_surfaces(unsplit, out, calibration(slug))
        out.with_suffix(".hair-fit.json").write_text(
            json.dumps(hair_fit(out, slug.split("_")[-1]), indent=2) + "\n"
        )
        print(slug, report["faces"], flush=True)
        if not a.skip_verify:
            clips = (
                ("Walk", "Run_Female", "Jog")
                if slug.startswith("ssarathi")
                else ("Walk", "Run_Female")
            )
            result = verify(out, library, base / f"in/{slug}.glb", clips)
            (base / f"reports/{slug}_validation.json").write_text(
                json.dumps(result, indent=2) + "\n"
            )
            print(slug, result["errors"], result["warnings"], flush=True)


if __name__ == "__main__":
    main()
