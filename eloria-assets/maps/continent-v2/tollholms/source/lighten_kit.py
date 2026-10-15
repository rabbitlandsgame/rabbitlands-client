"""Derive The Tollholms' lighter kit pieces from their prepared heavy ones (LIGHTENED), for the north lawn.

The owner chose lighter vineyard rows (2026-10-03, "use lighter vineyard rows for the north lawn"): the village's
north chunk (10, 16) was triangle-bound at 448,208 of the 450 k per-96 m-chunk cap, and its twenty vineyard rows
(kit-vineyard-rows-1, 4,432 triangles each) were 88,640 of them. `kit-vineyard-rows-1-light` is that same prepared
row (the SHARED byte copy of sw_isle's, sha 53cd84fc...) with about half its triangles. No new model was generated:
the piece keeps the source's glTF document - its nodes, its one double-sided opaque material, sampler and the three
content-addressed textures (the albedo grade unchanged) - and only its one primitive's buffer is replaced:

1. hidden-triangle cull: every triangle is ray-cast from 4 sample points toward the game camera's range of
   directions (elevations 15, 20, 30, 45, 60, 75 and 80 degrees at 12 yaws, plus straight down; the camera's pitch
   runs -15..-80), the piece standing alone (a field's edge row, the conservative case); a triangle no ray escapes
   from is never seen and is dropped (629 of 4,432: the trunks' and canes' inner faces under the leaf clumps);
2. collapse: Blender's Decimate modifier (Collapse, ratio 0.5824, triangulate) on the culled mesh, imported with
   its vertices merged as the glTF importer merges them (3,803 -> 2,214 triangles), exported as glTF without
   images or tangents;
3. clamp: the vertices the collapse pushed outside the source's box (-4..4 x 0..1.6 x -2.5..2.5 m) are pulled back
   onto it, so the kit's bounds, plan rectangle and contact ring - what the editor and the village rules seat and
   overlap by - stay the source's (22 vertices, at most 0.19 m);
4. slivers: triangles with an edge longer than SLIVER_M are dropped (the source's longest edge is 1.53 m; the
   collapse leaves two 2.76 m wire slivers that read as streaks), and vertices no triangle uses are compacted away;
5. winding: the collapse folds triangles over (5.9 % of them came out with their winding against their vertex
   normals, against the source's 3.1 %), and the double-sided material shades such a triangle as a back face, dark;
   each one whose nearest culled source triangle agrees with its normals is turned back (review of 2026-10-03, D7).

Measured against the source before it was chosen (Blender EEVEE at the game camera, pitch -60, distance 26, FOV 50,
1440 x 900, a 3 x 3 field; work-output/continent-v2/vm-pass/reports/vine_understand): silhouette IoU 0.906-0.917,
coverage 0.945-0.959 and the mean vine colour within 1.6 levels over four views (play y0 / y90, pitch -15, a 12 m
close view); all 26 placed rows seat under the village rules (burial at most 0.050, floating at most 0.049).

`python lighten_kit.py --blender <blender.exe>` rebuilds every LIGHTENED piece (Blender 5.2.1 in the background;
the build is deterministic) and writes it to the territory's prototypes with `lighten-kit.json` (the SHA-256 of the
input and the output, the triangle counts and the parameters). `--check` needs no Blender: it confirms the input is
still the prepared heavy piece the record names, the committed piece is the recorded output, and the piece is a
drop-in (the source's material, images and box, UVs in range). `prepare_meshy_kit.py --check` records each
LIGHTENED piece from that record.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CLIENT = HERE.parents[4]
PROTOTYPES = CLIENT / "godot-client/world_authoring/regions/tollholms/assets/prototypes"
TEXTURES = PROTOTYPES.parent / "textures"
RECORD = HERE / "lighten-kit.json"

# name -> (prepared heavy piece, collapse ratio applied to the culled mesh)
LIGHTENED = {
    "vineyard-rows-1-light": ("vineyard-rows-1", 0.5824),
}
ELEVATIONS = (15, 20, 30, 45, 60, 75, 80)
YAWS = 12
SLIVER_M = 2.0

# Blender (background): phase "visibility" writes, per triangle in glTF order, how many camera directions see it;
# phase "collapse" decimates a culled GLB and exports it (geometry and material, no images, no tangents).
BLENDER_SCRIPT = r'''
import bpy, bmesh, sys, json, math
from mathutils import Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:]
phase, src = argv[0], argv[1]
bpy.ops.wm.read_factory_settings(use_empty=True)
if phase == "visibility":
    out, elevs, yaws = argv[2], [int(e) for e in argv[3].split(",")], int(argv[4])
    bpy.ops.import_scene.gltf(filepath=src, merge_vertices=False)
    ob = [o for o in bpy.context.scene.objects if o.type == "MESH"][0]
    mw = ob.matrix_world
    V = [mw @ v.co for v in ob.data.vertices]
    tris = [tuple(p.vertices) for p in ob.data.polygons]
    assert all(len(t) == 3 for t in tris)
    bvh = BVHTree.FromPolygons(V, tris, all_triangles=True)
    dirs = []
    for el in elevs:
        for k in range(yaws):
            yaw, e = math.radians(360.0 / yaws * k), math.radians(el)
            g = (math.sin(yaw) * math.cos(e), math.sin(e), math.cos(yaw) * math.cos(e))
            dirs.append(Vector((g[0], -g[2], g[1])).normalized())   # Godot (x, y, z) -> Blender (x, -z, y)
    dirs.append(Vector((0.0, 0.0, 1.0)))
    bary = ((1 / 3, 1 / 3, 1 / 3), (0.6, 0.2, 0.2), (0.2, 0.6, 0.2), (0.2, 0.2, 0.6))
    counts = []
    for a, b, c in tris:
        n = 0
        for d in dirs:
            for u, v, w in bary:
                p = V[a] * u + V[b] * v + V[c] * w
                if bvh.ray_cast(p + d * 2e-3, d, 60.0)[0] is None:
                    n += 1
                    break
        counts.append(n)
    cent = [[(V[a][0] + V[b][0] + V[c][0]) / 3, (V[a][2] + V[b][2] + V[c][2]) / 3, -(V[a][1] + V[b][1] + V[c][1]) / 3]
            for a, b, c in tris]
    json.dump({"visible_dirs": counts, "centroids": cent, "directions": len(dirs)}, open(out, "w"))
elif phase == "collapse":
    out, ratio = argv[2], float(argv[3])
    bpy.ops.import_scene.gltf(filepath=src, merge_vertices=True)
    ob = [o for o in bpy.context.scene.objects if o.type == "MESH"][0]
    mw = ob.matrix_world.copy()
    ob.parent = None
    ob.matrix_world = mw
    for o in list(bpy.context.scene.objects):
        if o.type == "EMPTY":
            bpy.data.objects.remove(o)
    m = ob.modifiers.new("d", "DECIMATE")
    m.decimate_type = "COLLAPSE"
    m.ratio = ratio
    m.use_collapse_triangulate = True
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    ob.modifiers.clear()
    ob.data = me
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.to_mesh(me)
    bm.free()
    for o in bpy.context.scene.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.export_scene.gltf(filepath=out, use_selection=True, export_format="GLB", export_image_format="NONE",
                              export_materials="EXPORT", export_tangents=False)
print("PHASE DONE", phase)
'''


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def split(payload: bytes) -> tuple[dict, bytes]:
    length = struct.unpack_from("<I", payload, 12)[0]
    document = json.loads(payload[20:20 + length])
    return document, payload[20 + length + 8:]


def accessor(document: dict, binary: bytes, index: int) -> np.ndarray:
    acc = document["accessors"][index]
    view = document["bufferViews"][acc["bufferView"]]
    width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[acc["type"]]
    kind = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}[acc["componentType"]]
    data = np.frombuffer(binary, kind, acc["count"] * width, view.get("byteOffset", 0) + acc.get("byteOffset", 0))
    return data.reshape(-1, width) if width > 1 else data


def primitive(document: dict, binary: bytes) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    prims = [p for mesh in document["meshes"] for p in mesh["primitives"]]
    if len(prims) != 1:
        raise ValueError(f"expected one primitive, found {len(prims)}")
    p = prims[0]
    return (accessor(document, binary, p["attributes"]["POSITION"]).astype(np.float32),
            accessor(document, binary, p["attributes"]["NORMAL"]).astype(np.float32),
            accessor(document, binary, p["attributes"]["TEXCOORD_0"]).astype(np.float32),
            accessor(document, binary, p["indices"]).astype(np.int64).reshape(-1, 3))


def with_buffer(document: dict, positions, normals, uvs, faces) -> bytes:
    """The GLB of `document` with its one primitive's buffer replaced (POSITION, NORMAL, TEXCOORD_0, indices)."""
    document = json.loads(json.dumps(document))
    small = len(positions) < 65536
    blobs = [positions.astype("<f4").tobytes(), normals.astype("<f4").tobytes(), uvs.astype("<f4").tobytes(),
             faces.reshape(-1).astype("<u2" if small else "<u4").tobytes()]
    views, body = [], bytearray()
    for k, blob in enumerate(blobs):
        views.append({"buffer": 0, "byteOffset": len(body), "byteLength": len(blob),
                      "target": 34963 if k == 3 else 34962})
        body.extend(blob)
        body.extend(b"\0" * (-len(body) % 4))
    document["bufferViews"] = views
    document["buffers"] = [{"byteLength": len(body)}]
    document["accessors"] = [
        {"bufferView": 0, "componentType": 5126, "count": len(positions), "type": "VEC3",
         "min": [float(v) for v in positions.min(0)], "max": [float(v) for v in positions.max(0)]},
        {"bufferView": 1, "componentType": 5126, "count": len(normals), "type": "VEC3"},
        {"bufferView": 2, "componentType": 5126, "count": len(uvs), "type": "VEC2"},
        {"bufferView": 3, "componentType": 5123 if small else 5125, "count": int(faces.size), "type": "SCALAR"}]
    p = document["meshes"][0]["primitives"][0]
    p["attributes"] = {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2}
    p["indices"] = 3
    encoded = json.dumps(document, separators=(",", ":")).encode("utf-8")
    encoded += b" " * (-len(encoded) % 4)
    return (b"glTF" + struct.pack("<II", 2, 12 + 8 + len(encoded) + 8 + len(body))
            + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
            + struct.pack("<II", len(body), 0x004E4942) + bytes(body))


