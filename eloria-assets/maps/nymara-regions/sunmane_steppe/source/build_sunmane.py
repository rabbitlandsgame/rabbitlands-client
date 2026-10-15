#!/usr/bin/env python3
"""Build the Sunmane Steppe production map package.

Outputs, under `eloria-assets/maps/nymara-regions/sunmane_steppe/`:

    world.glb        self-contained glTF 2.0 with embedded textures
    world.json       schema 1.x manifest consumed by the Godot world loader
    minimap.webp     rendered from the exported geometry
    textures/        the authored PBR kit, also embedded in the GLB

Run from anywhere:  python3 eloria-assets/maps/nymara-regions/sunmane_steppe/source/build_sunmane.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import checks                                        # noqa: E402
import terrain                                       # noqa: E402
import layout as DESIGN
from amberwood import watercraft as WATER
import terrain_mesh                                  # noqa: E402
import textures as texture_kit                       # noqa: E402
from glb import GLBWriter, Geometry, compose         # noqa: E402
from shapes import UV_SCALE                          # noqa: E402

ASSET_ROOT = HERE.parents[3]
# The package this builds is the directory the source sits in, which is the
# layout every other region uses.
PACKAGE = HERE.parent

GENERATOR = "Eloria Sunmane Steppe production builder 1.0"
SCHEMA_VERSION = "1.1.0"
ASSET_VERSION = "1.0.0"

class Builder:
    """Accumulates geometry, materials and manifest metadata for one export."""

    def __init__(self, texture_scale: float = 1.0) -> None:
        self.glb = GLBWriter(GENERATOR)
        self.texture_scale = texture_scale
        self.kit = texture_kit.build_kit(scale=texture_scale)
        self.textures: dict[str, dict[str, int]] = {}
        self.materials: dict[str, int] = {}
        self.collision_nodes: list[str] = []
        # Appended to every node name this builder emits. Empty by default, so
        # nothing that builds one map is affected. A build that puts several
        # systems on one map sets it per system, because glTF node names must be
        # unique and the client resolves collision and navigation nodes by name -
        # two systems each numbering their boulders from zero collide.
        #
        # A *suffix*, not a prefix. `navigation.surfaceNodePrefixes` matches on
        # the start of the name, so tagging the front turns every
        # `Terrain_CaveFloor_*` into something the client does not recognise as
        # a walk surface - the first attempt at this built no navigation
        # surface at all and grounded nothing on the whole map.
        self.name_suffix: str = ""
        self.landmarks: list[dict] = []
        self.interactives: list[dict] = []
        self.notes: list[str] = []
        self.geometry_reports: list[dict] = []

    # ------------------------------------------------------------ materials
    def slots(self, family: str) -> dict[str, int]:
        """Register a texture family on first use so nothing unused is embedded."""
        cached = self.textures.get(family)
        if cached is None:
            maps = self.kit[family]
            cached = {
                "base": self.glb.texture(maps.base_color, f"{family}-basecolor"),
                "normal": self.glb.texture(maps.normal, f"{family}-normal"),
                "orm": self.glb.texture(maps.orm, f"{family}-orm"),
            }
            self.textures[family] = cached
        return cached

    def material(self, key: str, family: str, *, base_color=(1, 1, 1, 1),
                 metallic: float = 0.0, roughness: float = 1.0,
                 normal_scale: float = 1.0, emissive=None,
                 double_sided: bool = False, alpha_mode: str | None = None,
                 textured: bool = True, normal_map: bool = True) -> int:
        """Fetch or create a material derived from one texture family."""
        if key in self.materials:
            return self.materials[key]
        slots = self.slots(family)
        index = self.glb.material(
            key,
            base_color=base_color, metallic=metallic, roughness=roughness,
            base_color_texture=slots["base"] if textured else None,
            normal_texture=slots["normal"] if (textured and normal_map) else None,
            normal_scale=normal_scale,
            orm_texture=slots["orm"] if textured else None,
            emissive=emissive, double_sided=double_sided, alpha_mode=alpha_mode)
        self.materials[key] = index
        return index

    # ----------------------------------------------------------------- nodes
    def emit(self, name: str, parts: list[tuple[Geometry, int]], *,
             matrix=None, parent: int | None = None, weld: bool = True,
             collide: bool = False) -> int | None:
        """Weld, create a mesh and attach one node. Returns the node index."""
        prepared = [(geometry.weld() if weld else geometry, material)
                    for geometry, material in parts if geometry.triangle_count]
        if not prepared:
            return None
        for index, (geometry, _) in enumerate(prepared):
            report = checks.assert_well_formed(geometry, f"{name}[{index}]")
            self.geometry_reports.append(report)
        name = name + self.name_suffix
        mesh = self.glb.mesh(name, prepared)
        if mesh is None:
            return None
        node = self.glb.node(name, mesh=mesh, matrix=matrix, parent=parent)
        if collide:
            self.collision_nodes.append(name)
        return node

    def instance(self, name: str, mesh: int, matrix, *, parent: int | None = None,
                 collide: bool = False) -> int:
        """Reuse an existing mesh at a new transform - true glTF instancing."""
        name = name + self.name_suffix
        node = self.glb.node(name, mesh=mesh, matrix=matrix, parent=parent)
        if collide:
            self.collision_nodes.append(name)
        return node


# ---------------------------------------------------------------------- main
def build_terrain(builder: Builder, landform: terrain.Landform) -> dict:
    """Emit chunked terrain, sea and waterholes. Returns summary statistics."""
    class_material = {}
    for terrain_class, tint in terrain.CLASS_TINT.items():
        name = f"ground_{terrain.CLASS_NAMES[terrain_class]}"
        rocky = terrain_class in (terrain.CLASS_ROCK, terrain.CLASS_BADLAND,
                                  terrain.CLASS_MOUNTAIN)
        # Alpha-tested, because a class is cut against its neighbour inside
        # the cell rather than at the cell corner: each ground quad carries a
        # per-vertex coverage in COLOR_0's alpha and the test hands every pixel
        # to whichever class covers it. It is still opaque - an alpha test
        # writes depth and sorts like any other ground - so nothing about the
        # draw order changes.
        class_material[terrain_class] = builder.material(
            name, "stone" if rocky else "ground", base_color=tint,
            roughness=0.88 if rocky else 0.94, normal_scale=0.9,
            alpha_mode="MASK")

    chunks = terrain_mesh.build_chunks(landform)
    triangles = 0
    for chunk in chunks:
        parts = [(geometry, class_material[terrain_class])
                 for terrain_class, geometry in sorted(chunk["geometry"].items())]
        triangles += sum(geometry.triangle_count for geometry, _ in parts)
        builder.emit(chunk["name"], parts)

    sea_material = builder.glb.material(
        "sea_water", base_color=(0.018, 0.11, 0.14, 1.0), metallic=0.0,
        roughness=0.40, normal_texture=builder.slots("canvas")["normal"],
        normal_scale=0.35)
    sea = terrain_mesh.water_surface(landform)
    builder.emit("Water_Sea", [(sea, sea_material)])

    pond_material = builder.glb.material(
        "pond_water", base_color=(0.028, 0.085, 0.067, 1.0), metallic=0.0,
        roughness=0.64, normal_texture=builder.slots("canvas")["normal"],
        normal_scale=0.3)
    ponds = DESIGN.geometry(WATER.pools(landform.sample,DESIGN.POOLS))
    builder.emit("Water_Waterholes", [(ponds, pond_material)])
    DESIGN.emit_water(builder,landform,pond_material)

    # Named with the Terrain_ prefix so it joins the navigation surface.
    apron = terrain_mesh.edge_apron(landform)
    builder.emit("Terrain_EdgeApron",
                 [(apron, class_material[terrain.CLASS_ROCK])])
    return {"terrainTriangles": triangles, "terrainChunks": len(chunks),
            "seaTriangles": sea.triangle_count, "pondTriangles": ponds.triangle_count}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=PACKAGE)
    parser.add_argument("--terrain-only", action="store_true",
                        help="skip the settlement kit; used for the early "
                             "grounding and coordinate verification pass")
    parser.add_argument("--lod", type=int, default=1, choices=(1, 2),
                        help="1 is the full package; 2 drops ground clutter and "
                             "halves texture resolution for low-end settings")
    parser.add_argument("--name", default="world",
                        help="base name for the emitted package files")
    arguments = parser.parse_args()

    started = time.time()
    lod = arguments.lod
    layout = None
    pads: tuple = ()
    if not arguments.terrain_only:
        import settlement                            # noqa: E402  (late import)
        # Placement positions are authored constants, so the layout can be
        # composed before the terrain exists and used to level building pads.
        layout = settlement.compose_layout(None)
        pads = layout.pads()
    landform = terrain.build(pads=pads)
    builder = Builder(texture_scale=1.0 if lod == 1 else 0.5)
    statistics = build_terrain(builder, landform)

    if layout is not None:
        layout.landform = landform
        statistics.update(settlement.populate(builder, landform, layout=layout,
                                              lod=lod))

    output = arguments.output
    output.mkdir(parents=True, exist_ok=True)
    base = arguments.name if lod == 1 else f"{arguments.name}-lod2"
    glb_bytes = builder.glb.write(output / f"{base}.glb")

    if lod == 1:
        # Keep the authored texture kit beside the package as editable source.
        texture_dir = output / "textures"
        texture_dir.mkdir(exist_ok=True)
        for name, maps in builder.kit.items():
            (texture_dir / f"{name}-basecolor.png").write_bytes(maps.base_color)
            (texture_dir / f"{name}-normal.png").write_bytes(maps.normal)
            (texture_dir / f"{name}-orm.png").write_bytes(maps.orm)

    statistics.update(builder.glb.statistics())
    statistics["glbBytes"] = glb_bytes
    statistics["lod"] = lod
    statistics["textureScale"] = builder.texture_scale
    statistics["buildSeconds"] = round(time.time() - started, 1)

    manifest = build_manifest(builder, landform, statistics)
    posts = HERE / "server-content.json"
    if posts.is_file():
        import contentposts
        contentposts.apply(manifest, output, json.loads(posts.read_text()), glb_name=f"{base}.glb")
    manifest["asset"]["glb"] = f"{base}.glb"
    if lod != 1:
        manifest["asset"]["id"] = "sunmane_steppe_lod2"
        manifest["asset"]["name"] = "Sunmane Steppe (LOD2)"
        manifest["minimap"] = {"image": "minimap.webp",
                               "note": "shared with the LOD1 package"}
    (output / f"{base}.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (output / f"{base}-statistics.json").write_text(
        json.dumps(statistics, indent=2) + "\n")

    if lod == 1:
        # The walk grid the server cuts its collision map from. Only the
        # full package writes one: LOD2 drops ground clutter, and collision
        # is not a thing a graphics setting may disagree about.
        import collision                          # noqa: E402 (late import)

        payload, grid_statistics = collision.build_grid(output)
        (output / "collision.bin").write_bytes(payload)
        statistics["collision"] = grid_statistics
        # The grid is cut from the manifest - it needs the server origin and
        # the collision node names - so the manifest cannot describe it until
        # it exists. Rather than leave a reader to infer the world-to-cell
        # mapping, the collision block is filled in and the manifest rewritten.
        builder.collision_stats = grid_statistics
        manifest["collision"] = build_collision_block(builder)
        (output / (base + ".json")).write_text(
            json.dumps(manifest, indent=2) + "\n")
        (output / (base + "-statistics.json")).write_text(
            json.dumps(statistics, indent=2) + "\n")

    print(json.dumps(statistics, indent=2))
    return 0


def build_manifest(builder: Builder, landform: terrain.Landform,
                   statistics: dict) -> dict:
    import manifest                                  # noqa: E402
    return manifest.build(builder, landform, statistics)


def build_collision_block(builder: Builder) -> dict:
    import manifest                                  # noqa: E402
    return manifest.collision_block(builder)


if __name__ == "__main__":
    raise SystemExit(main())
