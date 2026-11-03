"""Wave 2 WD-C0: tools/world_draw_budget.py, the offline world draw/primitive estimate.

Synthetic territories check batching, size classes, ranges, proxies, frustum culling and
the class-table reader without assets; the reference test reproduces the world-distance
plan's section 2.2/2.3 numbers from the shipped maps (skipped when they are absent).
"""
from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

import numpy as np

CLIENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLIENT / "tools"))
import world_draw_budget as wdb  # noqa: E402

PLAN = {**wdb.PLAN_TABLE, "source": {}}


def write_glb(path: Path, gltf: dict) -> None:
    payload = json.dumps(gltf).encode("utf-8")
    payload += b" " * (-len(payload) % 4)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, 20 + len(payload))
                     + struct.pack("<I4s", len(payload), b"JSON") + payload)


def box_mesh(half: float, height: float, triangles: int, alpha: str = "OPAQUE") -> dict:
    return {"meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "material": 0}]}],
            "accessors": [{"count": 8, "min": [-half, 0.0, -half], "max": [half, height, half]},
                          {"count": triangles * 3}],
            "materials": [{"alphaMode": alpha}]}


def make_territory(root: Path, placements: list[tuple[str, str, list[float]]], own: list[tuple[str, float]],
                   name: str = "fixture") -> Path:
    """One chunk at the origin: own meshes (name, half size) and prototype placements."""
    maps = root / "maps"
    write_glb(maps / "_shared/meshes/bush.glb", box_mesh(0.5, 1.0, 100))        # S: r ~ 0.87
    write_glb(maps / "_shared/meshes/oak_tree.glb", box_mesh(3.0, 8.0, 2000))   # L: r ~ 5.8
    write_glb(maps / "_shared/meshes/glass.glb", box_mesh(0.5, 1.0, 10, "BLEND"))
    meshes, accessors, materials, nodes = [], [], [{"alphaMode": "OPAQUE"}], []
    for node_name, half in own:
        accessors += [{"count": 4, "min": [-half, 0.0, -half], "max": [half, 0.1, half]}, {"count": 6}]
        meshes.append({"primitives": [{"attributes": {"POSITION": len(accessors) - 2},
                                       "indices": len(accessors) - 1, "material": 0}]})
        nodes.append({"name": node_name, "mesh": len(meshes) - 1})
    for index, (key, label, position) in enumerate(placements):
        nodes.append({"name": f"{label}_{index}", "translation": position,
                      "extras": {"eloria": {"prototype": key}}})
    write_glb(maps / f"continent-v2/{name}/client/chunks/00_00/world.glb",
              {"scenes": [{"nodes": list(range(len(nodes)))}], "nodes": nodes, "meshes": meshes,
               "accessors": accessors, "materials": materials})
    manifest = {"spawnPoints": [{"id": "other", "position": [500, 0, 500]},
                                {"id": "arrival", "default": True, "position": [0, 0, 0], "serverTile": [7, 9]}],
                "streamingChunks": {"chunks": [
                    {"id": "00_00", "manifest": "chunks/00_00/world.json",
                     "bounds": {"min": [-100, -10, -100], "max": [100, 10, 100]}},
                    {"id": "far", "manifest": "chunks/far/world.json",
                     "bounds": {"min": [900, -10, 900], "max": [1000, 10, 1000]}}]}}
    (maps / f"continent-v2/{name}/client/world.json").write_text(json.dumps(manifest), encoding="utf-8")
    return maps


class TerritoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_resident_chunks_spawn_and_categories(self):
        maps = make_territory(self.root, [("bush", "Fern", [1, 0, 1]), ("missing", "Rock", [2, 0, 2])],
                              [("Terrain_fixture_00_00", 50.0)])
        territory = wdb.Territory(maps, "fixture")
        self.assertEqual(list(territory.chunks), ["00_00"], "chunks beyond the preload distance stay out")
        self.assertEqual(territory.spawn["id"], "arrival", "the default spawn is the focus, not the first")
        summary = territory.summary(PLAN)
        self.assertEqual(summary["serverTile"], [7, 9])
        self.assertEqual(summary["placements"], 1, "a placement whose prototype is missing is skipped")
        self.assertEqual(summary["trianglesByCategoryClass"], {"undergrowth/S": 100})
        self.assertEqual(wdb.category("Broadleaf_Tree_3"), "tree")
        self.assertEqual(wdb.category("Stone-bench_2"), "prop")
        self.assertEqual(wdb.ground_kind("AuthoredGround_LandfallBase_01"), "base")
        self.assertEqual(wdb.ground_kind("AuthoredGround_Landfall_path"), "patch")

    def test_batching_classes_cells_and_singles(self):
        bushes = [("bush", "Fern", [x, 0, 1]) for x in (1, 3, 5, 7, 40, 42, 44)]
        trees = [("oak_tree", "Oak_Tree", [x, 0, -20]) for x in (2, 12, 22, 32)]
        maps = make_territory(self.root, bushes + trees + [("glass", "Lamp", [0, 0, 0])] * 4, [])
        chunks = wdb.Territory(maps, "fixture").chunks
        today = wdb.build_units(chunks, wdb.variant_rules("today", PLAN), PLAN)
        kinds = sorted(unit["kind"] for unit in today)
        # 180 m cells: all seven bushes batch together, the four trees batch, translucent stays single.
        self.assertEqual(kinds, ["batch:tree", "batch:undergrowth"] + ["single:prop"] * 4)
        cells = wdb.build_units(chunks, wdb.variant_rules("cells", PLAN), PLAN)
        bush_units = [unit for unit in cells if unit["kind"].endswith("undergrowth")]
        # 32 m S cells: four bushes near x=1..7 batch; the three at x=40..44 fall below four members.
        self.assertEqual(sorted(unit["kind"] for unit in bush_units),
                         ["batch:undergrowth", "single:undergrowth", "single:undergrowth", "single:undergrowth"])
        self.assertEqual(next(unit["tris"] for unit in bush_units if unit["kind"].startswith("batch")), 400)
        tree_units = [unit for unit in cells if unit["kind"].endswith("tree")]
        self.assertEqual(len(tree_units), 1, "the four trees share one 64 m L cell")

    def test_ranges_shadow_rules_terrain_and_far_proxies(self):
        maps = make_territory(self.root, [("bush", "Fern", [x, 0, 1]) for x in (1, 3, 5, 7)]
                              + [("oak_tree", "Oak_Tree", [x, 0, -20]) for x in (2, 12, 22, 32)],
                              [("Terrain_fixture_00_00", 50.0), ("Walk_deck", 5.0)])
        chunks = wdb.Territory(maps, "fixture").chunks
        ranges = wdb.build_units(chunks, wdb.variant_rules("ranges", PLAN), PLAN)
        kinds = {unit["kind"]: unit for unit in ranges}
        self.assertNotIn("terrain", kinds, "the ranges variant hides Terrain_ (C1 upper bound)")
        self.assertFalse(kinds["deck"]["shadow"], "decks cast no shadow under the rules")
        self.assertEqual(kinds["batch:undergrowth"]["end"], 30.0)
        self.assertFalse(kinds["batch:undergrowth"]["shadow"], "small props cast no shadow")
        self.assertEqual(kinds["batch:tree"]["end"], 160.0)
        self.assertTrue(kinds["batch:tree"]["shadow"])
        kept = wdb.build_units(chunks, wdb.variant_rules("ranges_keep_terrain", PLAN), PLAN)
        terrain = next(unit for unit in kept if unit["kind"] == "terrain")
        self.assertFalse(terrain["shadow"], "C3 alone keeps Terrain_ but takes its shadow")
        self.assertEqual(len(kept), len(ranges) + 1)
        proxies = wdb.build_units(chunks, wdb.variant_rules("far_proxies", PLAN), PLAN)
        proxy = next(unit for unit in proxies if unit["kind"] == "impostor")
        self.assertEqual((proxy["begin"], proxy["tris"], proxy["abs"]), (100.0, 16, True))
        tree = next(unit for unit in proxies if unit["kind"] == "batch:tree")
        self.assertEqual((tree["end"], tree["abs"]), (100.0, True), "trees hand over to proxies at 100 m")
        # Relative reach: the S batch at ~4 m from the focus is kept at 26 m and at 90 m zoom.
        bush = kinds["batch:undergrowth"]
        for distance in (26.0, 90.0):
            position = wdb.camera(np.zeros(3), distance, -60.0, 0.0)[0]
            self.assertTrue(wdb._in_range(bush, position, 0.6, distance))
        far_bush = dict(bush, lo=bush["lo"] + 200.0, hi=bush["hi"] + 200.0)
        position = wdb.camera(np.zeros(3), 26.0, -60.0, 0.0)[0]
        self.assertFalse(wdb._in_range(far_bush, position, 1.0, 26.0))

    def test_frustum_and_count(self):
        position, forward, right, up, near = wdb.camera(np.zeros(3), 26.0, -60.0, 0.0)
        self.assertAlmostEqual(near, 1.0)
        planes = wdb.frustum_planes(position, forward, right, up, near, 1800.0, 16 / 9)
        here = {"kind": "own", "chunk": "a", "lo": np.array([-1.0, 0, -1]), "hi": np.array([1.0, 1, 1]),
                "tris": 10, "draws": 1, "end": 0.0, "begin": 0.0}
        behind = dict(here, lo=here["lo"] + np.array([0, 0, 200.0]), hi=here["hi"] + np.array([0, 0, 200.0]))
        self.assertTrue(wdb.visible(here, planes))
        self.assertFalse(wdb.visible(behind, planes), "a box far behind the camera is culled")
        draws, primitives, by_primitives, _ = wdb.count([here, behind], position, planes, 1.0, 26.0)
        self.assertEqual((draws, primitives, by_primitives["own"]), (1, 10, 10))

    def test_budget_report_rows_and_shadows(self):
        maps = make_territory(self.root, [("oak_tree", "Oak_Tree", [x, 0, 3]) for x in (2, 6, 10, 14)],
                              [("Terrain_fixture_00_00", 50.0)])
        report = wdb.budget(wdb.Territory(maps, "fixture"), PLAN, {"16:9": 16 / 9},
                            (("default 26m -60", 26.0, -60.0),), shadows=True)
        self.assertEqual(len(report["rows"]), len(wdb.VARIANTS) * 2)
        today = next(r for r in report["rows"] if r["variant"] == "today" and r["tier"] == "HIGH")
        self.assertEqual(today["primitives"], 8000 + 2, "four trees and the terrain are in view")
        ranges = next(r for r in report["rows"] if r["variant"] == "ranges" and r["tier"] == "LOW")
        self.assertEqual((ranges["farMetres"], ranges["reachScale"]), (260.0, 0.6))
        self.assertEqual(ranges["primitives"], 8000, "terrain hidden under the ranges variant")
        kept = next(r for r in report["rows"] if r["variant"] == "ranges_keep_terrain" and r["tier"] == "LOW")
        self.assertEqual(kept["primitives"], 8002, "C3 alone still draws the terrain")
        labels = {(r["tier"], r["label"]) for r in report["shadows"]}
        self.assertEqual(len(labels), 6)
        fitted = next(r for r in report["shadows"] if r["label"] == "today_fitted" and r["tier"] == "HIGH")
        self.assertEqual((fitted["shadowMaxDistance"], fitted["cascades"]), (1.4 * 26 + 12, 4))
        self.assertIn("default 26m -60", wdb.markdown(report))


