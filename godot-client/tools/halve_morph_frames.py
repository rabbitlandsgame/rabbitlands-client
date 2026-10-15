#!/usr/bin/env python3
"""Store every other morph-target frame of baked vertex animations.

Added 2026-09-16 for Eloria Client.

    python tools/halve_morph_frames.py --dry-run
    python tools/halve_morph_frames.py --archive ../../archive/morph-frames-2026-09-16

38 creatures animate Fly and Sword_Attack with one morph target per frame: a
weights track whose keyframe k drives target k at 1.0, LINEAR interpolation.
Keeping the even keyframes (and the last) and the targets they drive halves
that data; at a dropped keyframe time Godot's interpolation lands halfway
between the neighbouring kept targets. The bone tracks are untouched.

Godot 4.7.2 imports the result (checked on tengu with GLTFDocument: blend
shapes and blend shape tracks evaluated by Godot matched this tool's own
reconstruction). The 16-bit KHR_mesh_quantization step was tried and not
adopted: Godot refuses files that declare it as the spec requires.

For each clip the tool reports the vertex error at every original keyframe
time, in millimetres at a 1.7 m body height, so the loss is known per clip.
A GLB is skipped unless every weights track has the expected shape (LINEAR,
at most one target per keyframe, at weight 1.0, each target driven by one
keyframe of one clip).

Freed accessors are compacted with strip_unused_glb_data.strip, originals are
archived with a manifest, and the sha256/bytes build records follow the files.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from shrink_actor_textures import (CLIENT, REPO, read_glb, records_from_manifest, repo_path, sha256,
                                   tracked, update_records, write_glb)
from strip_unused_glb_data import strip

COMPONENT = {5126: np.float32, 5123: np.uint16, 5121: np.uint8, 5125: np.uint32, 5122: np.int16, 5120: np.int8}
WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
BODY_MM = 1700.0
MARKER = "eloriaMorphFramesHalved"
CLIENT_DATA = CLIENT / "data" / "actors"


def read(document: dict, binary: bytes, index: int) -> np.ndarray:
    accessor = document["accessors"][index]
    view = document["bufferViews"][accessor["bufferView"]]
    width = WIDTH[accessor["type"]]
    dtype = np.dtype(COMPONENT[accessor["componentType"]])
    if view.get("byteStride", dtype.itemsize * width) != dtype.itemsize * width:
        raise ValueError("interleaved accessors are not handled")
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    values = np.frombuffer(binary, dtype, count=accessor["count"] * width, offset=start)
    return values.reshape(accessor["count"], width).astype(np.float64)


class Appender:
    """Add float accessors at the end of the binary chunk."""

    def __init__(self, document: dict, binary: bytes):
        self.document, self.binary = document, bytearray(binary)

    def add(self, values: np.ndarray, kind: str, bounds: bool) -> int:
        data = np.ascontiguousarray(values, np.float32)
        self.binary.extend(b"\0" * ((-len(self.binary)) % 4))
        self.document["bufferViews"].append({"buffer": 0, "byteOffset": len(self.binary), "byteLength": data.nbytes})
        self.binary.extend(data.tobytes())
        accessor = {"bufferView": len(self.document["bufferViews"]) - 1, "componentType": 5126,
                    "count": len(data), "type": kind}
        if bounds:
            flat = data.reshape(len(data), -1)
            accessor.update(min=flat.min(0).astype(float).tolist(), max=flat.max(0).astype(float).tolist())
        self.document["accessors"].append(accessor)
        self.document["buffers"][0]["byteLength"] = len(self.binary)
        return len(self.document["accessors"]) - 1


def plan(document: dict, binary: bytes) -> dict | None:
    """Work out which keyframes and targets survive, or None if the GLB has none to halve."""
    meshes = [i for i, m in enumerate(document.get("meshes", [])) if any(p.get("targets") for p in m["primitives"])]
    if not meshes or document.get("asset", {}).get("extras", {}).get(MARKER):
        return None
    if len(meshes) > 1:
        raise ValueError("more than one morph mesh")
    mesh_index = meshes[0]
    mesh = document["meshes"][mesh_index]
    counts = {len(p.get("targets", [])) for p in mesh["primitives"]}
    if len(counts) != 1:
        raise ValueError("primitives disagree on target count")
    target_count = counts.pop()
    nodes = {i for i, node in enumerate(document["nodes"]) if node.get("mesh") == mesh_index}

    tracks = []  # (animation index, sampler index, times, weights, kept keys)
    drivers: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for ai, animation in enumerate(document.get("animations", [])):
        for channel in animation["channels"]:
            if channel["target"]["path"] != "weights":
                continue
            if channel["target"].get("node") not in nodes:
                raise ValueError("weights channel on a node without the morph mesh")
            sampler = animation["samplers"][channel["sampler"]]
            if sampler.get("interpolation", "LINEAR") != "LINEAR":
                raise ValueError("non-LINEAR weights track")
            times = read(document, binary, sampler["input"])[:, 0]
            weights = read(document, binary, sampler["output"]).reshape(len(times), target_count)
            active = weights > 1e-6
            if (active.sum(1) > 1).any() or not np.allclose(weights[active], 1.0):
                raise ValueError("a keyframe blends targets")
            keys = list(range(len(times)))
            if active.any() and len(times) > 2:
                keys = list(range(0, len(times), 2))
                if keys[-1] != len(times) - 1:
                    keys.append(len(times) - 1)
            for k in range(len(times)):
                for t in np.nonzero(active[k])[0]:
                    drivers[int(t)].append((len(tracks), k))
            tracks.append((ai, channel["sampler"], times, weights, keys))
    if any(len(v) > 1 for v in drivers.values()):
        raise ValueError("a target is driven by more than one keyframe")
    kept = [t for t in range(target_count)
            if t not in drivers or drivers[t][0][1] in tracks[drivers[t][0][0]][4]]
    if len(kept) == target_count:
        return None
    return {"mesh": mesh_index, "targets": target_count, "kept": kept, "tracks": tracks}


def apply(document: dict, binary: bytes, layout: dict) -> tuple[dict, bytes]:
    document = json.loads(json.dumps(document))
    # Halving is not idempotent by construction (a halved clip halves again),
    # so a done file says so.
    document.setdefault("asset", {}).setdefault("extras", {})[MARKER] = True
    out = Appender(document, binary)
    kept = layout["kept"]
    mesh = document["meshes"][layout["mesh"]]
    for primitive in mesh["primitives"]:
        primitive["targets"] = [primitive["targets"][t] for t in kept]
    if "weights" in mesh:
        mesh["weights"] = [mesh["weights"][t] for t in kept]
    names = mesh.get("extras", {}).get("targetNames")
    if names:
        mesh["extras"]["targetNames"] = [names[t] for t in kept]
    for ai, si, times, weights, keys in layout["tracks"]:
        sampler = document["animations"][ai]["samplers"][si]
        sampler["input"] = out.add(times[keys].reshape(-1, 1), "SCALAR", bounds=True)
        sampler["output"] = out.add(weights[keys][:, kept].reshape(-1, 1), "SCALAR", bounds=False)
    stripped = strip(document, bytes(out.binary))
    return stripped if stripped else (document, bytes(out.binary))


def displacement(document: dict, binary: bytes, primitive: dict, animation: str, time: float,
                 cache: dict) -> np.ndarray:
    anim = next(a for a in document["animations"] if a["name"] == animation)
    channel = next(c for c in anim["channels"] if c["target"]["path"] == "weights")
    sampler = anim["samplers"][channel["sampler"]]
    key = ("anim", animation)
    if key not in cache:
        times = read(document, binary, sampler["input"])[:, 0]
        cache[key] = (times, read(document, binary, sampler["output"]).reshape(len(times), -1))
    times, weights = cache[key]
    if ("deltas", id(primitive)) not in cache:
        cache[("deltas", id(primitive))] = np.stack([read(document, binary, t["POSITION"])
                                                     for t in primitive["targets"]])
    deltas = cache[("deltas", id(primitive))]
    w = np.array([np.interp(time, times, weights[:, t]) for t in range(weights.shape[1])])
    active = np.nonzero(np.abs(w) > 1e-9)[0]
    return np.einsum("t,tvc->vc", w[active], deltas[active])


def clip_errors(before: tuple[dict, bytes], after: tuple[dict, bytes], layout: dict) -> dict[str, dict]:
    doc_a, bin_a = before
    doc_b, bin_b = after
    report = {}
    cache_a, cache_b = {}, {}
    prims_a = doc_a["meshes"][layout["mesh"]]["primitives"]
    prims_b = doc_b["meshes"][layout["mesh"]]["primitives"]
    height = max(np.ptp(read(doc_a, bin_a, p["attributes"]["POSITION"])[:, 1]) for p in prims_a) or 1.0
    for ai, si, times, weights, keys in layout["tracks"]:
        if len(keys) == len(times):
            continue
        name = doc_a["animations"][ai]["name"]
        errors = []
        for time in times:
            for pa, pb in zip(prims_a, prims_b):
                a = displacement(doc_a, bin_a, pa, name, time, cache_a)
                b = displacement(doc_b, bin_b, pb, name, time, cache_b)
                errors.append(np.linalg.norm(a - b, axis=1))
        e = np.concatenate(errors) / height * BODY_MM
        report[name] = {"fps": round(float((len(times) - 1) / (times[-1] - times[0])), 1),
                        "keys": [len(times), len(keys)], "p95": float(np.percentile(e, 95)),
                        "p99": float(np.percentile(e, 99)), "max": float(e.max())}
    return report


def update_target_counts(report: dict) -> list[str]:
    """basic_creature_expansion.json records each model's morph target count."""
    path = CLIENT_DATA / "basic_creature_expansion.json"
    text = path.read_bytes().decode("utf-8")
    by_sha = {}
    for p, entry in report.items():
        document, _ = read_glb(REPO / p)
        # The record counts targets summed over primitives (pelican, rooster: 9 each).
        primitives = sum(1 for m in document["meshes"] for prim in m["primitives"] if prim.get("targets"))
        old, new = entry["targets"]
        by_sha[sha256((REPO / p).read_bytes())] = (old * primitives, new * primitives)

    def fix(match):
        block = match.group(0)
        for sha, (old, new) in by_sha.items():
            if sha in block:
                return re.sub(rf'("morph_targets"\s*:\s*){old}\b', rf"\g<1>{new}", block)
        return block

    new_text = re.sub(r"\{[^{}]*\}", fix, text)
    if new_text == text:
        return []
    path.write_bytes(new_text.encode("utf-8"))
    return [repo_path(path)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", type=Path, help="write the per-clip error report as JSON")
    options = parser.parse_args()
    if not options.dry_run and not options.archive:
        parser.error("--archive is required unless --dry-run")

    changes, report, skipped = [], {}, {}
    for path in tracked("godot-client/assets/actors/*.glb", "godot-client/assets/actors/**/*.glb"):
        document, binary = read_glb(path)
        try:
            layout = plan(document, binary)
        except ValueError as error:
            skipped[repo_path(path)] = str(error)
            continue
        if not layout:
            continue
        new_document, new_binary = apply(document, binary, layout)
        data = write_glb(new_document, new_binary)
        original = path.read_bytes()
        report[repo_path(path)] = {"bytes": [len(original), len(data)],
                                   "targets": [layout["targets"], len(layout["kept"])],
                                   "clips": clip_errors((document, binary), (new_document, new_binary), layout)}
        changes.append((path, original, data))

    for path, entry in sorted(report.items(), key=lambda kv: -max((c["max"] for c in kv[1]["clips"].values()), default=0)):
        b0, b1 = entry["bytes"]
        clips = "; ".join(f"{n} {c['fps']:.0f}->{c['fps'] / 2:.0f} fps p95 {c['p95']:.1f} max {c['max']:.0f} mm"
                          for n, c in entry["clips"].items())
        print(f"{Path(path).name:26s} {b0 / 1e6:6.1f} -> {b1 / 1e6:5.1f} MB  {clips}")
    for path, reason in skipped.items():
        print(f"SKIPPED {path}: {reason}")
    before = sum(len(o) for _, o, _ in changes)
    after = sum(len(d) for _, _, d in changes)
    print(f"{len(changes)} GLBs: {before / 1e6:.1f} MB -> {after / 1e6:.1f} MB")
    if options.report:
        options.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if options.dry_run or not changes:
        return 0

    archive = options.archive.resolve()
    manifest_path = archive / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    earlier = {p: (e.get("newSha256"), e.get("newBytes")) for p, e in manifest.items()}
    for path, original, _ in changes:
        target = archive / repo_path(path)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        if target.read_bytes() != original and repo_path(path) not in manifest:
            raise SystemExit(f"archive copy of {repo_path(path)} does not match the file being replaced")
    (archive / "clip-errors.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for path, original, data in changes:
        path.write_bytes(data)
        entry = manifest.setdefault(repo_path(path), {"sha256": sha256(original), "bytes": len(original)})
        entry.update({"newSha256": sha256(data), "newBytes": len(data)})
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    updated = update_records(*records_from_manifest(manifest, earlier))
    updated += update_target_counts(report)
    print(f"updated build records in {len(updated)} files")
    for path in updated:
        print("  " + path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
