import os

os.environ["OPENBLAS_NUM_THREADS"] = "2"
os.environ["OMP_NUM_THREADS"] = "2"
import argparse, json, pathlib, sys, numpy as np
import collections
import hashlib

parser = argparse.ArgumentParser(
    description="Evaluate actual Godot mesh arrays, native clips and every directed crossfade pair for an exact-storage job."
)
parser.add_argument("--job", type=pathlib.Path, required=True)
parser.add_argument("--mode", choices=["native", "imported", "fit"], default="native")
args = parser.parse_args()
inputs = json.loads(args.job.read_text(encoding="utf-8"))
out = pathlib.Path(inputs["output"])
mode = args.mode
runtime = out / mode
job = json.loads((runtime / "runtime.json").read_text())
reorder = np.arange(sum(m["vertices"] for m in job["descriptions"][0]["meshes"]))


def matrix(rows):
    a = np.array(rows, float).reshape(-1, 3, 4)
    out = np.tile(np.eye(4), (len(a), 1, 1))
    out[:, :3] = a
    return out


descs = []
for model in job["descriptions"]:
    groups = []
    for m in model["meshes"]:
        p = pathlib.Path(m["prefix"])
        n = m["vertices"]
        count = m["targets"]
        v = np.fromfile(str(p) + "-positions.f32", "<f4").reshape(n, 3).astype(float)
        nn = np.fromfile(str(p) + "-normals.f32", "<f4").reshape(n, 3).astype(float)
        j = np.fromfile(str(p) + "-joints.i32", "<i4").reshape(n, -1)
        w = np.fromfile(str(p) + "-weights.f32", "<f4").reshape(n, -1).astype(float)
        sp = (
            np.fromfile(str(p) + "-shape-positions.f32", "<f4")
            .reshape(count, n, 3)
            .astype(float)
        )
        sn = (
            np.fromfile(str(p) + "-shape-normals.f32", "<f4")
            .reshape(count, n, 3)
            .astype(float)
        )
        if m["mode"] == 0:
            sp -= v
            sn -= nn
        groups.append(
            dict(
                meta=m,
                base=v,
                normals=nn,
                joints=j,
                weights=w,
                position_targets=sp.reshape(count, n * 3),
                normal_targets=sn.reshape(count, n * 3),
                bind=matrix(m["binds"]),
            )
        )
    descs.append(groups)


def evaluate(groups, state):
    world = matrix(state["poses"])
    positions = []
    normals = []
    for group_index, (group, values) in enumerate(zip(groups, state["weights"])):
        p = group["base"].copy()
        n = group["normals"].copy()
        weights = np.array(values)
        active = np.flatnonzero(abs(weights) > 0.0001)
        if len(active):
            p += (weights[active] @ group["position_targets"][active]).reshape(-1, 3)
            n += (weights[active] @ group["normal_targets"][active]).reshape(-1, 3)
        transforms = world[group["meta"]["bones"]] @ group["bind"]
        hom = np.c_[p, np.ones(len(p))]
        outp = np.zeros_like(p)
        outn = np.zeros_like(n)
        if not len(group["meta"]["bones"]):
            frame = matrix([state["mesh_transforms"][group_index]])[0]
            outp = hom @ frame[:3].T
            outn = n @ frame[:3, :3].T
        for slot in range(group["joints"].shape[1]):
            ms = transforms[group["joints"][:, slot]]
            w = group["weights"][:, slot]
            outp += np.einsum("vab,vb->va", ms[:, :3], hom) * w[:, None]
            outn += np.einsum("vab,vb->va", ms[:, :3, :3], n) * w[:, None]
        positions.append(outp)
        normals.append(
            outn / np.maximum(np.linalg.norm(outn, axis=1, keepdims=True), 1e-30)
        )
    return np.concatenate(positions), np.concatenate(normals)


