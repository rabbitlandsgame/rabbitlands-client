#!/usr/bin/env python3
"""Build the frozen continent-v2 group terrain v2 from v1 and a pinned recipe.

v1 (group-terrain/) is an input artifact: it is verified against its recorded output hashes, never replayed from
Git and never rewritten. v2 extends the lattice (v1 copied byte for byte into its window), sinks recorded land
components to a shaped seabed, then applies pinned 2 m raster edits with per-vertex height and colour weights
(255 = the raster value, 0 = unchanged). Edits are refused where they touch a recorded exclusion (pit repairs,
terrain patches, water features, berths, sea lanes) or raise the height of land kept from v1.

  python godot-client/tools/build_continent_v2_ground.py                      # write group-terrain-v2/
  python godot-client/tools/build_continent_v2_ground.py --check              # write nothing, compare every byte
  python godot-client/tools/build_continent_v2_ground.py --base DIR           # stage the pre-edit base for authoring
  python godot-client/tools/build_continent_v2_ground.py --record-exclusions  # from the current (v1) scenes

Arithmetic is float64, cast once to little-endian float32; colours round half to even.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from scipy import ndimage

CHECKOUT = Path(__file__).resolve().parents[2]
SCHEMA = "eloria-continent-v2-frozen-group-terrain-v2"
GROUND = CHECKOUT / "eloria-assets/maps/continent-v2/_continent_v2/ground-v2"
RECIPE = GROUND / "recipe.json"
OUTPUT = CHECKOUT / "eloria-assets/maps/continent-v2/_continent_v2/group-terrain-v2"
CELL = 2.0


class GroundError(ValueError):
    """The recipe or its inputs cannot safely produce the v2 ground."""


def sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def json_bytes(value) -> bytes:
    return (json.dumps(value, indent=1, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def rel(path: Path) -> str:
    path = path.resolve()
    return path.relative_to(CHECKOUT).as_posix() if path.is_relative_to(CHECKOUT) else path.as_posix()


def read_pinned(path: Path, record: dict) -> bytes:
    blob = path.read_bytes()
    if sha256(blob) != record["sha256"] or len(blob) != record["bytes"]:
        raise GroundError(f"pinned input changed: {rel(path)}")
    return blob


def smoothstep(t: np.ndarray) -> np.ndarray:
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


class Grid:
    def __init__(self, first, size):
        self.first = np.asarray(first, np.float64)
        self.width, self.height = (int(v) for v in size)
        if np.any(self.first % 2 != 1):
            raise GroundError("grid vertices must sit on odd metres")

    def window(self, first, size) -> tuple[slice, slice]:
        offset = (np.asarray(first, np.float64) - self.first) / CELL
        if np.any(offset % 1) or np.any(offset < 0):
            raise GroundError(f"window {first} is off the lattice or outside the grid")
        c0, r0 = (int(v) for v in offset)
        w, h = (int(v) for v in size)
        if c0 + w > self.width or r0 + h > self.height:
            raise GroundError(f"window {first} {size} reaches outside the grid")
        return slice(r0, r0 + h), slice(c0, c0 + w)

    def index(self, x: float, z: float) -> tuple[int, int]:
        c, r = (np.array([x, z], np.float64) - self.first) / CELL
        return int(round(r)), int(round(c))


def load_recipe(path: Path = RECIPE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_v1(recipe: dict):
    provenance_path = CHECKOUT / recipe["predecessor"]["path"]
    blob = provenance_path.read_bytes()
    if sha256(blob) != recipe["predecessor"]["sha256"]:
        raise GroundError("the v1 provenance differs from the one the recipe pins")
    provenance = json.loads(blob)
    grid = provenance["grid"]
    width, height = grid["gridSize"]
    folder = provenance_path.parent
    heights = np.frombuffer(read_pinned(folder / "base-heights.f32le", provenance["outputs"]["base-heights.f32le"]),
                            "<f4").reshape(height, width)
    colors = np.frombuffer(read_pinned(folder / "base-colors.rgba8", provenance["outputs"]["base-colors.rgba8"]),
                           np.uint8).reshape(height, width, 4)
    return provenance, heights, colors


def seabed_colour(heights: np.ndarray, colors: np.ndarray) -> np.ndarray:
    return np.round(np.median(colors[heights <= 0].astype(np.float64), axis=0)).astype(np.uint8)


def edit_land(recipe: dict, grid: Grid) -> np.ndarray:
    """Vertices the edits raise above the sea (height weight > 0 and raster height > 0)."""
    land = np.zeros((grid.height, grid.width), bool)
    for edit in recipe["edits"]:
        sub = grid.window(edit["firstVertex"], edit["gridSize"])
        w, h = edit["gridSize"]
        files = edit["files"]
        eh = np.frombuffer(read_pinned(GROUND / files["heights"]["path"], files["heights"]), "<f4").reshape(h, w)
        wh = np.frombuffer(read_pinned(GROUND / files["heightWeights"]["path"], files["heightWeights"]), np.uint8).reshape(h, w)
        land[sub] |= (wh > 0) & (eh > 0)
    return land


def seabed(recipe: dict, distance: np.ndarray) -> np.ndarray:
    """Depth by distance from the final land, from v1's own median sea profile (recorded in the recipe)."""
    profile = np.asarray(recipe["seabed"]["profile"], np.float64)
    return np.interp(distance, profile[:, 0], profile[:, 1])


