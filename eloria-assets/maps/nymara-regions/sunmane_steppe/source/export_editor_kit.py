"""Export steppe ground cover and herding props as editor prototypes.

The kit builds these pieces (shrubs, dead scrub, grass, bones, boulders, hay)
but the saved-source migration only kept the pieces some legacy placement
used, so the editor had no ground cover to paint the plains with. This writes
each one as `godot-client/world_authoring/regions/sunmane_steppe/assets/
prototypes/kit-<name>.glb`, shaped like the migrated prototypes: one root named
after the file, one placement node, one mesh node per material, and the
territory's shared textures referenced by URI rather than embedded.

Run from anywhere: `python export_editor_kit.py` (add `--check` to only verify
that the committed files match what the kit builds today).
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import kit  # noqa: E402
from glb import GLBWriter  # noqa: E402
from shapes import UV_SCALE, beam, box, frustum, sphere  # noqa: E402

CLIENT = HERE.parents[4]
PROTOTYPES = CLIENT / "godot-client/world_authoring/regions/sunmane_steppe/assets/prototypes"
TEXTURES = "../textures/"

# The territory's shared textures (assets/textures/<sha256>.png), by role.
TIMBER = ("f176f3c33b51e9febc9e1c928fc101059e5d2acaa6910f96fadf49b28aba0aa3",
          "c2e63b92affec50d60b4eb6a5272962f804215f12bcbb621ffcf22c9167c7350",
          "d8c2578d76c1c26df32c7d7827db41910434f86c66d0c111cb8a596efff00b78")
THATCH = ("9bc7a88b27821940168ab9d381b558f24d0b74ccd5ba573651968da59d5a3bee",
          "7feeb1e75a59491990af669476a7f12531f4eec9cee2319d49358e6b46ac8701",
          "f0e4f0677c9583120a0378cfe5dbb5fddb9c67612f419c70d655711c8eaecdf3")
STONE = ("ccada634290b55490b333393c4213a30b597ed8474a08060332921e371b38760",
         "0124bfa5b5c25908af99e832239ad2804211846a585b225946ec0cd2331d6630",
         "1bd5132efaa99527f1873c902c7416430c7a97b31fd90c1dd3c42ea6677226ac")
BONE = ("1536228a69528acd56c649c5555e5a3dbbd25e8324cd891322046f5afecf7e6d",
        "dc007b56b0106096b20579a6da6fdfb4d67e9fd5fac656fc47a87d66113be95f",
        "4f84c72d31eb2d3e1246047a0ad955ea041b62ac42c959c307d9b113195fe755")
LEATHER = ("62bff95c8e13a206e351ef4d9b51a55a8894bb08d1e41c77b00e8297e277eab0",
           "e8d3a6ffa08f64505436f7ecb218b0ea42f0c10db98bfaf1466751e937e88551",
           "b6e3514b0710c10922611a854074b9c3643ee2469965aff2ca17afc5930b9906")

# glTF material name -> (texture triple, base colour, roughness, normal scale or
# None for no normal map, double sided). The first eight are the migrated
# prototypes' own definitions; the last four tint the thatch texture for
# ground cover the kit never had a colour for.
MATERIALS = {
    "sun_timber_dark": (TIMBER, (0.78, 0.74, 0.7, 1.0), 0.92, 0.65, False),
    "sun_thatch_gold": (THATCH, (1.0, 0.94, 0.76, 1.0), 0.92, 0.38, False),
    "sun_leather": (LEATHER, (1.0, 1.0, 1.0, 1.0), 0.7, 0.65, False),
    "sun_stone_pale": (STONE, (0.9, 0.8, 0.66, 1.0), 0.86, 0.38, False),
    "sun_stone_dark": (STONE, (0.88, 0.5, 0.32, 1.0), 0.78, 0.38, False),
    "sun_stone_menhir": (STONE, (0.52, 0.48, 0.44, 1.0), 0.9, 0.38, False),
    "sun_bone": (BONE, (1.0, 1.0, 1.0, 1.0), 0.52, 0.65, False),
    "sun_foliage": (THATCH, (0.5, 0.56, 0.32, 1.0), 0.94, None, False),
    "sun_sage": (THATCH, (0.56, 0.6, 0.47, 1.0), 0.95, None, False),
    "sun_scrub_ochre": (THATCH, (0.93, 0.56, 0.24, 1.0), 0.93, None, False),
    "sun_dry_grass": (THATCH, (0.9, 0.8, 0.5, 1.0), 0.95, None, True),
    "sun_water": (STONE, (0.26, 0.42, 0.44, 1.0), 0.2, None, False),
}
# Kit material key -> glTF material, per piece (a piece can recolour a key).
KIT_MATERIALS = {
    kit.TIMBER_DARK: "sun_timber_dark", kit.THATCH: "sun_thatch_gold",
    kit.LEATHER: "sun_leather", kit.STONE_PALE: "sun_stone_pale",
    kit.STONE_DARK: "sun_stone_dark", kit.BONE: "sun_bone", kit.FOLIAGE: "sun_foliage",
    kit.GRASS: "sun_dry_grass",
}


def sage_clump(radius: float = 0.8, seed: int = 0) -> kit.Parts:
    """A low, rounded sagebrush: overlapping grey-green domes, no visible wood."""
    parts = kit.Parts()
    rng = np.random.default_rng(seed + 310)
    leaves = parts.geometry(kit.FOLIAGE)
    for index in range(6):
        angle = kit.TAU * index / 6 + float(rng.random()) * 0.8
        reach = radius * (0.25 + 0.45 * float(rng.random()))
        size = radius * (0.38 + 0.2 * float(rng.random()))
        sphere(leaves, (math.cos(angle) * reach, size * 0.45, math.sin(angle) * reach), size,
               rings=4, sides=7, uv_scale=UV_SCALE["thatch"], squash=0.62)
    sphere(leaves, (0.0, radius * 0.38, 0.0), radius * 0.5, rings=4, sides=8,
           uv_scale=UV_SCALE["thatch"], squash=0.66)
    return parts


def grass_patch(spread: float = 0.9, tufts: int = 7, seed: int = 0) -> kit.Parts:
    """A handful of dry tufts, the unit the plains are painted with."""
    parts = kit.Parts()
    rng = np.random.default_rng(seed + 520)
    for index in range(tufts):
        angle = kit.TAU * float(rng.random())
        reach = spread * math.sqrt(float(rng.random()))
        kit.grass_tuft(parts, (math.cos(angle) * reach, math.sin(angle) * reach),
                       height=0.42 + 0.3 * float(rng.random()), blades=6,
                       seed=seed * 31 + index)
    return parts


def boulder(radius: float, seed: int) -> kit.Parts:
    """The kit's shore rock, with a third lump so a big one is not an egg."""
    parts = kit.shore_rock(radius, seed)
    rng = np.random.default_rng(seed + 740)
    stone = parts.geometry(kit.STONE_PALE)
    angle = kit.TAU * float(rng.random())
    sphere(stone, (math.cos(angle) * radius * 0.55, radius * 0.05, math.sin(angle) * radius * 0.55),
           radius * 0.55, rings=4, sides=6, uv_scale=UV_SCALE["stone"],
           squash=0.55 + 0.1 * float(rng.random()))
    return parts


