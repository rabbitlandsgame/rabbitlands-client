"""Replay nine reviewed inland sink repairs and a Saltsound hillside approach.

The frozen group base remains immutable. Repairs are ordinary sparse scene
sculpts, with decorative asset roots moved by the same triangle-sampled delta.
The hillside's narrow imported ledge is feathered into its gentle surroundings.
No shoreline, shared authority vertex, path, water, or gameplay marker is edited.
One content-table gecko spawn moves one metre onto a clear approach ring.
A later reviewed earthwork may re-grade part of a repair (SUPERSEDED); its
corridor then keeps the earthwork's sculpt.

    python godot-client/tools/repair_continent_v2_pits.py --check
    python godot-client/tools/repair_continent_v2_pits.py --apply --report FILE
"""
from __future__ import annotations

import argparse
import hashlib
import heapq
import json
from pathlib import Path
import re

import numpy as np
from scipy import ndimage, sparse
from scipy.sparse.linalg import spsolve

import continent_v2_territories as T

GROUP = T.CHECKOUT / "eloria-assets/maps/continent-v2/_continent_v2/group-terrain"
BASE_SHA = "176b536762632e57bc40a1298f9a6ccf304a2c27bd420ec9e0f7191314ed69ec"
# Reviewed closed inland tears, continent metres; channels and coastal cliffs
# from the broader audit are deliberately excluded.
SITES = {
    "warrenmead": [(747, 7261)],
    "twinbrook": [(1225, 7037), (1115, 6997), (961, 6893), (937, 6989)],
    "landfall": [(1247, 7199), (1199, 7181)],
    "boarsend": [(1419, 7967), (1205, 7963)],
}
HILL_REPAIR = {
    "region": "saltsound", "center": [2013, 6474], "radii": [25, 40],
    "sigmaCells": 2, "featherFraction": .45,
    "coastMinimumMetres": 2, "coastFeatherMetres": 3,
}
SPAWN_RELOCATION = {
    "region": "landfall", "id": "sw-spawn-0176",
    "beforeLocal": [87.5, -179.5], "afterLocal": [87.5, -178.5],
}
REPAIRED_REGIONS = set(SITES) | {HILL_REPAIR["region"]}
# Later reviewed earthworks over part of a repair, continent metres: vertices within reachMetres of the line carry
# the earthwork's sculpt instead of the repair's. Owner 2026-10-21: road R29-3 runs down into the gully east of
# Landfall's castle, where the (1247, 7199) repair had filled its graded corridor; the corridor is graded to the
# road's own ribbon again.
SUPERSEDED = {
    "landfall": [{"name": "R29-3 gully road", "reachMetres": 10,
                  "line": [(1261.5, 7157.8), (1268.5, 7162.1), (1276.9, 7169.0), (1282.3, 7173.8), (1288.1, 7179.1)]}],
}
FIRST = np.array([299, 6163])
SHAPE = (1259, 1446)
BUFFER_CELLS = 6


def superseded(t) -> np.ndarray:
    """The territory's vertices a later earthwork re-grades (SUPERSEDED), on its own grid."""
    xs, zs = t.vertex_xz()
    gx, gz = np.meshgrid(xs, zs)
    out = np.zeros(gx.shape, bool)
    for work in SUPERSEDED.get(t.id, []):
        line = np.asarray(work["line"], float)
        for (x0, z0), (x1, z1) in zip(line, line[1:]):
            dx, dz = x1 - x0, z1 - z0
            tt = np.clip(((gx - x0) * dx + (gz - z0) * dz) / (dx * dx + dz * dz), 0, 1)
            out |= np.hypot(gx - x0 - tt * dx, gz - z0 - tt * dz) <= work["reachMetres"]
    return out


def _overlap(lattice):
    """(v1 slices, lattice slices) of the reviewed v1 grid inside the territories' current lattice."""
    dc, dr = ((FIRST - lattice.first) / T.CELL).astype(int)
    r0, c0 = max(0, -dr), max(0, -dc)
    r1, c1 = min(SHAPE[0], lattice.height - dr), min(SHAPE[1], lattice.width - dc)
    return (slice(r0, r1), slice(c0, c1)), (slice(r0 + dr, r1 + dr), slice(c0 + dc, c1 + dc))


def to_lattice(values: np.ndarray, lattice, fill) -> np.ndarray:
    """A v1-grid array placed on the current lattice (a later ground extends the grid; v1 stays the reference)."""
    out = np.full((lattice.height, lattice.width), fill, values.dtype)
    v1, here = _overlap(lattice)
    out[here] = values[v1]
    return out


