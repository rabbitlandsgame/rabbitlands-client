"""Read-only source/contract inventory. Run from any directory with Python + numpy."""

from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

HERE = Path(__file__).resolve().parent
WORKTREE = HERE.parents[2]
ROOT = WORKTREE.parent
sys.path.insert(0, str(HERE / "vendor"))
import glbkit as g
import retarget


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inspect(path):
    d, b = g.read(path)
    world = g.globals_of(d)
    parents = g.parents_of(d)
    skins = []
    for s in d.get("skins", []):
        names = [d["nodes"][j].get("name", "") for j in s["joints"]]
        skins.append(
            {
                "joints": names,
                "parents": [
                    d["nodes"][parents[j]].get("name", "") if j in parents else None
                    for j in s["joints"]
                ],
                "head_world": [
                    world[j][:3, 3].tolist()
                    for j in s["joints"]
                    if d["nodes"][j].get("name") in ("Head", "head")
                ],
            }
        )
    meshes = []
    for i, n in enumerate(d.get("nodes", [])):
        if "mesh" not in n:
            continue
        for p in d["meshes"][n["mesh"]]["primitives"]:
            pos = g.accessor(d, b, p["attributes"]["POSITION"])
            if "skin" in n:
                skin = d["skins"][n["skin"]]
                ib = (
                    g.accessor(d, b, skin["inverseBindMatrices"])
                    .reshape(-1, 4, 4)
                    .transpose(0, 2, 1)
                )
                mats = np.array([world[j] for j in skin["joints"]]) @ ib
                moved = np.zeros_like(pos)
                for suffix in ("0", "1"):
                    if "JOINTS_" + suffix not in p["attributes"]:
                        continue
                    jj = g.accessor(d, b, p["attributes"]["JOINTS_" + suffix]).astype(
                        int
                    )
                    wi = p["attributes"]["WEIGHTS_" + suffix]
                    ww = g.accessor(d, b, wi)
                    if d["accessors"][wi].get("normalized"):
                        ww /= np.iinfo(
                            np.dtype(g.COMPONENT[d["accessors"][wi]["componentType"]])
                        ).max
                    for k in range(jj.shape[1]):
                        moved += (
                            np.einsum("nij,nj->ni", mats[jj[:, k], :3, :3], pos)
                            + mats[jj[:, k], :3, 3]
                        ) * ww[:, k, None]
                pos = moved
            else:
                pos = pos @ world[i][:3, :3].T + world[i][:3, 3]
            meshes.append(
                {
                    "node": n.get("name"),
                    "attributes": p["attributes"],
                    "vertices": len(pos),
                    "faces": (
                        d["accessors"][p["indices"]]["count"] // 3
                        if "indices" in p
                        else len(pos) // 3
                    ),
                    "material": p.get("material"),
                    "bounds": [pos.min(0).tolist(), pos.max(0).tolist()],
                }
            )
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": digest(path),
        "skins": skins,
        "meshes": meshes,
        "materials": len(d.get("materials", [])),
        "animations": [a.get("name") for a in d.get("animations", [])],
        "extensions_required": d.get("extensionsRequired", []),
    }


def reference_pose(path):
    d, b = g.read(path)
    out = copy.deepcopy(d)
    clip = next(a for a in d["animations"] if a["name"] == "Rest_Pose")
    channels = retarget.clip_channels(d, b, clip)
    for node, paths in channels.items():
        for key, (times, values, interp) in paths.items():
            out["nodes"][node][key] = retarget._sample(
                np.array([0.0]), times, values, interp, key == "rotation"
            )[0].tolist()
    return out, b, channels


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out", type=Path, default=WORKTREE / "tpose-body-build/reports/inventory.json"
    )
    args = ap.parse_args()
    client = ROOT / "rabbitlands-client/godot-client"
    catalog = json.loads((client / "data/actors/native_asset_catalog.json").read_text())
    races = catalog["races"]
    source = ROOT / "generate_models/eloria-races-meshy"
    report = {
        "roster": list(races),
        "sources": [inspect(p) for p in sorted(source.glob("*.glb"))],
        "other_files": [
            {"name": p.name, "bytes": p.stat().st_size, "sha256": digest(p)}
            for p in sorted(source.iterdir())
            if p.is_file() and p.suffix != ".glb"
        ],
        "shipped": [
            inspect(client / "assets/actors/native/races" / (slug + ".glb"))
            for slug in races
        ],
    }
    lib = client / "assets/actors/native/shared/Universal_Animation_Library.glb"
    ref, b, channels = reference_pose(lib)
    report["library"] = {
        "path": str(lib),
        "sha256": digest(lib),
        "rest_channels": {
            ref["nodes"][j]["name"]: list(v) for j, v in channels.items()
        },
        "rest_nodes": ref["nodes"],
    }
    report["contract_files"] = {
        str(p): digest(p)
        for p in [
            client / "data/actors/native_asset_catalog.json",
            client / "data/actors/models.json",
            client / "data/actors/equipment.json",
            client / "src/actors/appearance_variants.gd",
            client / "src/actors/replicated_actor_3d.gd",
            client / "src/actors/native_animation_importer.gd",
            client / "data/animations/luminous.json",
        ]
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    for group in ("sources", "shipped"):
        print(group)
        for f in report[group]:
            print(
                Path(f["path"]).name,
                "joints",
                [len(s["joints"]) for s in f["skins"]],
                "nodes",
                [m["node"] for m in f["meshes"]],
                "faces",
                sum(m["faces"] for m in f["meshes"]),
                "attrs",
                list(f["meshes"][0]["attributes"]) if f["meshes"] else [],
            )
    print("Report:", args.out)


if __name__ == "__main__":
    main()