def hay_stack(seed: int = 0) -> kit.Parts:
    """Three bales, two down and one on top, as a pen keeps them."""
    parts = kit.Parts()
    for side in (-1, 1):
        kit.hay_bale(parts, (0.0, side * 0.64), rotation=0.0)
    top = kit.Parts()
    kit.hay_bale(top, (0.0, 0.0), rotation=0.35 + 0.2 * seed)
    for key, geometry in top.items():
        positions, normals, uvs, indices, colors = geometry.arrays(with_colors=True)
        positions = positions + np.array([0.1, 1.08, 0.0], dtype="float32")
        parts.geometry(key).add(positions, normals, uvs, indices, colors)
    return parts


def water_trough(length: float = 2.4) -> kit.Parts:
    """A plank trough on two trestles, water standing a hand below the rim."""
    parts = kit.Parts()
    wood = parts.geometry(kit.TIMBER_DARK)
    width, height = 0.7, 0.62
    box(wood, (0.0, 0.2, 0.0), (length, 0.08, width), uv_scale=UV_SCALE["timber"])
    for side in (-1, 1):
        box(wood, (0.0, height * 0.6, side * (width * 0.5 - 0.04)), (length, height * 0.7, 0.08),
            uv_scale=UV_SCALE["timber"])
        box(wood, (side * (length * 0.5 - 0.04), height * 0.6, 0.0), (0.08, height * 0.7, width),
            uv_scale=UV_SCALE["timber"])
        for end in (-1, 1):
            beam(wood, (side * length * 0.38, 0.0, end * width * 0.55),
                 (side * length * 0.38, 0.24, 0.0), 0.08, uv_scale=UV_SCALE["timber"])
    water = parts.geometry("water")
    box(water, (0.0, height * 0.72, 0.0), (length - 0.16, 0.04, width - 0.16), uv_scale=4.0)
    return parts