def from_lattice(values: np.ndarray, lattice, fill) -> np.ndarray:
    out = np.full(SHAPE, fill, values.dtype)
    v1, here = _overlap(lattice)
    out[v1] = values[here]
    return out


def lattice_base(territories, lattice) -> np.ndarray:
    """The group base the current crops agree on, on their lattice (NaN where no crop reaches)."""
    out = np.full((lattice.height, lattice.width), np.nan, np.float32)
    for t in territories:
        window = lattice.window(t)
        out[window] = np.where(np.isnan(out[window]), t.heights, out[window])
    return out


def fill_sinks(heights: np.ndarray) -> np.ndarray:
    """Eight-neighbour priority flood to the lowest escaping rim, not a blur.

    This identifies closed depressions without confusing an open valley or sea
    cliff with a hole. A filled field is for diagnosis only, never publication.
    """
    if heights.ndim != 2 or min(heights.shape) < 2 or not np.isfinite(heights).all():
        raise ValueError("expected a finite two-dimensional terrain grid")
    rows, cols = heights.shape
    result = heights.copy()
    seen = np.zeros(heights.shape, bool)
    heap = []
    boundary = [(r, c) for r in (0, rows - 1) for c in range(cols)]
    boundary += [(r, c) for c in (0, cols - 1) for r in range(1, rows - 1)]
    for r, c in boundary:
        seen[r, c] = True
        heap.append((float(heights[r, c]), r, c))
    heapq.heapify(heap)
    while heap:
        height, row, col = heapq.heappop(heap)
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1),
                       (-1, -1), (-1, 1), (1, -1), (1, 1)):
            r, c = row + dr, col + dc
            if 0 <= r < rows and 0 <= c < cols and not seen[r, c]:
                seen[r, c] = True
                value = max(height, float(heights[r, c]))
                result[r, c] = value
                heapq.heappush(heap, (value, r, c))
    return result


