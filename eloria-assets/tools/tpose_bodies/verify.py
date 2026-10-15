"""Independent FK/LBS checks using the live shared library's name-only clip semantics."""

from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import numpy as np
from audit import g, retarget, reference_pose, digest


def groups(d, b):
    grouped = {}
    for n in d["nodes"]:
        if "mesh" not in n:
            continue
        for p in d["meshes"][n["mesh"]]["primitives"]:
            attrs = p["attributes"]
            key = (n.get("skin"), tuple(sorted(attrs.items())))
            if key not in grouped:
                grouped[key] = {
                    "attrs": attrs,
                    "skin": n.get("skin"),
                    "indices": [],
                    "nodes": [],
                }
            grouped[key]["indices"].append(
                g.accessor(d, b, p["indices"]).astype(int).reshape(-1, 3)
            )
            grouped[key]["nodes"].append(n.get("name"))
    for block in grouped.values():
        a = block["attrs"]
        block["v"] = g.accessor(d, b, a["POSITION"])
        block["faces"] = np.concatenate(block.pop("indices"))
        block["j"] = g.accessor(d, b, a["JOINTS_0"]).astype(int)
        block["w"] = g.accessor(d, b, a["WEIGHTS_0"])
        if d["accessors"][a["WEIGHTS_0"]].get("normalized"):
            block["w"] /= np.iinfo(
                np.dtype(g.COMPONENT[d["accessors"][a["WEIGHTS_0"]]["componentType"]])
            ).max
        f = block["faces"]
        block["edges"] = np.unique(
            np.sort(np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]]), axis=1),
            axis=0,
        )
    return list(grouped.values())


def sample_worlds(d, lib, lb, clip, times):
    names = {n.get("name"): i for i, n in enumerate(d["nodes"])}
    channels = retarget.clip_channels(lib, lb, clip)
    sampled = {}
    for i, paths in channels.items():
        name = lib["nodes"][i]["name"]
        if name == "head" and "Head" in names:
            name = "Head"
        if name not in names:
            continue
        sampled[names[name]] = {
            p: retarget._sample(times, tt, v, interp, p == "rotation")
            for p, (tt, v, interp) in paths.items()
        }
    for ti in range(len(times)):
        local = {}
        for i, paths in sampled.items():
            n = d["nodes"][i]
            local[i] = g.trs_matrix(
                *[
                    paths[p][ti] if p in paths else n.get(p, default)
                    for p, default in [
                        ("translation", [0, 0, 0]),
                        ("rotation", [0, 0, 0, 1]),
                        ("scale", [1, 1, 1]),
                    ]
                ]
            )
        yield g.globals_of(d, local)


def replay(d, b, lib, lb, clipname):
    clip = next(a for a in lib["animations"] if a["name"] == clipname)
    channels = retarget.clip_channels(lib, lb, clip)
    keys = retarget.clip_times(channels)
    duration = float(keys.max())
    times = np.unique(
        np.round(
            np.concatenate(
                [keys, np.linspace(0, duration, int(np.ceil(duration * 60)) + 1)]
            ),
            5,
        )
    )
    gg = groups(d, b)
    for block in gg:
        v = block["v"]
        e = block["edges"]
        block["rest_length"] = np.linalg.norm(v[e[:, 0]] - v[e[:, 1]], axis=1)
        block["ratios"] = np.zeros(len(e))
        block["gains"] = np.full(len(e), -np.inf)
        s = d["skins"][block["skin"]]
        block["skin_joints"] = s["joints"]
        block["ib"] = (
            g.accessor(d, b, s["inverseBindMatrices"])
            .reshape(-1, 4, 4)
            .transpose(0, 2, 1)
        )
    worst = {"gain_m": -1.0}
    floor = []
    loop_delta = 0.0
    for t, world in zip(times, sample_worlds(d, lib, lb, clip, times)):
        for block in gg:
            v, j, w = block["v"], block["j"], block["w"]
            m = np.array([world[i] for i in block["skin_joints"]]) @ block["ib"]
            posed = np.zeros_like(v)
            for k in range(j.shape[1]):
                posed += (
                    np.einsum("nij,nj->ni", m[j[:, k], :3, :3], v) + m[j[:, k], :3, 3]
                ) * w[:, k, None]
            floor.append(float(posed[:, 1].min()))
            if t == times[0]:
                block["first_pose"] = posed.copy()
            if t == times[-1]:
                loop_delta = max(
                    loop_delta,
                    float(np.linalg.norm(posed - block["first_pose"], axis=1).max()),
                )
            e = block["edges"]
            length = np.linalg.norm(posed[e[:, 0]] - posed[e[:, 1]], axis=1)
            gain = length - block["rest_length"]
            ratio = np.divide(
                length,
                block["rest_length"],
                out=np.ones_like(length),
                where=block["rest_length"] > 1e-5,
            )
            block["ratios"] = np.maximum(block["ratios"], ratio)
            block["gains"] = np.maximum(block["gains"], gain)
            wi = int(gain.argmax())
            if gain[wi] > worst["gain_m"]:
                worst = {
                    "gain_m": float(gain[wi]),
                    "ratio": float(ratio[wi]),
                    "time": float(t),
                    "edge": e[wi].tolist(),
                    "rest_positions": v[e[wi]].tolist(),
                    "nodes": block["nodes"],
                }
    ratios = np.concatenate([q["ratios"] for q in gg])
    gains = np.concatenate([q["gains"] for q in gg])
    return {
        "clip": clipname,
        "duration": duration,
        "frames": len(times),
        "edges": len(ratios),
        "minimum_vertex_y_m": min(floor),
        "loop_max_vertex_delta_m": loop_delta,
        "edge_max_ratio_percentiles": np.percentile(
            ratios, [50, 95, 99, 99.9, 100]
        ).tolist(),
        "edge_gain_m_percentiles": np.percentile(
            gains, [50, 95, 99, 99.9, 100]
        ).tolist(),
        "worst": worst,
    }


