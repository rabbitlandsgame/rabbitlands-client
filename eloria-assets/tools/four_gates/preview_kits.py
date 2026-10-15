"""Renderable contact sheet of the Four Gates asset kits (authoring aid)."""
from __future__ import annotations
import math, sys
import numpy as np
import kits, meshlib as M
from assembly import MaterialLibrary, SceneBuilder
from gltf_writer import GLB


def main(out: str) -> None:
    glb = GLB("Four Gates kit preview")
    lib = MaterialLibrary(glb, size=512, hero=1024, cache_dir="/root/work/texcache")
    scene = SceneBuilder(glb, lib)
    p = lib.palette
    items = [
        ("Gatehouse", lambda: kits.gatehouse(p), 0),
        ("WallSegment", lambda: kits.wall_segment(24.0, 16.0, 7.0, p), 0),
        ("WallTower", lambda: kits.wall_tower(6.5, 22.0, p), 0),
        ("CivicHall", lambda: kits.civic_hall(p, variant=1), 0),
        ("Townhouse", lambda: kits.townhouse(p, 9.0, 11.0, 3, 0), 0),
        ("TownhouseB", lambda: kits.townhouse(p, 7.0, 8.0, 2, 3, p.roof_slate), 0),
        ("MarketHall", lambda: kits.market_hall(p), 0),
        ("Farmhouse", lambda: kits.farmhouse(p, variant=1), 0),
        ("Granary", lambda: kits.granary(p), 0),
        ("Fountain", lambda: kits.fountain(p), 0),
        ("Statue", lambda: kits.hooded_statue(6.0, p), 0),
        ("MarketStall", lambda: kits.market_stall(p), 0),
        ("Tree", lambda: kits.broadleaf_tree(p, 10.0, 3), 0),
        ("Pine", lambda: kits.pine_tree(p, 15.0, 5), 0),
        ("Well", lambda: kits.well(p), 0),
        ("Cart", lambda: kits.handcart(p), 0),
        ("Dock", lambda: kits.dock_platform(p), 0),
        ("Crane", lambda: kits.harbour_crane(p), 0),
        ("Lamp", lambda: kits.crystal_lamp(6.0, p), 0),
        ("Warehouse", lambda: kits.warehouse(p), 0),
    ]
    roots = []
    ground = scene.mesh("Ground", M.plane(400.0, 400.0, p.paving_road, 4.0, 0.0, 40))
    roots.append(scene.instance("Ground_Plane", ground))
    columns = 5
    for index, (name, factory, _) in enumerate(items):
        mesh = scene.mesh(name, factory)
        x = (index % columns - (columns - 1) / 2) * 62.0
        z = (index // columns - 1.5) * 62.0
        roots.append(scene.instance(f"Kit_{name}", mesh, (x, 0.0, z)))
    glb.scene_roots = [glb.add_node("KitPreview", children=roots)]
    print(glb.save(out))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/root/work/kits.glb")