def interpolate(heights: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Harmonic interpolation from the unedited perimeter; preserve slopes.

    Solving all selected footprints together also handles overlapping buffers
    without an order-dependent seam. Vertices outside the mask stay byte exact.
    """
    if mask.shape != heights.shape or mask[0].any() or mask[-1].any() or \
            mask[:, 0].any() or mask[:, -1].any():
        raise ValueError("repair footprint must have an unedited outer boundary")
    rr, cc = np.where(mask)
    result = heights.copy()
    if not len(rr):
        return result
    lookup = np.full(heights.shape, -1, np.int64)
    lookup[mask] = np.arange(len(rr))
    rows, cols, values = list(range(len(rr))), list(range(len(rr))), [4.] * len(rr)
    rhs = np.zeros(len(rr))
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        neighbours = lookup[rr + dr, cc + dc]
        inside = neighbours >= 0
        rows.extend(np.flatnonzero(inside))
        cols.extend(neighbours[inside])
        values.extend([-1.] * int(inside.sum()))
        rhs[~inside] += heights[rr[~inside] + dr, cc[~inside] + dc]
    matrix = sparse.csr_matrix((values, (rows, cols)), shape=(len(rr), len(rr)))
    result[mask] = spsolve(matrix, rhs).astype(heights.dtype)
    return result


def sample(heights: np.ndarray, x: float, z: float) -> float:
    """Same two-triangle interpolation as Terrain.height_at_local."""
    fx, fz = (np.array([x, z]) - FIRST) / T.CELL
    c, r = int(np.floor(fx)), int(np.floor(fz))
    if not (0 <= r < heights.shape[0] - 1 and 0 <= c < heights.shape[1] - 1):
        return 0.
    tx, tz = fx - c, fz - r
    h00, h10 = heights[r, c:c + 2]
    h01, h11 = heights[r + 1, c:c + 2]
    if tx + tz <= 1:
        return float(h00 + (h10 - h00) * tx + (h01 - h00) * tz)
    return float(h11 + (h01 - h11) * (1 - tx) + (h10 - h11) * (1 - tz))


def repair_field():
    blob = (GROUP / "base-heights.f32le").read_bytes()
    if hashlib.sha256(blob).hexdigest() != BASE_SHA:
        raise ValueError("frozen terrain changed; review the sites against its new base")
    base = np.frombuffer(blob, "<f4").reshape(SHAPE)
    flooded = fill_sinks(base)
    labels, _ = ndimage.label(flooded - base > .1, np.ones((3, 3)))
    mask = np.zeros(base.shape, bool)
    sites = []
    for region, points in SITES.items():
        for x, z in points:
            col, row = ((np.array([x, z]) - FIRST) // 2).astype(int)
            label = labels[row, col]
            if not label:
                raise ValueError(f"reviewed sink no longer exists: {region} {x},{z}")
            basin = labels == label
            if basin.sum() > 1000 or base[basin].min() <= 10:
                raise ValueError("reviewed footprint reaches a large basin or shoreline")
            mask |= basin
            sites.append({"region": region, "continent": [x, z],
                          "basinVertices": int(basin.sum()),
                          "depthBeforeMetres": float((flooded - base)[basin].max())})
    territories = T.load_territories()
    lattice = T.Lattice.of(territories)
    shared = from_lattice(sum(T.authority(t, lattice).astype(np.uint8) for t in territories) > 1, lattice, False)
    if np.any(mask & shared):
        raise ValueError("a reviewed basin reaches shared terrain authority")
    # The outer smoothing buffer may approach a map seam. Keep that seam as
    # part of the fixed interpolation perimeter, just like the untouched hills.
    mask = ndimage.binary_dilation(mask, iterations=BUFFER_CELLS) & ~shared
    fixed = interpolate(base, mask)
    x = FIRST[0] + T.CELL * np.arange(SHAPE[1]); z = FIRST[1] + T.CELL * np.arange(SHAPE[0])
    hill = HILL_REPAIR
    radius = np.sqrt(((x[None, :] - hill["center"][0]) / hill["radii"][0]) ** 2 +
                     ((z[:, None] - hill["center"][1]) / hill["radii"][1]) ** 2)
    weight = np.clip((1 - radius) / hill["featherFraction"], 0, 1)
    weight = weight * weight * (3 - 2 * weight)
    coast = np.clip((base - hill["coastMinimumMetres"]) / hill["coastFeatherMetres"], 0, 1)
    weight *= coast * coast * (3 - 2 * coast)
    weight[shared] = 0
    hill_mask = weight > 0
    smooth = ndimage.gaussian_filter(base, sigma=hill["sigmaCells"])
    fixed[hill_mask] = (base + (smooth - base) * weight)[hill_mask]
    mask |= hill_mask
    # a later ground (group-terrain v2) must equal v1 wherever a repair or its smoothing reads (its exclusions)
    current = from_lattice(lattice_base(territories, lattice), lattice, np.float32(np.nan))
    footprint = ndimage.binary_dilation(mask, iterations=9)
    if not np.array_equal(current[footprint].view(np.uint32), base[footprint].view(np.uint32)):
        raise ValueError("the current ground differs from the reviewed v1 base under a repair")
    return base, fixed, mask, sites


def section_path(header: str) -> str | None:
    if not header.startswith("[node "):
        return None
    name = re.search(r'name=("(?:[^"\\]|\\.)*")', header)
    parent = re.search(r'parent=("(?:[^"\\]|\\.)*")', header)
    if not name or not parent:
        return None
    name, parent = json.loads(name[1]), json.loads(parent[1])
    return name if parent == "." else parent + "/" + name


def prepare_scene(t, expected: np.ndarray, base: np.ndarray, fixed: np.ndarray):
    current, errors = T.sculpt_deltas(t)
    if errors:
        raise ValueError("; ".join(errors))
    touched = expected != 0
    installed = np.array_equal(current[touched], expected[touched])
    if not installed and np.any(current[touched]):
        raise ValueError(f"{t.id}: an existing sculpt overlaps this repair")
    desired = current.copy()
    desired[touched] = expected[touched]
    indices = np.flatnonzero(desired)
    path = t.scene.path
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"(?m)(?=^\[)", text)
    reference = re.fullmatch(r'SubResource\("([^"]+)"\)',
                             t.scene.node("Terrain").properties["sculpt_layer"])[1]
    shifted = []
    delta = fixed - base
    for i, block in enumerate(blocks):
        header = block.split("\n", 1)[0]
        if header.startswith('[sub_resource ') and f'id="{reference}"' in header:
            block = re.sub(r"(?m)^indices = .*", "indices = PackedInt32Array(" +
                           ", ".join(str(int(v)) for v in indices) + ")", block)
            block = re.sub(r"(?m)^deltas = .*", "deltas = PackedFloat32Array(" +
                           ", ".join(format(float(v), ".9g") for v in desired.flat[indices]) + ")", block)
        node_path = section_path(header)
        if not installed and node_path and node_path.startswith("AuthoredAssets/") and \
                node_path.count("/") == 1:
            node = t.scene.nodes[node_path]
            matrix = t.scene.world(node_path)
            x, _, z = matrix[:3, 3] + t.translation
            movement = sample(delta, x, z)
            if abs(movement) > 1e-5:
                # These wrappers sit directly under an identity AuthoredAssets
                # container. Preserve their source embedding, basis and x/z.
                parent = t.scene.world("AuthoredAssets")
                if not np.allclose(parent, np.eye(4)):
                    raise ValueError(f"{t.id}: transformed asset container needs review")
                old = node.properties["transform"]
                values = [v.strip() for v in old[len("Transform3D("):-1].split(",")]
                before = float(values[10])
                values[10] = format(before + movement, ".10g")
                block = block.replace("transform = " + old,
                                      "transform = Transform3D(" + ", ".join(values) + ")")
                shifted.append({"node": node_path, "beforeY": before,
                                "afterY": float(values[10]), "terrainDelta": movement})
        blocks[i] = block
    return path, "".join(blocks), installed, shifted


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--check", action="store_true")
    ap.add_argument("--report", type=Path)
    args = ap.parse_args()
    base, fixed, mask, sites = repair_field()
    ts = T.load_territories()
    lattice = T.Lattice.of(ts)
    authorities = [T.authority(t, lattice) for t in ts]
    if np.any(mask & from_lattice(sum(a.astype(np.uint8) for a in authorities) > 1, lattice, False)):
        raise ValueError("repair reaches shared terrain authority")
    rr, cc = np.where(mask)
    for t in ts:
        for water in T.water_features(t):
            if np.any(T._distance_to_water(water, FIRST[0] + cc * 2,
                                           FIRST[1] + rr * 2) <= 2):
                raise ValueError("repair reaches an authored water feature")
    edits, summary = [], {}
    for t in ts:
        if t.id not in REPAIRED_REGIONS:
            continue
        window = lattice.window(t)
        expected = to_lattice(fixed - base, lattice, np.float32(0))[window].copy()
        expected[~authorities[[v.id for v in ts].index(t.id)][window]] = 0
        later = superseded(t) & (expected != 0)
        expected[later] = 0
        path, content, installed, shifted = prepare_scene(t, expected, base, fixed)
        edits.append((path, content))
        summary[t.id] = {"vertices": int(np.count_nonzero(expected)),
                         "installed": installed, "groundedAssets": shifted}
        if later.any():
            summary[t.id]["supersededVertices"] = int(later.sum())
    # Keep the gecko's full approach ring clear beside the restored hillside.
    spawn = SPAWN_RELOCATION
    spawn_path = T.CHECKOUT / "eloria-assets/maps/continent-v2" / spawn["region"] / "content/spawns.json"
    spawn_doc = json.loads(spawn_path.read_text(encoding="utf-8"))
    record, = [row for row in spawn_doc["spawns"] if row["id"] == spawn["id"]]
    spawn_installed = record["local"] == spawn["afterLocal"]
    if not spawn_installed and record["local"] != spawn["beforeLocal"]:
        raise ValueError("reviewed gecko spawn has moved; review its new approach ring")
    record["local"] = spawn["afterLocal"]
    # Complete all checks before the first write; never touch the frozen inputs.
    if args.apply:
        for path, content in edits:
            if path.read_text(encoding="utf-8") != content:
                path.write_text(content, encoding="utf-8", newline="\n")
        if not spawn_installed:
            spawn_path.write_text(json.dumps(spawn_doc, indent=1) + "\n", encoding="utf-8", newline="\n")
    report = {"baseSha256": BASE_SHA, "sites": sites, "hillApproach": HILL_REPAIR,
              "spawnRelocation": SPAWN_RELOCATION, "maps": summary,
              "bufferCells": BUFFER_CELLS, "changedVertices": int(mask.sum())}
    if args.report:
        if args.report.exists():
            previous = json.loads(args.report.read_text(encoding="utf-8"))
            if previous.get("baseSha256") == BASE_SHA:
                for region, entry in summary.items():
                    if entry["installed"]:
                        entry["groundedAssets"] = previous.get("maps", {}).get(region, {}).get("groundedAssets", [])
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8", newline="\n")
    for name, entry in summary.items():
        print(f'{name}: {entry["vertices"]} sculpt vertices; '
              f'{len(entry["groundedAssets"])} asset roots moved; '
              f'{"already repaired" if entry["installed"] else "repair applied" if args.apply else "repair missing"}')
    return 0 if args.apply or (spawn_installed and all(v["installed"] for v in summary.values())) else 1


if __name__ == "__main__":
    raise SystemExit(main())