def verify(model, library, template, clips=("Walk",)):
    d, b = g.read(model)
    lib, lb = g.read(library)
    ref, _, _ = reference_pose(library)
    old, ob = g.read(template)
    names = [d["nodes"][i]["name"] for i in d["skins"][0]["joints"]]
    onames = [old["nodes"][i]["name"] for i in old["skins"][0]["joints"]]
    rnames = {
        n["name"] if n["name"] != "head" else "Head": i
        for i, n in enumerate(ref["nodes"])
    }
    out = {
        "model": str(model),
        "sha256": digest(model),
        "library_sha256": digest(library),
        "errors": [],
        "warnings": [],
        "joints": len(names),
    }
    if len(names) != 77 or names != onames:
        out["errors"].append("Joint names/order mismatch")
    rw = g.globals_of(ref)
    world = g.globals_of(d)
    rp = g.parents_of(ref)
    dp = g.parents_of(d)
    deviations = []
    for j in d["skins"][0]["joints"]:
        n = d["nodes"][j]["name"]
        if n not in rnames:
            continue
        ri = rnames[n]
        delta = float(np.max(np.abs(world[j] - rw[ri])))
        deviations.append(delta)
        parentname = d["nodes"][dp[j]].get("name") if j in dp else None
        rparentname = ref["nodes"][rp[ri]].get("name") if ri in rp else None
        if n != "root" and parentname != rparentname:
            out["errors"].append("Parent mismatch " + n)
        if delta > 1e-5:
            out["errors"].append("Rest mismatch " + n)
    out["rest_max_matrix_error"] = max(deviations)
    ib = (
        g.accessor(d, b, d["skins"][0]["inverseBindMatrices"])
        .reshape(-1, 4, 4)
        .transpose(0, 2, 1)
    )
    out["inverse_bind_max_error"] = float(
        np.max(
            np.abs(
                np.array([world[j] for j in d["skins"][0]["joints"]]) @ ib - np.eye(4)
            )
        )
    )
    if out["inverse_bind_max_error"] > 1e-5:
        out["errors"].append("Inverse binds do not match rests")
    for block in groups(d, b):
        if not np.isfinite(block["v"]).all() or not np.isfinite(block["w"]).all():
            out["errors"].append("Nonfinite vertex/weight")
        if np.max(np.abs(block["w"].sum(1) - 1)) > 1e-5 or block["w"].min() < 0:
            out["errors"].append("Invalid weights")
        if block["j"].max() >= 77 or block["j"].min() < 0:
            out["errors"].append("Invalid joint index")
        for k in range(block["j"].shape[1]):
            if any(
                names[j].startswith("cape_")
                for j in np.unique(block["j"][block["w"][:, k] > 1e-5, k])
            ):
                out["errors"].append("Cape joint carries body weight")
    out["replay"] = [replay(d, b, lib, lb, c) for c in clips]
    for r in out["replay"]:
        if r["worst"]["gain_m"] > 0.1:
            out["errors"].append(
                r["clip"] + " edge extension exceeds 100mm review limit"
            )
        if r["edge_gain_m_percentiles"][2] > 0.02:
            out["warnings"].append(r["clip"] + " p99 edge extension exceeds 20mm")
        if r["loop_max_vertex_delta_m"] > 0.001:
            out["errors"].append(r["clip"] + " loop endpoint mismatch exceeds 1mm")
        if r["minimum_vertex_y_m"] < -0.025:
            out["warnings"].append(
                r["clip"] + " geometry extends more than 25mm below the floor"
            )
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("model", type=Path)
    ap.add_argument("--library", type=Path, required=True)
    ap.add_argument("--template", type=Path, required=True)
    ap.add_argument("--clips", default="Walk")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    r = verify(a.model, a.library, a.template, a.clips.split(","))
    a.out.write_text(json.dumps(r, indent=2) + "\n")
    print(json.dumps(r, indent=2))
    raise SystemExit(bool(r["errors"]))