def build_base(recipe: dict):
    """v1 copied into the v2 lattice; recorded components sunk; every other v2 vertex a seabed shaped by its distance
    from the final land (kept v1 land plus the land the edits raise), blended into v1's edge values near its window."""
    provenance, v1h, v1c = load_v1(recipe)
    grid = Grid(recipe["grid"]["continentFirstVertex"], recipe["grid"]["gridSize"])
    window = grid.window(provenance["grid"]["continentFirstVertex"], provenance["grid"]["gridSize"])
    lattice1 = Grid(provenance["grid"]["continentFirstVertex"], provenance["grid"]["gridSize"])
    sea_colour = seabed_colour(v1h, v1c)
    land1 = v1h > 0
    labels, _ = ndimage.label(land1)
    sunk = np.zeros(land1.shape, bool)
    records = []
    for sink in recipe.get("sinks", []):
        part = np.zeros(land1.shape, bool)
        for x, z in sink["components"]:
            r, c = lattice1.index(x, z)
            if not land1[r, c]:
                raise GroundError(f"sink {sink['id']}: ({x}, {z}) is not on v1 land")
            part |= labels == labels[r, c]
        sunk |= part
        records.append({"id": sink["id"], "vertices": int(part.sum())})
    final_land = edit_land(recipe, grid)
    final_land[window] |= land1 & ~sunk
    distance = ndimage.distance_transform_edt(~final_land) * CELL
    bed = seabed(recipe, distance)
    heights = np.empty((grid.height, grid.width))
    colors = np.empty((grid.height, grid.width, 4), np.uint8)
    # outside the v1 window: v1's nearest edge value blended into the seabed over windowBlendMetres
    rows = np.clip(np.arange(grid.height) - window[0].start, 0, v1h.shape[0] - 1)
    cols = np.clip(np.arange(grid.width) - window[1].start, 0, v1h.shape[1] - 1)
    h1 = np.where(sunk, np.minimum(v1h.astype(np.float64), bed[window]), v1h.astype(np.float64))
    c1 = v1c.copy()
    c1[sunk] = sea_colour
    # the sunk coast's own shallows go with it: v1 sea nearer the sunk land than any kept land, faded out by 120 m
    ghost_metres = recipe["sinks"][0]["shallowsMetres"] if sunk.any() else 0
    if ghost_metres:
        d_sunk = ndimage.distance_transform_edt(~sunk) * CELL
        d_kept = distance[window]
        w = smoothstep((d_kept - d_sunk) / 40.0) * smoothstep((ghost_metres - d_sunk) / 40.0)
        w = np.where((v1h <= 0) & ~sunk, w, 0.0)
        h1 = h1 + (bed[window] - h1) * w
        c1 = np.where((w > 0)[..., None], np.round(c1 + (sea_colour.astype(np.float64) - c1) * w[..., None]), c1).astype(np.uint8)
        sunk_shallows = w > 0
    else:
        sunk_shallows = np.zeros(sunk.shape, bool)
    edge_h = np.minimum(h1[np.ix_(rows, cols)], 0.0)
    edge_c = c1[np.ix_(rows, cols)].astype(np.float64)
    dr = np.maximum(window[0].start - np.arange(grid.height), np.arange(grid.height) - (window[0].stop - 1)).clip(0)
    dc = np.maximum(window[1].start - np.arange(grid.width), np.arange(grid.width) - (window[1].stop - 1)).clip(0)
    blend = smoothstep(np.hypot(dr[:, None], dc[None, :]) * CELL / recipe["seabed"]["windowBlendMetres"])
    heights[:] = edge_h + (bed - edge_h) * blend
    colors[:] = np.round(edge_c + (sea_colour.astype(np.float64) - edge_c) * blend[..., None]).astype(np.uint8)
    heights[window] = h1
    colors[window] = c1
    moved = ~(sunk | sunk_shallows)
    if (heights[window][moved] != v1h.astype(np.float64)[moved]).any():
        raise GroundError("the base changed a v1 vertex outside the sinks and their shallows")
    records[-1:] and records[-1].update({"shallowsVertices": int(sunk_shallows.sum())})
    return grid, window, provenance, v1h, v1c, heights, colors, sunk | sunk_shallows, records