if mode == "fit":
    low = np.full(3, np.inf)
    high = np.full(3, -np.inf)
    for index, state in enumerate(job["samples"]):
        points, _ = evaluate(descs[0], state["models"][0])
        low = np.minimum(low, points.min(0))
        high = np.maximum(high, points.max(0))
    report = dict(
        source_sha256=job["descriptions"][0]["sha256"],
        model_global=job["descriptions"][0]["model_global"],
        position=low.tolist(),
        size=(high - low).tolist(),
        poses=len(job["samples"]),
        scope="Every vertex at every full-cycle render frame and view-still pose, using actual complete Actor Godot arrays/poses/weights/transforms, renderer morph cutoff and four/eight influence skin. Evaluated in float64 with a separate 30% camera margin.",
    )
    (out / "render-fit.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(report, indent=2))
    sys.exit(0)

if mode == "imported":
    # The editor may reorder vertices when morph count changes. Recover a
    # bijection from retained physical data instead of comparing array ordinals.
    processing = json.loads(
        pathlib.Path(inputs["preparation"]).read_text(encoding="utf-8")
    )
    maps = []
    candidate_offset = 0
    assert len(descs[0]) == len(descs[1]), "Imported surface count changed"
    for source, candidate in zip(descs[0], descs[1]):
        count = len(source["base"])
        assert count == len(candidate["base"])
        old_targets = source["meta"]["targets"]
        new_targets = candidate["meta"]["targets"]
        choices = {
            tuple(row["retained_target_indices"])
            for row in processing["inactive_targets"]["meshes"]
            if row["targets_before"] == old_targets
            and row["targets_after"] == new_targets
        }
        keep = list(next(iter(choices))) if choices else list(range(old_targets))
        assert (
            len(choices) <= 1 and len(keep) == new_targets
        ), "Ambiguous retained target mask for imported surface"

        def static_signature(group, index):
            return b"".join(
                group[field][index].tobytes()
                for field in ("base", "normals", "joints", "weights")
            )

        buckets = collections.defaultdict(list)
        for index in range(count):
            buckets[static_signature(candidate, index)].append(index)

        def motion_signature(group, index, indices):
            h = hashlib.sha256()
            for field in ("position_targets", "normal_targets"):
                values = group[field].reshape(group["meta"]["targets"], count, 3)
                h.update(values[indices, index].tobytes())
            return h.digest()

        mapping = []
        for index in range(count):
            bucket = buckets[static_signature(source, index)]
            assert bucket, "No imported vertex has identical retained static attributes"
            if len(bucket) > 1:
                signature = motion_signature(source, index, keep)
                candidates = [
                    i
                    for i in bucket
                    if motion_signature(candidate, i, list(range(new_targets)))
                    == signature
                ]
                assert (
                    candidates
                ), "Coincident imported vertices differ in retained corrective signatures"
                found = candidates[0]
            else:
                found = bucket[0]
            bucket.remove(found)
            mapping.append(found)
        assert not any(buckets.values())
        maps.extend(candidate_offset + np.asarray(mapping))
        candidate_offset += count
    reorder = np.asarray(maps, dtype=int)
    np.save(runtime / "candidate-vertex-bijection.npy", reorder)

results = []
for k, s in enumerate(job["samples"]):
    a, an = evaluate(descs[0], s["models"][0])
    b, bn = evaluate(descs[1], s["models"][1])
    b = b[reorder]
    bn = bn[reorder]
    error = np.linalg.norm(b - a, axis=1)
    angles = np.degrees(np.arccos(np.clip(np.einsum("vi,vi->v", an, bn), -1, 1)))
    r = {
        "label": s["label"],
        "max_surface_error": float(error.max()),
        "max_normal_degrees": float(angles.max()),
        "p99_normal_degrees": float(np.percentile(angles, 99)),
    }
    results.append(r)
    if k % 50 == 0:
        print(k, r, flush=True)
summary = {
    "samples": results,
    "maximum_position_error": max(r["max_surface_error"] for r in results),
    "maximum_normal_angle_degrees": max(r["max_normal_degrees"] for r in results),
    "worst_position": max(results, key=lambda r: r["max_surface_error"]),
    "worst_normal": max(results, key=lambda r: r["max_normal_degrees"]),
    "scope": "Actual imported Godot mesh arrays, native-library sampled poses and crossfades or mounted gait samples, renderer activation cutoff, linear blended skin; image rendering remains a separate check.",
}
(out / (mode + "-validation.json")).write_text(json.dumps(summary, indent=2))
print(json.dumps({k: v for k, v in summary.items() if k != "samples"}, indent=2))
summary.update(
    source_sha256=job["descriptions"][0]["sha256"],
    candidate_sha256=job["descriptions"][1]["sha256"],
    scope="Actual Godot mesh arrays, every native clip and directed crossfade pair, renderer morph activation cutoff, linear blended four/eight-influence skin. Pixel rendering remains a separate check.",
)
(out / (mode + "-validation.json")).write_text(
    json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n"
)
