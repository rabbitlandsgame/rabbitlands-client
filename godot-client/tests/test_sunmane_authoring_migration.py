import json
import re
import sys
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
REGION = ROOT / "godot-client/world_authoring/regions/sunmane_steppe"
PROVENANCE = REGION / "migration-provenance.json"
SCENE = REGION / "sunmane_steppe.tscn"
RIVER_CURVE = REGION / "paths/southern-river.tres"
RUNTIME_SEED = REGION / "runtime-bindings.seed.json"
CONTINENT = ROOT / "eloria-assets/maps/nymara-regions/_continent"
TOOLS = ROOT / "godot-client/tools"

class SunmaneAuthoringMigrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.provenance = json.loads(PROVENANCE.read_text(encoding="utf-8"))
        cls.scene = SCENE.read_text(encoding="utf-8")

    def test_certified_sources_and_natural_grid_are_frozen(self):
        asset = self.provenance["asset"]
        self.assertEqual(asset["sourceWorldSha256"],
                         "52d5b96bc4fc68b554398a00b7b3dbfeb28979893406f26223229e86fbf9689d")
        self.assertEqual(asset["roadsSha256"],
                         "606908c8e68ddd87466c978fd5214857e0b2bcfbad62dd7900597ff3c33308d3")
        self.assertEqual(asset["baseHeightsSha256"],
                         "bb18a189f0b6ccc7ed3d1e47eaa83cb953cb7b6422a04f91be4ae57c938eedf3")
        self.assertRegex(asset["initialResolvedHeightsSha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(asset["sceneSha256"], r"^[0-9a-f]{64}$")

    def test_object_controls_use_reusable_prototypes(self):
        counts = self.provenance["counts"]
        self.assertEqual(counts["objects"], 298)
        self.assertEqual(counts["prototypeFamilies"], 80)
        objects = self.provenance["objects"]
        self.assertEqual(len({record["id"] for record in objects}), 298)
        self.assertEqual(sum(record["collisionRole"] == "solid" for record in objects), 156)
        self.assertNotIn("Terrain_", "".join(record["id"] for record in objects))
        self.assertEqual(sum(record["instances"]
                             for record in self.provenance["prototypes"].values()), 298)
        for family, record in self.provenance["prototypes"].items():
            self.assertRegex(record["sha256"], r"^[0-9a-f]{64}$", family)
            self.assertTrue(record["path"].endswith(".glb"), family)
            self.assertNotIn("sunmane_steppe/world.glb", record["path"], family)

    def test_routes_preserve_owned_identity_topology_and_full_widths(self):
        route_ids = self.provenance["ownedRouteIds"]
        self.assertEqual(len(route_ids), 19)
        self.assertEqual(len(set(route_ids)), 19)
        self.assertEqual(self.provenance["ownedPlanFeatureIds"], ["southern_river"])
        paths = {record["id"]: record for record in self.provenance["paths"]}
        self.assertEqual(set(paths), set(route_ids) | {"southern_river"})
        self.assertEqual(paths["southern_river"]["width"], 13.0)
        self.assertEqual(paths["southern_river"]["pointCount"], 43)
        self.assertEqual(paths["southern_river"]["sourceControlPointCount"], 8)
        self.assertEqual(paths["southern_river"]["sampling"],
                         "legacy-open-catmull-rom-6x-zero-handles")
        widths = {record["width"] for identity, record in paths.items()
                  if identity != "southern_river"}
        self.assertEqual(widths, {3.3, 8.0})
        self.assertEqual(sum(record["routingRole"] == "required"
                             for record in paths.values()), 5)
        self.assertIn('"channelDepth": 1.8', self.scene)
        self.assertIn('"valleyWidth": 73', self.scene)
        self.assertIn('"mouth": "sea"', self.scene)

    def test_saved_river_polyline_matches_legacy_curve_samples(self):
        for path in (str(CONTINENT), str(TOOLS)):
            if path not in sys.path:
                sys.path.insert(0, path)
        import landscape
        import import_sunmane_authoring as migration

        plan = json.loads((CONTINENT / "diagonal-plan.json").read_text(
            encoding="utf-8"))
        river = next(record for record in plan["rivers"]
                     if record["id"] == "southern_river")
        expected = np.asarray(migration.local_river_points({
            "points": landscape.curved_points(river["points"]).tolist()}))
        text = RIVER_CURVE.read_text(encoding="utf-8")
        packed = re.search(r'"points": PackedVector3Array\((.*?)\),\n"tilts"',
                           text, re.S)
        self.assertIsNotNone(packed)
        values = np.asarray([float(value.strip())
                             for value in packed.group(1).split(",")])
        actual = values.reshape((-1, 9))[:, 6:9]
        self.assertEqual(actual.shape, (43, 3))
        np.testing.assert_allclose(actual, expected, rtol=0.0, atol=1e-6)

    def test_current_gameplay_contract_is_exposed_as_editable_markers(self):
        self.assertEqual(self.provenance["counts"]["gameplay"], {
            "AmbientPopulation": 22, "Harvestables": 20, "Interactives": 88,
            "Landmarks": 120, "NpcMarkers": 15, "Portals": 5, "Spawns": 2,
        })
        gameplay = self.provenance["gameplay"]
        identities = {(record["section"], record["id"]) for record in gameplay}
        self.assertEqual(len(identities), 382)
        self.assertEqual(self.provenance["counts"]["runtimePoints"], 110)
        self.assertEqual(self.provenance["counts"]["runtimeBindings"], 191)
        self.assertGreater(sum(bool(record["followAssetId"]) for record in gameplay), 0)
        for identity in ("server-arrival", "arrival-datum", "cave-wind_caves",
                         "cave-crystal_hollow", "road-to-mirrorhold",
                         "road-to-amethyst_barrens", "road-to-verdant_stair"):
            self.assertTrue(any(record["id"] == identity for record in gameplay), identity)

    def test_runtime_binding_seed_is_exact_visible_and_hash_bound(self):
        seed = json.loads(RUNTIME_SEED.read_text(encoding="utf-8"))
        self.assertEqual(seed["counts"]["bindings"], 191)
        self.assertEqual(seed["counts"]["existingMarkers"], 81)
        self.assertEqual(seed["counts"]["runtimePoints"], 110)
        self.assertTrue(all(len(record.get("targetOffset", [])) == 3 and
                            record["targetOffset"][1] == 0
                            for record in seed["bindings"]))
        self.assertTrue(all(record["targetOffset"] == [0, 0, 0]
                            for record in seed["bindings"]
                            if record["marker"]["section"] == "runtimePoints"))
        existing = [record for record in seed["bindings"]
                    if record["marker"]["section"] != "runtimePoints"]
        self.assertTrue(all(any(abs(value) > 0 for value in record["targetOffset"])
                            for record in existing))
        grouped = {}
        for record in existing:
            marker = (record["marker"]["section"], record["marker"]["id"])
            grouped.setdefault(marker, []).append(record["targetOffset"])
        shared = [offsets for offsets in grouped.values() if len(offsets) > 1]
        self.assertEqual((len(shared), sum(map(len, shared))), (16, 46))
        self.assertTrue(any(len({tuple(offset) for offset in offsets}) > 1
                            for offsets in shared))
        self.assertEqual(self.provenance["runtimeBindingSeed"]["sha256"],
                         __import__("hashlib").sha256(RUNTIME_SEED.read_bytes()).hexdigest())
        self.assertIn('runtime_binding_seed_path = "res://world_authoring/regions/'
                      'sunmane_steppe/runtime-bindings.seed.json"', self.scene)
        self.assertEqual(self.scene.count('kind = "runtime_point"'), 110)
        self.assertEqual(self.scene.count('"provenance": {"sourceProfileSha256"'), 191)
        self.assertEqual(self.scene.count('"targetOffset": ['), 191)

    def test_scene_has_authoritative_editable_sections(self):
        for fragment in (
            'region_id = "sunmane_steppe"',
            "continent_translation = Vector3(1200, 0, 720)",
            "server_origin = Vector2i(194, 292)",
            "collision_origin_metres = Vector2(-194, 292)",
            'owned_plan_feature_ids = PackedStringArray("southern_river")',
            '[node name="Terrain" type="Node3D" parent="."]',
            '[node name="Roads" type="Node3D" parent="."]',
            '[node name="Rivers" type="Node3D" parent="."]',
            '[node name="AuthoredAssets" type="Node3D" parent="."]',
            '[node name="Gameplay" type="Node3D" parent="."]',
            'base_surface = ExtResource("desert")',
        ):
            self.assertIn(fragment, self.scene)
        self.assertNotIn("sunmane_steppe/world.glb", self.scene)

    def test_vertical_migration_is_saved_and_auditable(self):
        migration = self.provenance["verticalMigration"]
        self.assertIn("saved one-time", migration["method"])
        self.assertEqual(set(migration["objects"]),
                         {record["id"] for record in self.provenance["objects"]})
        expected_gameplay = {
            f'{record["section"]}/{record["id"]}'
            for record in self.provenance["gameplay"]
            if not record["section"].startswith("RuntimePoints/")
        }
        self.assertEqual(set(migration["gameplay"]), expected_gameplay)
        self.assertTrue(any(abs(value) > 0.25
                            for value in migration["objects"].values()))


if __name__ == "__main__":
    unittest.main()