def compact(positions, normals, uvs, faces):
    used = np.unique(faces)
    remap = np.full(len(positions), -1, np.int64)
    remap[used] = np.arange(len(used))
    return positions[used], normals[used], uvs[used], remap[faces]


def opposed(positions, normals, faces) -> np.ndarray:
    """Per triangle: its winding's normal points against the sum of its vertex normals."""
    winding = np.cross(positions[faces[:, 1]] - positions[faces[:, 0]], positions[faces[:, 2]] - positions[faces[:, 0]])
    return np.einsum("ij,ij->i", winding, normals[faces].sum(axis=1)) < 0


def longest_edges(positions, faces) -> np.ndarray:
    return np.stack([np.linalg.norm(positions[faces[:, a]] - positions[faces[:, b]], axis=1)
                     for a, b in ((0, 1), (1, 2), (2, 0))], 1).max(1)


def blender(exe: str, phase: str, *args: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "lighten_blender.py"
        script.write_text(BLENDER_SCRIPT, encoding="utf-8")
        run = subprocess.run([exe, "-b", "--factory-startup", "--python", str(script), "--", phase, *args],
                             capture_output=True, text=True, encoding="utf-8", errors="replace")
    if run.returncode != 0 or f"PHASE DONE {phase}" not in run.stdout:
        raise RuntimeError(f"Blender {phase} failed ({run.returncode}):\n{run.stdout[-3000:]}\n{run.stderr[-3000:]}")


def blender_version(exe: str) -> str:
    out = subprocess.run([exe, "-b", "--factory-startup", "--version"], capture_output=True, text=True,
                         encoding="utf-8", errors="replace").stdout
    return out.strip().splitlines()[0] if out.strip() else "unknown"


def build(exe: str, name: str, work: Path) -> tuple[bytes, dict]:
    """A LIGHTENED piece built from its prepared heavy piece: (GLB bytes, what was measured)."""
    base, ratio = LIGHTENED[name]
    source = PROTOTYPES / f"kit-{base}.glb"
    payload = source.read_bytes()
    document, binary = split(payload)
    P, N, UV, F = primitive(document, binary)
    # the textures sit beside the work folder as they do beside the prototypes, so Blender resolves the material
    (work / "textures").mkdir(parents=True, exist_ok=True)
    for image in document.get("images", []):
        file = image["uri"].rsplit("/", 1)[-1]
        shutil.copyfile(TEXTURES / file, work / "textures" / file)
    (work / "glb").mkdir(exist_ok=True)
    # 1. the hidden-triangle cull
    visibility = work / f"{name}-visibility.json"
    blender(exe, "visibility", str(source), str(visibility), ",".join(map(str, ELEVATIONS)), str(YAWS))
    seen = json.loads(visibility.read_text(encoding="utf-8"))
    counts = np.asarray(seen["visible_dirs"])
    centroids = np.asarray(seen["centroids"])
    if len(counts) != len(F) or not np.allclose(centroids, P[F].mean(axis=1), atol=1e-4):
        raise ValueError(f"{name}: Blender's triangles are not the glTF's, in order")
    keep = counts >= 1
    culled = compact(P, N, UV, F[keep])
    culled_path = work / "glb" / f"{name}-culled.glb"
    culled_path.write_bytes(with_buffer(document, *culled))
    # 2. the collapse
    collapsed_path = work / "glb" / f"{name}-collapsed.glb"
    blender(exe, "collapse", str(culled_path), str(collapsed_path), repr(ratio))
    cdoc, cbin = split(collapsed_path.read_bytes())
    node = [n for n in cdoc["nodes"] if "mesh" in n][0]
    if any(k in node for k in ("matrix", "rotation", "scale")) or node.get("translation", [0, 0, 0]) != [0, 0, 0]:
        raise ValueError(f"{name}: the collapsed mesh carries a node transform")
    P2, N2, UV2, F2 = primitive(cdoc, cbin)
    collapsed_tris = len(F2)
    # 3. the clamp onto the source's box
    low, high = P.min(0), P.max(0)
    outside = int(((P2 < low - 1e-5) | (P2 > high + 1e-5)).any(axis=1).sum())
    overshoot = float(np.abs(np.clip(P2, low, high) - P2).max()) if len(P2) else 0.0
    P2 = np.clip(P2, low, high).astype(np.float32)
    # 4. the slivers
    long = longest_edges(P2, F2)
    slivers = long > SLIVER_M
    P3, N3, UV3, F3 = compact(P2, N2, UV2, F2[~slivers])
    # 5. the winding: the collapse folds some triangles over, so their winding opposes their (interpolated) vertex
    # normals and a double-sided material shades them as back faces, dark; a triangle whose nearest culled source
    # triangle agrees with its own normals is turned back (the source's own opposed triangles are kept as they are)
    src_opposed = opposed(culled[0], culled[1], culled[3])
    src_centres = culled[0][culled[3]].mean(axis=1)
    mine = opposed(P3, N3, F3)
    turn = np.zeros(len(F3), bool)
    for i in np.nonzero(mine)[0]:
        j = int(np.argmin(((src_centres - P3[F3[i]].mean(axis=0)) ** 2).sum(axis=1)))
        turn[i] = not src_opposed[j]
    F3 = np.where(turn[:, None], F3[:, [0, 2, 1]], F3)
    # the drop-in: the source's document, its mesh node and mesh named for the piece and the derivation recorded
    light = json.loads(json.dumps(document))
    mesh_node = [n for n in light["nodes"] if "mesh" in n][0]
    mesh_node["name"] = "kit-" + name
    light["meshes"][mesh_node["mesh"]]["name"] = "kit-" + name
    mesh_node["extras"] = {"eloria": {
        "kit": "kit-" + name, "variant_of": f"kit-{base}", "operation": "lighten",
        "notes": (f"kit-{base} with {len(F3):,} of its {len(F):,} triangles: never-seen triangles culled for the "
                  f"game camera, Blender Decimate collapse {ratio}, clamped to the source's box, slivers over "
                  f"{SLIVER_M} m dropped, folded triangles turned back; same material, textures, size and origin")}}
    light["asset"] = {"version": "2.0", "generator": "Eloria tollholms lighten_kit"}
    out = with_buffer(light, P3, N3, UV3, F3)
    e1, e2 = UV3[F3[:, 1]] - UV3[F3[:, 0]], UV3[F3[:, 2]] - UV3[F3[:, 0]]
    uv_area = 0.5 * np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0])
    facts = {
        "variant_of": base, "operation": "lighten",
        "input": sha(payload), "output": sha(out),
        "triangles": {"source": int(len(F)), "culled": int(keep.sum()), "collapsed": int(collapsed_tris),
                      "final": int(len(F3))},
        "vertices": {"source": int(len(P)), "final": int(len(P3))},
        "cull": {"elevations_deg": list(ELEVATIONS), "yaws": YAWS, "plus_top": True, "samples_per_triangle": 4,
                 "neighbours": "none (a field's edge row)", "dropped": int((~keep).sum())},
        "collapse": {"ratio": ratio, "triangulate": True, "import_merge_vertices": True,
                     "intermediate_sha256": sha(collapsed_path.read_bytes())},
        "clamp": {"vertices_outside_source_box": outside, "largest_overshoot_m": round(overshoot, 4)},
        "slivers": {"longest_edge_over_m": SLIVER_M, "dropped": int(slivers.sum()),
                    "dropped_longest_m": [round(float(v), 3) for v in sorted(long[slivers])],
                    "longest_edge_kept_m": round(float(longest_edges(P3, F3).max()), 3),
                    "source_longest_edge_m": round(float(longest_edges(P, F).max()), 3)},
        "winding": {"opposed_after_collapse": int(mine.sum()), "turned": int(turn.sum()),
                    "opposed_share": round(float(opposed(P3, N3, F3).mean()), 4),
                    "source_opposed_share": round(float(opposed(P, N, F).mean()), 4)},
        "bounds_m": [[round(float(v), 4) for v in P3.min(0)], [round(float(v), 4) for v in P3.max(0)]],
        "source_bounds_m": [[round(float(v), 4) for v in low], [round(float(v), 4) for v in high]],
        "uv_range": [[round(float(v), 4) for v in UV3.min(0)], [round(float(v), 4) for v in UV3.max(0)]],
        "uv_zero_area_triangles": int((uv_area < 1e-9).sum()),
        "mesh_bytes": len(split(out)[1]), "source_mesh_bytes": len(binary),
        "glb_bytes": len(out), "source_glb_bytes": len(payload),
    }
    return out, facts


