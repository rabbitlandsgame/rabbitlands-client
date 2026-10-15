"""Install reviewed metadata and the validated library in this isolated worktree."""

import argparse, json, shutil
import numpy as np
from audit import WORKTREE, g, digest


def guarded_json(path, before, value):
    if digest(path) != before:
        raise RuntimeError("Concurrent edit: " + str(path))
    path.write_text(json.dumps(value, indent=2) + "\n")


def metadata():
    base = WORKTREE / "tpose-body-build"
    mp = WORKTREE / "godot-client/data/actors/models.json"
    cp = WORKTREE / "godot-client/data/actors/native_asset_catalog.json"
    mh, ch = digest(mp), digest(cp)
    models = json.loads(mp.read_text())
    catalog = json.loads(cp.read_text())
    for slug, entry in catalog["races"].items():
        model = base / f"out/{slug}.glb"
        d, b = g.read(model)
        world = g.globals_of(d)
        names = {n.get("name"): i for i, n in enumerate(d["nodes"])}
        attrs = {
            p["attributes"]["POSITION"] for m in d["meshes"] for p in m["primitives"]
        }
        pos = np.concatenate([g.accessor(d, b, a) for a in attrs])
        triangles = sum(
            d["accessors"][p["indices"]]["count"] // 3
            for m in d["meshes"]
            for p in m["primitives"]
        )
        fit = json.loads(model.with_suffix(".hair-fit.json").read_text())
        models["models"][slug]["hairFit"] = fit
        entry.update(
            vertices=len(pos),
            triangles=triangles,
            joints=77,
            wardrobe="skinned",
            anatomy="retargeted",
            baseBody=d["asset"]["extras"]["source"],
            stature=float(models["models"][slug]["import"]["scale"]),
            legChainScale=1.0,
            hipHeight=float(world[names["pelvis"]][1, 3]),
            groundHeight=float(pos[:, 1].min()),
            source=d["asset"]["extras"]["source"],
            sourceSHA256=d["asset"]["extras"]["sourceSHA256"],
            sha256=digest(model),
            surfaces=[n["name"] for n in d["nodes"] if "mesh" in n],
        )
        catalog["validation"]["results"][entry["path"]] = {
            "nodes": len(d["nodes"]),
            "meshes": len(d["meshes"]),
            "skins": len(d["skins"]),
            "animations": len(d.get("animations", [])),
        }
    catalog["racePipeline"] = "eloria-assets/tools/tpose_bodies/build.py + surfaces.py"
    guarded_json(mp, mh, models)
    guarded_json(cp, ch, catalog)
    return {
        "models_before": mh,
        "models_after": digest(mp),
        "catalog_before": ch,
        "catalog_after": digest(cp),
    }


def library():
    base = WORKTREE / "tpose-body-build"
    source = base / "out/Universal_Animation_Library.glb"
    target = (
        WORKTREE
        / "godot-client/assets/actors/native/shared/Universal_Animation_Library.glb"
    )
    before = digest(target)
    sha = digest(source)
    evidence = json.loads(source.with_suffix(".animations.json").read_text())
    if evidence["output_sha256"] != sha or not evidence["reference_pose_unchanged"]:
        raise ValueError("Library validation missing/stale")
    if before not in (evidence["source_sha256"], sha):
        raise ValueError("Client library changed since build")
    for slug in json.loads(
        (WORKTREE / "godot-client/data/actors/native_asset_catalog.json").read_text()
    )["races"]:
        r = json.loads((base / f"reports/{slug}_promotion.json").read_text())
        if not r["written"] or r["errors"] or r["review"]["library_sha256"] != sha:
            raise ValueError(
                "All bodies must be promoted against this library first: " + slug
            )
        if (
            digest(WORKTREE / f"godot-client/assets/actors/native/races/{slug}.glb")
            != r["model_sha256"]
        ):
            raise ValueError("Promoted body changed: " + slug)
    if digest(target) != before or digest(source) != sha:
        raise RuntimeError("Concurrent library edit")
    shutil.copyfile(source, target)
    if digest(target) != sha:
        raise RuntimeError("Library copy mismatch")
    return {"library_before": before, "library_after": sha}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("step", choices=["metadata", "library"])
    a = p.parse_args()
    if not WORKTREE.name.startswith("wt-") or not (WORKTREE / ".git").is_file():
        raise ValueError("Isolated worktree required")
    r = metadata() if a.step == "metadata" else library()
    (WORKTREE / f"tpose-body-build/reports/install_{a.step}.json").write_text(
        json.dumps(r, indent=2) + "\n"
    )
    print(json.dumps(r, indent=2))