def load_exclusions(recipe: dict, grid: Grid) -> np.ndarray:
    record = recipe["exclusions"]
    blob = read_pinned(GROUND / record["path"], record)
    bits = np.unpackbits(np.frombuffer(blob, np.uint8), count=grid.width * grid.height)
    return bits.reshape(grid.height, grid.width).astype(bool)


def apply_edits(recipe: dict, grid: Grid, window, v1h, heights, colors, sunk, exclusions):
    kept_land = np.zeros(heights.shape, bool)
    kept_land[window] = (v1h > 0) & ~sunk
    records = []
    for edit in recipe["edits"]:
        sub = grid.window(edit["firstVertex"], edit["gridSize"])
        w, h = edit["gridSize"]
        files = edit["files"]
        eh = np.frombuffer(read_pinned(GROUND / files["heights"]["path"], files["heights"]), "<f4").reshape(h, w)
        ec = np.frombuffer(read_pinned(GROUND / files["colors"]["path"], files["colors"]), np.uint8).reshape(h, w, 4)
        wh = np.frombuffer(read_pinned(GROUND / files["heightWeights"]["path"], files["heightWeights"]), np.uint8).reshape(h, w)
        wc = np.frombuffer(read_pinned(GROUND / files["colorWeights"]["path"], files["colorWeights"]), np.uint8).reshape(h, w)
        if not np.isfinite(eh).all():
            raise GroundError(f"edit {edit['id']}: non-finite heights")
        touched = (wh > 0) | (wc > 0)
        if (touched & exclusions[sub]).any():
            raise GroundError(f"edit {edit['id']}: touches {int((touched & exclusions[sub]).sum())} excluded vertices")
        if ((wh > 0) & kept_land[sub]).any():
            raise GroundError(f"edit {edit['id']}: changes the height of {int(((wh > 0) & kept_land[sub]).sum())} kept land vertices")
        a = wh.astype(np.float64) / 255.0
        cur = heights[sub]
        heights[sub] = np.where(wh == 255, eh.astype(np.float64), cur + (eh.astype(np.float64) - cur) * a)
        b = wc.astype(np.float64)[..., None] / 255.0
        cc = colors[sub].astype(np.float64)
        colors[sub] = np.where((wc == 255)[..., None], ec, np.round(cc + (ec.astype(np.float64) - cc) * b).astype(np.uint8))
        records.append({"id": edit["id"], "kind": edit.get("kind", "raster"), "firstVertex": edit["firstVertex"],
                        "gridSize": edit["gridSize"], "heightVertices": int((wh > 0).sum()),
                        "colourVertices": int((wc > 0).sum())})
    return records