# file stem -> (builder, {kit key: glTF material} overrides)
PIECES = {
    "kit-steppe-shrub-0": (lambda: kit.shrub(0.7, seed=0), {}),
    "kit-steppe-shrub-1": (lambda: kit.shrub(0.95, seed=1), {}),
    "kit-steppe-shrub-2": (lambda: kit.shrub(1.2, seed=2), {}),
    "kit-sage-clump-0": (lambda: sage_clump(0.7, seed=0), {kit.FOLIAGE: "sun_sage"}),
    "kit-sage-clump-1": (lambda: sage_clump(1.0, seed=1), {kit.FOLIAGE: "sun_sage"}),
    "kit-ochre-scrub-0": (lambda: kit.shrub(0.85, seed=5), {kit.FOLIAGE: "sun_scrub_ochre"}),
    "kit-ochre-scrub-1": (lambda: sage_clump(1.1, seed=6), {kit.FOLIAGE: "sun_scrub_ochre"}),
    "kit-dead-scrub-0": (lambda: kit.dead_scrub(0.8, seed=0), {}),
    "kit-dead-scrub-1": (lambda: kit.dead_scrub(1.15, seed=1), {}),
    "kit-dry-grass-0": (lambda: grass_patch(0.8, 6, seed=0), {}),
    "kit-dry-grass-1": (lambda: grass_patch(1.2, 9, seed=1), {}),
    "kit-dry-grass-2": (lambda: grass_patch(0.6, 4, seed=2), {}),
    "kit-bleached-bones-0": (lambda: kit.bleached_bones(seed=0), {}),
    "kit-grey-boulder-0": (lambda: boulder(1.3, seed=0), {kit.STONE_PALE: "sun_stone_menhir"}),
    "kit-grey-boulder-1": (lambda: boulder(2.1, seed=1), {kit.STONE_PALE: "sun_stone_menhir"}),
    "kit-grey-boulder-2": (lambda: boulder(3.2, seed=2), {kit.STONE_PALE: "sun_stone_menhir"}),
    "kit-sand-boulder-0": (lambda: boulder(1.5, seed=3), {}),
    "kit-sand-boulder-1": (lambda: boulder(2.6, seed=4), {kit.STONE_PALE: "sun_stone_dark"}),
    "kit-hay-stack": (lambda: hay_stack(seed=0), {}),
    "kit-water-trough": (lambda: water_trough(), {"water": "sun_water"}),
}


def _material(writer: GLBWriter, name: str, cache: dict) -> int:
    if name in cache:
        return cache[name]
    textures, colour, roughness, normal_scale, double = MATERIALS[name]
    base, orm, normal = (_texture(writer, digest, f"{name}_{role}", cache)
                         for digest, role in zip(textures, ("base", "orm", "normal")))
    cache[name] = writer.material(name, base_color=colour, roughness=roughness,
                                  base_color_texture=base, orm_texture=orm,
                                  normal_texture=normal if normal_scale is not None else None,
                                  normal_scale=normal_scale or 1.0, double_sided=double)
    return cache[name]


def _texture(writer: GLBWriter, digest: str, name: str, cache: dict) -> int:
    key = ("texture", digest)
    if key not in cache:
        writer.doc.setdefault("images", []).append({"uri": TEXTURES + digest + ".png", "name": name})
        writer.doc.setdefault("textures", []).append(
            {"source": len(writer.doc["images"]) - 1, "sampler": writer._sampler_index()})
        cache[key] = len(writer.doc["textures"]) - 1
    return cache[key]


def build(stem: str) -> bytes:
    builder, overrides = PIECES[stem]
    parts = builder()
    writer = GLBWriter("Eloria Sunmane editor kit")
    cache: dict = {}
    placement = "Kit_" + stem.removeprefix("kit-").replace("-", "_")
    children = []
    for key in sorted(parts):
        geometry = parts[key].weld()
        if geometry.triangle_count == 0:
            continue
        name = overrides.get(key, KIT_MATERIALS.get(key))
        if name is None:
            raise ValueError(f"{stem}: no material for kit key {key}")
        mesh = writer.mesh(f"{placement}__{name}", [(geometry, _material(writer, name, cache))])
        children.append(writer.node(f"{placement}__{name}", mesh=mesh, in_scene=False))
    holder = writer.node(placement, children=children, in_scene=False)
    writer.node(stem, children=[holder])
    path = PROTOTYPES / f"{stem}.glb.tmp"
    writer.write(path)
    payload = path.read_bytes()
    path.unlink()
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="verify, do not write")
    args = parser.parse_args()
    stale = []
    for stem in PIECES:
        payload = build(stem)
        target = PROTOTYPES / f"{stem}.glb"
        if args.check:
            if not target.exists() or target.read_bytes() != payload:
                stale.append(stem)
            continue
        if not target.exists() or target.read_bytes() != payload:
            target.write_bytes(payload)
            print(f"wrote {target.name} ({len(payload)} bytes)")
    if stale:
        print("stale: " + ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