class TableTests(unittest.TestCase):
    def test_reads_client_constants_and_falls_back_to_the_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "src/world").mkdir(parents=True)
            self.assertEqual(wdb.load_table(project)["source"]["CELL_METRES"], "plan")
            (project / "src/world/world_distance_classes.gd").write_text(
                "class_name WorldDistanceClasses\n"
                "const CLASS_RADIUS_LIMITS: Array[float] = [1.5, 4.0, 12.0] # wider XL\n"
                "const CELL_METRES := {\n\t\"S\": 24.0, # small\n\t\"M\": 48.0,\n\t\"L\": 64.0,\n\t\"XL\": 96.0,\n}\n"
                "const REACH_METRES := {&\"S\": 25, &\"M\": 70, &\"L\": 160, &\"XL\": 0}\n"
                "const TIER_REACH_SCALE := {\"low\": 0.5, \"medium\": 0.8, \"high\": 1.0}\n"
                "const FAR_PROXY_METRES := 120.0\n"
                "const LOW_FAR_METRES := Vector2(1, 2)\n", encoding="utf-8")
            (project / "src/world/world_loader.gd").write_text("const BATCH_CELL_METRES := 150.0\n", encoding="utf-8")
            table = wdb.load_table(project)
            self.assertEqual(table["CLASS_RADIUS_LIMITS"], [1.5, 4.0, 12.0])
            self.assertEqual(table["CELL_METRES"]["S"], 24.0)
            self.assertEqual(table["REACH_METRES"]["S"], 25.0)
            self.assertEqual(table["TIER_REACH_SCALE"]["LOW"], 0.5)
            self.assertEqual(table["FAR_PROXY_METRES"], 120.0)
            self.assertEqual(table["TODAY_CELL_METRES"], 150.0)
            self.assertEqual(table["source"]["CELL_METRES"], "src/world/world_distance_classes.gd")
            self.assertEqual(table["source"]["LOW_FAR_METRES"], "plan", "a non-literal constant keeps the plan value")
            self.assertEqual(wdb.size_class(11.0, table), "L")

    def test_this_checkout_table_is_valid(self):
        table = wdb.load_table()
        self.assertEqual(set(table["CELL_METRES"]), set(wdb.CLASSES))
        self.assertGreater(table["TODAY_CELL_METRES"], 0)


@unittest.skipUnless((wdb.DEFAULT_MAPS / "continent-v2/landfall/client/world.json").is_file(),
                     "shipped continent maps are not in this checkout")
class ReferenceTests(unittest.TestCase):
    def test_plan_section_2_2_and_2_3_reproduce_within_one_percent(self):
        self.assertEqual(wdb.check_reference(), [])


if __name__ == "__main__":
    unittest.main()