def build(recipe: dict) -> dict[str, bytes]:
    grid, window, provenance, v1h, v1c, heights, colors, sunk, sink_records = build_base(recipe)
    exclusions = load_exclusions(recipe, grid)
    if (exclusions[window] & sunk).any():
        raise GroundError("a sink touches an excluded vertex")
    edit_records = apply_edits(recipe, grid, window, v1h, heights, colors, sunk, exclusions)
    out_h = heights.astype("<f4")
    if not np.isfinite(out_h).all():
        raise GroundError("v2 heights contain non-finite values")
    edge = np.concatenate([out_h[0], out_h[-1], out_h[:, 0], out_h[:, -1]])
    if (edge >= 0).any():
        raise GroundError("v2 has land or shore on its outer edge")
    changed = np.zeros(out_h.shape, bool)
    changed[window] = (out_h[window].view(np.uint32) != v1h.view(np.uint32)) | (colors[window] != v1c).any(-1)
    if (changed & exclusions).any():
        raise GroundError("an excluded vertex changed")
    outputs = {"base-heights.f32le": out_h.tobytes(), "base-colors.rgba8": colors.tobytes(),
               "changed-mask.bits": np.packbits(changed.ravel()).tobytes()}
    predecessor = CHECKOUT / recipe["predecessor"]["path"]
    generator = Path(__file__).resolve()
    provenance_out = {
        "schema": SCHEMA,
        "method": "v1 frozen group terrain verified and copied into an extended lattice; recorded land components "
                  "sunk; pinned weighted 2 m raster edits applied; v1 vertices outside the changed mask byte-identical",
        "predecessor": {"path": recipe["predecessor"]["path"], "sha256": recipe["predecessor"]["sha256"],
                        "schema": provenance["schema"], "outputs": provenance["outputs"]},
        "grid": {"continentFirstVertex": grid.first.tolist(), "gridSize": [grid.width, grid.height], "cellMetres": CELL},
        "predecessorWindow": {"row0": window[0].start, "col0": window[1].start,
                              "rows": v1h.shape[0], "cols": v1h.shape[1]},
        "recipe": {"path": rel(RECIPE), "sha256": sha256(RECIPE.read_bytes())},
        "generator": {"path": rel(generator), "sha256": sha256(generator.read_bytes())},
        "toolchain": {"python": sys.version.split()[0], "numpy": np.__version__,
                      "scipy": __import__("scipy").__version__},
        "sinks": sink_records,
        "edits": edit_records,
        "changedMask": {"path": "changed-mask.bits", "encoding": "np.packbits row-major over the v2 grid",
                        "count": int(changed.sum())},
        "invariants": {"predecessorVerticesChanged": int(changed.sum()),
                       "predecessorVerticesUnchangedByteExact": int(v1h.size - changed[window].sum()),
                       "newVertices": int(grid.width * grid.height - v1h.size),
                       "edgeAllSea": True, "exclusionsUntouched": True,
                       "landKm2": round(float((out_h > 0).sum()) * CELL * CELL / 1e6, 3)},
        "sceneSidePatches": recipe.get("sceneSidePatches", []),
        "outputs": {name: {"sha256": sha256(blob), "bytes": len(blob)} for name, blob in outputs.items()},
        "baseCommit": recipe.get("baseCommit"),
    }
    outputs["terrain-provenance.json"] = json_bytes(provenance_out)
    return outputs


# --- exclusions -------------------------------------------------------------------------------------------------