def check_dropin(name: str, payload: bytes) -> list[str]:
    """What keeps the committed piece from being a drop-in for its heavy one (empty when it is one)."""
    base, _ = LIGHTENED[name]
    problems = []
    heavy, hbin = split((PROTOTYPES / f"kit-{base}.glb").read_bytes())
    light, lbin = split(payload)
    for key in ("materials", "textures", "images", "samplers", "scene", "scenes"):
        if light.get(key) != heavy.get(key):
            problems.append(f"{key} differ from kit-{base}'s")
    P, _, UV, F = primitive(heavy, hbin)
    P2, N2, UV2, F2 = primitive(light, lbin)
    if not (np.allclose(P2.min(0), P.min(0), atol=1e-4) and np.allclose(P2.max(0), P.max(0), atol=1e-4)):
        problems.append(f"box {P2.min(0)}..{P2.max(0)} is not the source's {P.min(0)}..{P.max(0)}")
    if UV2.min() < -1e-4 or UV2.max() > 1 + 1e-4:
        problems.append("UVs outside 0..1")
    if not np.allclose(np.linalg.norm(N2, axis=1), 1.0, atol=1e-3):
        problems.append("normals are not unit length")
    if F2.max() >= len(P2):
        problems.append("indices out of range")
    if float(longest_edges(P2, F2).max()) > SLIVER_M:
        problems.append("a sliver is left")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--blender", help="blender.exe (5.2.1) to rebuild the LIGHTENED pieces")
    parser.add_argument("--check", action="store_true", help="verify the committed pieces against the record")
    parser.add_argument("--work", type=Path, help="keep the intermediate files here (default: a temporary folder)")
    args = parser.parse_args()
    if args.check:
        record = json.loads(RECORD.read_text(encoding="utf-8")) if RECORD.exists() else {}
        stale = []
        for name, (base, _) in sorted(LIGHTENED.items()):
            entry = record.get("models", {}).get(name)
            target = PROTOTYPES / f"kit-{name}.glb"
            if entry is None or not target.exists():
                stale.append(f"{name}: not built")
                continue
            if sha((PROTOTYPES / f"kit-{base}.glb").read_bytes()) != entry["input"]:
                stale.append(f"{name}: kit-{base} is no longer the recorded input")
            payload = target.read_bytes()
            if sha(payload) != entry["output"]:
                stale.append(f"{name}: the committed piece is not the recorded output")
            stale += [f"{name}: {p}" for p in check_dropin(name, payload)]
        if stale:
            print("stale: " + "; ".join(stale))
            return 1
        print(f"{len(LIGHTENED)} lightened piece(s) match the record")
        return 0
    if not args.blender:
        parser.error("--blender is required to build (or pass --check)")
    record = {"schema": "eloria-lightened-kit-v1", "tool": "lighten_kit.py", "blender": blender_version(args.blender),
              "models": {}}
    for name in sorted(LIGHTENED):
        if args.work:
            args.work.mkdir(parents=True, exist_ok=True)
            payload, facts = build(args.blender, name, args.work)
        else:
            with tempfile.TemporaryDirectory() as tmp:
                payload, facts = build(args.blender, name, Path(tmp))
        problems = check_dropin(name, payload)
        if problems:
            raise ValueError(f"{name}: " + "; ".join(problems))
        target = PROTOTYPES / f"kit-{name}.glb"
        if not target.exists() or target.read_bytes() != payload:
            target.write_bytes(payload)
        record["models"][name] = facts
        t = facts["triangles"]
        print(f"{target.name}: {t['source']} -> {t['culled']} -> {t['collapsed']} -> {t['final']} triangles, "
              f"{len(payload) // 1024} KB, sha {facts['output'][:12]}", flush=True)
    RECORD.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