def record_exclusions(recipe: dict) -> tuple[bytes, dict]:
    """Recorded once from the v1 scenes: what any later edit must leave untouched."""
    import continent_v2_territories as T
    import repair_continent_v2_pits as P

    grid = Grid(recipe["grid"]["continentFirstVertex"], recipe["grid"]["gridSize"])
    provenance, v1h, _ = load_v1(recipe)
    window = grid.window(provenance["grid"]["continentFirstVertex"], provenance["grid"]["gridSize"])
    rules = recipe["exclusionRules"]
    mask = np.zeros((grid.height, grid.width), bool)
    counts = {}
    _, _, repair, _ = P.repair_field()
    repair = ndimage.binary_dilation(repair, iterations=rules["pitRepairDilateCells"])
    mask[window] |= repair
    counts["pitRepairs"] = int(repair.sum())
    xs = grid.first[0] + CELL * np.arange(grid.width)
    zs = grid.first[1] + CELL * np.arange(grid.height)
    territories = T.load_territories()
    part = np.zeros_like(mask)
    for t in territories:
        for patch in T.patches(t):
            ox, oz = patch["continentOrigin"][0], patch["continentOrigin"][2]
            reach = max(patch["size"]) + rules["patchMarginMetres"] + 4
            r0, r1 = np.searchsorted(zs, [oz - reach, oz + reach])
            c0, c1 = np.searchsorted(xs, [ox - reach, ox + reach])
            weight = T.patch_weight(patch, xs[None, c0:c1], zs[r0:r1, None])
            part[r0:r1, c0:c1] |= weight > 0
    part = ndimage.binary_dilation(part, iterations=int(np.ceil(rules["patchMarginMetres"] / CELL)))
    counts["patches"] = int(part.sum()); mask |= part
    part = np.zeros_like(mask)
    for t in territories:
        for feature in T.water_features(t):
            if "ellipse" in feature:
                reach = float(np.abs(feature["ellipse"]).sum(axis=1).max()) + rules["waterMarginMetres"] + 4
                lo = feature["xz"][0] - reach; hi = feature["xz"][0] + reach
            else:
                lo = feature["xz"].min(0) - feature["reach"] - rules["waterMarginMetres"] - 4
                hi = feature["xz"].max(0) + feature["reach"] + rules["waterMarginMetres"] + 4
            r0, r1 = np.searchsorted(zs, [lo[1], hi[1]])
            c0, c1 = np.searchsorted(xs, [lo[0], hi[0]])
            if r1 <= r0 or c1 <= c0:
                continue
            distance = T._distance_to_water(feature, xs[None, c0:c1], zs[r0:r1, None])
            part[r0:r1, c0:c1] |= distance <= rules["waterMarginMetres"]
    counts["water"] = int(part.sum()); mask |= part
    X, Z = np.meshgrid(xs, zs)
    part = np.zeros_like(mask)
    for berth in rules["berths"]:
        part |= np.hypot(X - berth["xz"][0], Z - berth["xz"][1]) <= berth["radiusMetres"]
    counts["berths"] = int(part.sum()); mask |= part
    part = np.zeros_like(mask)
    for lane in rules["seaLanes"]:
        points = np.asarray(lane["points"], np.float64)
        part |= T._distance_to_polyline(points, X, Z) <= lane["halfWidthMetres"]
    counts["seaLanes"] = int(part.sum()); mask |= part
    blob = np.packbits(mask.ravel()).tobytes()
    sources = sorted({rel(t.scene.path) for t in territories} |
                     {rel(Path(P.__file__)), rel(Path(T.__file__))})
    derivation = {"rules": rules, "counts": counts, "vertices": int(mask.sum()),
                  "inputs": {path: sha256((CHECKOUT / path).read_bytes()) for path in sources}}
    return blob, derivation


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--base", type=Path)
    mode.add_argument("--record-exclusions", action="store_true")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    try:
        recipe = load_recipe()
        if args.record_exclusions:
            blob, derivation = record_exclusions(recipe)
            path = GROUND / recipe["exclusions"]["path"]
            path.write_bytes(blob)
            (GROUND / "exclusions.json").write_bytes(json_bytes(derivation))
            print(json.dumps({"exclusions": rel(path), "sha256": sha256(blob), "bytes": len(blob),
                              "vertices": derivation["vertices"], "counts": derivation["counts"]}, indent=1))
            return 0
        if args.base:
            grid, window, _, _, _, heights, colors, sunk, _ = build_base(recipe)
            args.base.mkdir(parents=True, exist_ok=True)
            heights.astype("<f4").tofile(args.base / "base-heights.f32le")
            colors.tofile(args.base / "base-colors.rgba8")
            np.packbits(load_exclusions(recipe, grid).ravel()).tofile(args.base / "exclusions.bits")
            (args.base / "base.json").write_bytes(json_bytes({
                "grid": {"continentFirstVertex": grid.first.tolist(), "gridSize": [grid.width, grid.height]},
                "predecessorWindow": {"row0": window[0].start, "col0": window[1].start},
                "sunkVertices": int(sunk.sum())}))
            print(f"base staged in {args.base}")
            return 0
        expected = build(recipe)
        if args.check:
            for name, blob in expected.items():
                path = args.output / name
                if not path.is_file() or path.read_bytes() != blob:
                    raise GroundError(f"ground v2 output is missing, stale or corrupt: {name}")
        else:
            args.output.mkdir(parents=True, exist_ok=True)
            for name, blob in expected.items():
                path = args.output / name
                if not path.is_file() or path.read_bytes() != blob:
                    path.write_bytes(blob)
    except (GroundError, KeyError, ValueError, OSError) as error:
        print(f"build_continent_v2_ground: {error}")
        return 1
    print(json.dumps({"mode": "check" if args.check else "write", "output": rel(args.output),
                      "baseSha256": sha256(expected["base-heights.f32le"])}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
